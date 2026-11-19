from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .adapter import snapshot_paper
from .calibration import calibration_to_dict, fit_linear_axis
from .context_index import PaperContextIndex
from .entities import SubjectEntity, link_series_to_subject
from .errors import OptionalDependencyError
from .hashing import atomic_write_json
from .models import JobState, PaperSnapshot, SeriesRecord, safe_id
from .pdf_backend import PdfiumBackend
from .raster import map_explicit_polyline, trace_monotonic_color
from .storage import write_paper_artifacts, append_panel_series_csv


ALGORITHM_VERSION = "0.1.0"


def _json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _paper_relative_artifact(artifact_path: str, paper_relative: str) -> str:
    path = Path(artifact_path)
    base = Path(paper_relative)
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _inventory(paper_dir: Path, snapshot: PaperSnapshot) -> tuple[list[dict], Path | None]:
    for artifact in snapshot.artifacts:
        if artifact.role == "figure_inventory":
            rel = _paper_relative_artifact(artifact.path, snapshot.source_dir)
            path = paper_dir / rel
            if path.is_file():
                data = _json_file(path)
                if isinstance(data, list):
                    return data, path
                if isinstance(data, dict):
                    figures = data.get("figures") or data.get("items") or data.get("figure_inventory") or []
                    if isinstance(figures, list):
                        return figures, path
    return [], None


