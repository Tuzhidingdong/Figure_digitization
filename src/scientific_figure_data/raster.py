from __future__ import annotations

from pathlib import Path
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

    if isinstance(color_match, dict) and color_match.get("space") == "ACHROMATIC_LUMINANCE_RANGE":
        values = region.astype(np.int16)
        luminance = (
            0.2126 * values[:, :, 0]
            + 0.7152 * values[:, :, 1]
            + 0.0722 * values[:, :, 2]
        )
        chroma = values.max(axis=2) - values.min(axis=2)
        return (
            (chroma <= int(color_match.get("maximum_chroma", 24)))
            & (luminance >= int(color_match.get("minimum_luminance", 28)))
            & (luminance <= int(color_match.get("maximum_luminance", 210)))
        )
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


def _close_binary_mask(mask):
    """Bridge one-pixel rasterization gaps without joining visibly separate paths."""
    import numpy as np

    padded = np.pad(mask.astype(bool), 1, mode="constant")
    dilated = np.zeros(mask.shape, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            dilated |= padded[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    padded_dilated = np.pad(dilated, 1, mode="constant")
    closed = np.ones(mask.shape, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            closed &= padded_dilated[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return closed


def _find_color_components(
    image_path: str,
    rgb: tuple[int, int, int],
    tolerance: int,
    *,
    plot_box: tuple[float, float, float, float],
    color_match: dict | None = None,
    min_span_fraction: float = 0.08,
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
    if (
        isinstance(color_match, dict)
        and color_match.get("space") == "ACHROMATIC_LUMINANCE_RANGE"
    ):
        fraction = float(color_match.get("boundary_exclusion_fraction", 0.015))
        edge = max(1, int(round(min(mask.shape) * fraction)))
        mask[:edge, :] = False
        mask[-edge:, :] = False
        mask[:, :edge] = False
        mask[:, -edge:] = False
    from .plot_region import detect_colored_y_axis_spines

    spine_evidence = detect_colored_y_axis_spines(
        Path(image_path), (x0, y0, x1, y1)
    )
    edge_width = max(2, min(14, int(round((x1 - x0) * 0.012))))
    edge_axis_columns_removed = []
    sides = spine_evidence.get("sides", {})
    if sides.get("LEFT", {}).get("status") == "CHROMATIC_Y_AXIS_SPINE_DETECTED":
        mask[:, :min(edge_width, mask.shape[1])] = False
        edge_axis_columns_removed.extend(range(x0, min(x1, x0 + edge_width)))
    if sides.get("RIGHT", {}).get("status") == "CHROMATIC_Y_AXIS_SPINE_DETECTED":
        start = max(0, mask.shape[1] - edge_width)
        mask[:, start:] = False
        edge_axis_columns_removed.extend(range(x0 + start, x1))
    mask = _close_binary_mask(mask)
    active_count = int(mask.sum())
    if active_count > max_color_pixels:
        return {
            "status": "COLOR_MASK_TOO_DENSE",
            "reason": "CONNECTED_COMPONENT_PIXEL_BUDGET_EXCEEDED",
            "active_pixels": active_count,
            "pixel_budget": max_color_pixels,
            "edge_axis_columns_removed": edge_axis_columns_removed,
            "axis_spine_exclusion": spine_evidence,
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
            "edge_axis_columns_removed": edge_axis_columns_removed,
            "axis_spine_exclusion": spine_evidence,
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
        local_vertical_candidate = (
            summary["x_span"] <= max(6, int(round(min_x_span * 0.10)))
            and summary["y_span"] >= max(40, int(round(min_x_span * 0.40)))
            and summary["pixel_count"] >= max(24, int(round(min_x_span * 0.40)))
        )
        local_2d_candidate = (
            summary["x_span"] >= max(6, int(round(min_x_span * 0.25)))
            and summary["y_span"] >= max(2, int(round(min_x_span * 0.08)))
            and summary["y_span"] <= max(24, int(round(min_x_span * 0.25)))
            # Local 2-D fragments must be line-like, not compact rings/glyphs.
            and summary["x_span"] >= int(round(summary["y_span"] * 2.5))
            and summary["pixel_count"] >= max(24, int(round(min_x_span * 0.80)))
        )
        source_component_index = int(sy * width_local + sx)
        if summary["x_span"] < min_x_span and not (
            local_vertical_candidate or local_2d_candidate
        ):
            summary["rejection_reason"] = "COMPONENT_X_SPAN_TOO_SHORT"
            rejected.append(summary)
            continue
        candidate = {
            **summary,
            "source_component_index": source_component_index,
            "local_fragment_candidate": bool(
                local_vertical_candidate or local_2d_candidate
            ),
            "coords": (
                np.asarray(pixels, dtype=np.int32)
                + np.asarray([y0, x0], dtype=np.int32)
            ),
        }
        paths, path_qc = _ordered_skeleton_paths(
            candidate, minimum_path_x_span=min_x_span
        )
        if not paths:
            summary["rejection_reason"] = path_qc.get("reason", "PATH_VALIDATION_FAILED")
            summary["path_qc"] = path_qc
            rejected.append(summary)
            continue
        for path_index, path in enumerate(paths):
            path_x = [point[1] for point in path]
            path_y = [point[0] for point in path]
            path_summary = {
                "pixel_count": int(len(path)),
                "bbox": [
                    int(min(path_x)), int(min(path_y)),
                    int(max(path_x) + 1), int(max(path_y) + 1),
                ],
                "x_span": int(max(path_x) - min(path_x) + 1),
                "y_span": int(max(path_y) - min(path_y) + 1),
            }
            path_record = path_qc.get("path_summaries", [])
            path_record = next(
                (
                    item for item in path_record
                    if item.get("bbox") == path_summary["bbox"]
                    and item.get("path_points") == len(path)
                ),
                {},
            )
            components.append({
                **path_summary,
                "path": path,
                "path_qc": {
                    **path_qc,
                    "selected_path_index": path_index,
                },
                "source_component_index": source_component_index,
                "source_component_bbox": [int(value) for value in bbox],
                "source_component_pixel_count": len(pixels),
                "path_kind": path_record.get("retained_as", "FULL_X_SPAN_PATH"),
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
        "edge_axis_columns_removed": edge_axis_columns_removed,
        "axis_spine_exclusion": spine_evidence,
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


def _ordered_skeleton_paths(
    component: dict, *, minimum_path_x_span: int
) -> tuple[list[list[tuple[int, int]]], dict]:
    """Decompose a skeleton into paths using tangent-continuity at junctions.

    Degree-3/4 junctions are only traversed when the straight-through pairing is
    geometrically unique. This lets marker rings and clear crossings coexist
    with a curve, while symmetric/ambiguous branch points remain review items.
    """
    import itertools
    import math
    import numpy as np

    coords = component["coords"]
    x0, y0, x1, y1 = component["bbox"]
    local = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    local[coords[:, 0] - y0, coords[:, 1] - x0] = True
    skeleton, thinning = _thin_binary_component(local)
    points = {(y + y0, x + x0) for y, x in np.argwhere(skeleton)}
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
                # Suppress redundant diagonals when an orthogonal route exists.
                if dy and dx and (
                    (y, x + dx) in points or (y + dy, x) in points
                ):
                    continue
                neighbours.append(candidate)
        adjacency[(y, x)] = neighbours

    original_endpoints = [
        point for point, neighbours in adjacency.items() if len(neighbours) == 1
    ]
    junctions = [
        point for point, neighbours in adjacency.items() if len(neighbours) > 2
    ]
    junction_set = set(junctions)
    tangent_depth = max(4, min(12, int(round(minimum_path_x_span * 0.25))))

    def edge_key(left, right):
        return (left, right) if left <= right else (right, left)

    # Adjacent high-degree skeleton pixels are one physical junction region,
    # not several independent junctions. Compress each region to a virtual
    # node and match its external arms using longer-range tangents.
    junction_clusters = []
    unseen = set(junction_set)
    while unseen:
        seed = min(unseen, key=lambda point: (point[1], point[0]))
        unseen.remove(seed)
        cluster = {seed}
        stack = [seed]
        while stack:
            current = stack.pop()
            for neighbour in adjacency[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    cluster.add(neighbour)
                    stack.append(neighbour)
        junction_clusters.append(cluster)

    # A crossing can thin into two adjacent degree-3 pixels rather than one
    # degree-4 pixel. Merge junction regions connected by a short, unbranched
    # skeleton bridge before estimating their external arms.
    from collections import deque

    merge_distance = max(6, min(12, int(round(minimum_path_x_span * 0.60))))

    def find_short_junction_bridge(first_cluster, second_cluster):
        queue = deque()
        parents = {}
        distances = {}
        for point in sorted(first_cluster, key=lambda item: (item[1], item[0])):
            queue.append(point)
            parents[point] = None
            distances[point] = 0
        while queue:
            current = queue.popleft()
            if distances[current] >= merge_distance:
                continue
            for neighbour in adjacency[current]:
                if neighbour in first_cluster:
                    continue
                if neighbour in second_cluster:
                    path = [neighbour]
                    cursor = current
                    while cursor is not None:
                        path.append(cursor)
                        cursor = parents[cursor]
                    path.reverse()
                    return path
                if neighbour in junction_set or neighbour in parents:
                    continue
                parents[neighbour] = current
                distances[neighbour] = distances[current] + 1
                queue.append(neighbour)
        return None

    changed = True
    while changed:
        changed = False
        for first_index in range(len(junction_clusters)):
            for second_index in range(first_index + 1, len(junction_clusters)):
                bridge = find_short_junction_bridge(
                    junction_clusters[first_index],
                    junction_clusters[second_index],
                )
                if bridge is None:
                    continue
                merged = (
                    junction_clusters[first_index]
                    | junction_clusters[second_index]
                    | set(bridge)
                )
                junction_set.update(bridge)
                junction_clusters[first_index] = merged
                junction_clusters.pop(second_index)
                changed = True
                break
            if changed:
                break

    compressed_adjacency = {
        point: [neighbour for neighbour in neighbours if neighbour not in junction_set]
        for point, neighbours in adjacency.items()
        if point not in junction_set
    }
    bridge_expansions: dict[
        tuple[tuple[int, int], tuple[int, int]], list[tuple[int, int]]
    ] = {}
    junction_pairings = []
    ambiguous_clusters = []
    ambiguous_ports: set[tuple[int, int]] = set()
    unpaired_ports = []

    def shortest_cluster_bridge(cluster, start_nodes, end_nodes):
        """Find the shortest real skeleton route through one junction cluster."""
        from collections import deque

        end_set = set(end_nodes)
        queue = deque()
        parent = {}
        for node in sorted(start_nodes, key=lambda point: (point[1], point[0])):
            queue.append(node)
            parent[node] = None
        found = None
        while queue:
            current = queue.popleft()
            if current in end_set:
                found = current
                break
            for neighbour in sorted(adjacency[current], key=lambda point: (point[1], point[0])):
                if neighbour in cluster and neighbour not in parent:
                    parent[neighbour] = current
                    queue.append(neighbour)
        if found is None:
            return []
        path = []
        current = found
        while current is not None:
            path.append(current)
            current = parent[current]
        path.reverse()
        return path

    def cluster_port_tangent(cluster_center, port, contact_nodes, cluster):
        outside = [
            point for point in adjacency[port]
            if point not in cluster
        ]
        if len(outside) != 1:
            return (
                float(port[1] - cluster_center[1]),
                float(port[0] - cluster_center[0]),
            )
        previous = port
        current = outside[0]
        for _ in range(tangent_depth - 1):
            next_points = [
                point for point in adjacency[current]
                if point != previous and point not in junction_set
            ]
            if len(next_points) != 1:
                break
            previous, current = current, next_points[0]
        return (
            float(current[1] - cluster_center[1]),
            float(current[0] - cluster_center[0]),
        )

    for cluster_index, cluster in enumerate(junction_clusters):
        contacts: dict[tuple[int, int], set[tuple[int, int]]] = {}
        for node in cluster:
            for neighbour in adjacency[node]:
                if neighbour not in cluster:
                    contacts.setdefault(neighbour, set()).add(node)
        ports = sorted(contacts, key=lambda point: (point[1], point[0]))
        if len(ports) < 2:
            ambiguous_ports.update(ports)
            ambiguous_clusters.append({
                "cluster_index": int(cluster_index),
                "junction_pixels": int(len(cluster)),
                "port_count": int(len(ports)),
                "reason": "INSUFFICIENT_JUNCTION_PORTS",
            })
            continue

        center_y = sum(point[0] for point in cluster) / len(cluster)
        center_x = sum(point[1] for point in cluster) / len(cluster)
        cluster_center = (center_y, center_x)
        tangents = {
            port: cluster_port_tangent(
                cluster_center, port, contacts[port], cluster
            )
            for port in ports
        }

        def port_straightness(first, second):
            v1, v2 = tangents[first], tangents[second]
            norm1, norm2 = math.hypot(*v1), math.hypot(*v2)
            if not norm1 or not norm2:
                return 2.0
            cosine = (v1[0] * v2[0] + v1[1] * v2[1]) / (norm1 * norm2)
            return 1.0 + cosine

        pairs = []
        if len(ports) == 2:
            pairs = [(ports[0], ports[1])]
        elif len(ports) == 3:
            scored = sorted(
                (port_straightness(left, right), left, right)
                for left, right in itertools.combinations(ports, 2)
            )
            best, first, second = scored[0]
            margin = scored[1][0] - best
            if best > 0.65 or margin < 0.15:
                ambiguous_ports.update(ports)
                ambiguous_clusters.append({
                    "cluster_index": int(cluster_index),
                    "junction_pixels": int(len(cluster)),
                    "port_count": int(len(ports)),
                    "best_straightness_cost": float(round(best, 4)),
                    "pairing_margin": float(round(margin, 4)),
                    "ports": [[int(port[1]), int(port[0])] for port in ports],
                    "reason": "AMBIGUOUS_THREE_WAY_JUNCTION",
                })
                continue
            pairs = [(first, second)]
            unpaired = next(port for port in ports if port not in {first, second})
            ambiguous_ports.add(unpaired)
            unpaired_ports.append({
                "cluster_index": int(cluster_index),
                "pixel": [int(unpaired[1]), int(unpaired[0])],
                "reason": "UNPAIRED_SPUR_OR_AMBIGUOUS_BRANCH",
            })
        elif len(ports) == 4:
            a, b, c, d = ports
            possible = []
            for candidate_pairs in (
                ((a, b), (c, d)),
                ((a, c), (b, d)),
                ((a, d), (b, c)),
            ):
                costs = [
                    port_straightness(left, right)
                    for left, right in candidate_pairs
                ]
                possible.append((
                    sum(costs), max(costs), candidate_pairs, costs
                ))
            possible.sort(key=lambda item: item[0])
            best_total, worst_pair, selected_pairs, _ = possible[0]
            margin = possible[1][0] - best_total
            if worst_pair > 0.75 or margin < 0.20:
                ambiguous_ports.update(ports)
                ambiguous_clusters.append({
                    "cluster_index": int(cluster_index),
                    "junction_pixels": int(len(cluster)),
                    "port_count": int(len(ports)),
                    "best_pairing_cost": float(round(best_total, 4)),
                    "pairing_margin": float(round(margin, 4)),
                    "ports": [[int(port[1]), int(port[0])] for port in ports],
                    "reason": "AMBIGUOUS_FOUR_WAY_JUNCTION",
                })
                continue
            pairs = list(selected_pairs)
        else:
            ambiguous_ports.update(ports)
            ambiguous_clusters.append({
                "cluster_index": int(cluster_index),
                "junction_pixels": int(len(cluster)),
                "port_count": int(len(ports)),
                "ports": [[int(port[1]), int(port[0])] for port in ports],
                "reason": "UNSUPPORTED_JUNCTION_PORT_COUNT",
            })
            continue

        cluster_record = {
            "cluster_index": int(cluster_index),
            "junction_pixels": int(len(cluster)),
            "port_count": int(len(ports)),
            "pairings": [],
        }
        for left, right in pairs:
            bridge = shortest_cluster_bridge(
                cluster, contacts[left], contacts[right]
            )
            if not bridge:
                ambiguous_ports.update(ports)
                ambiguous_clusters.append({
                    **cluster_record,
                    "reason": "NO_JUNCTION_BRIDGE_PATH",
                })
                continue
            compressed_adjacency[left].append(right)
            compressed_adjacency[right].append(left)
            bridge_expansions[(left, right)] = bridge
            bridge_expansions[(right, left)] = list(reversed(bridge))
            cluster_record["pairings"].append({
                "ports": [
                    [int(left[1]), int(left[0])],
                    [int(right[1]), int(right[0])],
                ],
                "straightness_cost": float(round(port_straightness(left, right), 4)),
            })
        junction_pairings.append(cluster_record)

    # A compact unsupported N-way junction (for example, a five-way star)
    # is not equivalent to a long dense overlap zone. Its arms cannot safely be
    # attributed to separate traces, so reject the whole source component.
    hard_unsupported_junctions = [
        item for item in ambiguous_clusters
        if item.get("reason") == "UNSUPPORTED_JUNCTION_PORT_COUNT"
        and 3 <= int(item.get("port_count", 0)) <= 7
    ]
    if hard_unsupported_junctions:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW",
            "ambiguous_junction_clusters": hard_unsupported_junctions,
            "endpoint_count": len(original_endpoints),
            "junction_count": int(len(junctions)),
            "junction_cluster_count": int(len(junction_clusters)),
            "skeleton_pixels": int(len(points)),
            **thinning,
        }

    # Ambiguous junction clusters are hard breakpoints, not a reason to discard
    # every path in the source component. Their external ports remain terminals
    # in the compressed graph; no pairing or bridge is invented across them.

    for point, neighbours in compressed_adjacency.items():
        if len(neighbours) > 2:
            return [], {
                "status": "NEEDS_REVIEW",
                "reason": "COMPRESSED_GRAPH_STILL_BRANCHES",
                "pixel": [int(point[1]), int(point[0])],
                "degree": int(len(neighbours)),
                "junction_pairings": junction_pairings,
                "skeleton_pixels": int(len(points)),
                **thinning,
            }

    original_endpoint_set = set(original_endpoints)
    endpoints = [
        point for point, neighbours in compressed_adjacency.items()
        if len(neighbours) == 1
        and (point in original_endpoint_set or point in ambiguous_ports)
    ]
    used_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    paths = []

    def walk(start, initial_next):
        path = [start]
        previous = start
        current = initial_next
        first_edge = edge_key(previous, current)
        if first_edge in used_edges:
            return
        used_edges.add(first_edge)
        path.append(current)
        path.extend(bridge_expansions.get((previous, current), []))
        guard = 0
        while guard <= len(points):
            guard += 1
            neighbours = compressed_adjacency[current]
            if len(neighbours) == 1:
                next_point = neighbours[0] if neighbours[0] != previous else None
            elif len(neighbours) == 2:
                next_point = neighbours[0] if neighbours[1] == previous else neighbours[1]
            else:
                next_point = None
            if next_point is None:
                break
            key = edge_key(current, next_point)
            if key in used_edges:
                break
            used_edges.add(key)
            previous, current = current, next_point
            path.extend(bridge_expansions.get((previous, current), []))
            path.append(current)
        if len(path) >= 8:
            if (path[-1][1], path[-1][0]) < (path[0][1], path[0][0]):
                path.reverse()
            # Keep a segment only when both ends are genuine raster endpoints
            # or explicit ambiguous-junction breakpoints. Never connect across
            # an uncertain cluster.
            if (
                path[0] not in original_endpoint_set | ambiguous_ports
                or path[-1] not in original_endpoint_set | ambiguous_ports
            ):
                return
            paths.append(path)

    for endpoint in sorted(endpoints, key=lambda point: (point[1], point[0])):
        neighbour = compressed_adjacency[endpoint][0]
        if edge_key(endpoint, neighbour) not in used_edges:
            walk(endpoint, neighbour)

    # Isolated graph fragments inside the same original component are reported
    # Isolated graph fragments inside the same original component are reported
    # but not connected by invented straight lines.
    unique_paths = []
    seen = set()
    for path in paths:
        signature = tuple(path)
        reverse_signature = tuple(reversed(path))
        if signature in seen or reverse_signature in seen:
            continue
        seen.add(signature)
        unique_paths.append(path)

    if not unique_paths:
        reason = "CLOSED_COMPONENT_OR_LOOP" if not endpoints else "NO_UNAMBIGUOUS_ENDPOINT_PATH"
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": reason,
            "endpoint_count": len(endpoints),
            "junction_count": len(junctions),
            "skeleton_pixels": len(points),
            **thinning,
        }

    summaries = []
    accepted = []
    min_x_span = max(6, int(minimum_path_x_span))
    for path_index, path in enumerate(unique_paths):
        xs = [point[1] for point in path]
        ys = [point[0] for point in path]
        x_span = max(xs) - min(xs) + 1
        backwards = sum(
            1 for left, right in zip(xs, xs[1:]) if right < left - 1
        )
        summary = {
            "path_index": int(path_index),
            "path_points": int(len(path)),
            "bbox": [
                int(min(xs)), int(min(ys)), int(max(xs) + 1), int(max(ys) + 1)
            ],
            "x_span": int(x_span),
            "y_span": int(max(ys) - min(ys) + 1),
            "backward_x_steps": int(backwards),
        }
        y_span = int(max(ys) - min(ys) + 1)
        vertical_fragment = (
            y_span >= max(20, int(round(min_x_span * 0.20)))
            and x_span <= max(6, int(round(min_x_span * 0.10)))
            and len(path) >= max(16, int(round(min_x_span * 0.15)))
        )
        short_2d_fragment = (
            x_span >= max(6, int(round(min_x_span * 0.25)))
            and y_span >= max(2, int(round(min_x_span * 0.08)))
            and y_span <= max(24, int(round(min_x_span * 0.25)))
            and len(path) >= max(8, int(round(min_x_span * 0.25)))
        )
        retained_as = (
            "FULL_X_SPAN_PATH" if x_span >= min_x_span
            else "LOCAL_VERTICAL_FRAGMENT_NEEDS_REVIEW" if vertical_fragment
            else "LOCAL_SHORT_2D_FRAGMENT_NEEDS_REVIEW" if short_2d_fragment
            else None
        )
        if retained_as is None:
            summary["rejection_reason"] = "PATH_X_SPAN_TOO_SHORT"
            summaries.append(summary)
            continue
        if backwards > max(2, int(round(len(path) * 0.05))):
            summary["rejection_reason"] = "PATH_BACKTRACKS_IN_X"
            summaries.append(summary)
            continue
        summary["retained_as"] = retained_as
        summaries.append(summary)
        accepted.append(path)

    accepted.sort(key=lambda path: (
        min(point[1] for point in path),
        sum(point[0] for point in path) / len(path),
    ))
    local_fragment_count = sum(
        1 for item in summaries
        if str(item.get("retained_as", "")).startswith("LOCAL_")
    )
    partial_review_required = bool(
        ambiguous_clusters or unpaired_ports or local_fragment_count
    )
    return accepted, {
        "status": (
            "PARTIAL_PATHS_NEEDS_REVIEW"
            if accepted and partial_review_required
            else "PATHS_EXTRACTED" if accepted else "NEEDS_REVIEW"
        ),
        "reason": (
            "AMBIGUOUS_JUNCTIONS_RETAINED_AS_LOCAL_BREAKPOINTS"
            if accepted and (ambiguous_clusters or unpaired_ports)
            else "LOCAL_GEOMETRY_FRAGMENTS_RETAINED_WITHOUT_FULL_X_COVERAGE"
            if accepted and local_fragment_count
            else None if accepted else "NO_PATH_SPANS_REQUIRED_X_RANGE"
        ),
        "partial_path_review_required": partial_review_required,
        "local_fragment_count": int(local_fragment_count),
        "ambiguous_junction_clusters": ambiguous_clusters,
        "endpoint_count": len(endpoints),
        "junction_count": int(len(junctions)),
        "junction_cluster_count": int(len(junction_clusters)),
        "junction_pairings": junction_pairings,
        "unpaired_ports": unpaired_ports,
        "path_count": len(accepted),
        "path_summaries": summaries,
        "skeleton_pixels": len(points),
        "used_edges": len(used_edges),
        **thinning,
    }


def _path_branch_groups(
    components: list[dict], *, collapse_all_partial: bool = True
) -> list[list[dict]]:
    """Group partial paths from one ambiguous source component without joining them.

    A full-span path remains an independent branch. When one source component
    has been decomposed at ambiguous junctions, its safe local path segments are
    returned as one branch group; the individual paths remain separate segments.
    """
    groups: list[list[dict]] = []
    partial_by_source: dict[int, list[dict]] = {}
    for index, item in enumerate(components):
        path_qc = item.get("path_qc") or {}
        source_index = int(item.get("source_component_index", index))
        if path_qc.get("status") == "PARTIAL_PATHS_NEEDS_REVIEW":
            if source_index not in partial_by_source:
                partial_by_source[source_index] = []
                groups.append(partial_by_source[source_index])
            partial_by_source[source_index].append(item)
        else:
            groups.append([item])

    for group in groups:
        group.sort(key=lambda item: (
            int(item.get("bbox", [0, 0, 0, 0])[0]),
            int(item.get("bbox", [0, 0, 0, 0])[1]),
            -int(item.get("pixel_count", 0)),
        ))

    # If every surviving candidate is explicitly partial-review geometry,
    # preserve them as one review collection with independent path segments.
    # This is essential for dashed/fractured traces such as blue early-cycle
    # curves: returning zero points merely because their fragments are
    # disconnected would discard all available geometry. No line is drawn
    # between the segments and the collection cannot be a complete extraction.
    if collapse_all_partial and len(groups) > 1 and all(
        all(
            (item.get("path_qc") or {}).get("status")
            == "PARTIAL_PATHS_NEEDS_REVIEW"
            for item in group
        )
        for group in groups
    ):
        groups = [[item for group in groups for item in group]]
        groups[0].sort(key=lambda item: (
            int(item.get("bbox", [0, 0, 0, 0])[0]),
            int(item.get("bbox", [0, 0, 0, 0])[1]),
            -int(item.get("pixel_count", 0)),
        ))

    groups.sort(key=lambda group: (
        min(int(item.get("bbox", [0, 0, 0, 0])[0]) for item in group),
        min(int(item.get("bbox", [0, 0, 0, 0])[1]) for item in group),
        -sum(int(item.get("pixel_count", 0)) for item in group),
    ))
    return groups


def _group_achromatic_fragment_tracks(
    groups: list[list[dict]], *, plot_width: int, plot_height: int,
    include_full_span_fragments: bool = False,
    include_partial_fragments: bool = True,
) -> tuple[list[list[dict]], list[dict], dict]:
    """Associate disconnected raster fragments only when local geometry is unique.

    Local dashed fragments require chains of at least three segments. Optionally,
    two full-span fragments may be grouped when a short occlusion gap and
    reciprocal endpoint/tangent evidence uniquely support the continuation.
    Original pixel paths remain separate segments; no pixels are inserted.
    """
    full_groups = [
        group for group in groups
        if len(group) == 1
        and group[0].get("path_kind", "FULL_X_SPAN_PATH") == "FULL_X_SPAN_PATH"
    ]
    full_component_ids = {id(group[0]) for group in full_groups}
    partial_items = [
        item for group in groups
        for item in group
        if id(item) not in full_component_ids
        and (
            str(item.get("path_kind", "")).startswith("LOCAL_")
            or (item.get("path_qc") or {}).get("status") == "PARTIAL_PATHS_NEEDS_REVIEW"
        )
    ]
    candidate_items = (
        [(item, False) for item in partial_items]
        if include_partial_fragments else []
    )
    if include_full_span_fragments:
        candidate_items.extend((group[0], True) for group in full_groups)

    def describe(item: dict, *, full_span_fragment: bool = False) -> dict | None:
        path = item.get("path") or []
        if len(path) < 8:
            return None
        xy = sorted(
            ((float(px), float(py)) for py, px in path),
            key=lambda point: point[0],
        )
        x0, y0 = xy[0]
        x1, y1 = xy[-1]
        sample_count = max(3, min(len(xy), int(round(len(xy) / 3))))

        def slope(samples):
            mean_x = sum(point[0] for point in samples) / len(samples)
            mean_y = sum(point[1] for point in samples) / len(samples)
            denominator = sum((point[0] - mean_x) ** 2 for point in samples)
            if denominator <= 1e-9:
                return 0.0
            return sum(
                (point[0] - mean_x) * (point[1] - mean_y)
                for point in samples
            ) / denominator

        start = xy[:sample_count]
        end = xy[-sample_count:]
        return {
            "component": item,
            "x0": x0,
            "x1": x1,
            "y0": sum(point[1] for point in start) / len(start),
            "y1": sum(point[1] for point in end) / len(end),
            "slope_start": slope(start),
            "slope_end": slope(end),
            "full_span_fragment": bool(full_span_fragment),
        }

    descriptions = [
        description for item, is_full_span in candidate_items
        if (description := describe(item, full_span_fragment=is_full_span)) is not None
    ]
    max_gap = max(8, int(round(plot_width * 0.05)))
    residual_limit = max(4.0, plot_height * 0.02)
    slope_limit = 0.70

    def unassigned_rows() -> list[dict]:
        return [
            {
                "bbox": [int(value) for value in description["component"].get("bbox", [])],
                "point_count": int(description["component"].get("pixel_count", 0)),
                "path_kind": description["component"].get("path_kind"),
                "reason": "FRAGMENT_NOT_PART_OF_UNIQUE_SUPPORTED_TRACK",
            }
            for description in descriptions
            if not description["full_span_fragment"]
        ]

    # A dense neutral pool can contain text, ticks and annotations. Fail closed
    # rather than doing unbounded fragment matching or guessing their identities.
    max_partial_fragments = 512
    if len(descriptions) > max_partial_fragments:
        return full_groups, unassigned_rows(), {
            "status": "FRAGMENT_COUNT_LIMIT_REACHED_NEEDS_REVIEW",
            "partial_component_count": len(partial_items),
            "described_fragment_count": len(descriptions),
            "fragment_limit": max_partial_fragments,
            "track_count": 0,
            "unassigned_fragment_count": len(descriptions),
            "inter_fragment_pixels_inserted": 0,
        }

    # Index fragments by their left edge. Only components whose left edge falls
    # inside the admissible endpoint window can be a successor; this avoids an
    # all-pairs scan of every neutral annotation and local raster fragment.
    descriptions.sort(key=lambda item: (item["x0"], item["x1"], item["y0"]))
    x_starts = [item["x0"] for item in descriptions]
    successor_candidates: dict[int, list[tuple[float, int]]] = {}
    predecessor_candidates: dict[int, list[tuple[float, int]]] = {}
    candidate_pair_count = 0
    max_candidate_pairs = 50000

    from bisect import bisect_left, bisect_right

    for first_index, first in enumerate(descriptions):
        lower = bisect_left(
            x_starts, first["x1"] - 1, lo=first_index + 1
        )
        upper = bisect_right(
            x_starts, first["x1"] + max_gap, lo=lower
        )
        candidates = []
        for second_index in range(lower, upper):
            candidate_pair_count += 1
            if candidate_pair_count > max_candidate_pairs:
                return full_groups, unassigned_rows(), {
                    "status": "FRAGMENT_MATCH_LIMIT_REACHED_NEEDS_REVIEW",
                    "partial_component_count": len(partial_items),
                    "described_fragment_count": len(descriptions),
                    "candidate_pair_count": candidate_pair_count,
                    "candidate_pair_limit": max_candidate_pairs,
                    "track_count": 0,
                    "unassigned_fragment_count": len(descriptions),
                    "inter_fragment_pixels_inserted": 0,
                }
            second = descriptions[second_index]
            gap = max(0.0, second["x0"] - first["x1"])
            predicted_y = first["y1"] + first["slope_end"] * (
                second["x0"] - first["x1"]
            )
            residual = abs(second["y0"] - predicted_y)
            slope_delta = abs(first["slope_end"] - second["slope_start"])
            allowed_residual = residual_limit + gap * 0.18
            if residual > allowed_residual or slope_delta > slope_limit:
                continue
            cost = residual + slope_delta * 2.0 + gap * 0.05
            candidates.append((float(cost), second_index))
            predecessor_candidates.setdefault(second_index, []).append(
                (float(cost), first_index)
            )
        candidates.sort()
        if candidates:
            successor_candidates[first_index] = candidates

    def unique_best(items: list[tuple[float, int]]) -> int | None:
        if not items:
            return None
        ordered = sorted(items)
        if len(ordered) > 1 and ordered[1][0] - ordered[0][0] < 1.75:
            return None
        return ordered[0][1]

    successors = {}
    predecessors = {}
    for source_index, candidates in successor_candidates.items():
        target_index = unique_best(candidates)
        if target_index is None:
            continue
        reverse_best = unique_best(predecessor_candidates.get(target_index, []))
        if reverse_best == source_index:
            successors[source_index] = target_index
            predecessors[target_index] = source_index

    chains = []
    visited = set()
    for start_index in range(len(descriptions)):
        if start_index in predecessors or start_index in visited:
            continue
        chain = []
        cursor = start_index
        while cursor not in visited:
            visited.add(cursor)
            chain.append(cursor)
            if cursor not in successors:
                break
            cursor = successors[cursor]
        dashed_chain_supported = len(chain) >= 3
        occlusion_chain_supported = (
            include_full_span_fragments
            and len(chain) >= 2
            and all(descriptions[index]["full_span_fragment"] for index in chain)
        )
        if dashed_chain_supported or occlusion_chain_supported:
            x_start = min(descriptions[index]["x0"] for index in chain)
            x_end = max(descriptions[index]["x1"] for index in chain)
            coverage = (x_end - x_start) / max(1, plot_width)
            if coverage >= 0.22:
                components = [
                    descriptions[index]["component"] for index in chain
                ]
                components.sort(key=lambda item: (
                    int(item.get("bbox", [0, 0, 0, 0])[0]),
                    int(item.get("bbox", [0, 0, 0, 0])[1]),
                ))
                chains.append({
                    "component_indexes": chain,
                    "segment_count": len(components),
                    "x_coverage_fraction": float(coverage),
                    "bbox": [
                        min(int(item["bbox"][0]) for item in components),
                        min(int(item["bbox"][1]) for item in components),
                        max(int(item["bbox"][2]) for item in components),
                        max(int(item["bbox"][3]) for item in components),
                    ],
                })

    tracks = []
    tracked_indexes = {
        index for chain in chains for index in chain["component_indexes"]
    }
    tracked_full_span_ids = {
        id(descriptions[index]["component"])
        for index in tracked_indexes
        if descriptions[index]["full_span_fragment"]
    }
    for chain in chains:
        tracks.append([
            descriptions[index]["component"]
            for index in chain["component_indexes"]
        ])
    unassigned = [
        {
            "bbox": [int(value) for value in descriptions[index]["component"].get("bbox", [])],
            "point_count": int(descriptions[index]["component"].get("pixel_count", 0)),
            "path_kind": descriptions[index]["component"].get("path_kind"),
            "reason": "FRAGMENT_NOT_PART_OF_UNIQUE_SUPPORTED_TRACK",
        }
        for index, description in enumerate(descriptions)
        if not description["full_span_fragment"] and index not in tracked_indexes
    ]
    remaining_full_groups = [
        group for group in full_groups if id(group[0]) not in tracked_full_span_ids
    ]
    result_groups = remaining_full_groups + tracks
    result_groups.sort(key=lambda group: (
        min(int(item.get("bbox", [0, 0, 0, 0])[0]) for item in group),
        min(int(item.get("bbox", [0, 0, 0, 0])[1]) for item in group),
        -sum(int(item.get("pixel_count", 0)) for item in group),
    ))
    diagnostics = {
        "status": "TRACKS_FOUND" if tracks else "NO_UNIQUE_DASH_TRACK",
        "partial_component_count": len(partial_items),
        "partial_fragments_considered": bool(include_partial_fragments),
        "full_span_fragment_count": sum(
            1 for item in descriptions if item["full_span_fragment"]
        ),
        "described_fragment_count": len(descriptions),
        "candidate_pair_count": candidate_pair_count,
        "candidate_pair_limit": max_candidate_pairs,
        "track_count": len(tracks),
        "tracks": chains,
        "unassigned_fragment_count": len(unassigned),
        "max_gap_pixels": max_gap,
        "residual_limit_pixels": residual_limit,
        "slope_difference_limit": slope_limit,
        "inter_fragment_pixels_inserted": 0,
    }
    return result_groups, unassigned, diagnostics


def _branch_group_has_full_span_path(group: list[dict]) -> bool:
    """A full-span geometric candidate, independent of its separate QC status."""
    return (
        len(group) == 1
        and group[0].get("path_kind", "FULL_X_SPAN_PATH") == "FULL_X_SPAN_PATH"
    )


def _branch_group_is_local_review(group: list[dict]) -> bool:
    """Only explicit LOCAL_* geometry may be auto-excluded beside a unique full path."""
    return bool(group) and all(
        str(item.get("path_kind", "")).startswith("LOCAL_")
        and (item.get("path_qc") or {}).get("status") == "PARTIAL_PATHS_NEEDS_REVIEW"
        for item in group
    )


def _select_unique_full_span_group(groups: list[list[dict]]) -> tuple[list[list[dict]], list[dict]]:
    """Suppress only local-review groups, never long full-span paths with QC warnings."""
    if len(groups) <= 1:
        return groups, []
    full_span_indices = [
        index for index, group in enumerate(groups)
        if _branch_group_has_full_span_path(group)
    ]
    if len(full_span_indices) != 1:
        return groups, []
    selected_index = full_span_indices[0]
    if not all(
        index == selected_index or _branch_group_is_local_review(group)
        for index, group in enumerate(groups)
    ):
        return groups, []
    excluded = [
        _branch_group_summary(index, group)
        for index, group in enumerate(groups)
        if index != selected_index
    ]
    return [groups[selected_index]], excluded


def _compact_rejected_review_candidates(
    rejected_components: list[dict], selected_group: list[dict],
) -> list[dict]:
    """Record small, spatially separate unsupported junction components beside a unique path.

    These are review-only exclusions, not assertions that a component is definitely
    an annotation. The original rejection cause and geometry are kept verbatim.
    """
    if not _branch_group_has_full_span_path(selected_group):
        return []
    selected = selected_group[0]
    selected_bbox = selected.get("bbox", [])
    if len(selected_bbox) != 4:
        return []
    sx0, sy0, sx1, sy1 = [int(value) for value in selected_bbox]
    selected_x_span = max(1, sx1 - sx0)
    selected_y_span = max(1, sy1 - sy0)
    selected_pixel_count = max(1, int(selected.get("pixel_count", 0)))
    output = []
    for item in rejected_components:
        path_qc = item.get("path_qc") or {}
        top_level_reason = item.get("rejection_reason")
        nested_reason = path_qc.get("reason")
        required_source_reason = "UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW"
        # Component-level rejection may wrap a more specific path-level reason
        # (for example UNSUPPORTED_JUNCTION_PORT_COUNT). Check both fields:
        # preferring the nested detail must not hide the public rejection reason.
        if required_source_reason not in {top_level_reason, nested_reason}:
            continue
        source_reason = required_source_reason

        bbox = item.get("bbox", [])
        if len(bbox) != 4:
            continue
        x0, y0, x1, y1 = [int(value) for value in bbox]
        x_span = max(0, x1 - x0)
        y_span = max(0, y1 - y0)
        overlaps_selected = (
            max(x0, sx0) < min(x1, sx1)
            and max(y0, sy0) < min(y1, sy1)
        )
        pixel_count = int(item.get("pixel_count", 0))
        # This is QC bookkeeping only, not geometric path admission. A
        # thin waveform can have very few raster pixels while a spatially
        # separate callout/text component has a larger pixel count. Do not use
        # pixel-count ratios to suppress its exclusion record once the bbox
        # size and non-overlap checks pass.
        compact_and_separate = (
            not overlaps_selected
            and x_span <= selected_x_span * 0.40
            and y_span <= selected_y_span * 0.50
        )
        if not compact_and_separate:
            continue
        output.append({
            **item,
            "rejection_reason": "PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS",
            "source_qc_rejection_reason": source_reason,
            "source_path_qc_reason": nested_reason,
            "classification": "UNRESOLVED_COMPACT_COMPONENT_RETAINED_IN_REVIEW_QC",
            "bbox": [x0, y0, x1, y1],
            "x_span": x_span,
            "y_span": y_span,
            "decision_basis": {
                "unique_full_span_path_bbox": [sx0, sy0, sx1, sy1],
                "spatially_separate": True,
                "relative_x_span_max": 0.40,
                "relative_y_span_max": 0.50,
                "selected_path_pixel_count": selected_pixel_count,
                "candidate_component_pixel_count": pixel_count,
                "pixel_count_ratio_used_for_selection": False,
            },
        })
    return output


def _branch_group_summary(index: int, group: list[dict]) -> dict:
    boxes = [item["bbox"] for item in group]
    x0 = min(int(box[0]) for box in boxes)
    y0 = min(int(box[1]) for box in boxes)
    x1 = max(int(box[2]) for box in boxes)
    y1 = max(int(box[3]) for box in boxes)
    return {
        "component_index": int(index),
        "source_component_index": int(group[0].get("source_component_index", index)),
        "pixel_count": int(sum(item.get("pixel_count", 0) for item in group)),
        "bbox": [x0, y0, x1, y1],
        "x_span": int(x1 - x0),
        "y_span": int(y1 - y0),
        "path_count": int(len(group)),
        "path_qc": group[0].get("path_qc", {}),
        "path_segments": [
            {
                "bbox": [int(value) for value in item.get("bbox", [])],
                "point_count": int(item.get("pixel_count", 0)),
                "path_kind": item.get("path_kind", "FULL_X_SPAN_PATH"),
            }
            for item in group
        ],
        "source_component_pixel_count": int(
            group[0].get("source_component_pixel_count", 0)
        ),
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
    preserve_partial_fragments: bool = False,
    associate_full_span_fragments: bool = False,
) -> dict:
    """Inventory independent paths and grouped local fragments without joining them.

    A single fully validated data path takes precedence over disconnected
    partial-review candidates (for example, a same-colour callout box). Those
    excluded candidates remain explicitly recorded in QC.
    """
    result = _find_color_components(
        image_path, rgb, tolerance, plot_box=plot_box, color_match=color_match
    )
    components = result.get("components", [])
    groups = _path_branch_groups(
        components, collapse_all_partial=not preserve_partial_fragments
    )
    fragment_review = []
    fragment_tracking = None
    if preserve_partial_fragments or associate_full_span_fragments:
        x0, y0, x1, y1 = result.get("plot_box") or [0, 0, 0, 0]
        groups, fragment_review, fragment_tracking = _group_achromatic_fragment_tracks(
            groups, plot_width=max(1, int(x1) - int(x0)),
            plot_height=max(1, int(y1) - int(y0)),
            include_full_span_fragments=associate_full_span_fragments,
            include_partial_fragments=preserve_partial_fragments,
        )
    summaries = [
        _branch_group_summary(index, group)
        for index, group in enumerate(groups)
    ]
    if result.get("status") not in {"CONNECTED_COMPONENTS_FOUND", "NO_TRACE_COMPONENTS"}:
        return {
            "status": "NEEDS_REVIEW",
            "reason": result.get("reason") or result.get("status"),
            "branches": summaries,
            "branch_count": len(groups),
            "rejected_components": result.get("rejected_components", []),
            "edge_axis_columns_removed": result.get("edge_axis_columns_removed", []),
            "axis_spine_exclusion": result.get("axis_spine_exclusion", {}),
            "plot_box": result.get("plot_box"),
        }
    if not groups:
        return {
            "status": "NO_CONTINUOUS_PATH_COMPONENTS",
            "branch_count": 0,
            "branches": [],
            "rejected_components": result.get("rejected_components", []),
            "plot_box": result.get("plot_box"),
        }

    excluded_partial_branches = []
    if not preserve_partial_fragments:
        groups, excluded_partial_branches = _select_unique_full_span_group(groups)
        summaries = [
            _branch_group_summary(index, group)
            for index, group in enumerate(groups)
        ]
    if len(groups) == 1:
        excluded_partial_branches.extend(
            _compact_rejected_review_candidates(
                result.get("rejected_components", []), groups[0]
            )
        )
    if len(groups) > max_branches:
        return {
            "status": "TOO_MANY_PATH_COMPONENTS",
            "reason": "COMPONENT_COUNT_EXCEEDS_REVIEW_LIMIT",
            "branch_count": len(groups),
            "branches": summaries,
            "max_branches": max_branches,
            "excluded_partial_branches": excluded_partial_branches,
            "rejected_components": result.get("rejected_components", []),
            "plot_box": result.get("plot_box"),
        }

    rejected_components = list(result.get("rejected_components", []))
    for item in excluded_partial_branches:
        if item not in rejected_components:
            rejected_components.append({
                "rejection_reason": "PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS",
                "source_qc_rejection_reason": item.get("source_qc_rejection_reason"),
                "source_path_qc_reason": item.get("source_path_qc_reason"),
                "classification": item.get("classification", "LOCAL_REVIEW_PATH_EXCLUDED"),
                "bbox": item.get("bbox"),
                "pixel_count": item.get("pixel_count"),
                "path_count": item.get("path_count"),
                "source_component_index": item.get("source_component_index"),
            })
    return {
        "status": (
            "MULTIPLE_MONOTONIC_COLOR_BRANCHES" if len(groups) > 1
            else "SINGLE_MONOTONIC_COLOR_BAND"
        ),
        "branch_count": len(groups),
        "branches": summaries,
        "excluded_partial_branches": excluded_partial_branches,
        "supported_columns": result.get("active_pixels"),
        "support_fraction": 1.0,
        "rejected_components": rejected_components,
        "plot_box": result.get("plot_box"),
        "path_model": "CONNECTED_2D_PIXEL_COMPONENTS_WITH_EXPLICIT_SEGMENT_BREAKS",
        "partial_fragment_review": fragment_review,
        "partial_fragment_tracking": fragment_tracking,
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
    preserve_partial_fragments: bool = False,
    associate_full_span_fragments: bool = False,
) -> tuple[list[SeriesPoint], dict]:
    """Trace ordered paths while retaining ambiguous local fragments as segments.

    Separate path segments are never connected by synthetic lines. Multiple
    disconnected complete branches still require explicit selection; a unique
    complete path may be selected over partial-review annotation candidates.
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
    groups = _path_branch_groups(
        components, collapse_all_partial=not preserve_partial_fragments
    )
    partial_fragment_review = []
    partial_fragment_tracking = None
    if preserve_partial_fragments or associate_full_span_fragments:
        x0, y0, x1, y1 = result.get("plot_box") or [0, 0, 0, 0]
        groups, partial_fragment_review, partial_fragment_tracking = (
            _group_achromatic_fragment_tracks(
                groups, plot_width=max(1, int(x1) - int(x0)),
                plot_height=max(1, int(y1) - int(y0)),
                include_full_span_fragments=associate_full_span_fragments,
            )
        )
    if not groups:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "NO_CONTINUOUS_PATH_COMPONENTS",
            "component_detection": {
                key: value for key, value in result.items() if key != "components"
            },
            "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
        }

    auto_excluded = []
    if branch_index is None:
        selected_groups, auto_excluded = (
            (groups, []) if preserve_partial_fragments
            else _select_unique_full_span_group(groups)
        )
        if len(selected_groups) == 1 and len(groups) > 1:
            groups = selected_groups
            selected_index = 0
        elif len(groups) > 1:
            return [], {
                "status": "NEEDS_REVIEW",
                "reason": "MULTIPLE_DISCONNECTED_PATHS_REQUIRE_SEPARATE_SERIES",
                "component_count": len(groups),
                "branches": [
                    _branch_group_summary(index, group)
                    for index, group in enumerate(groups)
                ],
                "partial_fragment_review": partial_fragment_review,
                "partial_fragment_tracking": partial_fragment_tracking,
                "path_model": "CONNECTED_2D_PIXEL_COMPONENTS",
            }
        else:
            selected_index = 0
    else:
        selected_index = int(branch_index)

    if selected_index < 0 or selected_index >= len(groups):
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "PATH_COMPONENT_INDEX_OUT_OF_RANGE",
            "component_count": len(groups),
            "requested_component_index": selected_index,
        }

    selected_group = groups[selected_index]
    selected_group = sorted(selected_group, key=lambda item: (
        int(item.get("bbox", [0, 0, 0, 0])[0]),
        int(item.get("bbox", [0, 0, 0, 0])[1]),
    ))
    points = []
    path_segments = []
    for segment_index, component in enumerate(selected_group):
        path = component["path"]
        start_point_index = len(points)
        points.extend(
            SeriesPoint(
                point_index=len(points),
                x=map_pixel(x_calibration, float(px)) if x_calibration else None,
                y=map_pixel(y_calibration, float(py)) if y_calibration else None,
                pixel_x=float(px),
                pixel_y=float(py),
            )
            for py, px in path
        )
        end_point_index = len(points) - 1
        path_segments.append({
            "segment_index": int(segment_index),
            "start_point_index": int(start_point_index),
            "end_point_index": int(end_point_index),
            "point_count": int(end_point_index - start_point_index + 1),
            "bbox": [int(value) for value in component["bbox"]],
            "path_kind": component.get("path_kind", "FULL_X_SPAN_PATH"),
        })

    if not points:
        return [], {
            "status": "NEEDS_REVIEW",
            "reason": "SELECTED_BRANCH_CONTAINS_NO_ORDERED_POINTS",
            "component_count": len(groups),
        }

    path_qc = dict(selected_group[0].get("path_qc") or {})
    local_fragment_count = sum(
        1 for item in selected_group
        if str(item.get("path_kind", "")).startswith("LOCAL_")
    )
    is_achromatic = (
        isinstance(color_match, dict)
        and color_match.get("space") == "ACHROMATIC_LUMINANCE_RANGE"
    )
    selected_path_bbox = [
        min(int(item["bbox"][0]) for item in selected_group),
        min(int(item["bbox"][1]) for item in selected_group),
        max(int(item["bbox"][2]) for item in selected_group),
        max(int(item["bbox"][3]) for item in selected_group),
    ]
    plot_box_values = result.get("plot_box") or [0, 0, 0, 0]
    plot_width = max(1, int(plot_box_values[2]) - int(plot_box_values[0]))
    plot_height = max(1, int(plot_box_values[3]) - int(plot_box_values[1]))
    horizontal_gridline_like = bool(
        is_achromatic
        and (selected_path_bbox[2] - selected_path_bbox[0]) >= plot_width * 0.60
        and (selected_path_bbox[3] - selected_path_bbox[1]) <= max(2, plot_height * 0.004)
    )
    partial_review_required = bool(
        len(selected_group) > 1
        or path_qc.get("partial_path_review_required")
        or path_qc.get("status") == "PARTIAL_PATHS_NEEDS_REVIEW"
        or local_fragment_count
        or horizontal_gridline_like
    )
    path_qc.update({
        "selected_branch_index": int(selected_index),
        "selected_path_count": int(len(selected_group)),
        "path_segments": path_segments,
        "local_fragment_count": int(local_fragment_count),
        "partial_path_review_required": partial_review_required,
    })
    boxes = [item["bbox"] for item in selected_group]
    component_bbox = [
        min(int(box[0]) for box in boxes),
        min(int(box[1]) for box in boxes),
        max(int(box[2]) for box in boxes),
        max(int(box[3]) for box in boxes),
    ]
    component_pixel_count = int(
        sum(item.get("pixel_count", 0) for item in selected_group)
    )
    return points, {
        "status": (
            "EXTRACTED_PROVISIONAL_NEEDS_REVIEW"
            if partial_review_required else "EXTRACTED_PROVISIONAL"
        ),
        "method": (
            "raster_achromatic_connected_path"
            if isinstance(color_match, dict)
            and color_match.get("space") == "ACHROMATIC_LUMINANCE_RANGE"
            else "raster_color_connected_path"
        ),
        "path_model": "CONNECTED_2D_PIXEL_COMPONENTS_WITH_EXPLICIT_SEGMENT_BREAKS",
        "path_order": "LEFT_TO_RIGHT_WITHIN_EACH_DISCONNECTED_SEGMENT",
        "component_index": selected_index,
        "component_count": len(groups),
        "component_bbox": component_bbox,
        "component_pixel_count": component_pixel_count,
        "component_x_span": int(component_bbox[2] - component_bbox[0]),
        "component_y_span": int(component_bbox[3] - component_bbox[1]),
        "path_points": len(points),
        "path_segment_count": len(path_segments),
        "path_segments": path_segments,
        "plot_box": result.get("plot_box"),
        "qc_status": (
            "NEEDS_REVIEW_PARTIAL_PATH"
            if partial_review_required else "PROVISIONAL_UNCALIBRATED"
        ),
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
        "edge_axis_columns_removed": result.get("edge_axis_columns_removed", []),
        "axis_spine_exclusion": result.get("axis_spine_exclusion", {}),
        "component_detection": {
            "active_pixels": result.get("active_pixels"),
            "rejected_components": result.get("rejected_components", []),
            "min_component_pixels": result.get("min_component_pixels"),
            "min_component_x_span": result.get("min_component_x_span"),
            "connectivity": result.get("connectivity"),
        },
        "path_qc": path_qc,
        "review_required": partial_review_required,
        "excluded_partial_branches": (
            auto_excluded
            + _compact_rejected_review_candidates(
                result.get("rejected_components", []), selected_group
            )
        ),
        "branch_index": selected_index,
        "branch_count": branch_count or len(groups),
        "partial_fragment_review": partial_fragment_review,
        "partial_fragment_tracking": partial_fragment_tracking,
        "achromatic_geometry_review": {
            "horizontal_gridline_like": horizontal_gridline_like,
            "rule": (
                "ACHROMATIC_PATH_WITH_X_SPAN_GE_60_PERCENT_AND_Y_SPAN_LE_0_4_PERCENT"
                if is_achromatic else None
            ),
            "status": "NEEDS_REVIEW" if horizontal_gridline_like else "NO_RULE_TRIGGERED",
        },
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
