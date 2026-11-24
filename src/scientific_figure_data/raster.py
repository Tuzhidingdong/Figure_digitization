from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .calibration import map_pixel
from .models import AxisCalibration, SeriesPoint


def _resolve_plot_box(
    width: int, height: int, plot_box: tuple[float, float, float, float]
) -> tuple[int, int, int, int]:
    bx0, by0, bx1, by1 = [float(value) for value in plot_box]
    if max(abs(bx0), abs(by0), abs(bx1), abs(by1)) <= 1.01:
        bx0, bx1 = bx0 * width, bx1 * width
        by0, by1 = by0 * height, by1 * height
    x0, y0 = max(0, int(bx0)), max(0, int(by0))
    x1, y1 = min(width, int(bx1)), min(height, int(by1))
    return x0, y0, x1, y1


def _build_color_mask(
    region,
    rgb: tuple[int, int, int],
    tolerance: int,
    color_match: dict | None,
):
    import numpy as np

    if isinstance(color_match, dict) and color_match.get("space") == "HSV_HUE_FAMILY":
        from .plot_region import _rgb_to_hsv_arrays

        flat = region.reshape(-1, 3)
        hues, saturations, values = _rgb_to_hsv_arrays(flat)
        hue_center = float(color_match.get("hue_center_degrees", 0.0))
        hue_tolerance = float(color_match.get("hue_tolerance_degrees", 12.0))
        minimum_saturation = float(color_match.get("minimum_saturation", 0.14))
        minimum_value = float(color_match.get("minimum_value", 0.20))
        distance = np.abs((hues - hue_center + 180.0) % 360.0 - 180.0)
        return (
            (distance <= hue_tolerance)
            & (saturations >= minimum_saturation)
            & (values >= minimum_value)
        ).reshape(region.shape[:2])
    target = np.asarray(rgb, dtype=np.int16)
    return np.max(np.abs(region.astype(np.int16) - target), axis=2) <= int(tolerance)


