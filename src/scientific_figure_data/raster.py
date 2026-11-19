from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .calibration import map_pixel
from .models import AxisCalibration, SeriesPoint


def trace_monotonic_color(
    image_path: str,
    rgb: tuple[int, int, int],
    tolerance: int,
    x_calibration: AxisCalibration,
    y_calibration: AxisCalibration,
    *,
    min_pixels_per_column: int = 1,
    max_gap_columns: int = 3,
    plot_box: tuple[float, float, float, float] | None = None,
) -> tuple[list[SeriesPoint], dict]:
    """Conservative monotonic raster tracer for one explicitly selected color.

    It uses per-column robust medians and therefore must not be used for CV/EIS,
    loops, or curves that are not single-valued in X.
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError("Raster extraction requires Pillow and NumPy: pip install '.[images]'") from exc

    with Image.open(image_path) as source:
        image = np.asarray(source.convert("RGB"), dtype=np.int16)
    target = np.asarray(rgb, dtype=np.int16)
    mask = np.max(np.abs(image - target), axis=2) <= int(tolerance)
    height, width = mask.shape
    if plot_box is None:
        x0, y0, x1, y1 = 0, 0, width, height
    else:
        bx0, by0, bx1, by1 = [float(v) for v in plot_box]
        if max(abs(bx0), abs(by0), abs(bx1), abs(by1)) <= 1.01:
            bx0, bx1 = bx0 * width, bx1 * width
            by0, by1 = by0 * height, by1 * height
        x0, y0 = max(0, int(bx0)), max(0, int(by0))
        x1, y1 = min(width, int(bx1)), min(height, int(by1))
        if x1 <= x0 or y1 <= y0:
            return [], {"status": "NEEDS_REVIEW", "reason": "INVALID_PLOT_BOX"}
    columns: list[tuple[int, float, int]] = []
    for x in range(x0, x1):
        ys = np.flatnonzero(mask[y0:y1, x]) + y0
        if len(ys) >= min_pixels_per_column:
            columns.append((x, float(np.median(ys)), len(ys)))
    if len(columns) < 8:
        return [], {"status": "NEEDS_REVIEW", "reason": "INSUFFICIENT_TRACE_PIXELS",
                    "matched_columns": len(columns)}
    gaps = [b[0] - a[0] - 1 for a, b in zip(columns, columns[1:])]
    max_gap = max(gaps, default=0)
    if max_gap > max_gap_columns:
        return [], {"status": "NEEDS_REVIEW", "reason": "DISCONTINUOUS_OR_DASHED_TRACE",
                    "matched_columns": len(columns), "max_gap_columns": max_gap}
    # Detect multiple vertically separated bands in a column; their median would be unsafe.
    for x in range(x0, x1):
        ys = np.flatnonzero(mask[y0:y1, x]) + y0
        if len(ys) > 12 and (int(ys.max()) - int(ys.min())) > 10:
            return [], {"status": "NEEDS_REVIEW", "reason": "MULTIPLE_OR_THICK_BANDS",
                        "ambiguous_column": x}
    points = []
    for index, (x, py, _) in enumerate(columns):
        points.append(SeriesPoint(
            point_index=index,
            x=map_pixel(x_calibration, x),
            y=map_pixel(y_calibration, py),
            pixel_x=float(x), pixel_y=float(py),
        ))
    return points, {
        "status": "EXTRACTED_PROVISIONAL",
        "method": "raster_color_column_median",
        "matched_columns": len(columns),
        "matched_pixel_fraction": len(columns) / max(1, x1 - x0),
        "plot_box": [x0, y0, x1, y1],
        "max_gap_columns": max_gap,
        "path_constraint": "X_MONOTONIC_ONLY",
        "qc_status": "PROVISIONAL_UNCALIBRATED",
    }


def map_explicit_polyline(
    points: Iterable[tuple[float, float]],
    x_calibration: AxisCalibration,
    y_calibration: AxisCalibration,
) -> list[SeriesPoint]:
    """Map an explicitly ordered pixel polyline; point order is never sorted."""
    output = []
    for index, (px, py) in enumerate(points):
        output.append(SeriesPoint(index, map_pixel(x_calibration, px),
                                  map_pixel(y_calibration, py), float(px), float(py)))
    return output
