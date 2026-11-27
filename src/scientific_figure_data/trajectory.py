from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any


def _box(width: int, height: int, values: tuple[float, float, float, float]):
    values = [float(v) for v in values]
    if max(abs(v) for v in values) <= 1.01:
        values[0] *= width
        values[2] *= width
        values[1] *= height
        values[3] *= height
    x0, y0, x1, y1 = (int(round(v)) for v in values)
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def _mask(pixels, threshold: float, edge_fraction: float):
    import numpy as np
    background = np.percentile(pixels.reshape(-1, 3).astype(float), 92, axis=0)
    contrast = np.sqrt(np.mean((pixels.astype(float) - background) ** 2, axis=2))
    mask = contrast >= threshold
    h, w = mask.shape
    edge = max(1, round(min(h, w) * edge_fraction))
    mask[:edge] = False
    mask[-edge:] = False
    mask[:, :edge] = False
    mask[:, -edge:] = False
    return background, contrast, mask


def _column_nodes(pixels, contrast, mask, x0: int, y0: int,
                  max_runs: int, max_height: int):
    import numpy as np
    nodes: list[dict[str, Any]] = []
    for local_x in range(mask.shape[1]):
        rows = np.flatnonzero(mask[:, local_x])
        if not rows.size:
            continue
        splits = np.flatnonzero(np.diff(rows) > 1) + 1
        column = []
        for run in np.split(rows, splits):
            if run.size > max_height:
                continue
            values = contrast[run, local_x]
            peak = int(np.argmax(values))
            y = int(run[peak])
            width = int(run.size)
            mean_score = float(np.mean(values))
            reward = (0.30 + min(1.50, mean_score / 42.0)
                      + min(0.18, 0.06 * (width - 1))
                      - max(0, width - 5) * 0.10)
            if reward <= 0:
                continue
            column.append({
                "x": local_x + x0, "y": y + y0, "width": width,
                "rgb": [int(v) for v in pixels[y, local_x]],
                "contrast": mean_score, "peak_contrast": float(values[peak]),
                "reward": reward,
            })
        column.sort(key=lambda node: (-node["reward"], node["y"], node["width"]))
        nodes.extend(column[:max_runs])
    return nodes


def _best_path(nodes: list[dict], *, max_gap: int, max_slope: float,
               slope_step: float, max_slope_change: float,
               curve_cost: float, gap_cost: float, color_cost: float,
               width_cost: float, start_cost: float):
    import math
    import numpy as np
    from bisect import bisect_left
    if not nodes:
        return [], 0.0
    nodes = sorted(nodes, key=lambda n: (n["x"], n["y"]))
    xs = [int(n["x"]) for n in nodes]
    slopes = np.arange(-max_slope, max_slope + slope_step * 0.5, slope_step)
    count = int(slopes.size)
    none = count
    scores = np.full((len(nodes), count + 1), -np.inf)
    prev_node = np.full((len(nodes), count + 1), -1, dtype=np.int32)
    prev_state = np.full((len(nodes), count + 1), -1, dtype=np.int16)
    for i, current in enumerate(nodes):
        scores[i, none] = current["reward"] - start_cost
        first = bisect_left(xs, current["x"] - max_gap - 1, 0, i)
        for j in range(first, i):
            previous = nodes[j]
            dx = current["x"] - previous["x"]
            if dx < 1 or dx > max_gap + 1:
                continue
            slope = (current["y"] - previous["y"]) / dx
            if abs(slope) > max_slope:
                continue
            si = max(0, min(count - 1, round((slope - slopes[0]) / slope_step)))
            qs = float(slopes[si])
            if abs(slope - qs) > slope_step * 0.75:
                continue
            color_delta = math.sqrt(sum(
                (current["rgb"][k] - previous["rgb"][k]) ** 2 for k in range(3)
            ) / 3) / 255
            width_delta = abs(current["width"] - previous["width"]) / max(
                1, current["width"], previous["width"]
            )
            base = gap_cost * (dx - 1) + color_cost * color_delta + width_cost * width_delta
            transition = curve_cost * np.abs(slopes - qs)
            valid = np.abs(slopes - qs) <= max_slope_change
            candidates = np.where(valid, scores[j, :count] - transition, -np.inf)
            state = int(np.argmax(candidates))
            value = float(candidates[state])
            if scores[j, none] > value:
                state, value = none, float(scores[j, none])
            candidate = value - base + current["reward"]
            if candidate > scores[i, si]:
                scores[i, si] = candidate
                prev_node[i, si] = j
                prev_state[i, si] = state
    end_node, end_state = np.unravel_index(int(np.argmax(scores)), scores.shape)
    best_score = float(scores[end_node, end_state])
    indices, seen = [], set()
    i, state = int(end_node), int(end_state)
    while i >= 0 and (i, state) not in seen:
        seen.add((i, state))
        indices.append(i)
        i, state = int(prev_node[i, state]), int(prev_state[i, state])
    indices.reverse()
    return [nodes[i] for i in indices], best_score