def _find_color_components(
    image_path: str,
    rgb: tuple[int, int, int],
    tolerance: int,
    *,
    plot_box: tuple[float, float, float, float],
    color_match: dict | None = None,
    min_span_fraction: float = 0.02,
    max_color_pixels: int = 400_000,
) -> dict:
    """Find spatially connected trace candidates inside one plot crop.

    Components are kept separate: pixels from two disconnected paths are never
    joined merely because they share a colour. Small annotation dashes and
    isolated legend-like marks are recorded as rejected components.
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError as exc:
        from .errors import OptionalDependencyError

        raise OptionalDependencyError(
            "Raster path tracing requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        width, height = source.size
        x0, y0, x1, y1 = _resolve_plot_box(width, height, plot_box)
        if x1 <= x0 or y1 <= y0:
            return {
                "status": "INVALID_PLOT_BOX",
                "components": [],
                "rejected_components": [],
                "plot_box": [x0, y0, x1, y1],
            }
        region = np.asarray(source.convert("RGB").crop((x0, y0, x1, y1)), dtype=np.uint8)

    mask = _build_color_mask(region, rgb, tolerance, color_match)
    active_count = int(mask.sum())
    if active_count > max_color_pixels:
        return {
            "status": "COLOR_MASK_TOO_DENSE",
            "reason": "CONNECTED_COMPONENT_PIXEL_BUDGET_EXCEEDED",
            "active_pixels": active_count,
            "pixel_budget": max_color_pixels,
            "components": [],
            "rejected_components": [],
            "plot_box": [x0, y0, x1, y1],
        }
    if active_count < 8:
        return {
            "status": "NO_COLOR_PIXELS",
            "active_pixels": active_count,
            "components": [],
            "rejected_components": [],
            "plot_box": [x0, y0, x1, y1],
        }

    height_local, width_local = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    active = np.argwhere(mask)
    min_x_span = max(6, int(round(width_local * min_span_fraction)))
    min_pixels = max(12, int(round(width_local * 0.01)))
    components = []
    rejected = []

    for start_y, start_x in active:
        sy, sx = int(start_y), int(start_x)
        if visited[sy, sx]:
            continue
        visited[sy, sx] = True
        stack = [(sy, sx)]
        pixels = []
        while stack:
            cy, cx = stack.pop()
            pixels.append((cy, cx))
            for dy in (-1, 0, 1):
                ny = cy + dy
                if ny < 0 or ny >= height_local:
                    continue
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx = cx + dx
                    if nx < 0 or nx >= width_local or visited[ny, nx] or not mask[ny, nx]:
                        continue
                    visited[ny, nx] = True
                    stack.append((ny, nx))

        ys = [point[0] for point in pixels]
        xs = [point[1] for point in pixels]
        bbox = [
            min(xs) + x0,
            min(ys) + y0,
            max(xs) + x0 + 1,
            max(ys) + y0 + 1,
        ]
        summary = {
            "pixel_count": len(pixels),
            "bbox": bbox,
            "x_span": max(xs) - min(xs) + 1,
            "y_span": max(ys) - min(ys) + 1,
        }
        if len(pixels) < min_pixels:
            summary["rejection_reason"] = "COMPONENT_TOO_SMALL"
            rejected.append(summary)
            continue
        if summary["x_span"] < min_x_span:
            summary["rejection_reason"] = "COMPONENT_X_SPAN_TOO_SHORT"
            rejected.append(summary)
            continue
        components.append({
            **summary,
            "coords": np.asarray(pixels, dtype=np.int32),
        })

    components.sort(key=lambda item: (
        item["bbox"][0], item["bbox"][1], -item["pixel_count"]
    ))
    return {
        "status": "CONNECTED_COMPONENTS_FOUND" if components else "NO_TRACE_COMPONENTS",
        "active_pixels": active_count,
        "component_count": len(components),
        "components": components,
        "rejected_components": rejected,
        "min_component_pixels": min_pixels,
        "min_component_x_span": min_x_span,
        "plot_box": [x0, y0, x1, y1],
        "connectivity": 8,
    }


def _thin_binary_component(mask, *, max_iterations: int = 64):
    """Zhang-Suen thinning using NumPy only; preserve the original 8-connected path."""
    import numpy as np

    work = np.pad(mask.astype(bool), 1, mode="constant")
    iterations = 0
    changed = True
    while changed and iterations < max_iterations:
        changed = False
        iterations += 1
        for phase in (0, 1):
            p2 = work[:-2, 1:-1]
            p3 = work[:-2, 2:]
            p4 = work[1:-1, 2:]
            p5 = work[2:, 2:]
            p6 = work[2:, 1:-1]
            p7 = work[2:, :-2]
            p8 = work[1:-1, :-2]
            p9 = work[:-2, :-2]
            neighbours = (p2, p3, p4, p5, p6, p7, p8, p9)
            count = sum(item.astype(np.uint8) for item in neighbours)
            transitions = np.zeros(count.shape, dtype=np.uint8)
            for first, second in zip(neighbours, neighbours[1:] + neighbours[:1]):
                transitions += (~first & second).astype(np.uint8)
            remove = (
                work[1:-1, 1:-1]
                & (count >= 2)
                & (count <= 6)
                & (transitions == 1)
            )
            if phase == 0:
                remove &= ~(p2 & p4 & p6)
                remove &= ~(p4 & p6 & p8)
            else:
                remove &= ~(p2 & p4 & p8)
                remove &= ~(p2 & p6 & p8)
            if np.any(remove):
                work[1:-1, 1:-1][remove] = False
                changed = True
    return work[1:-1, 1:-1], {
        "thinning_iterations": iterations,
        "thinning_converged": not changed,
    }


def _ordered_skeleton_path(component: dict) -> tuple[list[tuple[int, int]], dict]:
    """Return a single unambiguous endpoint-to-endpoint path in source pixels."""
    import numpy as np

    coords = component["coords"]
    x0, y0, x1, y1 = component["bbox"]
    local = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    local[coords[:, 0] - y0, coords[:, 1] - x0] = True
    skeleton, thinning = _thin_binary_component(local)
    local_points = [tuple(map(int, pair)) for pair in np.argwhere(skeleton)]
    points = {(y + y0, x + x0) for y, x in local_points}
    if len(points) < 8:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "SKELETON_TOO_SHORT",
            "skeleton_pixels": len(points),
            **thinning,
        }

    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for y, x in points:
        neighbours = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                candidate = (y + dy, x + dx)
                if candidate not in points:
                    continue
                # Suppress redundant diagonal edges where an orthogonal route
                # already connects the same two pixels.
                if dy and dx and (
                    (y, x + dx) in points or (y + dy, x) in points
                ):
                    continue
                neighbours.append(candidate)
        adjacency[(y, x)] = neighbours

    endpoints = [point for point, neighbours in adjacency.items() if len(neighbours) == 1]
    junctions = [point for point, neighbours in adjacency.items() if len(neighbours) > 2]
    if len(endpoints) != 2 or junctions:
        reason = "CLOSED_COMPONENT_OR_LOOP" if not endpoints else "BRANCHED_PIXEL_GRAPH"
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": reason,
            "endpoint_count": len(endpoints),
            "junction_count": len(junctions),
            "skeleton_pixels": len(points),
            **thinning,
        }

    start = min(endpoints, key=lambda point: (point[1], point[0]))
    path = [start]
    previous = None
    current = start
    while True:
        next_points = [
            point for point in adjacency[current]
            if point != previous
        ]
        if not next_points:
            break
        if len(next_points) != 1:
            return [], {
                "status": "NEEDS_REVIEW",
                "reason": "BRANCH_DURING_PATH_WALK",
                "endpoint_count": len(endpoints),
                "junction_count": len(junctions),
                "skeleton_pixels": len(points),
                **thinning,
            }
        previous, current = current, next_points[0]
        if current in path:
            return [], {
                "status": "NEEDS_REVIEW",
                "reason": "PIXEL_PATH_CYCLE",
                "endpoint_count": len(endpoints),
                "junction_count": len(junctions),
                "skeleton_pixels": len(points),
                **thinning,
            }
        path.append(current)

    if len(path) != len(points):
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "DISCONNECTED_SKELETON_SUBPATHS",
            "traced_pixels": len(path),
            "skeleton_pixels": len(points),
            **thinning,
        }
    if path[-1][1] < path[0][1]:
        path.reverse()
    x_values = np.asarray([point[1] for point in path], dtype=np.int32)
    backward_steps = int(np.count_nonzero(np.diff(x_values) < -1))
    if backward_steps:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "PATH_BACKTRACKS_IN_X",
            "backward_x_steps": backward_steps,
            "endpoint_count": len(endpoints),
            "junction_count": len(junctions),
            "skeleton_pixels": len(points),
            **thinning,
        }
    return path, {
        "status": "PATH_EXTRACTED",
        "endpoint_count": len(endpoints),
        "junction_count": len(junctions),
        "skeleton_pixels": len(points),
        "path_points": len(path),
        "backward_x_steps": backward_steps,
        **thinning,
    }


def detect_monotonic_color_branches(
    image_path: str,
    rgb: tuple[int, int, int],
    tolerance: int,
    *,
    plot_box: tuple[float, float, float, float],
    color_match: dict | None = None,
    min_column_support: float = 0.65,
    min_branch_presence_fraction: float = 0.15,
    max_branches: int = 24,
) -> dict:
    """Inventory disconnected 2-D trace paths; do not rank row bands by column.

    Kept under the historical function name for API compatibility. Branches
    are now spatial path components and are validated again by the tracer.
    """
    result = _find_color_components(
        image_path, rgb, tolerance, plot_box=plot_box, color_match=color_match
    )
    components = result.get("components", [])
    summaries = [
        {
            "component_index": index,
            "pixel_count": item["pixel_count"],
            "bbox": item["bbox"],
            "x_span": item["x_span"],
            "y_span": item["y_span"],
        }
        for index, item in enumerate(components)
    ]
    if result.get("status") not in {"CONNECTED_COMPONENTS_FOUND", "NO_TRACE_COMPONENTS"}:
        return {
            "status": "NEEDS_REVIEW",
            "reason": result.get("reason") or result.get("status"),
            "branches": summaries,
            "branch_count": len(components),
            "rejected_components": result.get("rejected_components", []),
            "plot_box": result.get("plot_box"),
        }
    if not components:
        return {
            "status": "NO_CONTINUOUS_PATH_COMPONENTS",
            "branch_count": 0,
            "branches": [],
            "rejected_components": result.get("rejected_components", []),
            "plot_box": result.get("plot_box"),
        }
    if len(components) > max_branches:
        return {
            "status": "TOO_MANY_PATH_COMPONENTS",
            "reason": "COMPONENT_COUNT_EXCEEDS_REVIEW_LIMIT",
            "branch_count": len(components),
            "branches": summaries,
            "max_branches": max_branches,
            "rejected_components": result.get("rejected_components", []),
            "plot_box": result.get("plot_box"),
        }
    return {
        "status": (
            "MULTIPLE_MONOTONIC_COLOR_BRANCHES" if len(components) > 1
            else "SINGLE_MONOTONIC_COLOR_BAND"
        ),
        "branch_count": len(components),
        "branches": summaries,
        "supported_columns": result.get("active_pixels"),
        "support_fraction": 1.0,
        "rejected_components": result.get("rejected_components", []),
        "plot_box": result.get("plot_box"),
        "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
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
    """Trace one connected 2-D colour path without collapsing vertical segments.

    Disconnected components remain separate series candidates. Components with
    loops, junctions, ambiguous skeletons or backward-X motion are rejected
    rather than joined or assigned an arbitrary median path.
    """
    if plot_box is None:
        return [], {"status": "NEEDS_REVIEW", "reason": "PLOT_REGION_REQUIRED"}
    result = _find_color_components(
        image_path, rgb, tolerance, plot_box=plot_box, color_match=color_match
    )
    if result.get("status") not in {"CONNECTED_COMPONENTS_FOUND", "NO_TRACE_COMPONENTS"}:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": result.get("reason") or result.get("status"),
            "component_detection": {
                key: value for key, value in result.items() if key != "components"
            },
            "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
        }
    components = result.get("components", [])
    if not components:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "NO_CONTINUOUS_PATH_COMPONENTS",
            "component_detection": {
                key: value for key, value in result.items() if key != "components"
            },
            "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
        }
    if branch_index is None and len(components) > 1:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "MULTIPLE_DISCONNECTED_PATHS_REQUIRE_SEPARATE_SERIES",
            "component_count": len(components),
            "branches": [
                {
                    "component_index": index,
                    "pixel_count": item["pixel_count"],
                    "bbox": item["bbox"],
                    "x_span": item["x_span"],
                }
                for index, item in enumerate(components)
            ],
            "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
        }
    selected_index = 0 if branch_index is None else int(branch_index)
    if selected_index < 0 or selected_index >= len(components):
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "PATH_COMPONENT_INDEX_OUT_OF_RANGE",
            "component_count": len(components),
            "requested_component_index": selected_index,
        }

    path, path_qc = _ordered_skeleton_path(components[selected_index])
    if not path:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": path_qc.get("reason", "PATH_EXTRACTION_FAILED"),
            "component_index": selected_index,
            "component": {
                key: value for key, value in components[selected_index].items()
                if key != "coords"
            },
            "path_qc": path_qc,
            "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
        }

    points = [
        SeriesPoint(
            point_index=index,
            x=map_pixel(x_calibration, float(px)) if x_calibration else None,
            y=map_pixel(y_calibration, float(py)) if y_calibration else None,
            pixel_x=float(px),
            pixel_y=float(py),
        )
        for index, (py, px) in enumerate(path)
    ]
    component = components[selected_index]
    return points, {
        "status": "EXTRACTED_PROVISIONAL",
        "method": "raster_color_connected_path",
        "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
        "path_order": "CONNECTED_PIXEL_GRAPH_LEFT_TO_RIGHT",
        "component_index": selected_index,
        "component_count": len(components),
        "component_bbox": component["bbox"],
        "component_pixel_count": component["pixel_count"],
        "component_x_span": component["x_span"],
        "component_y_span": component["y_span"],
        "path_points": len(points),
        "plot_box": result.get("plot_box"),
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
        "max_gap_columns_not_used": max_gap_columns,
        "legacy_min_pixels_per_column_not_used": min_pixels_per_column,
        "component_detection": {
            "active_pixels": result.get("active_pixels"),
            "rejected_components": result.get("rejected_components", []),
            "min_component_pixels": result.get("min_component_pixels"),
            "min_component_x_span": result.get("min_component_x_span"),
            "connectivity": result.get("connectivity"),
        },
        "path_qc": path_qc,
        "branch_index": branch_index,
        "branch_count": branch_count or len(components),
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