def _safe_local_file(paper_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    candidate = (paper_dir / value).resolve()
    try:
        candidate.relative_to(paper_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _normalize_bbox(bbox: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in bbox]
    if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.01:
        x0, x1 = x0 * width, x1 * width
        y0, y1 = y0 * height, y1 * height
    coords = (max(0, int(x0)), max(0, int(y0)), min(width, int(x1)), min(height, int(y1)))
    if coords[2] <= coords[0] or coords[3] <= coords[1]:
        return None
    return coords


def _figure_panels(figure: dict) -> list[dict]:
    panels = figure.get("panels")
    if isinstance(panels, list) and panels:
        return [p if isinstance(p, dict) else {"label": str(p)} for p in panels]
    return [{"panel_id": "1", "label": figure.get("panel_label", "whole-figure"),
             "bbox": figure.get("bbox") or figure.get("bounding_box")}]


def _load_overrides(output_root: Path, paper_id: str) -> dict:
    path = output_root / "overrides" / paper_id / "digitization_overrides.json"
    if not path.is_file():
        return {}
    data = _json_file(path)
    return data if isinstance(data, dict) else {}


def _series_overrides(overrides: dict, figure_id: str, panel_id: str) -> list[dict]:
    figures = overrides.get("figures", {})
    figure = figures.get(figure_id, {}) if isinstance(figures, dict) else {}
    panels = figure.get("panels", {}) if isinstance(figure, dict) else {}
    panel = panels.get(panel_id, {}) if isinstance(panels, dict) else {}
    series = panel.get("series", []) if isinstance(panel, dict) else []
    return series if isinstance(series, list) else []


def _cached_result(paper_root: Path, snapshot: PaperSnapshot, locked: bool = False) -> dict | None:
    digitization_path = paper_root / "digitization.json"
    manifest_path = paper_root / "paper_manifest.json"
    figures_path = paper_root / "figure_inventory.json"
    panels_path = paper_root / "panel_layout.json"
    if not all(p.is_file() for p in (digitization_path, manifest_path, figures_path, panels_path)):
        return None
    digitization = _json_file(digitization_path)
    if not locked and digitization.get("input_fingerprint") != snapshot.input_fingerprint:
        return None
    figures = _json_file(figures_path).get("figures", [])
    panels = _json_file(panels_path).get("panels", [])
    series = []
    accepted_fields = {
        "series_id", "paper_id", "figure_id", "panel_id", "technique", "domain", "label",
        "x_label", "y_label", "x_unit", "y_unit", "y_axis_side", "extraction_method",
        "extraction_status", "qc_status", "review_state", "subject_links", "conditions",
        "evidence", "metadata",
    }
    for item in digitization.get("series", []):
        payload = {key: value for key, value in item.items() if key in accepted_fields}
        payload.setdefault("points", [])
        series.append(payload)
    status = "BLOCKED_REVIEW_LOCKED" if locked else digitization.get("status", "COMPLETED")
    job_state = JobState.BLOCKED.value if locked else (
        JobState.NEEDS_REVIEW.value if status in {"NEEDS_REVIEW", "COMPLETED_WITH_REVIEW"} else JobState.COMPLETED.value
    )
    return {
        "cached": True, "snapshot": snapshot.to_dict(), "figures": figures, "panels": panels,
        "series": series, "status": status, "job_state": job_state,
        "reason": "REVIEWED_RESULT_PROTECTED" if locked else "UNCHANGED_INPUT_AND_ALGORITHM",
    }


def _check_memory_budget(memory_limit_mb: int):
    if memory_limit_mb <= 0:
        return
    try:
        import psutil
        rss = psutil.Process().memory_info().rss
        if rss > memory_limit_mb * 1024 * 1024:
            raise MemoryError(f"Worker RSS {rss // (1024 * 1024)} MiB exceeds configured budget {memory_limit_mb} MiB")
    except ImportError:
        return


def _extract_panel(
    image_path: Path | None, paper_id: str, figure_id: str, panel_id: str,
    panel: dict, figure: dict, overrides: dict, context: PaperContextIndex,
    pdf_page: int | None,
) -> list[SeriesRecord]:
    definitions = _series_overrides(overrides, figure_id, panel_id)
    evidence = {
        "figure_id": figure_id, "panel_id": panel_id, "source_page": pdf_page,
        "source_image": image_path.name if image_path else None,
        "context_reference_candidates": context.search("reference_electrode"),
        "context_statistics_candidates": context.search("statistics"),
    }
    if not definitions:
        definitions = [{
            "series_id": f"{figure_id}_{panel_id}_unassigned", "label": None,
            "technique": panel.get("technique") or figure.get("technique"),
            "domain": panel.get("domain") or figure.get("domain"),
        }]
    results: list[SeriesRecord] = []
    for index, definition in enumerate(definitions, 1):
        series_id = safe_id(str(definition.get("series_id") or f"{figure_id}_{panel_id}_series{index}"))
        record = SeriesRecord(
            series_id=series_id, paper_id=paper_id, figure_id=figure_id, panel_id=panel_id,
            technique=definition.get("technique") or panel.get("technique") or figure.get("technique"),
            domain=definition.get("domain") or panel.get("domain") or figure.get("domain"),
            label=definition.get("label"), x_label=definition.get("x_label"),
            y_label=definition.get("y_label"), x_unit=definition.get("x_unit"),
            y_unit=definition.get("y_unit"), y_axis_side=definition.get("y_axis_side", "UNASSIGNED"),
            extraction_method="UNRESOLVED", extraction_status="NEEDS_REVIEW",
            qc_status="PROVISIONAL_UNCALIBRATED", review_state="NEEDS_REVIEW",
            evidence=[evidence], metadata={"reason": "INSUFFICIENT_EXPLICIT_DIGITIZATION_EVIDENCE"},
        )
        for link in definition.get("subject_links", []):
            entity_data = link.get("entity") or {}
            entity = SubjectEntity(
                entity_id=str(entity_data.get("entity_id", "UNKNOWN")),
                canonical_name=str(entity_data.get("canonical_name", "")),
                entity_type=str(entity_data.get("entity_type", "unknown")),
                domain=entity_data.get("domain"), aliases=entity_data.get("aliases", []),
            ) if entity_data else None
            record.subject_links.append(link_series_to_subject(
                series_id, entity, str(link.get("role_in_series", "unknown")),
                link.get("evidence"), exact_match=bool(link.get("exact_match", False)),
            ))
        record.conditions = definition.get("conditions", [])
        try:
            x_cal = fit_linear_axis("x", definition.get("x_axis_anchors", []), definition.get("x_unit"))
            y_cal = fit_linear_axis("y", definition.get("y_axis_anchors", []), definition.get("y_unit"))
        except (ValueError, TypeError):
            results.append(record)
            continue

        pixel_points = definition.get("pixel_points")
        family = str(definition.get("data_family", "")).upper()
        if isinstance(pixel_points, list) and len(pixel_points) >= 2:
            clean_points = [(float(p[0]), float(p[1])) for p in pixel_points
                            if isinstance(p, (list, tuple)) and len(p) == 2]
            record.points = map_explicit_polyline(clean_points, x_cal, y_cal)
            record.extraction_method = "EXPLICIT_ORDERED_PIXEL_POLYLINE"
            record.extraction_status = "EXTRACTED_PROVISIONAL" if len(record.points) >= 2 else "NEEDS_REVIEW"
            record.metadata = {"path_order": "PRESERVED", "data_family": family,
                               "x_calibration": calibration_to_dict(x_cal),
                               "y_calibration": calibration_to_dict(y_cal)}
        elif image_path and definition.get("color_rgb") and family not in {"CV", "EIS", "NON_MONOTONIC"}:
            record.points, qc = trace_monotonic_color(
                str(image_path), tuple(int(v) for v in definition["color_rgb"]),
                int(definition.get("color_tolerance", 24)), x_cal, y_cal,
            )
            record.extraction_method = qc.get("method", "RASTER_COLOR")
            record.extraction_status = "EXTRACTED_PROVISIONAL" if record.points else "NEEDS_REVIEW"
            record.metadata = {"x_calibration": calibration_to_dict(x_cal),
                               "y_calibration": calibration_to_dict(y_cal), "raster_qc": qc}
        else:
            record.metadata = {
                "reason": "NO_SUPPORTED_TRACE_SPECIFICATION",
                "note": "Provide ordered pixel_points for non-monotonic paths or explicit color and calibrations for monotonic raster traces.",
                "data_family": family,
                "x_calibration": calibration_to_dict(x_cal), "y_calibration": calibration_to_dict(y_cal),
            }
        if record.points:
            record.qc_status = "PROVISIONAL_UNCALIBRATED"
            record.review_state = "NEEDS_REVIEW"
        results.append(record)
    return results


def _crop_local_image(source_path: Path, bbox: Any, output_path: Path) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return source_path
    with Image.open(source_path) as image:
        coords = _normalize_bbox(bbox, image.width, image.height)
        if not coords:
            return source_path
        crop = image.crop(coords)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(output_path, format="PNG")
        crop.close()
    return output_path


def process_paper(input_root: Path, paper_relative: Path, output_root: Path,
                  options: dict | None = None) -> dict:
    """Process one paper with lazy pages, compact text context, and immutable inputs."""
    options = options or {}
    input_root = input_root.resolve()
    output_root = output_root.resolve()
    paper_dir = (input_root / paper_relative).resolve()
    try:
        paper_dir.relative_to(input_root)
    except ValueError as exc:
        raise ValueError("Paper path escapes input root") from exc
    snapshot = snapshot_paper(paper_dir, input_root)
    paper_output = output_root / "papers" / snapshot.paper_id
    existing = paper_output / "digitization.json"
    force_reviewed = bool(options.get("force_recompute_reviewed", False))
    if existing.is_file():
        old = _json_file(existing)
        accepted = any(s.get("review_state") == "REVIEWED_ACCEPTED" for s in old.get("series", []))
        unchanged = (old.get("input_fingerprint") == snapshot.input_fingerprint
                     and old.get("algorithm_version") == ALGORITHM_VERSION)
        if unchanged:
            cached = _cached_result(paper_output, snapshot)
            if cached:
                cached["artifact_paths"] = {
                    "manifest_path": str(paper_output / "paper_manifest.json"),
                    "bundle_path": str(paper_output / "paper_bundle.json"),
                }
                return cached
        elif accepted and not force_reviewed:
            locked = _cached_result(paper_output, snapshot, locked=True)
            if locked:
                locked["artifact_paths"] = {
                    "manifest_path": str(paper_output / "paper_manifest.json"),
                    "bundle_path": str(paper_output / "paper_bundle.json"),
                }
                return locked
    if existing.is_file() and (force_reviewed or not accepted or old.get("input_fingerprint") != snapshot.input_fingerprint
                                or old.get("algorithm_version") != ALGORITHM_VERSION):
        version_key = snapshot.input_fingerprint[:12] + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        version_dir = paper_output / "versions" / f"pre-recompute-{version_key}"
        version_dir.mkdir(parents=True, exist_ok=True)
        for name in ("digitization.json", "paper_manifest.json", "figure_inventory.json", "panel_layout.json"):
            candidate = paper_output / name
            if candidate.is_file():
                shutil.copy2(candidate, version_dir / candidate.name)
        series_dir = paper_output / "series"
        if series_dir.exists():
            shutil.copytree(series_dir, version_dir / "series", dirs_exist_ok=True)
            shutil.rmtree(series_dir)

    memory_limit_mb = int(options.get("memory_limit_mb", 2048))
    render_scale = float(options.get("render_scale", 1.5))
    max_render_pixels = int(options.get("max_render_pixels", 12_000_000))
    _check_memory_budget(memory_limit_mb)
    context = PaperContextIndex.build(
        paper_dir, paper_output / "context",
        memory_budget_bytes=int(options.get("context_memory_budget", 500_000)),
    )
    figures_raw, inventory_path = _inventory(paper_dir, snapshot)
    overrides = _load_overrides(output_root, snapshot.paper_id)
    pdf_path = None
    for artifact in snapshot.artifacts:
        if artifact.role == "main_pdf":
            candidate = input_root / artifact.path
            if candidate.is_file():
                pdf_path = candidate
                break

    figures: list[dict] = []
    panels: list[dict] = []
    series: list[SeriesRecord] = []
    review_needed = False
    backend = None
    for figure_index, source_figure in enumerate(figures_raw, 1):
        if not isinstance(source_figure, dict):
            continue
        figure_id = safe_id(str(source_figure.get("figure_id") or source_figure.get("id") or f"Figure{figure_index}"))
        page_number = source_figure.get("page") or source_figure.get("page_number")
        figure = {
            "figure_id": figure_id, "page": int(page_number) if page_number else None,
            "caption": source_figure.get("caption") or source_figure.get("title"),
            "shared_legends": source_figure.get("shared_legends") or source_figure.get("legend") or [],
            "technique": source_figure.get("technique"), "domain": source_figure.get("domain"),
        }
        if isinstance(figure["shared_legends"], str):
            figure["shared_legends"] = [{"text": figure["shared_legends"], "scope": "FIGURE"}]
        figures.append(figure)
        for panel_index, source_panel in enumerate(_figure_panels(source_figure), 1):
            panel = dict(source_panel)
            panel_id = safe_id(str(panel.get("panel_id") or panel.get("id") or panel.get("label") or panel_index))
            panel["panel_id"] = panel_id
            bbox = panel.get("bbox") or panel.get("bounding_box") or source_figure.get("bbox")
            panel_specific_image = bool(panel.get("image_path"))
            panel_path = _safe_local_file(paper_dir, panel.get("image_path") or source_figure.get("image_path"))
            saved_crop = None
            if panel_path and not panel_specific_image and bbox:
                saved_crop = _crop_local_image(
                    panel_path, bbox, paper_output / "evidence" / f"{figure_id}_{panel_id}.png")
            elif panel_path:
                saved_crop = panel_path
            if saved_crop is None and pdf_path and figure["page"]:
                if backend is None:
                    backend = PdfiumBackend()
                with backend.open(pdf_path) as doc:
                    with doc.page(int(figure["page"])) as pdf_page:
                        page_width, page_height = pdf_page.size
                        safe_scale = min(render_scale, (max_render_pixels / max(1, page_width * page_height)) ** 0.5)
                        safe_scale = max(0.25, safe_scale)
                        rendered = pdf_page.render(scale=safe_scale)
                        try:
                            coords = _normalize_bbox(bbox, rendered.width, rendered.height)
                            if coords:
                                crop = rendered.crop(coords)
                                saved_crop = paper_output / "evidence" / f"{figure_id}_{panel_id}.png"
                                saved_crop.parent.mkdir(parents=True, exist_ok=True)
                                crop.save(saved_crop, format="PNG")
                                crop.close()
                        finally:
                            rendered.close()
            _check_memory_budget(memory_limit_mb)
            extracted = _extract_panel(saved_crop, snapshot.paper_id, figure_id, panel_id,
                                       panel, figure, overrides, context, figure["page"])
            append_panel_series_csv(paper_output, figure_id, panel_id, extracted)
            panel_status = "EXTRACTED" if any(s.points for s in extracted) else "NEEDS_REVIEW"
            # Keep only compact per-series metadata in the paper worker; point batches are already persisted.
            for item in extracted:
                item.metadata.setdefault("points_count", len(item.points))
                item.points.clear()
            series.extend(extracted)
            review_needed = review_needed or panel_status == "NEEDS_REVIEW"
            panels.append({"figure_id": figure_id, "panel_id": panel_id,
                           "bbox": bbox, "status": panel_status,
                           "shared_legend_refs": figure["shared_legends"]})

    if not figures:
        status = "NEEDS_REVIEW"
        review_needed = True
    else:
        status = "COMPLETED_WITH_REVIEW" if review_needed else "COMPLETED"
    job_state = JobState.NEEDS_REVIEW.value if review_needed else JobState.COMPLETED.value
    artifacts = write_paper_artifacts(
        output_root, snapshot, figures, panels, series, status,
        extra={"context_index_fingerprint": context.fingerprint,
               "figure_inventory_source": inventory_path.name if inventory_path else None,
               "pdf_source": pdf_path.name if pdf_path else None,
               "memory_limit_mb": memory_limit_mb, "render_scale": render_scale,
               "llm_tokens": 0},
    )
    # Snapshot is also persisted outside the per-paper bundle for corpus-level auditing.
    from .hashing import atomic_write_json
    atomic_write_json(output_root / "manifests" / f"{safe_id(snapshot.paper_id)}.json", snapshot.to_dict())
    return {
        "cached": False, "snapshot": snapshot.to_dict(), "figures": figures, "panels": panels,
        "series": [asdict(s) for s in series], "status": status, "job_state": job_state,
        "artifact_paths": {
            "manifest_path": str(Path(artifacts["paper_root"]) / "paper_manifest.json"),
            "bundle_path": str(Path(artifacts["paper_root"]) / "paper_bundle.json"),
        },
        "context_fingerprint": context.fingerprint,
        "figure_count": len(figures), "panel_count": len(panels), "series_count": len(series),
    }
