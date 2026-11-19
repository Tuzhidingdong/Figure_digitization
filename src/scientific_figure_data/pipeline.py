from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .adapter import snapshot_paper
from .calibration import calibration_to_dict, fit_linear_axis, map_pixel
from .axis_text import extract_native_numeric_axis_anchors, extract_numeric_axis_anchors
from .chart_classifier import classify_chart_family
from .context_index import PaperContextIndex
from .entities import SubjectEntity, link_series_to_subject
from .errors import OptionalDependencyError
from .hashing import atomic_write_json, sha256_file, sha256_json
from .models import AxisCalibration, JobState, PaperSnapshot, SeriesPoint, SeriesRecord, safe_id
from .pdf_backend import PdfiumBackend
from .raster import map_explicit_polyline, trace_monotonic_color
from .profiles import profile_registry_fingerprint
from .plot_region import detect_plot_box, detect_single_trace_color
from .qc import load_thresholds
from .storage import write_paper_artifacts, append_panel_series_csv
from .vector_paths import choose_vector_paths, pdf_points_to_crop_pixels


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
    preferred = {"figure_inventory": 0, "evidence_index": 1}
    candidates = sorted(
        (artifact for artifact in snapshot.artifacts
         if artifact.role in preferred and Path(artifact.path).suffix.lower() == ".json"),
        key=lambda item: (preferred[item.role], item.path.casefold()),
    )
    for artifact in candidates:
        rel = _paper_relative_artifact(artifact.path, snapshot.source_dir)
        path = paper_dir / rel
        if not path.is_file():
            continue
        try:
            data = _json_file(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, list):
            figures = data
        elif isinstance(data, dict):
            figures = None
            for key in ("figures", "items", "figure_inventory", "figure_index"):
                value = data.get(key)
                if isinstance(value, list):
                    figures = value
                    break
                if isinstance(value, dict) and isinstance(value.get("figures"), list):
                    figures = value["figures"]
                    break
        else:
            figures = None
        if figures is not None:
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
    try:
        x0, y0, x1, y1 = [float(v) for v in bbox]
    except (TypeError, ValueError, OverflowError):
        return None
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


def _load_overrides(paper_dir: Path, output_root: Path, paper_id: str) -> dict:
    # The upstream-side override is read-only. A separate downstream override takes precedence.
    candidates = [
        paper_dir / "digitization_overrides.json",
        output_root / "overrides" / paper_id / "digitization_overrides.json",
    ]
    merged = {}
    for path in candidates:
        if path.is_file():
            data = _json_file(path)
            if isinstance(data, dict):
                merged = {**merged, **data}
    return merged


def _series_overrides(overrides: dict, figure_id: str, panel_id: str) -> list[dict]:
    figures = overrides.get("figures", {})
    figure = figures.get(figure_id, {}) if isinstance(figures, dict) else {}
    panels = figure.get("panels", {}) if isinstance(figure, dict) else {}
    panel = panels.get(panel_id, {}) if isinstance(panels, dict) else {}
    series = panel.get("series", []) if isinstance(panel, dict) else []
    return series if isinstance(series, list) else []


