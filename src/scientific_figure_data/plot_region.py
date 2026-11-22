from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_plot_box(
    image_path: Path,
    *,
    dark_threshold: int = 165,
    minimum_side_coverage: float = 0.62,
    minimum_width_fraction: float = 0.25,
    minimum_height_fraction: float = 0.25,
) -> dict:
    """Detect one conservative rectangular plot frame from raster line projections.

    Returns NEEDS_REVIEW when a four-sided frame cannot be distinguished. It does
    not guess a plotting region from arbitrary image borders or text blocks.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Plot-region detection requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    if width < 40 or height < 40:
        return {"status": "NEEDS_REVIEW", "reason": "IMAGE_TOO_SMALL"}

    # Use low luminance rather than a fixed RGB value to tolerate grayscale and dark axes.
    luminance = (
        0.2126 * rgb[:, :, 0].astype(np.float32)
        + 0.7152 * rgb[:, :, 1].astype(np.float32)
        + 0.0722 * rgb[:, :, 2].astype(np.float32)
    )
    dark = luminance <= float(dark_threshold)
    row_candidates = [
        index for index, fraction in enumerate(dark.mean(axis=1))
        if fraction >= minimum_side_coverage and 0.025 * height <= index <= 0.975 * height
    ]
    column_candidates = [
        index for index, fraction in enumerate(dark.mean(axis=0))
        if fraction >= minimum_side_coverage and 0.025 * width <= index <= 0.975 * width
    ]
    row_candidates = _collapse_nearby(row_candidates, max(1, round(height * 0.008)))
    column_candidates = _collapse_nearby(column_candidates, max(1, round(width * 0.008)))

    if len(row_candidates) < 2 or len(column_candidates) < 2:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "NO_UNAMBIGUOUS_RECTANGULAR_FRAME",
            "horizontal_candidates": len(row_candidates),
            "vertical_candidates": len(column_candidates),
        }

    ranked = []
    for top_index, top in enumerate(row_candidates[:-1]):
        for bottom in row_candidates[top_index + 1:]:
            box_height = bottom - top
            if box_height < height * minimum_height_fraction:
                continue
            for left_index, left in enumerate(column_candidates[:-1]):
                for right in column_candidates[left_index + 1:]:
                    box_width = right - left
                    if box_width < width * minimum_width_fraction:
                        continue
                    if not 0.18 <= box_width / box_height <= 5.5:
                        continue
                    horizontal_top = float(dark[top, left:right].mean())
                    horizontal_bottom = float(dark[bottom, left:right].mean())
                    vertical_left = float(dark[top:bottom, left].mean())
                    vertical_right = float(dark[top:bottom, right].mean())
                    sides = (horizontal_top, horizontal_bottom, vertical_left, vertical_right)
                    if min(sides) < minimum_side_coverage:
                        continue
                    coverage = sum(sides) / 4.0
                    area_fraction = (box_width * box_height) / (width * height)
                    margin_fraction = min(
                        left / width, (width - right) / width,
                        top / height, (height - bottom) / height,
                    )
                    # Favor a large, well-supported internal frame, but reject one-sided panel borders.
                    score = 0.62 * coverage + 0.30 * area_fraction + 0.08 * min(1.0, margin_fraction / 0.08)
                    ranked.append((score, left, top, right, bottom, sides))

    if not ranked:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "NO_RECTANGULAR_FRAME_PASSED_SIDE_COVERAGE",
            "horizontal_candidates": len(row_candidates),
            "vertical_candidates": len(column_candidates),
        }

    ranked.sort(reverse=True)
    best = ranked[0]
    if len(ranked) > 1:
        second = ranked[1]
        best_box = best[1:5]
        second_box = second[1:5]
        overlap_difference = sum(abs(a - b) for a, b in zip(best_box, second_box))
        if second[0] >= best[0] * 0.985 and overlap_difference > 0.10 * (width + height):
            return {
                "status": "NEEDS_REVIEW",
                "reason": "MULTIPLE_SIMILAR_PLOT_FRAME_CANDIDATES",
                "candidate_boxes": [list(best_box), list(second_box)],
                "scores": [best[0], second[0]],
            }

    _, left, top, right, bottom, sides = best
    return {
        "status": "PROVISIONAL_PLOT_BOX",
        "pixel_bbox": [int(left), int(top), int(right), int(bottom)],
        "normalized_bbox": [left / width, top / height, right / width, bottom / height],
        "image_size": [width, height],
        "side_coverage": {
            "top": sides[0], "bottom": sides[1], "left": sides[2], "right": sides[3],
        },
        "score": best[0],
        "provisional": True,
    }


def _collapse_nearby(values: list[int], gap: int) -> list[int]:
    if not values:
        return []
    groups = [[values[0]]]
    for value in values[1:]:
        if value - groups[-1][-1] <= gap:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [round(sum(group) / len(group)) for group in groups]


def detect_single_trace_color(
    image_path: Path,
    plot_box: tuple[int, int, int, int],
    *,
    minimum_saturated_pixels: int = 12,
    minimum_color_purity: float = 0.86,
    maximum_distance: float = 52.0,
) -> dict:
    """Return a dominant chromatic line color only when one color family is clear."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Color trace detection requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = [int(value) for value in plot_box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 <= x0 or y1 <= y0:
        return {"status": "NEEDS_REVIEW", "reason": "INVALID_PLOT_BOX"}
    region = rgb[y0:y1, x0:x1].reshape(-1, 3)
    values = region.astype(np.int16)
    saturation = values.max(axis=1) - values.min(axis=1)
    brightness = values.max(axis=1)
    selected = values[(saturation >= 45) & (brightness >= 55)]
    if len(selected) < minimum_saturated_pixels:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "NO_DOMINANT_CHROMATIC_TRACE",
            "saturated_pixel_count": int(len(selected)),
        }
    colors, counts = np.unique(selected, axis=0, return_counts=True)
    dominant = colors[int(counts.argmax())].astype(np.float32)
    distances = np.sqrt(((selected.astype(np.float32) - dominant) ** 2).sum(axis=1))
    family = selected[distances <= maximum_distance]
    purity = len(family) / max(1, len(selected))
    if purity < minimum_color_purity:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "MULTIPLE_CHROMATIC_FAMILIES",
            "saturated_pixel_count": int(len(selected)),
            "dominant_family_pixels": int(len(family)),
            "dominant_family_purity": float(purity),
            "dominant_color_rgb": [int(value) for value in dominant],
        }
    center = np.median(family, axis=0)
    color = [int(round(value)) for value in center]
    return {
        "status": "UNIQUE_CHROMATIC_FAMILY",
        "color_rgb": color,
        "color_tolerance": int(maximum_distance / 2),
        "saturated_pixel_count": int(len(selected)),
        "dominant_family_pixels": int(len(family)),
        "dominant_family_purity": float(purity),
        "provisional": True,
    }


