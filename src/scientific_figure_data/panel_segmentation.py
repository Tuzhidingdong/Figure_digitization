from __future__ import annotations

from pathlib import Path
from typing import Any


def _runs(mask) -> list[tuple[int, int]]:
    values = [bool(value) for value in mask]
    output: list[tuple[int, int]] = []
    start = None
    for index, value in enumerate(values + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            output.append((start, index))
            start = None
    return output


def _ink_mask(image):
    import numpy as np

    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    luminance = (
        0.2126 * rgb[:, :, 0].astype(np.float32)
        + 0.7152 * rgb[:, :, 1].astype(np.float32)
        + 0.0722 * rgb[:, :, 2].astype(np.float32)
    )
    chroma = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    return (luminance < 246) | ((chroma > 28) & (luminance < 252))


def _best_split(mask, rect: tuple[int, int, int, int], min_gap: int,
                projection_threshold: float, min_child_fraction: float):
    x0, y0, x1, y1 = rect
    region = mask[y0:y1, x0:x1]
    height, width = region.shape
    candidates = []

    for axis, profile, dimension in (
        ("horizontal", region.mean(axis=1), height),
        ("vertical", region.mean(axis=0), width),
    ):
        for start, end in _runs(profile <= projection_threshold):
            gap = end - start
            if gap < min_gap or start < dimension * 0.06 or end > dimension * 0.94:
                continue
            first_size, second_size = start, dimension - end
            if min(first_size, second_size) < dimension * min_child_fraction:
                continue
            if axis == "horizontal":
                first = mask[y0:y0 + start, x0:x1]
                second = mask[y0 + end:y1, x0:x1]
                boxes = (
                    (x0, y0, x1, y0 + start),
                    (x0, y0 + end, x1, y1),
                )
            else:
                first = mask[y0:y1, x0:x0 + start]
                second = mask[y0:y1, x0 + end:x1]
                boxes = (
                    (x0, y0, x0 + start, y1),
                    (x0 + end, y0, x1, y1),
                )
            total_area = max(1, int(mask.shape[0] * mask.shape[1]))
            if any(
                (box[2] - box[0]) * (box[3] - box[1]) < total_area * 0.045
                for box in boxes
            ):
                continue
            if min(int(first.sum()), int(second.sum())) < 35:
                continue
            if min(float(first.mean()), float(second.mean())) < 0.002:
                continue
            gap_fraction = gap / dimension
            balance = min(first_size, second_size) / max(first_size, second_size)
            blankness = 1.0 - min(
                1.0, float(profile[start:end].mean()) / max(projection_threshold, 1e-9)
            )
            score = (
                0.55 * min(1.0, gap_fraction / 0.04)
                + 0.30 * balance
                + 0.15 * blankness
            )
            candidates.append((score, axis, start, end, boxes))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    best = candidates[0]
    return {
        "score": float(best[0]),
        "axis": best[1],
        "start": best[2],
        "end": best[3],
        "boxes": best[4],
    }


def detect_panel_regions(
    image_path: Path,
    *,
    max_panels: int = 12,
    projection_threshold: float = 0.006,
    minimum_gap_fraction: float = 0.008,
    minimum_child_fraction: float = 0.20,
) -> dict[str, Any]:
    """Conservatively split a raster figure at broad, near-white gutters.

    This is geometric panel segmentation only. It does not identify scientific
    content or infer panel labels. A single unsplit image is returned as a
    reviewable fallback rather than inventing panel boundaries.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Panel segmentation requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        width, height = source.size
        if width < 100 or height < 100:
            return {
                "status": "NEEDS_REVIEW",
                "reason": "IMAGE_TOO_SMALL_FOR_PANEL_SEGMENTATION",
                "image_size": [width, height],
                "panels": [],
            }
        mask = _ink_mask(source)

    if not bool(np.any(mask)):
        return {
            "status": "NEEDS_REVIEW",
            "reason": "NO_VISIBLE_FIGURE_CONTENT",
            "image_size": [width, height],
            "panels": [],
        }

    leaves: list[tuple[tuple[int, int, int, int], float]] = []

    def split(rect: tuple[int, int, int, int], inherited_score: float = 0.0) -> None:
        if len(leaves) >= max_panels:
            leaves.append((rect, inherited_score))
            return
        x0, y0, x1, y1 = rect
        minimum_gap = max(3, int(round(min(x1 - x0, y1 - y0) * minimum_gap_fraction)))
        candidate = _best_split(
            mask, rect, minimum_gap, projection_threshold, minimum_child_fraction
        )
        if candidate is None:
            leaves.append((rect, inherited_score))
            return
        for box in candidate["boxes"]:
            split(box, max(inherited_score, candidate["score"]))

    split((0, 0, width, height))
    if len(leaves) < 2:
        # Many scientific figures have touching or crowded panels without a
        # broad white gutter. Detect several independent plot frames directly
        # instead of silently treating the complete source figure as one panel.
        from .plot_region import detect_plot_box_candidates

        frame_detection = detect_plot_box_candidates(image_path)
        frame_candidates = frame_detection.get("candidates", [])
        if len(frame_candidates) >= 2:
            frames = [
                item for item in frame_candidates
                if isinstance(item.get("pixel_bbox"), list)
                and len(item["pixel_bbox"]) == 4
            ]
            panel_rows = []
            for index, candidate in enumerate(frames, 1):
                x0, y0, x1, y1 = [int(value) for value in candidate["pixel_bbox"]]
                frame_width, frame_height = x1 - x0, y1 - y0
                margin_x = min(max(8, round(frame_width * 0.16)), max(8, round(width * 0.12)))
                margin_y = min(max(8, round(frame_height * 0.20)), max(8, round(height * 0.14)))
                panel_x0, panel_y0 = max(0, x0 - margin_x), max(0, y0 - margin_y)
                panel_x1, panel_y1 = min(width, x1 + margin_x), min(height, y1 + margin_y)

                for other_index, other in enumerate(frames):
                    if other_index == index - 1:
                        continue
                    ox0, oy0, ox1, oy1 = [int(value) for value in other["pixel_bbox"]]
                    overlap_y = max(0, min(y1, oy1) - max(y0, oy0))
                    overlap_x = max(0, min(x1, ox1) - max(x0, ox0))
                    if overlap_y >= 0.30 * min(frame_height, oy1 - oy0):
                        if ox1 <= x0:
                            panel_x0 = max(panel_x0, (ox1 + x0) // 2)
                        elif ox0 >= x1:
                            panel_x1 = min(panel_x1, (x1 + ox0) // 2)
                    if overlap_x >= 0.30 * min(frame_width, ox1 - ox0):
                        if oy1 <= y0:
                            panel_y0 = max(panel_y0, (oy1 + y0) // 2)
                        elif oy0 >= y1:
                            panel_y1 = min(panel_y1, (y1 + oy0) // 2)

                if panel_x1 <= panel_x0 or panel_y1 <= panel_y0:
                    continue
                panel_rows.append({
                    "panel_id": f"auto-frame-{index:02d}",
                    "label": None,
                    "bbox": [panel_x0, panel_y0, panel_x1, panel_y1],
                    "bbox_coordinate_space": "IMAGE_PIXELS",
                    "plot_frame_bbox_pixels": [x0, y0, x1, y1],
                    "plot_frame_score": candidate.get("score"),
                    "segmentation_provenance": "AUTO_PLOT_FRAME_CANDIDATE_SEGMENTATION",
                    "segmentation_status": "PROVISIONAL_PLOT_FRAME_SPLIT",
                    "segmentation_confidence": round(
                        max(0.0, min(0.95, float(candidate.get("score", 0.0)))), 4
                    ),
                    "segmentation_confidence_status": "HEURISTIC_UNCALIBRATED",
                })

            if len(panel_rows) >= 2:
                return {
                    "status": "PROVISIONAL_PANELS_DETECTED",
                    "reason": "MULTIPLE_PLOT_FRAME_CANDIDATES",
                    "image_size": [width, height],
                    "panel_count": len(panel_rows),
                    "plot_frame_detection": frame_detection,
                    "panels": panel_rows,
                    "provisional": True,
                }

        if len(frame_candidates) == 1:
            candidate = frame_candidates[0]
            return {
                "status": "SINGLE_PLOT_FRAME_DETECTED",
                "reason": "ONE_SUPPORTED_PLOT_FRAME",
                "image_size": [width, height],
                "plot_frame_detection": frame_detection,
                "plot_frame_bbox_pixels": candidate.get("pixel_bbox"),
                "plot_frame_score": candidate.get("score"),
                "panels": [],
                "provisional": True,
            }

        return {
            "status": "NO_CONFIDENT_PANEL_SPLIT",
            "reason": "NO_WHITESPACE_GUTTER_OR_PLOT_FRAME_CANDIDATES",
            "image_size": [width, height],
            "plot_frame_detection": frame_detection,
            "panels": [],
        }

    leaves.sort(key=lambda item: (item[0][1], item[0][0]))
    panels = []
    for index, (box, score) in enumerate(leaves, 1):
        x0, y0, x1, y1 = box
        if x1 - x0 < width * 0.18 or y1 - y0 < height * 0.18:
            continue
        panels.append({
            "panel_id": f"auto-{index:02d}",
            "label": None,
            "bbox": [int(x0), int(y0), int(x1), int(y1)],
            "bbox_coordinate_space": "IMAGE_PIXELS",
            "segmentation_provenance": "AUTO_RASTER_WHITESPACE_SEGMENTATION",
            "segmentation_status": "PROVISIONAL_GEOMETRY_SPLIT",
            "segmentation_confidence": round(min(0.90, 0.55 + 0.25 * score), 4),
            "segmentation_confidence_status": "UN_CALIBRATED",
        })

    if len(panels) < 2:
        return {
            "status": "NO_CONFIDENT_PANEL_SPLIT",
            "reason": "SPLIT_REGIONS_FAILED_MINIMUM_GEOMETRY",
            "image_size": [width, height],
            "panels": [],
        }
    return {
        "status": "PROVISIONAL_PANELS_DETECTED",
        "reason": "BROAD_WHITESPACE_GUTTERS",
        "image_size": [width, height],
        "panel_count": len(panels),
        "panels": panels,
        "provisional": True,
    }
