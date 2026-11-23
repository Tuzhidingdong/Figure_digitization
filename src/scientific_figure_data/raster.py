from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .calibration import map_pixel
from .models import AxisCalibration, SeriesPoint


def detect_monotonic_color_branches(
    image_path: str,
    rgb: tuple[int, int, int],
    tolerance: int,
    *,
    plot_box: tuple[float, float, float, float],
    color_match: dict | None = None,
    min_column_support: float = 0.65,
    max_branches: int = 4,
) -> dict:
    """Detect persistent vertically separated same-color X-monotonic branches.

    The central plot width is used so a legend at the left edge cannot create
    a false extra branch. This inventories candidate bands only; each branch
    still goes through independent continuity and calibration checks.
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Raster branch detection requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        image = np.asarray(source.convert("RGB"), dtype=np.uint8)
    height, width = image.shape[:2]
    bx0, by0, bx1, by1 = [float(value) for value in plot_box]
    if max(abs(bx0), abs(by0), abs(bx1), abs(by1)) <= 1.01:
        bx0, bx1 = bx0 * width, bx1 * width
        by0, by1 = by0 * height, by1 * height
    x0, y0 = max(0, int(bx0)), max(0, int(by0))
    x1, y1 = min(width, int(bx1)), min(height, int(by1))
    if x1 <= x0 or y1 <= y0:
        return {"status": "INVALID_PLOT_BOX", "branches": [], "plot_box": [x0, y0, x1, y1]}

    if isinstance(color_match, dict) and color_match.get("space") == "HSV_HUE_FAMILY":
        from .plot_region import _rgb_to_hsv_arrays
        hues, saturations, values = _rgb_to_hsv_arrays(image.reshape(-1, 3))
        hue_center = float(color_match.get("hue_center_degrees", 0.0))
        hue_tolerance = float(color_match.get("hue_tolerance_degrees", 12.0))
        minimum_saturation = float(color_match.get("minimum_saturation", 0.14))
        minimum_value = float(color_match.get("minimum_value", 0.20))
        distance = np.abs((hues - hue_center + 180.0) % 360.0 - 180.0)
        mask = (
            (distance <= hue_tolerance)
            & (saturations >= minimum_saturation)
            & (values >= minimum_value)
        ).reshape(height, width)
    else:
        target = np.asarray(rgb, dtype=np.int16)
        mask = np.max(
            np.abs(image.astype(np.int16) - target), axis=2
        ) <= int(tolerance)

    # Ignore legend samples and frame-edge artifacts when estimating the
    # persistent number of data branches.
    x_start = x0 + max(1, int(round((x1 - x0) * 0.12)))
    x_stop = x1 - max(1, int(round((x1 - x0) * 0.12)))
    branch_counts: list[int] = []
    centers_by_count: dict[int, list[list[float]]] = {}
    for x in range(x_start, x_stop):
        ys = np.flatnonzero(mask[y0:y1, x]) + y0
        if len(ys) < 2:
            continue
        clusters: list[list[int]] = []
        current = [int(ys[0])]
        for y_value in ys[1:]:
            value = int(y_value)
            if value - current[-1] <= 3:
                current.append(value)
            else:
                clusters.append(current)
                current = [value]
        clusters.append(current)
        substantial = [cluster for cluster in clusters if len(cluster) >= 2]
        if not substantial:
            continue
        count = min(len(substantial), max_branches + 1)
        branch_counts.append(count)
        if count <= max_branches:
            centers_by_count.setdefault(count, []).append(
                [float(np.mean(cluster)) for cluster in substantial]
            )

    if len(branch_counts) < 20:
        return {
            "status": "INSUFFICIENT_BRANCH_COLUMNS",
            "branches": [],
            "supported_columns": len(branch_counts),
            "plot_box": [x0, y0, x1, y1],
        }
    histogram = {
        count: branch_counts.count(count)
        for count in sorted(set(branch_counts))
    }
    dominant_count = max(histogram, key=lambda count: (histogram[count], -count))
    support = histogram[dominant_count] / len(branch_counts)
    centers = centers_by_count.get(dominant_count, [])
    median_centers = []
    if centers:
        max_rank = min(dominant_count, max_branches)
        for branch_index in range(max_rank):
            values = [
                column[branch_index]
                for column in centers if len(column) > branch_index
            ]
            if values:
                median_centers.append(float(np.median(values)))
    if dominant_count >= 2 and dominant_count <= max_branches and support >= min_column_support:
        return {
            "status": "MULTIPLE_MONOTONIC_COLOR_BRANCHES",
            "branch_count": dominant_count,
            "branch_centers_y": median_centers,
            "supported_columns": len(branch_counts),
            "dominant_count_columns": histogram[dominant_count],
            "support_fraction": round(support, 4),
            "branch_count_histogram": histogram,
            "plot_box": [x0, y0, x1, y1],
            "provisional": True,
        }
    if dominant_count == 1:
        return {
            "status": "SINGLE_MONOTONIC_COLOR_BAND",
            "branch_count": 1,
            "supported_columns": len(branch_counts),
            "support_fraction": round(support, 4),
            "branch_count_histogram": histogram,
            "plot_box": [x0, y0, x1, y1],
            "provisional": True,
        }
    return {
        "status": "AMBIGUOUS_COLOR_BAND_COUNT",
        "branch_count": dominant_count,
        "supported_columns": len(branch_counts),
        "support_fraction": round(support, 4),
        "branch_count_histogram": histogram,
        "plot_box": [x0, y0, x1, y1],
        "provisional": True,
    }


def trace_monotonic_color(
    image_path: str,
    rgb: tuple[int, int, int],
    tolerance: int,
    x_calibration: AxisCalibration | None,
    y_calibration: AxisCalibration | None,
    *,
    min_pixels_per_column: int = 1,
    max_gap_columns: int = 3,
    plot_box: tuple[float, float, float, float] | None = None,
    color_match: dict | None = None,
    branch_index: int | None = None,
    branch_count: int | None = None,
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
    if isinstance(color_match, dict) and color_match.get("space") == "HSV_HUE_FAMILY":
        from .plot_region import _rgb_to_hsv_arrays

        height, width = image.shape[:2]
        flat = image.reshape(-1, 3)
        hues, saturations, values = _rgb_to_hsv_arrays(flat)
        hue_center = float(color_match.get("hue_center_degrees", 0.0))
        hue_tolerance = float(color_match.get("hue_tolerance_degrees", 12.0))
        minimum_saturation = float(color_match.get("minimum_saturation", 0.14))
        minimum_value = float(color_match.get("minimum_value", 0.20))
        hue_distance = np.abs((hues - hue_center + 180.0) % 360.0 - 180.0)
        mask = (
            (hue_distance <= hue_tolerance)
            & (saturations >= minimum_saturation)
            & (values >= minimum_value)
        ).reshape(height, width)
    else:
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

    # A color-coded Y-axis spine can share the curve hue. It must not be
    # interpreted as a second, vertically separated data branch at the first
    # or last X column. Remove only boundary columns with strong long-run
    # vertical evidence; ordinary curve endpoints/ticks do not meet this test.
    edge_axis_columns_removed = []
    if plot_box is not None:
        edge_width = min(4, max(2, int(round((x1 - x0) * 0.012))))
        edge_columns = (
            list(range(x0, min(x1, x0 + edge_width)))
            + list(range(max(x0, x1 - edge_width), x1))
        )
        for x in sorted(set(edge_columns)):
            present_rows = np.flatnonzero(mask[y0:y1, x])
            if len(present_rows) < max(8, int(round((y1 - y0) * 0.15))):
                continue
            longest_run = 0
            current_run = 0
            previous_row = None
            for row in present_rows:
                row = int(row)
                if previous_row is None or row - previous_row > 3:
                    current_run = 1
                else:
                    current_run += row - previous_row
                longest_run = max(longest_run, current_run)
                previous_row = row
            if longest_run / max(1, y1 - y0) >= 0.25:
                mask[y0:y1, x] = False
                edge_axis_columns_removed.append(int(x))

    columns: list[tuple[int, float, int]] = []
    for x in range(x0, x1):
        ys = np.flatnonzero(mask[y0:y1, x]) + y0
        if branch_index is None:
            if len(ys) >= min_pixels_per_column:
                columns.append((x, float(np.median(ys)), len(ys)))
            continue
        clusters: list[list[int]] = []
        if len(ys):
            current = [int(ys[0])]
            for y_value in ys[1:]:
                value = int(y_value)
                if value - current[-1] <= 3:
                    current.append(value)
                else:
                    clusters.append(current)
                    current = [value]
            clusters.append(current)
        substantial = [cluster for cluster in clusters if len(cluster) >= 2]
        if 0 <= branch_index < len(substantial):
            selected = substantial[branch_index]
            columns.append((x, float(np.median(selected)), len(selected)))
    if len(columns) < 8:
        return [], {"status": "NEEDS_REVIEW", "reason": "INSUFFICIENT_TRACE_PIXELS",
                    "matched_columns": len(columns),
                    "edge_axis_columns_removed": edge_axis_columns_removed}
    gaps = [b[0] - a[0] - 1 for a, b in zip(columns, columns[1:])]
    max_gap = max(gaps, default=0)
    if max_gap > max_gap_columns:
        return [], {"status": "NEEDS_REVIEW", "reason": "DISCONTINUOUS_OR_DASHED_TRACE",
                    "matched_columns": len(columns), "max_gap_columns": max_gap}
    # Detect multiple vertically separated bands in a column. Same-color traces
    # must not be collapsed to a median when two branches/curves occupy one X column.
    for x in range(x0, x1):
        if branch_index is not None:
            continue
        ys = np.flatnonzero(mask[y0:y1, x]) + y0
        if len(ys) < 4:
            continue
        clusters = []
        current = [int(ys[0])]
        for y_value in ys[1:]:
            y_integer = int(y_value)
            if y_integer - current[-1] <= 3:
                current.append(y_integer)
            else:
                clusters.append(current)
                current = [y_integer]
        clusters.append(current)
        substantial = [cluster for cluster in clusters if len(cluster) >= 2]
        if len(substantial) >= 2:
            return [], {
                "status": "NEEDS_REVIEW",
                "reason": "MULTIPLE_SAME_COLOR_BANDS",
                "ambiguous_column": x,
                "band_centers": [float(np.mean(cluster)) for cluster in substantial],
            }
        if len(ys) > 12 and (int(ys.max()) - int(ys.min())) > 10:
            return [], {
                "status": "NEEDS_REVIEW",
                "reason": "THICK_OR_AMBIGUOUS_TRACE",
                "ambiguous_column": x,
                "matched_pixel_count": int(len(ys)),
                "vertical_span_pixels": int(ys.max() - ys.min()),
                "cluster_count": len(clusters),
                "band_centers": [
                    float(np.mean(cluster)) for cluster in substantial
                ],
            }
    points = []
    for index, (x, py, _) in enumerate(columns):
        points.append(SeriesPoint(
            point_index=index,
            x=map_pixel(x_calibration, x) if x_calibration else None,
            y=map_pixel(y_calibration, py) if y_calibration else None,
            pixel_x=float(x), pixel_y=float(py),
        ))
    return points, {
        "status": "EXTRACTED_PROVISIONAL",
        "method": "raster_color_column_median",
        "matched_columns": len(columns),
        "matched_pixel_fraction": len(columns) / max(1, x1 - x0),
        "plot_box": [x0, y0, x1, y1],
        "edge_axis_columns_removed": edge_axis_columns_removed,
        "branch_index": branch_index,
        "branch_count": branch_count,
        "max_gap_columns": max_gap,
        "path_constraint": "X_MONOTONIC_ONLY",
        "qc_status": "PROVISIONAL_UNCALIBRATED",
        "geometry_only": x_calibration is None or y_calibration is None,
        "numeric_mapping_status": (
            "CALIBRATED_NUMERIC" if x_calibration is not None and y_calibration is not None
            else "PARTIALLY_CALIBRATED" if x_calibration is not None or y_calibration is not None
            else "PIXEL_GEOMETRY_ONLY"
        ),
        "color_matching_space": (
            color_match.get("space") if isinstance(color_match, dict) else "RGB_DISTANCE"
        ),
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