def _angle_difference_pi(a: float, b: float) -> float:
    """Smallest undirected angle difference in radians (line direction is modulo pi)."""
    import math
    return abs((a - b + math.pi / 2) % math.pi - math.pi / 2)


def _attach_local_tangents(nodes: list[dict], contrast, x0: int, y0: int,
                           radius: int = 2) -> None:
    """Estimate a local line tangent from the contrast structure tensor."""
    import math
    import numpy as np

    gy, gx = np.gradient(contrast.astype(np.float32))
    height, width = contrast.shape
    for node in nodes:
        x = int(node["x"]) - x0
        y = int(node["y"]) - y0
        xa, xb = max(0, x - radius), min(width, x + radius + 1)
        ya, yb = max(0, y - radius), min(height, y + radius + 1)
        patch_x, patch_y = gx[ya:yb, xa:xb], gy[ya:yb, xa:xb]
        jxx = float(np.sum(patch_x * patch_x))
        jyy = float(np.sum(patch_y * patch_y))
        jxy = float(np.sum(patch_x * patch_y))
        matrix = np.asarray([[jxx, jxy], [jxy, jyy]], dtype=np.float64)
        values, vectors = np.linalg.eigh(matrix)
        tangent = vectors[:, 0]
        if tangent[0] < 0:
            tangent = -tangent
        energy = float(values[0] + values[1])
        confidence = float(values[1] - values[0]) / energy if energy > 1e-8 else 0.0
        node["_tangent_angle"] = math.atan2(float(tangent[1]), float(tangent[0]))
        node["_tangent_confidence"] = max(0.0, min(1.0, confidence))


