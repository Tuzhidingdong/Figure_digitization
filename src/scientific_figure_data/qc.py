from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

PROVISIONAL = {
    "schema_version": "1.0",
    "status": "PROVISIONAL_UNCALIBRATED",
    "notes": "Engineering defaults only; not calibrated against annotated real papers.",
    "minimum_calibration_anchors": 2,
    "maximum_axis_anchor_rmse": None,
    "minimum_trace_points": 8,
    "minimum_trace_pixel_fraction": 0.15,
    "allow_automatic_same_color_crossing": False,
    "allow_automatic_marker_disambiguation": False,
}


def _validate_calibrated_thresholds(config: dict) -> None:
    benchmark = config.get("benchmark")
    thresholds = config.get("thresholds")
    if not isinstance(benchmark, dict) or not isinstance(thresholds, dict):
        raise ValueError("CALIBRATED QC thresholds require benchmark and thresholds mappings")

    required_benchmark = (
        "dataset_manifest", "annotation_manifest", "paper_count", "figure_count",
        "calibrated_at", "calibration_method", "algorithm_version", "profile_version",
    )
    missing = [
        key for key in required_benchmark
        if benchmark.get(key) in (None, "", 0)
    ]
    if missing:
        raise ValueError(
            "CALIBRATED QC thresholds lack benchmark provenance: " + ", ".join(missing)
        )
    for key in ("paper_count", "figure_count"):
        if not isinstance(benchmark.get(key), int) or benchmark[key] < 1:
            raise ValueError(f"CALIBRATED benchmark {key} must be a positive integer")

    numeric_bounds = {
        "maximum_axis_anchor_rmse": (0.0, None),
        "minimum_trace_points": (2.0, None),
        "minimum_trace_pixel_fraction": (0.0, 1.0),
        "maximum_overlay_distance": (0.0, None),
        "minimum_curve_coverage": (0.0, 1.0),
    }
    for key, (minimum, maximum) in numeric_bounds.items():
        value = thresholds.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"CALIBRATED threshold {key} must be a finite number")
        if value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"CALIBRATED threshold {key} is outside its permitted range")

    for key in ("additional_domain_rules",):
        value = thresholds.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"CALIBRATED threshold {key} must be a mapping")


def load_thresholds(path: Path | None = None) -> dict:
    if not path or not path.is_file():
        return dict(PROVISIONAL)
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            config = json.load(handle)
        else:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("PyYAML is required to read YAML QC thresholds") from exc
            config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("QC threshold file must contain a mapping")
    status = config.get("status")
    if status not in {"PROVISIONAL_UNCALIBRATED", "CALIBRATED"}:
        raise ValueError("QC thresholds must explicitly declare PROVISIONAL_UNCALIBRATED or CALIBRATED")
    if status == "CALIBRATED":
        _validate_calibrated_thresholds(config)
    return config


