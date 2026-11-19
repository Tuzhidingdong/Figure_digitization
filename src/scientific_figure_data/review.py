from __future__ import annotations

import csv
import json
import math
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import StalePatchError
from .calibration import calibration_to_dict, fit_linear_axis, map_pixel
from .hashing import atomic_write_json, sha256_file
from .storage import connect_catalog

ALLOWED_FIELDS = {
    "label", "technique", "domain", "x_label", "y_label", "x_unit", "y_unit",
    "y_axis_side", "x_axis_anchors", "y_axis_anchors", "points"
}
ALLOWED_AXIS_SIDES = {"LEFT", "RIGHT", "UNASSIGNED"}


def _validate_anchors(value: Any, axis: str) -> None:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError(f"{axis}_axis_anchors must contain at least two anchors")
    pixels = set()
    for anchor in value:
        if not isinstance(anchor, dict) or set(anchor) != {"pixel", "value"}:
            raise ValueError(f"Each {axis} anchor must contain exactly pixel and value")
        for key in ("pixel", "value"):
            number = anchor[key]
            if not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError(f"{axis} anchor {key} must be finite numeric data")
        pixel_key = round(float(anchor["pixel"]), 9)
        if pixel_key in pixels:
            raise ValueError(f"{axis} anchor pixel positions must be unique")
        pixels.add(pixel_key)


def _validate_patch(patch: dict) -> None:
    required = ("patch_id", "paper_id", "target_artifact", "original_result_hash", "changes")
    missing = [key for key in required if key not in patch]
    if missing:
        raise ValueError(f"Review patch missing required fields: {', '.join(missing)}")
    if patch["target_artifact"] != "digitization.json":
        raise ValueError("Only digitization.json is a supported patch target")
    patch_id = str(patch["patch_id"])
    if len(patch_id) > 80 or not re.fullmatch(r"[A-Za-z0-9_.-]+", patch_id):
        raise ValueError("patch_id must contain only letters, digits, dot, underscore or hyphen (max 80)")
    if not isinstance(patch["paper_id"], str) or not patch["paper_id"] or len(patch["paper_id"]) > 240:
        raise ValueError("paper_id must be a non-empty string of at most 240 characters")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(patch["original_result_hash"])):
        raise ValueError("original_result_hash must be a 64-character SHA256 hex digest")
    reviewer = patch.get("reviewer", "")
    if not isinstance(reviewer, str) or len(reviewer) > 200:
        raise ValueError("reviewer must be a string of at most 200 characters")
    if not isinstance(patch["changes"], list) or not patch["changes"]:
        raise ValueError("changes must be a non-empty list")
    seen_series = set()
    for change in patch["changes"]:
        if not isinstance(change, dict) or not change.get("series_id"):
            raise ValueError("Every change must contain series_id")
        if change["series_id"] in seen_series:
            raise ValueError(f"Duplicate series_id in patch: {change['series_id']}")
        seen_series.add(change["series_id"])
        unknown = set(change) - {"series_id", "set"}
        if unknown:
            raise ValueError(f"Unsupported change keys: {sorted(unknown)}")
        values = change.get("set")
        if not isinstance(values, dict) or not values:
            raise ValueError("Each change requires a non-empty set mapping")
        forbidden = set(values) - ALLOWED_FIELDS
        if forbidden:
            raise ValueError(f"Unsupported review fields: {sorted(forbidden)}")
        if "y_axis_side" in values and values["y_axis_side"] not in ALLOWED_AXIS_SIDES:
            raise ValueError("y_axis_side must be LEFT, RIGHT, or UNASSIGNED")
        if "x_axis_anchors" in values:
            _validate_anchors(values["x_axis_anchors"], "x")
        if "y_axis_anchors" in values:
            _validate_anchors(values["y_axis_anchors"], "y")
        if "points" in values:
            points = values["points"]
            if not isinstance(points, list):
                raise ValueError("points must be a list")
            if len(points) > 250000:
                raise ValueError("A review patch cannot contain more than 250000 points per series")
            allowed_point_keys = {
                "point_index", "x", "y", "pixel_x", "pixel_y",
                "y_err_low", "y_err_high", "err_type",
            }
            indexes = set()
            for point in points:
                if not isinstance(point, dict) or "point_index" not in point:
                    raise ValueError("Each point requires point_index")
                if set(point) - allowed_point_keys:
                    raise ValueError("Review point contains unsupported fields")
                index = point["point_index"]
                if not isinstance(index, int) or index < 0 or index in indexes:
                    raise ValueError("point_index values must be unique non-negative integers")
                indexes.add(index)
                for key in ("y", "pixel_x", "pixel_y", "y_err_low", "y_err_high"):
                    value = point.get(key)
                    if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                        raise ValueError(f"{key} must be finite numeric data or null")
                x = point.get("x")
                if x is not None and not isinstance(x, (str, int, float)):
                    raise ValueError("x must be a string, number, or null")
                if isinstance(x, float) and not math.isfinite(x):
                    raise ValueError("x must be finite")