def _global_node_disjoint_paths(
    nodes: list[dict], contrast, x0: int, y0: int, *,
    max_tracks: int, max_gap: int, max_slope: float,
    start_cost: float, gap_cost: float, angle_cost: float,
    color_cost: float, width_cost: float, max_graph_edges: int = 300_000,
) -> tuple[list[dict], dict]:
    """Select globally node-disjoint paths with successive-shortest-path min-cost flow.

    Every run-node has unit capacity. Residual edges allow later augmentations to
    reroute earlier choices, unlike sequential greedy path peeling.
    """
    import heapq
    import math

    if not nodes:
        return [], {"flow_count": 0, "transition_edges": 0, "objective": 0.0}
    ordered = sorted(nodes, key=lambda node: (int(node["x"]), int(node["y"])))
    count = len(ordered)
    if count > 6000:
        return [], {
            "flow_count": 0, "transition_edges": 0, "objective": 0.0,
            "status": "NODE_BUDGET_EXCEEDED", "node_count": count,
        }

    _attach_local_tangents(ordered, contrast, x0, y0)
    by_x: dict[int, list[int]] = {}
    for index, node in enumerate(ordered):
        by_x.setdefault(int(node["x"]), []).append(index)

    source, sink = 2 * count, 2 * count + 1
    graph: list[list[list[Any]]] = [[] for _ in range(2 * count + 2)]

    def add_edge(u: int, v: int, capacity: int, cost: float):
        forward = [v, len(graph[v]), capacity, float(cost)]
        reverse = [u, len(graph[u]), 0, -float(cost)]
        graph[u].append(forward)
        graph[v].append(reverse)
        return forward

    node_edges = []
    transitions: list[tuple[int, int, list[Any], float]] = []
    transitions_by_node: list[list[tuple[int, list[Any]]]] = [[] for _ in range(count)]
    for index, node in enumerate(ordered):
        incoming, outgoing = 2 * index, 2 * index + 1
        add_edge(source, incoming, 1, start_cost)
        node_edges.append(add_edge(incoming, outgoing, 1, -float(node["reward"])))
        add_edge(outgoing, sink, 1, 0.0)

    for index, current in enumerate(ordered):
        current_x = int(current["x"])
        for dx in range(1, max_gap + 2):
            for next_index in by_x.get(current_x + dx, []):
                following = ordered[next_index]
                dy = int(following["y"]) - int(current["y"])
                if abs(dy / dx) > max_slope:
                    continue
                rgb_delta = math.sqrt(sum(
                    (int(current["rgb"][k]) - int(following["rgb"][k])) ** 2
                    for k in range(3)
                ) / 3.0) / 255.0
                width_delta = abs(
                    int(current["width"]) - int(following["width"])
                ) / max(1, int(current["width"]), int(following["width"]))
                edge_angle = math.atan2(float(dy), float(dx))
                conf_a = float(current.get("_tangent_confidence", 0.0))
                conf_b = float(following.get("_tangent_confidence", 0.0))
                angle_a = _angle_difference_pi(
                    edge_angle, float(current.get("_tangent_angle", edge_angle))
                )
                angle_b = _angle_difference_pi(
                    edge_angle, float(following.get("_tangent_angle", edge_angle))
                )
                tangent_error = (
                    conf_a * angle_a + conf_b * angle_b
                ) / max(1e-8, conf_a + conf_b)
                tangent_error /= math.pi / 2.0
                cost = (
                    gap_cost * (dx - 1) + angle_cost * tangent_error
                    + color_cost * rgb_delta + width_cost * width_delta
                )
                edge = add_edge(2 * index + 1, 2 * next_index, 1, cost)
                transitions.append((index, next_index, edge, cost))
                transitions_by_node[index].append((next_index, edge))
                if len(transitions) > max_graph_edges:
                    return [], {
                        "flow_count": 0, "transition_edges": len(transitions),
                        "objective": 0.0, "status": "EDGE_BUDGET_EXCEEDED",
                        "node_count": count,
                    }

    infinity = float("inf")
    potentials = [infinity] * len(graph)
    potentials[source] = 0.0
    for index, node in enumerate(ordered):
        incoming, outgoing = 2 * index, 2 * index + 1
        potentials[incoming] = min(potentials[incoming], start_cost)
        potentials[outgoing] = min(
            potentials[outgoing], potentials[incoming] - float(node["reward"])
        )
        potentials[sink] = min(potentials[sink], potentials[outgoing])
        for next_index, edge in transitions_by_node[index]:
            next_incoming = 2 * next_index
            potentials[next_incoming] = min(
                potentials[next_incoming], potentials[outgoing] + float(edge[3])
            )
    potentials = [value if math.isfinite(value) else 0.0 for value in potentials]

    flow, objective = 0, 0.0
    while flow < max_tracks:
        distances = [infinity] * len(graph)
        previous_node, previous_edge = [-1] * len(graph), [-1] * len(graph)
        distances[source] = 0.0
        queue = [(0.0, source)]
        while queue:
            distance, u = heapq.heappop(queue)
            if distance > distances[u] + 1e-12:
                continue
            for edge_index, edge in enumerate(graph[u]):
                if edge[2] <= 0:
                    continue
                v = int(edge[0])
                reduced = float(edge[3]) + potentials[u] - potentials[v]
                if reduced < 0.0 and reduced > -1e-8:
                    reduced = 0.0
                candidate = distance + reduced
                if candidate + 1e-12 < distances[v]:
                    distances[v] = candidate
                    previous_node[v], previous_edge[v] = u, edge_index
                    heapq.heappush(queue, (candidate, v))
        if not math.isfinite(distances[sink]):
            break
        actual_cost = distances[sink] - potentials[source] + potentials[sink]
        if actual_cost >= -1e-8:
            break
        for vertex, distance in enumerate(distances):
            if math.isfinite(distance):
                potentials[vertex] += distance
        vertex = sink
        while vertex != source:
            parent, edge_index = previous_node[vertex], previous_edge[vertex]
            if parent < 0 or edge_index < 0:
                raise RuntimeError("Incomplete augmenting path in trajectory flow graph")
            edge = graph[parent][edge_index]
            edge[2] -= 1
            graph[vertex][edge[1]][2] += 1
            vertex = parent
        flow += 1
        objective += -actual_cost

    selected = {index for index, edge in enumerate(node_edges) if edge[2] == 0}
    successor: dict[int, int] = {}
    predecessor: dict[int, int] = {}
    edge_costs: dict[tuple[int, int], float] = {}
    for left, right, edge, cost in transitions:
        if edge[2] == 0:
            successor[left], predecessor[right] = right, left
            edge_costs[(left, right)] = cost

    paths, visited = [], set()
    starts = sorted(
        (index for index in selected if index not in predecessor),
        key=lambda index: (ordered[index]["x"], ordered[index]["y"]),
    )
    for start in starts:
        indices, current = [], start
        while current in selected and current not in visited:
            indices.append(current)
            visited.add(current)
            if current not in successor:
                break
            current = successor[current]
        if not indices:
            continue
        score = (
            sum(float(ordered[index]["reward"]) for index in indices) - start_cost
            - sum(edge_costs[(a, b)] for a, b in zip(indices, indices[1:]))
        )
        paths.append({"nodes": [ordered[index] for index in indices],
                      "objective": float(score)})
    paths.sort(key=lambda item: (
        -len(item["nodes"]), item["nodes"][0]["x"], item["nodes"][0]["y"]
    ))
    return paths, {
        "status": "PASS", "flow_count": flow, "selected_node_count": len(selected),
        "transition_edges": len(transitions), "objective": round(objective, 6),
        "node_disjoint": len(visited) == len(selected), "max_tracks": max_tracks,
    }


