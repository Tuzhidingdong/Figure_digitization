from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapter import snapshot_paper
from .calibration import calibration_to_dict, fit_linear_axis
from .context_index import PaperContextIndex
from .errors import OptionalDependencyError
from .hashing import atomic_write_json
from .models import JobState, PaperSnapshot, SeriesRecord, SeriesPoint, safe_id
from .pdf_backend import PdfiumBackend
from .raster import map_explicit_polyline, trace_monotonic_color
from .storage import write_paper_artifacts


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


def _load_overrides(paper_dir: Path) -> dict:
    path = paper_dir / "digitization_overrides.json"
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


def _extract_panel(
    image_path: Path | None, image_crop: Any, paper_id: str, figure_id: str,
    panel_id: str, panel: dict, figure: dict, overrides: dict,
    context: PaperContextIndex, pdf_page: int | None,
) -> tuple[list[SeriesRecord], dict]:
    definitions = _series_overrides(overrides, figure_id, panel_id)
    results: list[SeriesRecord] = []
    evidence = {
        "figure_id": figure_id, "panel_id": panel_id, "source_page": pdf_page,
        "source_image": str(image_path) if image_path else None,
        "context_reference_candidates": context.search("reference_electrode"),
        "context_statistics_candidates": context.search("statistics"),
    }
    if not definitions:
        definitions = [{
            "series_id": f"{figure_id}_{panel_id}_unassigned",
            "label": None,
            "technique": panel.get("technique") or figure.get("technique"),
            "domain": panel.get("domain") or figure.get("domain"),
        }]
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
        try:
            x_cal = fit_linear_axis("x", definition.get("x_axis_anchors", []), definition.get("x_unit"))
            y_cal = fit_linear_axis("y", definition.get("y_axis_anchors", []), definition.get("y_unit"))
        except (ValueError, TypeError):
            results.append(record)
            continue

        pixel_points = definition.get("pixel_points")
        if isinstance(pixel_points, list) and len(pixel_points) >= 2:
            record.points = map_explicit_polyline(
                [(float(p[0]), float(p[1])) for p in pixel_points if isinstance(p, (list, tuple)) and len(p) == 2],
                x_cal, y_cal,
            )
            record.extraction_method = "EXPLICIT_ORDERED_PIXEL_POLYLINE"
            record.extraction_status = "EXTRACTED_PROVISIONAL" if len(record.points) >= 2 else "NEEDS_REVIEW"
            record.metadata = {"path_order": "PRESERVED", "x_calibration": calibration_to_dict(x_cal),
                               "y_calibration": calibration_to_dict(y_cal)}
        elif image_path and definition.get("color_rgb") and not str(definition.get("data_family", "")).upper() in {"CV", "EIS", "NON_MONOTONIC"}:
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
                "note": "Provide ordered pixel_points for non-monotonic paths or an explicit color and calibrations for a monotonic raster trace.",
                "x_calibration": calibration_to_dict(x_cal),
                "y_calibration": calibration_to_dict(y_cal),
            }
        if record.points:
            record.qc_status = "PROVISIONAL_UNCALIBRATED"
            record.review_state = "NEEDS_REVIEW"
        results.append(record)
    return results, evidence


def process_paper(input_root: Path, paper_relative: Path, output_root: Path) -> dict:
    """Process one paper. Heavy PDF/page/image resources are opened only when needed."""
    input_root = input_root.resolve()
    paper_dir = (input_root / paper_relative).resolve()
    try:
        paper_dir.relative_to(input_root)
    except ValueError as exc:
        raise ValueError("Paper path escapes input root") from exc
    snapshot = snapshot_paper(paper_dir, input_root)
    paper_output = output_root / "papers" / snapshot.paper_id
    context = PaperContextIndex.build(paper_dir, paper_output / "context")
    figures_raw, inventory_path = _inventory(paper_dir, snapshot)
    overrides = _load_overrides(paper_dir)
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
            panel_id = safe_id(str(source_panel.get("panel_id") or source_panel.get("id") or source_panel.get("label") or panel_index))
            panel = dict(source_panel)
            panel["panel_id"] = panel_id
            panel["figure_id"] = figure_id
            bbox = panel.get("bbox") or panel.get("bounding_box") or source_figure.get("bbox")
            panel_path = _safe_local_file(paper_dir, panel.get("image_path") or source_figure.get("image_path"))
            saved_crop = None
            if panel_path is None and pdf_path and figure["page"]:
                if backend is None:
                    backend = PdfiumBackend()
                with backend.open(pdf_path) as doc:
                    with doc.page(int(figure["page"])) as pdf_page:
                        rendered = pdf_page.render(scale=float(source_figure.get("render_scale", 1.5)))
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
            panel_image = panel_path or saved_crop
            extracted, _ = _extract_panel(panel_image, None, snapshot.paper_id, figure_id, panel_id,
                                          panel, figure, overrides, context, figure["page"])
            series.extend(extracted)
            panel_status = "EXTRACTED" if any(s.points for s in extracted) else "NEEDS_REVIEW"
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
               "figure_inventory_source": str(inventory_path) if inventory_path else None,
               "pdf_source": str(pdf_path) if pdf_path else None},
    )
    return {
        "snapshot": snapshot.to_dict(), "figures": figures, "panels": panels,
        "series": [{**{k: v for k, v in asdict(s).items()}} for s in series],
        "status": status, "job_state": job_state,
        "artifact_paths": {
            "manifest_path": str(Path(artifacts["paper_root"]) / "paper_manifest.json"),
            "bundle_path": str(Path(artifacts["paper_root"]) / "paper_bundle.json"),
        },
        "context_fingerprint": context.fingerprint,
        "figure_count": len(figures), "panel_count": len(panels), "series_count": len(series),
    }