def _cached_result(paper_root: Path, snapshot: PaperSnapshot, locked: bool = False,
                   expected_stage_fingerprint: str | None = None) -> dict | None:
    digitization_path = paper_root / "digitization.json"
    manifest_path = paper_root / "paper_manifest.json"
    figures_path = paper_root / "figure_inventory.json"
    panels_path = paper_root / "panel_layout.json"
    if not all(p.is_file() for p in (digitization_path, manifest_path, figures_path, panels_path)):
        return None
    digitization = _json_file(digitization_path)
    bundle_path = paper_root / "paper_bundle.json"
    if not bundle_path.is_file():
        return None
    bundle = _json_file(bundle_path)
    for relative, expected_hash in bundle.get("content_hashes", {}).items():
        artifact = (paper_root / relative).resolve()
        try:
            artifact.relative_to(paper_root.resolve())
        except ValueError:
            return None
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            return None
    if not locked:
        if digitization.get("input_fingerprint") != snapshot.input_fingerprint:
            return None
        if expected_stage_fingerprint and digitization.get("stage_fingerprint") != expected_stage_fingerprint:
            return None
    figures = _json_file(figures_path).get("figures", [])
    panels = _json_file(panels_path).get("panels", [])
    series = []
    accepted_fields = {
        "series_id", "paper_id", "figure_id", "panel_id", "technique", "domain", "label",
        "x_label", "y_label", "x_unit", "y_unit", "measurement_id", "y_axis_side", "extraction_method",
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


def _plot_box_pixels(image_path: Path | None, plot_box: Any) -> tuple[int, int, int, int] | None:
    if image_path is None or not plot_box or len(plot_box) != 4:
        return None
    try:
        from PIL import Image
        with Image.open(image_path) as image:
            width, height = image.size
        return _normalize_bbox(plot_box, width, height)
    except (ImportError, OSError, TypeError, ValueError):
        return None


def _plot_box_to_pdf(
    plot_box_pixels: tuple[int, int, int, int] | None,
    crop_mapping: dict | None,
) -> tuple[float, float, float, float] | None:
    if not plot_box_pixels or not crop_mapping or crop_mapping.get("page_rotation_degrees", 0) != 0:
        return None
    scale = float(crop_mapping.get("render_scale", 0))
    if scale <= 0:
        return None
    left = float(crop_mapping["crop_left_pdf"])
    top = float(crop_mapping["crop_top_pdf"])
    x0, y0, x1, y1 = plot_box_pixels
    return (
        left + x0 / scale,
        top - y1 / scale,
        left + x1 / scale,
        top - y0 / scale,
    )



def _extract_panel(
    image_path: Path | None, paper_id: str, figure_id: str, panel_id: str,
    panel: dict, figure: dict, overrides: dict, context: PaperContextIndex,
    pdf_page: int | None, native_page_evidence: dict | None = None,
    ocr_evidence: list[dict] | None = None,
    source_pdf_sha256: str | None = None, input_fingerprint: str | None = None,
    native_page_path: Path | None = None, crop_mapping: dict | None = None,
) -> list[SeriesRecord]:
    definitions = _series_overrides(overrides, figure_id, panel_id)
    native_text_preview = str((native_page_evidence or {}).get("native_text_preview", ""))
    base_technique = panel.get("technique") or figure.get("technique")
    if not definitions:
        definitions = [{
            "series_id": f"{figure_id}_{panel_id}_unassigned", "label": None,
            "technique": base_technique,
            "domain": panel.get("domain") or figure.get("domain"),
        }]
    evidence = {
        "figure_id": figure_id, "panel_id": panel_id, "source_page": pdf_page,
        "source_image": image_path.name if image_path else None,
        "source_image_sha256": sha256_file(image_path) if image_path and image_path.is_file() else None,
        "source_pdf_sha256": source_pdf_sha256,
        "paper_input_fingerprint": input_fingerprint,
        "extraction_channel": "UNRESOLVED",
        "algorithm_version": ALGORITHM_VERSION,
        "context_reference_candidates": context.search("reference_electrode"),
        "context_statistics_candidates": context.search("statistics"),
        "native_page_evidence": native_page_evidence or {},
        "ocr_evidence": ocr_evidence or [],
    }
    results: list[SeriesRecord] = []
    for index, definition in enumerate(definitions, 1):
        series_id = safe_id(str(definition.get("series_id") or f"{figure_id}_{panel_id}_series{index}"))
        record = SeriesRecord(
            series_id=series_id, paper_id=paper_id, figure_id=figure_id, panel_id=panel_id,
            technique=definition.get("technique") or panel.get("technique") or figure.get("technique"),
            domain=definition.get("domain") or panel.get("domain") or figure.get("domain"),
            label=definition.get("label"), x_label=definition.get("x_label"),
            y_label=definition.get("y_label"), x_unit=definition.get("x_unit"),
            y_unit=definition.get("y_unit"),
            measurement_id=definition.get("measurement_id") or f"measurement:{series_id}",
            y_axis_side=definition.get("y_axis_side", "UNASSIGNED"),
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
        classification = classify_chart_family(
            definition.get("technique") or panel.get("technique") or figure.get("technique"),
            definition.get("x_label") or panel.get("x_label"),
            definition.get("y_label") or panel.get("y_label"),
            figure.get("caption"), native_text_preview,
        )
        if not record.technique and classification.get("technique"):
            record.technique = classification["technique"]
        explicit_family = str(definition.get("data_family", "")).upper()
        family = explicit_family or str(classification.get("chart_family", "UNCLASSIFIED")).upper()
        record.metadata["chart_family_classification"] = classification

        plot_box = definition.get("plot_box")
        plot_detection = None
        if not plot_box and image_path:
            try:
                plot_detection = detect_plot_box(image_path)
                if plot_detection.get("status") == "PROVISIONAL_PLOT_BOX":
                    plot_box = plot_detection["pixel_bbox"]
            except OptionalDependencyError:
                plot_detection = {"status": "UNAVAILABLE", "reason": "OPTIONAL_IMAGE_DEPENDENCY_MISSING"}
        plot_box_pixels = _plot_box_pixels(image_path, plot_box)
        if plot_box and image_path and plot_box_pixels is None:
            plot_detection = {"status": "NEEDS_REVIEW", "reason": "INVALID_MANUAL_PLOT_BOX"}

        plot_bbox_pdf = definition.get("plot_bbox_pdf")
        if plot_bbox_pdf is None:
            plot_bbox_pdf = _plot_box_to_pdf(plot_box_pixels, crop_mapping)
        vector_indices = definition.get("vector_object_indices")
        axis_text_evidence = None
        native_axis_evidence = None
        ocr_axis_evidence = None
        native_payload = None
        x_axis_anchors = definition.get("x_axis_anchors", [])
        y_axis_anchors = definition.get("y_axis_anchors", [])
        explicit_relative_signal = str(definition.get("y_signal_mode", "")).upper() in {
            "ARBITRARY_RELATIVE", "SERIES_RELATIVE_SIGNAL"
        }
        relative_signal = explicit_relative_signal or (
            family == "SPECTRUM" and len(y_axis_anchors) < 2
        )

        if (native_page_path and native_page_path.is_file() and plot_bbox_pdf and crop_mapping
                and crop_mapping.get("page_rotation_degrees", 0) == 0):
            try:
                native_payload = _json_file(native_page_path)
                native_axis_evidence = extract_native_numeric_axis_anchors(
                    native_payload, tuple(float(value) for value in plot_bbox_pdf), crop_mapping
                )
            except (OSError, KeyError, TypeError, ValueError):
                native_axis_evidence = None

        def use_y_axis_candidates(axis_candidates):
            nonlocal y_axis_anchors
            if explicit_relative_signal or len(y_axis_anchors) >= 2 or not axis_candidates:
                return
            requested_side = str(definition.get("y_axis_side") or "UNASSIGNED").upper()
            left_anchors = axis_candidates["y_left_anchors"]
            right_anchors = axis_candidates["y_right_anchors"]
            if requested_side == "LEFT" and len(left_anchors) >= 2:
                y_axis_anchors = left_anchors
            elif requested_side == "RIGHT" and len(right_anchors) >= 2:
                y_axis_anchors = right_anchors
            elif len(left_anchors) >= 2 and len(right_anchors) < 2:
                y_axis_anchors = left_anchors
                record.y_axis_side = "LEFT"
            elif len(right_anchors) >= 2 and len(left_anchors) < 2:
                y_axis_anchors = right_anchors
                record.y_axis_side = "RIGHT"

        if native_axis_evidence:
            if len(x_axis_anchors) < 2 and len(native_axis_evidence["x_anchors"]) >= 2:
                x_axis_anchors = native_axis_evidence["x_anchors"]
            use_y_axis_candidates(native_axis_evidence)
        if not explicit_relative_signal and family == "SPECTRUM":
            relative_signal = len(y_axis_anchors) < 2

        if ocr_evidence and plot_box_pixels and (
            len(x_axis_anchors) < 2 or (not explicit_relative_signal and len(y_axis_anchors) < 2)
        ):
            ocr_axis_evidence = extract_numeric_axis_anchors(ocr_evidence, tuple(plot_box_pixels))
            if len(x_axis_anchors) < 2 and len(ocr_axis_evidence["x_anchors"]) >= 2:
                x_axis_anchors = ocr_axis_evidence["x_anchors"]
            use_y_axis_candidates(ocr_axis_evidence)
            if not explicit_relative_signal and family == "SPECTRUM":
                relative_signal = len(y_axis_anchors) < 2

        if native_axis_evidence or ocr_axis_evidence:
            axis_text_evidence = {
                "native": native_axis_evidence,
                "ocr": ocr_axis_evidence,
                "source": (
                    "PDF_NATIVE_TEXT" if native_axis_evidence and (
                        native_axis_evidence["x_anchors"] or native_axis_evidence["y_left_anchors"]
                        or native_axis_evidence["y_right_anchors"]
                    ) else "OCR" if ocr_axis_evidence else "NONE"
                ),
                "provisional": True,
            }

        x_cal = None
        y_cal = None
        calibration_errors = {}
        try:
            x_cal = fit_linear_axis("x", x_axis_anchors, definition.get("x_unit"))
        except (ValueError, TypeError) as exc:
            calibration_errors["x"] = f"{type(exc).__name__}: {exc}"

        if relative_signal:
            try:
                if not plot_box_pixels:
                    raise ValueError("Relative signal requires a resolved plot box and panel image")
                _, by0, _, by1 = plot_box_pixels
                y_cal = AxisCalibration(
                    "y", None, -1.0 / (by1 - by0), by1 / (by1 - by0), [], 0.0,
                    status="SERIES_RELATIVE_SIGNAL",
                )
            except (ValueError, TypeError, ImportError) as exc:
                calibration_errors["y"] = f"{type(exc).__name__}: {exc}"
        else:
            try:
                y_cal = fit_linear_axis("y", y_axis_anchors, definition.get("y_unit"))
            except (ValueError, TypeError) as exc:
                calibration_errors["y"] = f"{type(exc).__name__}: {exc}"

        pixel_points = definition.get("pixel_points")
        color_rgb = definition.get("color_rgb")
        color_detection = None
        if (not color_rgb and image_path and plot_box_pixels
                and family not in {"NON_MONOTONIC", "NON_MONOTONIC_CURVE", "CV", "EIS", "UNCLASSIFIED"}):
            try:
                color_detection = detect_single_trace_color(image_path, plot_box_pixels)
                if color_detection.get("status") == "UNIQUE_CHROMATIC_FAMILY":
                    color_rgb = color_detection["color_rgb"]
            except OptionalDependencyError:
                color_detection = {"status": "UNAVAILABLE", "reason": "OPTIONAL_IMAGE_DEPENDENCY_MISSING"}
        vector_selection = None
        vector_requested = bool(vector_indices) or (
            bool(plot_bbox_pdf) and not pixel_points and not color_rgb
        )
        if (vector_requested and native_page_path and native_page_path.is_file() and plot_bbox_pdf
                and crop_mapping and crop_mapping.get("page_rotation_degrees", 0) == 0):
            try:
                if native_payload is None:
                    native_payload = _json_file(native_page_path)
                selected_paths, vector_selection = choose_vector_paths(
                    native_payload, tuple(float(value) for value in plot_bbox_pdf),
                    [int(value) for value in vector_indices] if vector_indices else None,
                )
                if selected_paths and len(selected_paths) == 1:
                    clean_points = pdf_points_to_crop_pixels(
                        selected_paths[0].points_pdf,
                        crop_left_pdf=float(crop_mapping["crop_left_pdf"]),
                        crop_top_pdf=float(crop_mapping["crop_top_pdf"]),
                        render_scale=float(crop_mapping["render_scale"]),
                    )
                    record.points = [
                        SeriesPoint(
                            point_index=point_index,
                            x=map_pixel(x_cal, point[0]) if x_cal else None,
                            y=map_pixel(y_cal, point[1]) if y_cal else None,
                            pixel_x=float(point[0]), pixel_y=float(point[1]),
                        )
                        for point_index, point in enumerate(clean_points)
                    ]
                    record.extraction_method = "PDFIUM_NATIVE_VECTOR_POLYLINE"
                    record.extraction_status = (
                        "EXTRACTED_PROVISIONAL" if x_cal and y_cal and len(record.points) >= 2
                        else "GEOMETRY_ONLY_NEEDS_REVIEW"
                    )
                    record.metadata = {
                        "path_order": "PRESERVED",
                        "data_family": family,
                        "vector_object_index": selected_paths[0].object_index,
                        "vector_bbox_pdf": list(selected_paths[0].bbox_pdf),
                        "vector_stroke_rgba": selected_paths[0].stroke_rgba,
                        "vector_stroke_width_pdf": selected_paths[0].stroke_width_pdf,
                        "vector_selection": vector_selection,
                        "plot_detection": plot_detection,
                        "color_detection": color_detection,
                        "axis_text_evidence": axis_text_evidence,
                        "crop_mapping": crop_mapping,
                        "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                        "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "calibration_errors": calibration_errors,
                    }
                else:
                    record.metadata = {
                        "reason": "VECTOR_PATH_CANDIDATES_REQUIRE_REVIEW",
                        "vector_selection": vector_selection,
                        "plot_detection": plot_detection,
                        "data_family": family,
                        "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                        "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "calibration_errors": calibration_errors,
                    }
            except (OSError, KeyError, TypeError, ValueError) as exc:
                record.metadata = {
                    "reason": "VECTOR_PATH_SELECTION_ERROR",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "data_family": family,
                }
            if record.points:
                record.qc_status = "PROVISIONAL_UNCALIBRATED"
                record.review_state = "NEEDS_REVIEW"
                results.append(record)
                continue
            if vector_selection and vector_selection.get("status") == "NEEDS_REVIEW":
                results.append(record)
                continue
        elif vector_requested:
            record.metadata = {
                "reason": "VECTOR_PATH_MAPPING_UNAVAILABLE",
                "note": "Vector extraction requires an unrotated PDF page, explicit plot_bbox_pdf, crop geometry, and PDFium native path evidence.",
                "vector_object_indices": vector_indices,
                "plot_bbox_pdf": plot_bbox_pdf,
                "calibration_errors": calibration_errors,
            }
            results.append(record)
            continue
        if isinstance(pixel_points, list) and len(pixel_points) >= 2:
            clean_points = [(float(p[0]), float(p[1])) for p in pixel_points
                            if isinstance(p, (list, tuple)) and len(p) == 2]
            record.points = [
                SeriesPoint(
                    point_index=point_index,
                    x=map_pixel(x_cal, point[0]) if x_cal else None,
                    y=map_pixel(y_cal, point[1]) if y_cal else None,
                    pixel_x=float(point[0]), pixel_y=float(point[1]),
                )
                for point_index, point in enumerate(clean_points)
            ]
            record.extraction_method = "EXPLICIT_ORDERED_PIXEL_POLYLINE"
            record.extraction_status = (
                "EXTRACTED_PROVISIONAL" if x_cal and y_cal and len(record.points) >= 2
                else "GEOMETRY_ONLY_NEEDS_REVIEW"
            )
            record.metadata = {"path_order": "PRESERVED", "data_family": family,
                               "chart_family_classification": classification,
                               "plot_detection": plot_detection, "color_detection": color_detection,
                               "axis_text_evidence": axis_text_evidence,
                               "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                               "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                               "calibration_errors": calibration_errors}
        elif image_path and color_rgb and family not in {"CV", "EIS", "NON_MONOTONIC", "NON_MONOTONIC_CURVE"}:
            record.points, qc = trace_monotonic_color(
                str(image_path), tuple(int(v) for v in color_rgb),
                int(definition.get("color_tolerance", color_detection.get("color_tolerance", 24) if color_detection else 24)),
                x_cal, y_cal, plot_box=plot_box_pixels,
            )
            record.extraction_method = qc.get("method", "RASTER_COLOR")
            record.extraction_status = (
                "EXTRACTED_PROVISIONAL" if record.points and x_cal and y_cal
                else "GEOMETRY_ONLY_NEEDS_REVIEW" if record.points else "NEEDS_REVIEW"
            )
            record.metadata = {"x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                               "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                               "calibration_errors": calibration_errors,
                               "raster_qc": qc, "axis_text_evidence": axis_text_evidence,
                               "plot_detection": plot_detection, "color_detection": color_detection,
                               "chart_family_classification": classification,
                               "y_signal_mode": "SERIES_RELATIVE_SIGNAL" if relative_signal else "CALIBRATED_NUMERIC"}
        else:
            record.metadata = {
                "reason": "NO_SUPPORTED_TRACE_SPECIFICATION",
                "note": "Provide ordered pixel_points for non-monotonic paths or explicit color and calibrations for monotonic raster traces.",
                "data_family": family,
                "plot_detection": plot_detection,
                "color_detection": color_detection,
                "chart_family_classification": classification,
                "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                "calibration_errors": calibration_errors,
            }
        if record.points:
            record.qc_status = "PROVISIONAL_UNCALIBRATED"
            record.review_state = "NEEDS_REVIEW"
        results.append(record)
    return results


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for directory, _, filenames in __import__("os").walk(path):
        for name in filenames:
            try:
                total += (Path(directory) / name).stat().st_size
            except OSError:
                continue
    return total


def _within_evidence_budget(paper_output: Path, budget_mb: int) -> bool:
    return budget_mb <= 0 or _directory_size(paper_output / "evidence") < budget_mb * 1024 * 1024


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
    overrides = _load_overrides(paper_dir, output_root, snapshot.paper_id)
    threshold_path = Path(options["qc_thresholds"]) if options.get("qc_thresholds") else None
    thresholds = load_thresholds(threshold_path)
    stage_fingerprint = sha256_json({
        "input_fingerprint": snapshot.input_fingerprint,
        "algorithm_version": ALGORITHM_VERSION,
        "overrides": overrides,
        "profile_config_fingerprint": profile_registry_fingerprint(),
        "qc_thresholds": thresholds,
    })
    if existing.is_file():
        old = _json_file(existing)
        accepted = any(s.get("review_state") == "REVIEWED_ACCEPTED" for s in old.get("series", []))
        unchanged = (old.get("input_fingerprint") == snapshot.input_fingerprint
                     and old.get("algorithm_version") == ALGORITHM_VERSION
                     and old.get("stage_fingerprint") == stage_fingerprint)
        if unchanged and not force_reviewed:
            cached = _cached_result(paper_output, snapshot, expected_stage_fingerprint=stage_fingerprint)
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
        evidence_dir = paper_output / "evidence"
        if evidence_dir.exists():
            shutil.copytree(evidence_dir, version_dir / "evidence", dirs_exist_ok=True)
            shutil.rmtree(evidence_dir)
    elif not existing.is_file():
        # A previous worker may have died after streaming panel CSVs but before
        # committing digitization.json. Such partial rows are not resumable truth.
        for partial_name in ("series", "evidence"):
            partial_path = paper_output / partial_name
            if partial_path.exists():
                shutil.rmtree(partial_path)

    memory_limit_mb = int(options.get("memory_limit_mb", 2048))
    render_scale = float(options.get("render_scale", 1.5))
    max_render_pixels = int(options.get("max_render_pixels", 12_000_000))
    temp_disk_limit_mb = int(options.get("temp_disk_limit_mb", 2048))
    _check_memory_budget(memory_limit_mb)
    context = PaperContextIndex.build(
        paper_dir, paper_output / "context",
        memory_budget_bytes=int(options.get("context_memory_budget", 500_000)),
    )
    figures_raw, inventory_path = _inventory(paper_dir, snapshot)
    pdf_path = None
    pdf_sha256 = None
    for artifact in snapshot.artifacts:
        if artifact.role == "main_pdf":
            candidate = input_root / artifact.path
            if candidate.is_file():
                pdf_path = candidate
                pdf_sha256 = artifact.sha256
                break

    figures: list[dict] = []
    panels: list[dict] = []
    series: list[SeriesRecord] = []
    review_needed = False
    backend = None
    native_evidence_by_page: dict[int, dict] = {}
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
        if pdf_path and figure["page"]:
            page_number_int = int(figure["page"])
            if page_number_int not in native_evidence_by_page:
                try:
                    if backend is None:
                        backend = PdfiumBackend()
                    with backend.open(pdf_path) as doc:
                        with doc.page(page_number_int) as native_page:
                            native_payload = native_page.inspect_native_objects(
                                max_objects=5000, max_total_path_segments=12000,
                                max_segments_per_path=1500,
                            )
                    native_path = paper_output / "evidence" / f"page_{page_number_int:04d}_native.json"
                    if _within_evidence_budget(paper_output, temp_disk_limit_mb):
                        atomic_write_json(native_path, native_payload)
                        native_artifact = native_path.relative_to(paper_output).as_posix()
                        native_hash = sha256_file(native_path)
                    else:
                        native_artifact = None
                        native_hash = None
                    native_evidence_by_page[page_number_int] = {
                        "artifact": native_artifact,
                        "sha256": native_hash,
                        "status": "STORED" if native_artifact else "EVIDENCE_DISK_BUDGET_EXCEEDED",
                        "object_inventory_status": native_payload.get("object_inventory_status"),
                        "object_count": native_payload.get("object_count"),
                        "object_type_counts": native_payload.get("object_type_counts", {}),
                        "path_segment_count": native_payload.get("path_segment_count", 0),
                        "native_text_preview": native_payload.get("native_text", "")[:3000],
                    }
                except Exception as exc:
                    native_evidence_by_page[page_number_int] = {
                        "status": "NATIVE_EVIDENCE_UNAVAILABLE",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
        for panel_index, source_panel in enumerate(_figure_panels(source_figure), 1):
            panel = dict(source_panel)
            panel_id = safe_id(str(panel.get("panel_id") or panel.get("id") or panel.get("label") or panel_index))
            panel["panel_id"] = panel_id
            bbox = panel.get("bbox") or panel.get("bounding_box") or source_figure.get("bbox")
            panel_specific_image = bool(panel.get("image_path"))
            panel_path = _safe_local_file(paper_dir, panel.get("image_path") or source_figure.get("image_path"))
            saved_crop = None
            crop_mapping = None
            if panel_path and not panel_specific_image and bbox:
                if _within_evidence_budget(paper_output, temp_disk_limit_mb):
                    saved_crop = _crop_local_image(
                        panel_path, bbox, paper_output / "evidence" / f"{figure_id}_{panel_id}.png")
            elif panel_path:
                saved_crop = panel_path
            if saved_crop is None and pdf_path and figure["page"] and _within_evidence_budget(
                paper_output, temp_disk_limit_mb):
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
                                crop_mapping = {
                                    "crop_left_pdf": coords[0] / safe_scale,
                                    "crop_top_pdf": page_height - coords[1] / safe_scale,
                                    "crop_right_pdf": coords[2] / safe_scale,
                                    "crop_bottom_pdf": page_height - coords[3] / safe_scale,
                                    "render_scale": safe_scale,
                                    "page_width_pdf": page_width,
                                    "page_height_pdf": page_height,
                                    "page_rotation_degrees": pdf_page.rotation_degrees,
                                }
                        finally:
                            rendered.close()
            _check_memory_budget(memory_limit_mb)
            ocr_evidence = []
            if options.get("ocr") and saved_crop:
                from .ocr import run_ocr
                ocr_evidence = run_ocr(saved_crop)
            native_summary = native_evidence_by_page.get(int(figure["page"])) if figure["page"] else None
            native_file_path = (
                paper_output / native_summary["artifact"]
                if native_summary and native_summary.get("artifact") else None
            )
            extracted = _extract_panel(
                saved_crop, snapshot.paper_id, figure_id, panel_id, panel, figure,
                overrides, context, figure["page"],
                native_summary, ocr_evidence, pdf_sha256, snapshot.input_fingerprint,
                native_file_path, crop_mapping,
            )
            append_panel_series_csv(paper_output, figure_id, panel_id, extracted)
            has_points = any(item.points for item in extracted)
            needs_series_review = any(
                item.review_state != "REVIEWED_ACCEPTED" for item in extracted
            )
            panel_status = (
                "EXTRACTED_NEEDS_REVIEW" if has_points and needs_series_review
                else "EXTRACTED" if has_points
                else "NEEDS_REVIEW"
            )
            for item in extracted:
                item.evidence[0]["extraction_channel"] = item.extraction_method
                item.metadata.setdefault("qc_components", {
                    "panel_segmentation": "INVENTORIED_UNVALIDATED",
                    "chart_family": item.metadata.get("chart_family_classification", {}).get("status", "UNCLASSIFIED"),
                    "axis_calibration": "CALIBRATED" if (
                        item.metadata.get("x_calibration") or item.metadata.get("y_calibration")
                    ) else "UNRESOLVED",
                    "series_extraction": item.extraction_status,
                    "subject_link": "ASSIGNED_WITH_EVIDENCE" if any(
                        link.get("status") == "ASSIGNED_WITH_EVIDENCE" for link in item.subject_links
                    ) else "UNASSIGNED",
                    "condition_interpretation": "EVIDENCE_ATTACHED" if item.conditions else "UNKNOWN",
                    "unit_interpretation": "RAW_UNIT_RETAINED" if item.x_unit or item.y_unit else "UNKNOWN",
                })
            # Keep only compact per-series metadata in the paper worker; point batches are already persisted.
            for item in extracted:
                item.metadata.setdefault("points_count", len(item.points))
                item.points.clear()
            series.extend(extracted)
            review_needed = review_needed or panel_status in {"NEEDS_REVIEW", "EXTRACTED_NEEDS_REVIEW"}
            panels.append({
                "figure_id": figure_id, "panel_id": panel_id,
                "bbox": bbox, "normalized_bbox": bbox if isinstance(bbox, (list, tuple)) and
                    all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in bbox) else None,
                "status": panel_status,
                "segmentation_confidence": None,
                "segmentation_confidence_status": "NOT_CALIBRATED",
                "chart_family": (
                    extracted[0].metadata.get("chart_family_classification", {}).get("chart_family", "UNCLASSIFIED")
                    if extracted else "UNCLASSIFIED"
                ),
                "chart_family_status": (
                    extracted[0].metadata.get("chart_family_classification", {}).get("status", "NEEDS_REVIEW")
                    if extracted else "NEEDS_REVIEW"
                ),
                "shared_legend_refs": figure["shared_legends"],
            })

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
               "native_page_evidence": native_evidence_by_page,
               "stage_fingerprint": stage_fingerprint,
               "memory_limit_mb": memory_limit_mb, "render_scale": render_scale,
               "temp_disk_limit_mb": temp_disk_limit_mb,
               "evidence_bytes": _directory_size(paper_output / "evidence"),
               "qc_threshold_status": thresholds["status"],
               "qc_thresholds": thresholds,
               "llm_tokens": 0},
    )
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