def _stats(path: list[dict], plot_width: int):
    import math
    import statistics

    path = sorted(path, key=lambda node: node["x"])
    xs, ys = [node["x"] for node in path], [node["y"] for node in path]
    widths = [node["width"] for node in path]
    gaps = [max(0, xs[index] - xs[index - 1] - 1)
            for index in range(1, len(xs))]
    lengths, current = [], 1
    for gap in gaps:
        if gap:
            lengths.append(current)
            current = 1
        else:
            current += 1
    lengths.append(current)
    positive_gaps = [gap for gap in gaps if gap]
    gap_cv = (
        statistics.pstdev(positive_gaps) / statistics.mean(positive_gaps)
        if len(positive_gaps) > 1 else None
    )
    length_cv = (
        statistics.pstdev(lengths) / statistics.mean(lengths)
        if len(lengths) > 1 else None
    )
    slopes = [(ys[index] - ys[index - 1]) / max(1, xs[index] - xs[index - 1])
              for index in range(1, len(xs))]
    curvature = [abs(slopes[index] - slopes[index - 1])
                 for index in range(1, len(slopes))]
    median_curvature = statistics.median(curvature) if curvature else 0.0
    mean_width = statistics.mean(widths)
    width_cv = statistics.pstdev(widths) / mean_width if mean_width else 0.0
    median_gap = statistics.median(positive_gaps) if positive_gaps else 0.0
    median_segment_length = statistics.median(lengths)
    segments = len(lengths)
    dash_pattern = (
        segments >= 3 and gap_cv is not None and length_cv is not None
        and gap_cv <= 0.55 and length_cv <= 0.60 and median_gap >= 2.0
        and median_segment_length >= 3.0
        and 0.20 <= median_gap / max(1.0, median_segment_length) <= 1.8
    )
    small_gaps = (
        segments <= 3 and len(positive_gaps) <= 2
        and (not positive_gaps
             or max(positive_gaps) <= max(2, round(plot_width * 0.02)))
    )
    if dash_pattern:
        style = "DASHED_CANDIDATE"
    elif segments == 1:
        style = "SOLID_CANDIDATE"
    elif small_gaps:
        style = "SOLID_WITH_OCCLUSION_CANDIDATE"
    else:
        style = "DISCONTINUOUS_UNRESOLVED"

    dash_periodicity = 0.0
    if dash_pattern:
        dash_periodicity = math.exp(-float(gap_cv)) * math.exp(-float(length_cv))
    elif positive_gaps and length_cv is not None and gap_cv is not None:
        dash_periodicity = (
            0.25 * math.exp(-float(gap_cv)) * math.exp(-float(length_cv))
        )
    x_span = max(1, xs[-1] - xs[0] + 1)
    active = len(set(xs)) / x_span
    coverage = x_span / max(1, plot_width)
    rgb_median = [statistics.median(node["rgb"][k] for node in path)
                  for k in range(3)]
    color_spread = statistics.median(
        math.sqrt(sum((node["rgb"][k] - rgb_median[k]) ** 2 for k in range(3)) / 3)
        / 255.0 for node in path
    )
    raw_confidence = (
        0.28 * min(1.0, coverage / 0.65)
        + 0.24 * min(1.0, active / (0.58 if dash_pattern else 0.90))
        + 0.24 * math.exp(-median_curvature / 1.25)
        + 0.14 * math.exp(-color_spread / 0.12)
        + 0.10 * math.exp(-max(0.0, width_cv - 0.20))
    )
    structure_factor = (
        1.0 if style in {"SOLID_CANDIDATE", "SOLID_WITH_OCCLUSION_CANDIDATE"}
        else dash_periodicity if dash_pattern else 0.25
    )
    return {
        "point_count": len(path), "segment_count": segments,
        "segment_lengths_columns": lengths, "gap_lengths_columns": positive_gaps,
        "gap_cv": round(gap_cv, 4) if gap_cv is not None else None,
        "segment_length_cv": round(length_cv, 4) if length_cv is not None else None,
        "median_gap_columns": round(float(median_gap), 3),
        "median_segment_length_columns": round(float(median_segment_length), 3),
        "dash_periodicity_score": round(float(dash_periodicity), 4),
        "x_range": [xs[0], xs[-1]], "y_range": [min(ys), max(ys)],
        "x_coverage_fraction": round(coverage, 4),
        "active_column_fraction": round(active, 4),
        "median_abs_curvature": round(median_curvature, 4),
        "median_run_width": round(statistics.median(widths), 3),
        "run_width_cv": round(width_cv, 4),
        "line_style_candidate": style,
        "confidence": round(raw_confidence * structure_factor, 4),
    }


