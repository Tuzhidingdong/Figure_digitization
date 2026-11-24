from __future__ import annotations

from pathlib import Path
from typing import Any

from .calibration import calibration_to_dict
from .hashing import sha256_file
from .models import AxisCalibration

NON_MONOTONIC_FAMILIES = {
    "CV", "EIS", "NON_MONOTONIC", "NON_MONOTONIC_CURVE",
}
MONOTONIC_X_TERMS = (
    "time", "second", "minute", "hour", "cycle", "wavelength",
    "wavenumber", "frequency", "2theta", "2 θ", "scan number",
)


def is_supported_monotonic_x_label(value: str | None) -> bool:
    text = " ".join(str(value or "").casefold().replace("−", "-").split())
    if not text:
        return False
    if any(term in text for term in ("potential", "voltage", "current")):
        return False
    return any(term in text for term in MONOTONIC_X_TERMS)


def generate_trace_specification(
    image_path: Path,
    plot_box: tuple[int, int, int, int] | None,
    color_detection: dict[str, Any] | None,
    x_calibration: AxisCalibration | None,
    y_calibration: AxisCalibration | None,
    chart_family: str | None,
    x_axis_label: str | None = None,
    allow_unlabelled_manual_override: bool = False,
    allow_geometry_only: bool = False,
) -> dict[str, Any]:
    """Create a connected-path trace contract from observed image/color/axis evidence.

    Unknown chart families are allowed only when the OCR-derived X-axis label
    explicitly identifies an ordered independent variable. Known non-monotonic
    chart families are never routed through the X-monotonic column tracer.
    """
    family = str(chart_family or "UNCLASSIFIED").upper()
    if family in NON_MONOTONIC_FAMILIES:
        return {
            "status": "NOT_SUPPORTED",
            "reason": "NON_MONOTONIC_PATH_REQUIRES_ORDERED_TRACE_ALGORITHM",
            "chart_family": family,
        }
    if not image_path.is_file():
        return {"status": "NEEDS_REVIEW", "reason": "SOURCE_IMAGE_UNAVAILABLE"}
    if not plot_box or len(plot_box) != 4:
        return {"status": "NEEDS_REVIEW", "reason": "PLOT_REGION_UNRESOLVED"}
    x0, y0, x1, y1 = [int(value) for value in plot_box]
    if x1 <= x0 or y1 <= y0:
        return {"status": "NEEDS_REVIEW", "reason": "INVALID_PLOT_REGION"}
    ordered_label = is_supported_monotonic_x_label(x_axis_label)
    if not ordered_label and family not in {"TIME_SERIES", "SPECTRUM"} and not allow_unlabelled_manual_override:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER",
            "x_axis_label": x_axis_label,
        }
    if not isinstance(color_detection, dict) or color_detection.get("status") != "UNIQUE_CHROMATIC_FAMILY":
        return {
            "status": "NEEDS_REVIEW",
            "reason": "UNIQUE_SINGLE_TRACE_COLOR_NOT_ESTABLISHED",
            "color_detection_status": (
                color_detection.get("status") if isinstance(color_detection, dict) else None
            ),
        }
    x_is_calibrated = (
        isinstance(x_calibration, AxisCalibration)
        and x_calibration.status == "CALIBRATED_NUMERIC"
        and len(x_calibration.anchors) >= 2
    )
    y_is_calibrated = (
        isinstance(y_calibration, AxisCalibration)
        and y_calibration.status == "CALIBRATED_NUMERIC"
        and len(y_calibration.anchors) >= 2
    )
    if x_calibration is not None and not x_is_calibrated:
        return {"status": "NEEDS_REVIEW", "reason": "INVALID_X_AXIS_CALIBRATION"}
    if y_calibration is not None and not y_is_calibrated:
        return {"status": "NEEDS_REVIEW", "reason": "INVALID_Y_AXIS_CALIBRATION"}
    if not (x_is_calibrated and y_is_calibrated) and not allow_geometry_only:
        return {"status": "NEEDS_REVIEW", "reason": "BOTH_NUMERIC_AXIS_CALIBRATIONS_REQUIRED"}
    if not x_is_calibrated and not y_is_calibrated and not allow_geometry_only:
        return {"status": "NEEDS_REVIEW", "reason": "INSUFFICIENT_NUMERIC_AXIS_ANCHORS"}

    color = color_detection.get("color_rgb")
    if not isinstance(color, (list, tuple)) or len(color) != 3:
        return {"status": "NEEDS_REVIEW", "reason": "TRACE_COLOR_MISSING"}
    try:
        rgb = [int(value) for value in color]
    except (TypeError, ValueError, OverflowError):
        return {"status": "NEEDS_REVIEW", "reason": "TRACE_COLOR_INVALID"}
    if any(value < 0 or value > 255 for value in rgb):
        return {"status": "NEEDS_REVIEW", "reason": "TRACE_COLOR_INVALID"}

    return {
        "status": "READY",
        "specification": {
            "schema_version": "1.0",
            "specification_type": "SINGLE_COLOR_CONNECTED_2D_RASTER_PATH",
            "numeric_mapping_status": (
                "CALIBRATED_NUMERIC" if x_is_calibrated and y_is_calibrated
                else "PARTIALLY_CALIBRATED" if x_is_calibrated or y_is_calibrated
                else "PIXEL_GEOMETRY_ONLY"
            ),
            "geometry_only_allowed": bool(allow_geometry_only),
            "source_image_sha256": sha256_file(image_path),
            "plot_box_pixels": [x0, y0, x1, y1],
            "color_rgb": rgb,
            "color_tolerance": int(color_detection.get("color_tolerance", 24)),
            "color_match": color_detection.get("color_match"),
            "x_calibration": calibration_to_dict(x_calibration) if x_calibration else None,
            "y_calibration": calibration_to_dict(y_calibration) if y_calibration else None,
            "chart_family": family,
            "x_axis_label": x_axis_label,
            "path_order": "CONNECTED_2D_PIXEL_PATH_LEFT_TO_RIGHT",
            "generated_from": [
                "AUTOMATIC_PLOT_REGION_CANDIDATE",
                "AUTOMATIC_SINGLE_COLOR_DETECTION",
                *(["AUTOMATIC_X_AXIS_NUMERIC_ANCHORS"] if x_is_calibrated else []),
                *(["AUTOMATIC_Y_AXIS_NUMERIC_ANCHORS"] if y_is_calibrated else []),
                *(
                    ["OCR_X_AXIS_SEMANTICS"] if ordered_label
                    else ["EXPLICIT_MONOTONIC_FAMILY_OR_MANUAL_OVERRIDE"]
                ),
            ],
            "provisional": True,
        },
    }