def apply_review_patch(output_root: Path, patch_path: Path, dry_run: bool = False) -> dict:
    patch = json.loads(patch_path.read_text(encoding="utf-8-sig"))
    _validate_patch(patch)
    paper_id = str(patch["paper_id"])
    paper_root = (output_root / "papers" / paper_id).resolve()
    try:
        paper_root.relative_to((output_root / "papers").resolve())
    except ValueError as exc:
        raise ValueError("paper_id escapes output root") from exc
    target = paper_root / "digitization.json"
    if not target.is_file():
        raise FileNotFoundError(f"Target digitization artifact not found: {target}")
    current_hash = sha256_file(target)
    patch_id = str(patch["patch_id"])
    db_path = output_root / "catalog.sqlite"
    con = connect_catalog(db_path)
    try:
        already = con.execute("SELECT 1 FROM applied_patches WHERE patch_id=?", (patch_id,)).fetchone()
        if already:
            return {"status": "ALREADY_APPLIED", "patch_id": patch_id}
        if current_hash != patch["original_result_hash"]:
            conflict = {
                "schema_version": "1.0", "patch_id": patch_id, "paper_id": paper_id,
                "status": "PATCH_CONFLICT_STALE_BASE", "expected_hash": patch["original_result_hash"],
                "current_hash": current_hash, "detected_at": datetime.now(timezone.utc).isoformat(),
                "patch_file": patch_path.name,
            }
            conflict_path = output_root / "review" / "conflicts" / f"{patch_id}.json"
            atomic_write_json(conflict_path, conflict)
            with con:
                con.execute(
                    "INSERT INTO job_events(paper_id,event_type,created_at,payload_json) VALUES(?,?,?,?)",
                    (paper_id, "PATCH_CONFLICT_STALE_BASE", conflict["detected_at"],
                     json.dumps(conflict, ensure_ascii=False)),
                )
                con.execute(
                    """INSERT INTO reviews(review_id,paper_id,patch_id,reviewer,reviewed_at,
                       original_hash,revised_hash,decision,patch_path)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), paper_id, patch_id, patch.get("reviewer"),
                     conflict["detected_at"], patch["original_result_hash"], current_hash,
                     "PATCH_CONFLICT_STALE_BASE", str(conflict_path)),
                )
            return conflict
        document = json.loads(target.read_text(encoding="utf-8"))
        series_index = {item["series_id"]: item for item in document.get("series", [])}
        csv_updates: dict[Path, dict[str, list[dict]]] = {}
        csv_axis_updates: dict[Path, dict[str, dict[str, Any]]] = {}
        for change in patch["changes"]:
            series_id = change["series_id"]
            if series_id not in series_index:
                raise ValueError(f"Unknown series_id in patch: {series_id}")
            item = series_index[series_id]
            values = change["set"]
            csv_path = paper_root / "series" / f"{item['figure_id']}__{item['panel_id']}" / "panel_series.csv"
            axis_transforms = {}
            for key in ("x_axis_anchors", "y_axis_anchors"):
                if key in values:
                    axis = key[0]
                    calibration = fit_linear_axis(axis, values[key], item.get(f"{axis}_unit"))
                    item.setdefault("metadata", {})[f"{axis}_axis_anchors"] = values[key]
                    item.setdefault("metadata", {})[f"{axis}_calibration"] = calibration_to_dict(calibration)
                    axis_transforms[axis] = calibration
            for key, value in values.items():
                if key == "points":
                    item["points_count"] = len(value)
                    if not csv_path.is_file():
                        raise FileNotFoundError(f"Panel point artifact missing: {csv_path}")
                    csv_updates.setdefault(csv_path, {})[series_id] = value
                elif key in {"x_axis_anchors", "y_axis_anchors"}:
                    continue
                else:
                    item[key] = value
            if axis_transforms:
                if not csv_path.is_file():
                    raise FileNotFoundError(f"Panel point artifact missing: {csv_path}")
                csv_axis_updates.setdefault(csv_path, {})[series_id] = axis_transforms
            item["extraction_status"] = "REVIEWED_ACCEPTED"
            item["review_state"] = "REVIEWED_ACCEPTED"
            item.setdefault("metadata", {})["review_patch_id"] = patch_id
        document["generated_at"] = datetime.now(timezone.utc).isoformat()
        document["review_status"] = "REVIEWED_ACCEPTED"
        new_hash_preview = "DRY_RUN"
        if dry_run:
            return {"status": "DRY_RUN_OK", "patch_id": patch_id,
                    "series_count": len(patch["changes"]), "original_hash": current_hash}
        version_dir = paper_root / "versions" / f"review-{patch_id}"
        version_dir.mkdir(parents=True, exist_ok=True)
        backup_digitization = version_dir / "digitization.before.json"
        shutil.copy2(target, backup_digitization)
        bundle_path = paper_root / "paper_bundle.json"
        bundle_backup = version_dir / "paper_bundle.before.json"
        if bundle_path.is_file():
            shutil.copy2(bundle_path, bundle_backup)
        backups = {}
        for csv_path in csv_updates:
            backup_path = version_dir / (csv_path.parent.name + ".before.csv")
            shutil.copy2(csv_path, backup_path)
            backups[csv_path] = backup_path
        try:
            for csv_path in set(csv_updates) | set(csv_axis_updates):
                _replace_series_points_atomic(
                    csv_path, csv_updates.get(csv_path, {}),
                    csv_axis_updates.get(csv_path, {}),
                )
            atomic_write_json(target, document)
            new_hash_preview = sha256_file(target)
            # Refresh canonical hashes before committing the SQLite transaction so files and
            # index can be rolled back together if any later write fails.
            if bundle_path.is_file():
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle["generated_at"] = datetime.now(timezone.utc).isoformat()
                refreshed = {}
                for relative in bundle.get("canonical_artifacts", []):
                    artifact_path = paper_root / relative
                    if artifact_path.is_file():
                        refreshed[relative] = sha256_file(artifact_path)
                bundle["content_hashes"] = refreshed
                atomic_write_json(bundle_path, bundle)
            with con:
                for change in patch["changes"]:
                    values = change["set"]
                    sid = change["series_id"]
                    assignments = ["review_state='REVIEWED_ACCEPTED'", "extraction_status='REVIEWED_ACCEPTED'"]
                    args: list[Any] = []
                    for key in ("label", "technique", "domain", "x_label", "y_label", "x_unit", "y_unit", "y_axis_side"):
                        if key in values:
                            assignments.append(f"{key}=?")
                            args.append(values[key])
                    args.append(sid)
                    con.execute(f"UPDATE series SET {', '.join(assignments)} WHERE series_id=?", args)
                    if "points" in values:
                        con.execute("DELETE FROM series_points WHERE series_id=?", (sid,))
                        def point_values():
                            for point in values["points"]:
                                x_value = point.get("x")
                                yield (
                                    sid, int(point["point_index"]),
                                    x_value if isinstance(x_value, (int, float)) else None,
                                    x_value if isinstance(x_value, str) else None,
                                    point.get("y"), point.get("pixel_x"), point.get("pixel_y"),
                                    point.get("y_err_low"), point.get("y_err_high"),
                                    point.get("err_type", "UNKNOWN"),
                                )
                        con.executemany(
                            """INSERT INTO series_points(series_id,point_index,x_value,x_label,y_value,
                               pixel_x,pixel_y,y_err_low,y_err_high,err_type) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            point_values(),
                        )
                con.execute(
                    "INSERT INTO applied_patches VALUES(?,?,?,?,?)",
                    (patch_id, paper_id, datetime.now(timezone.utc).isoformat(), current_hash, new_hash_preview),
                )
                con.execute(
                    """INSERT INTO reviews(review_id,paper_id,patch_id,reviewer,reviewed_at,
                       original_hash,revised_hash,decision,patch_path) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), paper_id, patch_id, patch.get("reviewer"),
                     datetime.now(timezone.utc).isoformat(), current_hash, new_hash_preview,
                     "REVIEWED_ACCEPTED", str(patch_path)),
                )
                con.execute(
                    "INSERT INTO job_events(paper_id,event_type,created_at,payload_json) VALUES(?,?,?,?)",
                    (paper_id, "REVIEW_PATCH_APPLIED", datetime.now(timezone.utc).isoformat(),
                     json.dumps({"patch_id": patch_id, "original_hash": current_hash,
                                 "revised_hash": new_hash_preview}, ensure_ascii=False)),
                )
                con.execute(
                    "UPDATE papers SET status='REVIEWED_ACCEPTED',updated_at=? WHERE paper_id=?",
                    (datetime.now(timezone.utc).isoformat(), paper_id),
                )
        except Exception:
            shutil.copy2(backup_digitization, target)
            for csv_path, backup_path in backups.items():
                shutil.copy2(backup_path, csv_path)
            if bundle_backup.is_file():
                shutil.copy2(bundle_backup, bundle_path)
            raise
        return {"status": "REVIEWED_ACCEPTED", "patch_id": patch_id,
                "original_hash": current_hash, "revised_hash": new_hash_preview,
                "version_backup": str(version_dir)}
    finally:
        con.close()


def _replacement_row(series_id: str, point: dict) -> dict:
    x = point.get("x")
    return {
        "series_id": series_id,
        "point_index": str(point["point_index"]),
        "x_value": str(x) if isinstance(x, (int, float)) else "",
        "x_label": x if isinstance(x, str) else "",
        "y_value": "" if point.get("y") is None else str(point["y"]),
        "pixel_x": "" if point.get("pixel_x") is None else str(point["pixel_x"]),
        "pixel_y": "" if point.get("pixel_y") is None else str(point["pixel_y"]),
        "y_err_low": "" if point.get("y_err_low") is None else str(point["y_err_low"]),
        "y_err_high": "" if point.get("y_err_high") is None else str(point["y_err_high"]),
        "err_type": point.get("err_type", "UNKNOWN"),
    }


def _replace_series_points_atomic(
    csv_path: Path,
    replacements: dict[str, list[dict]],
    axis_updates: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Rewrite a panel CSV atomically using bounded memory and optional recalibration."""
    import os
    import tempfile
    axis_updates = axis_updates or {}
    header = ["series_id", "point_index", "x_value", "x_label", "y_value", "pixel_x",
              "pixel_y", "y_err_low", "y_err_high", "err_type"]
    fd, temporary = tempfile.mkstemp(prefix=f".{csv_path.name}.", suffix=".tmp", dir=csv_path.parent)
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as source, \
             os.fdopen(fd, "w", newline="", encoding="utf-8") as target:
            reader = csv.DictReader(source)
            writer = csv.DictWriter(target, fieldnames=header)
            writer.writeheader()
            replaced_ids = set(replacements)
            for row in reader:
                series_id = row.get("series_id")
                if series_id in replaced_ids:
                    continue
                transforms = axis_updates.get(series_id, {})
                pixel_x = _float_or_none(row.get("pixel_x"))
                pixel_y = _float_or_none(row.get("pixel_y"))
                if "x" in transforms and pixel_x is not None:
                    row["x_value"] = str(map_pixel(transforms["x"], pixel_x))
                    row["x_label"] = ""
                if "y" in transforms and pixel_y is not None:
                    row["y_value"] = str(map_pixel(transforms["y"], pixel_y))
                writer.writerow(row)
            for series_id, points in replacements.items():
                transforms = axis_updates.get(series_id, {})
                for point in points:
                    row = _replacement_row(series_id, point)
                    pixel_x = _float_or_none(row.get("pixel_x"))
                    pixel_y = _float_or_none(row.get("pixel_y"))
                    if "x" in transforms and pixel_x is not None:
                        row["x_value"] = str(map_pixel(transforms["x"], pixel_x))
                        row["x_label"] = ""
                    if "y" in transforms and pixel_y is not None:
                        row["y_value"] = str(map_pixel(transforms["y"], pixel_y))
                    writer.writerow(row)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, csv_path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