def detect_monotonic_raster_trajectories(
    image_path: str | Path, plot_box: tuple[float, float, float, float], *,
    max_tracks: int = 12, max_gap_columns: int = 12, max_abs_slope: float = 6.0,
    slope_step: float = 0.5, min_contrast: float = 12.0, max_run_height: int = 12,
    max_nodes_per_column: int = 16, min_x_coverage: float = 0.25,
    min_active_columns: int = 48, min_active_fraction: float = 0.20,
    start_penalty: float = 6.0, max_slope_change: float = 1.5,
    curvature_penalty: float = 1.20, gap_penalty: float = 0.35,
    color_penalty: float = 2.4, width_penalty: float = 0.30,
    min_dashed_points: int = 24, min_dashed_x_coverage: float = 0.10,
    min_dashed_active_fraction: float = 0.30,
    boundary_exclusion_fraction: float = 0.012,
    max_candidate_pixels: int = 250_000,
) -> dict:
    """Discover globally competing review-only paths from original image pixels."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError("Install Pillow and NumPy with the images extra.") from exc

    path = Path(image_path)
    if not path.is_file():
        return {"status": "NEEDS_REVIEW", "reason": "SOURCE_IMAGE_UNAVAILABLE", "tracks": []}
    with Image.open(path) as source_image:
        image_width, image_height = source_image.size
        x0, y0, x1, y1 = _box(image_width, image_height, plot_box)
        if x1 <= x0 or y1 <= y0:
            return {"status": "NEEDS_REVIEW", "reason": "INVALID_PLOT_BOX", "tracks": []}
        pixels = np.asarray(
            source_image.convert("RGB").crop((x0, y0, x1, y1)), dtype=np.uint8
        )
    region_height, region_width = pixels.shape[:2]
    if region_width < 32 or region_height < 16:
        return {"status": "NEEDS_REVIEW", "reason": "PLOT_BOX_TOO_SMALL", "tracks": []}
    background, contrast, mask = _mask(pixels, min_contrast, boundary_exclusion_fraction)
    candidate_count = int(mask.sum())
    if candidate_count > max_candidate_pixels:
        return {
            "status": "NEEDS_REVIEW", "reason": "CANDIDATE_PIXEL_BUDGET_EXCEEDED",
            "candidate_pixel_count": candidate_count, "tracks": [],
        }
    if candidate_count < min_active_columns:
        return {
            "status": "NO_TRAJECTORY_CANDIDATES",
            "reason": "INSUFFICIENT_CONTRAST_PIXELS", "tracks": [],
        }
    nodes = _column_nodes(
        pixels, contrast, mask, x0, y0, max_nodes_per_column, max_run_height
    )
    if not nodes:
        return {"status": "NO_TRAJECTORY_CANDIDATES", "reason": "NO_COLUMN_RUNS", "tracks": []}

    path_solutions, flow_diagnostics = _global_node_disjoint_paths(
        nodes, contrast, x0, y0,
        max_tracks=max_tracks, max_gap=max_gap_columns,
        max_slope=max_abs_slope, start_cost=start_penalty,
        gap_cost=gap_penalty, angle_cost=curvature_penalty,
        color_cost=color_penalty, width_cost=width_penalty,
    )
    if flow_diagnostics.get("status") in {"NODE_BUDGET_EXCEEDED", "EDGE_BUDGET_EXCEEDED"}:
        return {
            "status": "NEEDS_REVIEW", "reason": flow_diagnostics["status"],
            "candidate_pixel_count": candidate_count,
            "candidate_run_count": len(nodes), "flow_diagnostics": flow_diagnostics,
            "tracks": [],
        }

    tracks, rejected = [], []
    minimum_solid_nodes = max(min_active_columns, round(region_width * 0.18))
    for track_index, solution in enumerate(path_solutions):
        path_nodes = solution["nodes"]
        stats = _stats(path_nodes, region_width)
        style = stats["line_style_candidate"]
        solid_style = style in {
            "SOLID_CANDIDATE", "SOLID_WITH_OCCLUSION_CANDIDATE"
        }
        solid_eligible = (
            solid_style and len(path_nodes) >= minimum_solid_nodes
            and stats["x_coverage_fraction"] >= min_x_coverage
            and stats["active_column_fraction"] >= max(0.65, min_active_fraction)
        )
        dashed_eligible = (
            style == "DASHED_CANDIDATE" and len(path_nodes) >= min_dashed_points
            and stats["x_coverage_fraction"] >= min_dashed_x_coverage
            and stats["active_column_fraction"] >= min_dashed_active_fraction
            and stats["dash_periodicity_score"] >= 0.30
        )
        eligible = solid_eligible or dashed_eligible
        if eligible:
            status = "CANDIDATE_REVIEW"
            reason = "COHERENT_SOLID_PATH" if solid_eligible else "PERIODIC_DASH_PATTERN"
        elif style == "DISCONTINUOUS_UNRESOLVED":
            status = "UNRESOLVED_FRAGMENT_PATH"
            reason = "GAP_PATTERN_NOT_SUFFICIENTLY_REGULAR"
        else:
            status = "REJECTED_WEAK_PATH"
            reason = "INSUFFICIENT_COVERAGE_OR_SUPPORT"

        segments, segment, previous_x = [], [], None
        for node in path_nodes:
            if previous_x is not None and node["x"] > previous_x + 1 and segment:
                segments.append(segment)
                segment = []
            segment.append([int(node["x"]), int(node["y"])])
            previous_x = node["x"]
        if segment:
            segments.append(segment)
        record = {
            "track_id": f"TR{track_index + 1:02d}",
            "status": status, "eligible_for_review": bool(eligible),
            "review_reason": reason,
            "path_objective": round(float(solution["objective"]), 6),
            "median_source_rgb": [
                int(round(float(np.median([node["rgb"][k] for node in path_nodes]))))
                for k in range(3)
            ],
            **stats, "segments": segments,
            "point_records": [
                {
                    "pixel_x": int(node["x"]), "pixel_y": int(node["y"]),
                    "source_rgb": node["rgb"], "source_run_width": node["width"],
                    "mean_contrast": float(node["contrast"]),
                    "peak_contrast": float(node["peak_contrast"]),
                }
                for node in path_nodes
            ],
            "source_points_are_mask_members": all(
                mask[int(node["y"] - y0), int(node["x"] - x0)] for node in path_nodes
            ),
            "source_pixel_policy": "ONE_REAL_SOURCE_PIXEL_PER_ACTIVE_COLUMN",
        }
        record["segment_count"] = len(segments)
        record["point_count"] = sum(len(points) for points in segments)
        tracks.append(record)
        if not eligible:
            rejected.append(record["track_id"])

    review_count = sum(bool(track["eligible_for_review"]) for track in tracks)
    return {
        "status": "CANDIDATE_TRACKS_FOUND" if review_count else "NO_CONFIDENT_TRAJECTORY_CANDIDATES",
        "method": "GLOBAL_NODE_DISJOINT_MIN_COST_FLOW_WITH_LOCAL_TANGENTS",
        "experimental": True, "plot_box": [x0, y0, x1, y1],
        "image_size": [image_width, image_height],
        "estimated_background_rgb": [round(float(value), 2) for value in background],
        "candidate_pixel_count": candidate_count,
        "candidate_run_count": len(nodes),
        "review_candidate_count": review_count,
        "rejected_candidate_track_ids": rejected,
        "tracks": tracks, "flow_diagnostics": flow_diagnostics,
        "parameters": {
            "max_tracks": max_tracks, "max_gap_columns": max_gap_columns,
            "max_abs_slope": max_abs_slope, "slope_step": slope_step,
            "min_contrast": min_contrast, "max_run_height": max_run_height,
            "max_nodes_per_column": max_nodes_per_column,
            "min_x_coverage": min_x_coverage,
            "min_active_columns": minimum_solid_nodes,
            "min_active_fraction": min_active_fraction,
            "start_penalty": start_penalty, "max_slope_change": max_slope_change,
            "curvature_penalty": curvature_penalty, "gap_penalty": gap_penalty,
            "color_penalty": color_penalty, "width_penalty": width_penalty,
            "min_dashed_points": min_dashed_points,
            "min_dashed_x_coverage": min_dashed_x_coverage,
            "min_dashed_active_fraction": min_dashed_active_fraction,
            "boundary_exclusion_fraction": boundary_exclusion_fraction,
        },
        "source_pixel_integrity": {
            "status": "PASS" if all(
                track["source_points_are_mask_members"] for track in tracks
            ) else "FAIL",
            "generated_pixels": 0, "interpolated_pixels": 0,
        },
        "note": (
            "Global node-disjoint path hypotheses only; candidate-review status is not "
            "acceptance as scientific measurements."
        ),
    }


def write_trajectory_artifacts(image_path: str | Path,
                               plot_box: tuple[float, float, float, float],
                               output_dir: str | Path, **options) -> dict:
    """Write offline overlays, point CSV, inventory, and source-pixel diagnostics."""
    import html
    import numpy as np
    from PIL import Image, ImageDraw
    source_path = Path(image_path).resolve()
    output = Path(output_dir).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if output == source_path.parent or source_path.is_relative_to(output):
        raise ValueError("Output directory must not contain or replace the source image")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    result = detect_monotonic_raster_trajectories(source_path, plot_box, **options)
    shutil.copy2(source_path, output / "01_original.png")
    with Image.open(source_path) as src:
        original = src.convert("RGB")
        width, height = original.size
        x0, y0, x1, y1 = _box(width, height, plot_box)
        crop = np.asarray(original.crop((x0, y0, x1, y1)), dtype=np.uint8)
    _, _, local_mask = _mask(
        crop, float(result.get("parameters", {}).get("min_contrast", 12)),
        float(result.get("parameters", {}).get("boundary_exclusion_fraction", .012)),
    )
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y0:y1, x0:x1] = local_mask.astype(np.uint8) * 255
    Image.fromarray(full_mask).save(output / "02_candidate_mask.png")
    palette = [(255, 40, 150), (0, 160, 255), (255, 170, 0), (0, 190, 120),
               (160, 80, 255), (230, 60, 50), (30, 180, 180), (120, 90, 40)]
    combined = original.copy()
    point_fields = ["track_id", "segment_index", "point_index", "pixel_x", "pixel_y",
                    "source_r", "source_g", "source_b", "source_run_width",
                    "mean_contrast", "peak_contrast", "source_pixel_verified"]
    inventory_fields = ["track_id", "status", "eligible_for_review", "point_count",
                        "segment_count", "x_start", "x_end", "y_min", "y_max",
                        "x_coverage_fraction", "active_column_fraction",
                        "line_style_candidate", "confidence", "path_score",
                        "median_source_rgb", "median_run_width", "run_width_cv",
                        "gap_lengths_columns", "segment_lengths_columns", "gap_cv",
                        "segment_length_cv", "median_gap_columns",
                        "median_segment_length_columns", "dash_periodicity_score",
                        "review_reason", "path_objective"]
    rows = []
    with (output / "all_series_digitized.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=point_fields)
        writer.writeheader()
        for index, track in enumerate(result.get("tracks", [])):
            color = palette[index % len(palette)]
            individual = original.copy()
            segment_map = {
                (int(x), int(y)): sid
                for sid, segment in enumerate(track["segments"]) for x, y in segment
            }
            for point_index, record in enumerate(track["point_records"]):
                x, y = int(record["pixel_x"]), int(record["pixel_y"])
                verified = 0 <= x < width and 0 <= y < height and full_mask[y, x] > 0
                rgb = record["source_rgb"]
                writer.writerow({
                    "track_id": track["track_id"],
                    "segment_index": segment_map.get((x, y), -1),
                    "point_index": point_index, "pixel_x": x, "pixel_y": y,
                    "source_r": rgb[0], "source_g": rgb[1], "source_b": rgb[2],
                    "source_run_width": record["source_run_width"],
                    "mean_contrast": record["mean_contrast"],
                    "peak_contrast": record["peak_contrast"],
                    "source_pixel_verified": verified,
                })
                if verified:
                    ImageDraw.Draw(combined).point((x, y), fill=color)
                    ImageDraw.Draw(individual).point((x, y), fill=color)
            individual.save(output / f"track_{track['track_id']}_overlay.png")
            xr, yr = track["x_range"], track["y_range"]
            rows.append({
                "track_id": track["track_id"], "status": track["status"],
                "eligible_for_review": track["eligible_for_review"],
                "point_count": track["point_count"], "segment_count": track["segment_count"],
                "x_start": xr[0], "x_end": xr[1], "y_min": yr[0], "y_max": yr[1],
                "x_coverage_fraction": track["x_coverage_fraction"],
                "active_column_fraction": track["active_column_fraction"],
                "line_style_candidate": track["line_style_candidate"],
                "confidence": track["confidence"], "path_score": track["path_score"],
                "median_source_rgb": json.dumps(track["median_source_rgb"]),
                "median_run_width": track["median_run_width"],
                "run_width_cv": track["run_width_cv"],
                "gap_lengths_columns": json.dumps(track["gap_lengths_columns"]),
                "segment_lengths_columns": json.dumps(track["segment_lengths_columns"]),
                "gap_cv": track.get("gap_cv"),
                "segment_length_cv": track.get("segment_length_cv"),
                "median_gap_columns": track.get("median_gap_columns"),
                "median_segment_length_columns": track.get("median_segment_length_columns"),
                "dash_periodicity_score": track.get("dash_periodicity_score"),
                "review_reason": track.get("review_reason"),
                "path_objective": track.get("path_objective"),
            })
    combined.save(output / "03_reconstructed_trajectories.png")
    combined.save(output / "04_all_series_overlay.png")
    with (output / "trajectory_inventory.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=inventory_fields)
        writer.writeheader()
        writer.writerows(rows)
    result["artifact_summary"] = {
        "output_dir": str(output), "source_image": str(source_path),
        "tracks_written": len(result.get("tracks", [])),
        "review_candidates": result.get("review_candidate_count", 0),
    }
    (output / "trajectory_diagnostics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    images = ["01_original.png", "02_candidate_mask.png",
              "03_reconstructed_trajectories.png", "04_all_series_overlay.png"]
    images += sorted(p.name for p in output.glob("track_TR*_overlay.png"))
    cards = "".join(
        f"<figure><img src='{html.escape(name, quote=True)}' alt='{html.escape(name)}'>"
        f"<figcaption>{html.escape(name)}</figcaption></figure>" for name in images
    )
    table = "".join(
        f"<tr><td>{r['track_id']}</td><td>{r['status']}</td>"
        f"<td>{r['line_style_candidate']}</td><td>{r['point_count']}</td>"
        f"<td>{r['segment_count']}</td><td>{r['x_coverage_fraction']}</td></tr>"
        for r in rows
    )
    document = (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Experimental raster trajectory hypotheses</title>"
        "<style>body{font:15px system-ui,sans-serif;margin:24px;color:#222}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}"
        "figure{margin:0}img{max-width:100%;height:auto;border:1px solid #bbb}"
        "figcaption{margin-top:6px}table{border-collapse:collapse;margin:16px 0}"
        "td,th{border:1px solid #ccc;padding:5px 8px;text-align:left}</style>"
        "<h1>Experimental raster trajectory hypotheses</h1>"
        "<p>Candidate paths only, not accepted scientific measurements. "
        "Every point is a source pixel; no gap interpolation or smoothing.</p>"
        f"<p>Review candidates: {result.get('review_candidate_count', 0)}</p>"
        f"<div class='grid'>{cards}</div><h2>Inventory</h2>"
        "<table><tr><th>ID</th><th>Status</th><th>Style</th><th>Points</th>"
        f"<th>Segments</th><th>X coverage</th></tr>{table}</table>"
        "<p><a href='trajectory_inventory.csv'>Inventory CSV</a> · "
        "<a href='all_series_digitized.csv'>Point CSV</a> · "
        "<a href='trajectory_diagnostics.json'>Diagnostics JSON</a></p></html>"
    )
    (output / "index.html").write_text(document, encoding="utf-8")
    return result