def write_provisional_thresholds(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "schema_version: '1.0'",
        "status: PROVISIONAL_UNCALIBRATED",
        "notes: Engineering defaults only; not calibrated against annotated real papers.",
        "minimum_calibration_anchors: 2",
        "minimum_trace_points: 8",
        "minimum_trace_pixel_fraction: 0.15",
        "allow_automatic_same_color_crossing: false",
        "allow_automatic_marker_disambiguation: false",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _axis_report(calibration: Any, axis: str, minimum_anchors: int) -> dict:
    if not isinstance(calibration, dict):
        return {
            "status": "UNRESOLVED",
            "anchor_count": 0,
            "rmse": None,
            "unit": None,
        }
    anchors = calibration.get("anchors") or []
    rmse = _number(calibration.get("rmse"))
    state = calibration.get("status") or "CALIBRATION_PRESENT"
    if state == "SERIES_RELATIVE_SIGNAL":
        status = "RELATIVE_SIGNAL"
    elif len(anchors) >= minimum_anchors and rmse is not None:
        status = "CALIBRATION_EVIDENCE_PRESENT"
    else:
        status = "INSUFFICIENT_CALIBRATION_EVIDENCE"
    return {
        "status": status,
        "anchor_count": len(anchors),
        "rmse": rmse,
        "unit": calibration.get("unit"),
        "calibration_status": state,
    }


def build_series_qc_report(series: Any, panel: dict | None = None,
                           thresholds: dict | None = None) -> dict:
    """Build separate, evidence-backed QC dimensions without an aggregate score.

    This report describes observable engineering evidence only. Provisional thresholds
    are never promoted to scientific acceptance criteria without a real-paper benchmark.
    """
    panel = panel or {}
    thresholds = thresholds or PROVISIONAL
    metadata = getattr(series, "metadata", {}) or {}
    points = list(getattr(series, "points", []) or [])
    minimum_anchors = int(thresholds.get("minimum_calibration_anchors", 2))
    minimum_points = int(thresholds.get("minimum_trace_points", 8))
    minimum_fraction = float(thresholds.get("minimum_trace_pixel_fraction", 0.15))

    x_calibration = metadata.get("x_calibration") or metadata.get("x_axis_calibration")
    y_calibration = metadata.get("y_calibration") or metadata.get("y_axis_calibration")
    x_axis = _axis_report(x_calibration, "x", minimum_anchors)
    y_axis = _axis_report(y_calibration, "y", minimum_anchors)

    axis_text = metadata.get("axis_text_evidence") or {}
    axis_text_sources = [
        source for source in ("native", "ocr")
        if isinstance(axis_text.get(source), dict)
    ]
    axis_detection = (
        "EVIDENCE_ATTACHED" if axis_text_sources
        else "EXPLICIT_OVERRIDE_OR_UNRESOLVED"
    )

    pixel_points = [
        point for point in points
        if _number(getattr(point, "pixel_x", None)) is not None
        and _number(getattr(point, "pixel_y", None)) is not None
    ]
    point_count = len(points)
    pixel_count = len(pixel_points)
    x_pixels = [_number(getattr(point, "pixel_x", None)) for point in pixel_points]
    y_pixels = [_number(getattr(point, "pixel_y", None)) for point in pixel_points]
    x_pixels = [value for value in x_pixels if value is not None]
    y_pixels = [value for value in y_pixels if value is not None]
    pixel_x_span = max(x_pixels) - min(x_pixels) if x_pixels else None
    pixel_y_span = max(y_pixels) - min(y_pixels) if y_pixels else None

    raster = metadata.get("raster_qc") or {}
    trace_fraction = _number(raster.get("matched_pixel_fraction"))
    matched_columns = _number(raster.get("matched_columns"))
    max_gap = _number(raster.get("max_gap_columns"))
    if trace_fraction is None and pixel_x_span is not None:
        plot_box = raster.get("plot_box") or metadata.get("plot_box_pixels")
        if isinstance(plot_box, (list, tuple)) and len(plot_box) == 4:
            plot_width = _number(plot_box[2])
            left = _number(plot_box[0])
            if plot_width is not None and left is not None and plot_width > left:
                trace_fraction = pixel_x_span / (plot_width - left)

    if trace_fraction is None:
        coverage_status = "NOT_MEASURED"
    elif trace_fraction < minimum_fraction:
        coverage_status = "BELOW_PROVISIONAL_ENGINEERING_FLOOR"
    else:
        coverage_status = "MEASURED_ABOVE_PROVISIONAL_ENGINEERING_FLOOR"

    if max_gap is None:
        continuity_status = "NOT_MEASURED"
    else:
        continuity_status = "MEASURED"

    point_index_valid = all(
        _number(getattr(point, "point_index", None)) == index
        for index, point in enumerate(points)
    )
    numeric_x = [_number(getattr(point, "x", None)) for point in points]
    numeric_x = [value for value in numeric_x if value is not None]
    direction_changes = 0
    previous_direction = 0
    for left, right in zip(numeric_x, numeric_x[1:]):
        delta = right - left
        direction = 1 if delta > 0 else -1 if delta < 0 else 0
        if direction and previous_direction and direction != previous_direction:
            direction_changes += 1
        if direction:
            previous_direction = direction

    data_family = metadata.get("data_family") or metadata.get("chart_family")
    path_constraint = (
        "ORDERED_NON_MONOTONIC_ALLOWED" if str(data_family).upper() in {
            "CV", "EIS", "NON_MONOTONIC", "NON_MONOTONIC_CURVE"
        } else metadata.get("y_signal_mode") or metadata.get("path_constraint") or "UNRESOLVED"
    )

    legend_refs = panel.get("shared_legend_refs") or panel.get("legend_refs") or []
    subject_links = getattr(series, "subject_links", []) or []
    conditions = getattr(series, "conditions", []) or []
    evidenced_subjects = [
        item for item in subject_links if item.get("status") == "ASSIGNED_WITH_EVIDENCE"
    ]
    has_unit = bool(getattr(series, "x_unit", None) or getattr(series, "y_unit", None))
    metadata_text = json.dumps(metadata, ensure_ascii=False)
    reference_status = (
        "UNRESOLVED" if "REFERENCE_CONVERSION_UNRESOLVED" in metadata_text
        else "NO_CONVERSION_CLAIMED"
    )

    components = {
        "panel_segmentation": (
            "BOUNDARY_EVIDENCE_PRESENT" if panel.get("bbox") is not None else "UNKNOWN"
        ),
        "chart_family": (
            metadata.get("chart_family_classification", {}).get("status", "UNKNOWN")
            if isinstance(metadata.get("chart_family_classification"), dict) else "UNKNOWN"
        ),
        "axis_detection": axis_detection,
        "axis_calibration_x": x_axis["status"],
        "axis_calibration_y": y_axis["status"],
        "series_extraction": getattr(series, "extraction_status", "UNKNOWN"),
        "point_reconstruction": (
            "PIXEL_GEOMETRY_PRESENT" if pixel_count == point_count and point_count
            else "PARTIAL_PIXEL_GEOMETRY" if pixel_count
            else "NO_PIXEL_GEOMETRY"
        ),
        "legend_association": "EVIDENCE_ATTACHED" if legend_refs else "UNKNOWN",
        "subject_link": "ASSIGNED_WITH_EVIDENCE" if evidenced_subjects else "UNASSIGNED",
        "condition_interpretation": "EVIDENCE_ATTACHED" if conditions else "UNKNOWN",
        "unit_interpretation": "RAW_UNIT_RETAINED" if has_unit else "UNKNOWN",
        "reference_scale_conversion": reference_status,
    }

    warnings = []
    if point_count < minimum_points:
        warnings.append("TRACE_POINT_COUNT_BELOW_PROVISIONAL_ENGINEERING_FLOOR")
    if coverage_status == "BELOW_PROVISIONAL_ENGINEERING_FLOOR":
        warnings.append("TRACE_PIXEL_COVERAGE_BELOW_PROVISIONAL_ENGINEERING_FLOOR")
    if pixel_count < point_count:
        warnings.append("PIXEL_COORDINATES_INCOMPLETE")
    if not point_index_valid:
        warnings.append("POINT_ORDER_INDEX_INCONSISTENT")
    if getattr(series, "y_axis_side", "UNASSIGNED") == "UNASSIGNED":
        warnings.append("DUAL_AXIS_UNASSIGNED")
    if not evidenced_subjects:
        warnings.append("SUBJECT_LINK_UNASSIGNED")
    if not conditions:
        warnings.append("CONDITIONS_NOT_LINKED")
    if reference_status == "UNRESOLVED":
        warnings.append("REFERENCE_CONVERSION_UNRESOLVED")

    return {
        "schema_version": "1.0",
        "status": "PROVISIONAL_UNCALIBRATED",
        "assessment_mode": "INDEPENDENT_DIMENSIONS_NO_AGGREGATE_SCORE",
        "components": components,
        "axes": {"x": x_axis, "y": y_axis},
        "trace_metrics": {
            "point_count": point_count,
            "pixel_coordinate_count": pixel_count,
            "pixel_coordinate_fraction": pixel_count / point_count if point_count else 0.0,
            "pixel_x_span": pixel_x_span,
            "pixel_y_span": pixel_y_span,
            "matched_columns": matched_columns,
            "matched_pixel_fraction": trace_fraction,
            "coverage_status": coverage_status,
            "max_gap_columns": max_gap,
            "continuity_status": continuity_status,
            "point_index_valid": point_index_valid,
            "x_direction_changes": direction_changes,
            "path_constraint": path_constraint,
        },
        "threshold_source": thresholds.get("status", "PROVISIONAL_UNCALIBRATED"),
        "warnings": warnings,
        "aggregate_score": None,
        "scientific_acceptance": "NOT_ASSESSED_WITHOUT_ANNOTATED_REAL_PAPER_BENCHMARK",
    }