def detect_chromatic_color_families(
    image_path: Path,
    plot_box: tuple[int, int, int, int],
    *,
    max_families: int = 4,
    minimum_family_pixels: int = 24,
    minimum_family_fraction: float = 0.025,
    maximum_distance: float = 52.0,
) -> dict:
    """Find distinct saturated color families without selecting a curve by itself.

    Candidate families are only proposals. Callers must still verify each color
    with the ordered-path tracer and chart-family/axis evidence. Quantization
    combines anti-aliased shades before deterministic nearest-center grouping.
    """
    if max_families < 1 or minimum_family_pixels < 1:
        raise ValueError("max_families and minimum_family_pixels must be positive")
    if not 0.0 < minimum_family_fraction <= 1.0:
        raise ValueError("minimum_family_fraction must be between 0 and 1")
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Color trace detection requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = [int(value) for value in plot_box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 <= x0 or y1 <= y0:
        return {"status": "NEEDS_REVIEW", "reason": "INVALID_PLOT_BOX", "families": []}

    region = rgb[y0:y1, x0:x1].reshape(-1, 3).astype(np.int16)
    saturation = region.max(axis=1) - region.min(axis=1)
    brightness = region.max(axis=1)
    selected = region[(saturation >= 45) & (brightness >= 55)]
    total = int(len(selected))
    if total < minimum_family_pixels:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "INSUFFICIENT_CHROMATIC_PIXELS",
            "saturated_pixel_count": total,
            "families": [],
        }

    remaining = selected.copy()
    families = []
    quantization = 24
    while len(remaining) >= minimum_family_pixels and len(families) < max_families:
        quantized = ((remaining + quantization // 2) // quantization) * quantization
        quantized = np.clip(quantized, 0, 255).astype(np.uint8)
        bins, counts = np.unique(quantized, axis=0, return_counts=True)
        seed = bins[int(counts.argmax())].astype(np.float32)
        distances = np.sqrt(((remaining.astype(np.float32) - seed) ** 2).sum(axis=1))
        members = distances <= maximum_distance
        family_pixels = remaining[members]
        count = int(len(family_pixels))
        if count < minimum_family_pixels or count / total < minimum_family_fraction:
            break

        center = np.median(family_pixels, axis=0)
        refined_distances = np.sqrt(
            ((remaining.astype(np.float32) - center) ** 2).sum(axis=1)
        )
        refined_members = refined_distances <= maximum_distance
        refined_pixels = remaining[refined_members]
        refined_count = int(len(refined_pixels))
        if refined_count < minimum_family_pixels or refined_count / total < minimum_family_fraction:
            break

        color_rgb = [int(round(value)) for value in np.median(refined_pixels, axis=0)]
        families.append({
            "color_rgb": color_rgb,
            "color_tolerance": int(max(12, round(maximum_distance / 2))),
            "pixel_count": refined_count,
            "pixel_fraction": refined_count / total,
            "seed_rgb": [int(value) for value in seed],
            "provisional": True,
        })
        remaining = remaining[~refined_members]

    families.sort(key=lambda item: (-item["pixel_count"], item["color_rgb"]))
    if not families:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "NO_SEPARABLE_CHROMATIC_FAMILY",
            "saturated_pixel_count": total,
            "families": [],
        }
    return {
        "status": "UNIQUE_CHROMATIC_FAMILY" if len(families) == 1 else "MULTIPLE_CHROMATIC_FAMILIES",
        "reason": "COLOR_FAMILIES_ARE_CANDIDATES_NOT_CONFIRMED_SERIES",
        "saturated_pixel_count": total,
        "family_count": len(families),
        "families": families,
        "truncated": len(remaining) >= minimum_family_pixels,
        "provisional": True,
    }
