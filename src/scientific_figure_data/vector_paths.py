from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class VectorPathCandidate:
    object_index: int
    points_pdf: tuple[tuple[float, float], ...]
    bbox_pdf: tuple[float, float, float, float]
    stroke_rgba: tuple[int, int, int, int] | None
    stroke_width_pdf: float | None
    segment_count: int
    closed: bool
    score: float


def _bounds(points: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    values = list(points)
    return (
        min(point[0] for point in values), min(point[1] for point in values),
        max(point[0] for point in values), max(point[1] for point in values),
    )


def _line_subpaths(path_object: dict) -> list[list[tuple[float, float]]] | None:
    segments = path_object.get("segments") or []
    output: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for segment in segments:
        kind = segment.get("type_name")
        point = segment.get("point_pdf")
        if kind == "MOVE_TO":
            if len(current) >= 2:
                output.append(current)
            current = []
            if point is not None:
                current.append((float(point[0]), float(point[1])))
        elif kind == "LINE_TO":
            if point is None:
                return None
            current.append((float(point[0]), float(point[1])))
        elif kind == "BEZIER_TO":
            # Control points are not silently reduced to straight lines.
            return None
        else:
            return None
        if segment.get("closes_subpath"):
            if len(current) >= 2:
                output.append(current)
            current = []
    if len(current) >= 2:
        output.append(current)
    return output


def _inside_fraction(bbox, plot_bbox) -> float:
    x0, y0, x1, y1 = bbox
    px0, py0, px1, py1 = plot_bbox
    width = max(0.0, min(x1, px1) - max(x0, px0))
    height = max(0.0, min(y1, py1) - max(y0, py0))
    intersection = width * height
    area = max(1e-9, (x1 - x0) * (y1 - y0))
    return min(1.0, intersection / area)


def vector_path_candidates(
    native_page: dict,
    plot_bbox_pdf: tuple[float, float, float, float],
    *,
    min_segments: int = 7,
    min_plot_width_fraction: float = 0.12,
    min_inside_fraction: float = 0.85,
) -> list[VectorPathCandidate]:
    """Return only bounded stroked polylines plausible as plot traces.

    This is a conservative preselector, not a semantic classifier. Curves with
    Bezier segments, closed shapes, axes/borders, fills, glyph outlines, and
    ambiguous geometry are excluded or left for review.
    """
    px0, py0, px1, py1 = [float(v) for v in plot_bbox_pdf]
    if px1 <= px0 or py1 <= py0:
        raise ValueError("plot_bbox_pdf must have positive width and height")
    plot_width, plot_height = px1 - px0, py1 - py0
    objects = native_page.get("objects", [])
    candidates = []
    for obj in objects:
        if obj.get("object_type") != "PATH" or obj.get("segments_truncated"):
            continue
        style = obj.get("path_style") or {}
        if style.get("stroke_enabled") is not True:
            continue
        fill_mode = style.get("fill_mode")
        if fill_mode not in (0, None) and style.get("stroke_enabled") is not True:
            continue
        color = style.get("stroke_rgba")
        if color and len(color) == 4 and int(color[3]) == 0:
            continue
        subpaths = _line_subpaths(obj)
        if not subpaths or len(subpaths) != 1:
            continue
        points = subpaths[0]
        # Deduplicate consecutive points without altering traversal order.
        clean = []
        for point in points:
            if not clean or math.dist(clean[-1], point) > 1e-7:
                clean.append(point)
        if len(clean) < min_segments:
            continue
        bbox = _bounds(clean)
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if width <= plot_width * min_plot_width_fraction:
            continue
        if _inside_fraction(bbox, (px0, py0, px1, py1)) < min_inside_fraction:
            continue
        # Long, thin paths are likely axes/grid lines, not a digitized curve.
        if width >= plot_width * 0.75 and height <= plot_height * 0.012:
            continue
        if height >= plot_height * 0.75 and width <= plot_width * 0.012:
            continue
        closed = any(segment.get("closes_subpath") for segment in obj.get("segments", []))
        if closed:
            continue
        # Mild deterministic score; used only to prioritize human review, not infer identity.
        x_coverage = width / plot_width
        y_coverage = min(1.0, height / plot_height)
        score = min(1.0, 0.55 * x_coverage + 0.25 * y_coverage + 0.20 * min(1.0, len(clean) / 40))
        candidates.append(VectorPathCandidate(
            object_index=int(obj["object_index"]),
            points_pdf=tuple(clean),
            bbox_pdf=bbox,
            stroke_rgba=tuple(int(value) for value in color) if color else None,
            stroke_width_pdf=style.get("stroke_width_pdf"),
            segment_count=len(clean),
            closed=closed,
            score=score,
        ))
    return sorted(candidates, key=lambda item: (-item.score, item.object_index))


def choose_vector_paths(
    native_page: dict,
    plot_bbox_pdf: tuple[float, float, float, float],
    requested_indices: list[int] | None = None,
) -> tuple[list[VectorPathCandidate], dict]:
    candidates = vector_path_candidates(native_page, plot_bbox_pdf)
    if requested_indices:
        by_id = {candidate.object_index: candidate for candidate in candidates}
        missing = [index for index in requested_indices if index not in by_id]
        if missing:
            return [], {"status": "NEEDS_REVIEW", "reason": "REQUESTED_VECTOR_OBJECT_NOT_A_SUPPORTED_POLYLINE",
                        "missing_object_indices": missing, "candidate_count": len(candidates)}
        return [by_id[index] for index in requested_indices], {
            "status": "SELECTED_EXPLICITLY", "candidate_count": len(candidates),
            "selected_object_indices": requested_indices,
        }
    if len(candidates) == 1:
        return candidates, {"status": "UNIQUE_LOW_AMBIGUITY_CANDIDATE",
                            "candidate_count": 1, "selected_object_indices": [candidates[0].object_index]}
    return [], {
        "status": "NEEDS_REVIEW",
        "reason": "NO_VECTOR_CANDIDATE" if not candidates else "MULTIPLE_VECTOR_CANDIDATES",
        "candidate_count": len(candidates),
        "candidate_object_indices": [candidate.object_index for candidate in candidates[:100]],
    }


def pdf_points_to_crop_pixels(
    points_pdf: Iterable[tuple[float, float]],
    *,
    crop_left_pdf: float,
    crop_top_pdf: float,
    render_scale: float,
) -> list[tuple[float, float]]:
    if render_scale <= 0:
        raise ValueError("render_scale must be positive")
    return [
        ((float(x) - crop_left_pdf) * render_scale,
         (crop_top_pdf - float(y)) * render_scale)
        for x, y in points_pdf
    ]
