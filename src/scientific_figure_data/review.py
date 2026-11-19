from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import StalePatchError
from .hashing import atomic_write_json, sha256_file
from .storage import connect_catalog

ALLOWED_FIELDS = {
    "label", "technique", "domain", "x_label", "y_label", "x_unit", "y_unit",
    "y_axis_side", "extraction_status", "points"
}
ALLOWED_AXIS_SIDES = {"LEFT", "RIGHT", "UNASSIGNED"}


def _validate_patch(patch: dict) -> None:
    required = ("patch_id", "paper_id", "target_artifact", "original_result_hash", "changes")
    missing = [key for key in required if key not in patch]
    if missing:
        raise ValueError(f"Review patch missing required fields: {', '.join(missing)}")
    if patch["target_artifact"] != "digitization.json":
        raise ValueError("Only digitization.json is a supported patch target")
    if not isinstance(patch["changes"], list) or not patch["changes"]:
        raise ValueError("changes must be a non-empty list")
    for change in patch["changes"]:
        if not isinstance(change, dict) or not change.get("series_id"):
            raise ValueError("Every change must contain series_id")
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
        if "points" in values:
            points = values["points"]
            if not isinstance(points, list):
                raise ValueError("points must be a list")
            for point in points:
                if not isinstance(point, dict) or "point_index" not in point:
                    raise ValueError("Each point requires point_index")


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
        csv_updates: dict[Path, list[dict]] = {}
        for change in patch["changes"]:
            series_id = change["series_id"]
            if series_id not in series_index:
                raise ValueError(f"Unknown series_id in patch: {series_id}")
            item = series_index[series_id]
            values = change["set"]
            for key, value in values.items():
                if key == "points":
                    item["points_count"] = len(value)
                    csv_path = paper_root / "series" / f"{item['figure_id']}__{item['panel_id']}" / "panel_series.csv"
                    if not csv_path.is_file():
                        raise FileNotFoundError(f"Panel point artifact missing: {csv_path}")
                    csv_updates[csv_path] = _replace_series_points(csv_path, series_id, value)
                else:
                    item[key] = value
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
        backups = {}
        for csv_path in csv_updates:
            backup_path = version_dir / (csv_path.parent.name + ".before.csv")
            shutil.copy2(csv_path, backup_path)
            backups[csv_path] = backup_path
        try:
            for csv_path, rows in csv_updates.items():
                _write_csv_atomic(csv_path, rows)
            atomic_write_json(target, document)
            new_hash_preview = sha256_file(target)
            with con:
                for change in patch["changes"]:
                    values = change["set"]
                    sid = change["series_id"]
                    assignments = ["review_state='REVIEWED_ACCEPTED'", "extraction_status='REVIEWED_ACCEPTED'"]
                    args: list[Any] = []
                    for key in ("label", "technique", "domain", "x_unit", "y_unit", "y_axis_side"):
                        if key in values:
                            assignments.append(f"{key}=?")
                            args.append(values[key])
                    args.append(sid)
                    con.execute(f"UPDATE series SET {', '.join(assignments)} WHERE series_id=?", args)
                    if "points" in values:
                        con.execute("DELETE FROM series_points WHERE series_id=?", (sid,))
                        con.executemany(
                            """INSERT INTO series_points(series_id,point_index,x_value,x_label,y_value,
                               pixel_x,pixel_y,y_err_low,y_err_high,err_type) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            [(sid, int(p["point_index"]), p.get("x") if isinstance(p.get("x"), (int, float)) else None,
                              p.get("x") if isinstance(p.get("x"), str) else None, p.get("y"),
                              p.get("pixel_x"), p.get("pixel_y"), p.get("y_err_low"),
                              p.get("y_err_high"), p.get("err_type", "UNKNOWN")) for p in values["points"]],
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
            # Keep the paper bundle's artifact hashes consistent with the newly accepted result.
            bundle_path = paper_root / "paper_bundle.json"
            if bundle_path.is_file():
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle["generated_at"] = datetime.now(timezone.utc).isoformat()
                paths = bundle.get("canonical_artifacts", [])
                refreshed = {}
                for relative in paths:
                    artifact_path = paper_root / relative
                    if artifact_path.is_file():
                        refreshed[relative] = sha256_file(artifact_path)
                bundle["content_hashes"] = refreshed
                atomic_write_json(bundle_path, bundle)
        except Exception:
            shutil.copy2(backup_digitization, target)
            for csv_path, backup_path in backups.items():
                shutil.copy2(backup_path, csv_path)
            raise
        return {"status": "REVIEWED_ACCEPTED", "patch_id": patch_id,
                "original_hash": current_hash, "revised_hash": new_hash_preview,
                "version_backup": str(version_dir)}
    finally:
        con.close()


def _replace_series_points(csv_path: Path, series_id: str, replacement: list[dict]) -> list[dict]:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    header = ["series_id", "point_index", "x_value", "x_label", "y_value", "pixel_x",
              "pixel_y", "y_err_low", "y_err_high", "err_type"]
    retained = [r for r in rows if r.get("series_id") != series_id]
    for point in replacement:
        x = point.get("x")
        retained.append({
            "series_id": series_id, "point_index": str(point["point_index"]),
            "x_value": str(x) if isinstance(x, (int, float)) else "",
            "x_label": x if isinstance(x, str) else "",
            "y_value": "" if point.get("y") is None else str(point["y"]),
            "pixel_x": "" if point.get("pixel_x") is None else str(point["pixel_x"]),
            "pixel_y": "" if point.get("pixel_y") is None else str(point["pixel_y"]),
            "y_err_low": "" if point.get("y_err_low") is None else str(point["y_err_low"]),
            "y_err_high": "" if point.get("y_err_high") is None else str(point["y_err_high"]),
            "err_type": point.get("err_type", "UNKNOWN"),
        })
    return retained


def _write_csv_atomic(path: Path, rows: list[dict]) -> None:
    import os
    import tempfile
    header = ["series_id", "point_index", "x_value", "x_label", "y_value", "pixel_x",
              "pixel_y", "y_err_low", "y_err_high", "err_type"]
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
