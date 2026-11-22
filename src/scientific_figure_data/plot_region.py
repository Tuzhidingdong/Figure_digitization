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



def detect_plot_box_candidates(
    image_path: Path,
    *,
    max_candidates: int = 12,
    minimum_width_fraction: float = 0.18,
    minimum_height_fraction: float = 0.18,
    minimum_line_fraction: float = 0.12,
    minimum_adjacent_coverage: float = 0.50,
    max_axis_lines: int = 20,
) -> dict:
    """Detect multiple independent chart frames in one source figure.

    Unlike the single-frame detector, this function does not rank the largest
    rectangle as the sole plot. It retains spatially distinct frame candidates
    so a large subplot cannot hide the remaining plots in a multi-panel figure.
    Three-sided/open-axis plots are allowed when two adjacent sides provide
    strong evidence. Candidates remain provisional and are never treated as
    scientific data until panel-level axis and trace checks pass.
    """
    if max_candidates < 1 or max_axis_lines < 4:
        raise ValueError("max_candidates must be positive and max_axis_lines at least 4")
    if not 0 < minimum_line_fraction < 1 or not 0 < minimum_adjacent_coverage <= 1:
        raise ValueError("line and side coverage thresholds must be in (0, 1]")
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Plot-frame detection requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        original_width, original_height = source.size
        if original_width < 100 or original_height < 100:
            return {
                "status": "NEEDS_REVIEW",
                "reason": "IMAGE_TOO_SMALL_FOR_PLOT_FRAME_CANDIDATES",
                "image_size": [original_width, original_height],
                "candidates": [],
            }
        max_analysis_pixels = 5_000_000
        analysis_scale = min(
            1.0,
            (max_analysis_pixels / float(original_width * original_height)) ** 0.5,
        )
        analysis_width = max(100, int(round(original_width * analysis_scale)))
        analysis_height = max(100, int(round(original_height * analysis_scale)))
        converted = source.convert("RGB")
        if (analysis_width, analysis_height) != (original_width, original_height):
            resampling = getattr(Image, "Resampling", Image).BOX
            converted = converted.resize((analysis_width, analysis_height), resample=resampling)
        rgb = np.asarray(converted, dtype=np.uint8)
        if converted is not source:
            converted.close()
    height, width = rgb.shape[:2]

    luminance = (
        0.2126 * rgb[:, :, 0].astype(np.float32)
        + 0.7152 * rgb[:, :, 1].astype(np.float32)
        + 0.0722 * rgb[:, :, 2].astype(np.float32)
    )
    chroma = (
        rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    )
    dark = luminance <= 178.0
    # Use mostly achromatic ink to locate axes. Saturated data traces can be
    # long and nearly horizontal/vertical, so counting them as frame lines
    # creates false plot rectangles and can suppress the true panel candidates.
    axis_ink = dark & (chroma <= 65)
    row_profile = axis_ink.mean(axis=1)
    column_profile = axis_ink.mean(axis=0)

    def line_positions(profile, dimension):
        raw = [
            index for index, fraction in enumerate(profile)
            if fraction >= minimum_line_fraction
            and dimension * 0.015 <= index <= dimension * 0.985
        ]
        clusters = _collapse_nearby(raw, max(1, round(dimension * 0.004)))
        ranked = []
        for position in clusters:
            radius = max(1, round(dimension * 0.002))
            start, end = max(0, position - radius), min(dimension, position + radius + 1)
            ranked.append((float(profile[start:end].max()), int(position)))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return sorted(position for _, position in ranked[:max_axis_lines])

    rows = line_positions(row_profile, height)
    columns = line_positions(column_profile, width)
    if len(rows) < 2 or len(columns) < 2:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "INSUFFICIENT_LONG_AXIS_LINES",
            "image_size": [original_width, original_height],
            "analysis_image_size": [width, height],
            "analysis_scale": analysis_scale,
            "horizontal_candidate_count": len(rows),
            "vertical_candidate_count": len(columns),
            "candidates": [],
        }

    horizontal_pairs = []
    for top_index, top in enumerate(rows[:-1]):
        for bottom in rows[top_index + 1:]:
            box_height = bottom - top
            if box_height < height * minimum_height_fraction or box_height > height * 0.96:
                continue
            horizontal_pairs.append((top, bottom))

    vertical_pairs = []
    for left_index, left in enumerate(columns[:-1]):
        for right in columns[left_index + 1:]:
            box_width = right - left
            if box_width < width * minimum_width_fraction or box_width > width * 0.96:
                continue
            vertical_pairs.append((left, right))

    candidates = []
    for top, bottom in horizontal_pairs:
        box_height = bottom - top
        for left, right in vertical_pairs:
            box_width = right - left
            aspect = box_width / max(1, box_height)
            if not 0.20 <= aspect <= 5.0:
                continue

            horizontal_top = float(axis_ink[max(0, top - 1):min(height, top + 2), left:right].mean())
            horizontal_bottom = float(axis_ink[max(0, bottom - 1):min(height, bottom + 2), left:right].mean())
            vertical_left = float(axis_ink[top:bottom, max(0, left - 1):min(width, left + 2)].mean())
            vertical_right = float(axis_ink[top:bottom, max(0, right - 1):min(width, right + 2)].mean())
            sides = (horizontal_top, horizontal_bottom, vertical_left, vertical_right)

            adjacent = max(
                min(horizontal_top, vertical_left),
                min(horizontal_top, vertical_right),
                min(horizontal_bottom, vertical_left),
                min(horizontal_bottom, vertical_right),
            )
            if adjacent < minimum_adjacent_coverage:
                continue

            strongest = sorted(sides, reverse=True)
            # Full rectangular frames are preferred, while ordinary L-shaped
            # axes remain discoverable from one horizontal and one vertical side.
            if strongest[1] < minimum_adjacent_coverage:
                continue

            area_fraction = (box_width * box_height) / float(width * height)
            if area_fraction < 0.035:
                continue
            size_score = max(0.25, 1.0 - max(0.0, area_fraction - 0.38) * 1.7)
            interior = rgb[
                min(height - 1, top + 2):max(top + 3, bottom - 1),
                min(width - 1, left + 2):max(left + 3, right - 1),
            ].astype(np.int16)
            if interior.size:
                chroma_fraction = float(
                    ((interior.max(axis=2) - interior.min(axis=2)) >= 32).mean()
                )
            else:
                chroma_fraction = 0.0
            chroma_score = min(1.0, chroma_fraction / 0.018)
            side_score = 0.55 * adjacent + 0.45 * (sum(strongest[:2]) / 2.0)
            score = 0.55 * side_score + 0.22 * size_score + 0.23 * chroma_score
            if score < 0.44:
                continue
            candidates.append({
                "pixel_bbox": [int(left), int(top), int(right), int(bottom)],
                "normalized_bbox": [
                    left / width, top / height, right / width, bottom / height,
                ],
                "image_size": [width, height],
                "side_coverage": {
                    "top": horizontal_top, "bottom": horizontal_bottom,
                    "left": vertical_left, "right": vertical_right,
                },
                "adjacent_side_coverage": adjacent,
                "area_fraction": area_fraction,
                "chromatic_pixel_fraction": chroma_fraction,
                "score": float(score),
                "provisional": True,
            })

    candidates.sort(key=lambda item: (
        -item["score"],
        (item["pixel_bbox"][2] - item["pixel_bbox"][0])
        * (item["pixel_bbox"][3] - item["pixel_bbox"][1]),
        item["pixel_bbox"][1], item["pixel_bbox"][0],
    ))

    def intersection_over_union(first, second):
        ax0, ay0, ax1, ay1 = first
        bx0, by0, bx1, by1 = second
        ix0, iy0, ix1, iy1 = max(ax0, bx0), max(ay0, by0), min(ax1, bx1), min(ay1, by1)
        intersection = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        area_a = max(1, ax1 - ax0) * max(1, ay1 - ay0)
        area_b = max(1, bx1 - bx0) * max(1, by1 - by0)
        return intersection / max(1, area_a + area_b - intersection)

    deduplicated = []
    for candidate in candidates:
        box = candidate["pixel_bbox"]
        if any(intersection_over_union(box, prior["pixel_bbox"]) >= 0.72
               for prior in deduplicated):
            continue
        deduplicated.append(candidate)

    # Remove an enclosing rectangle when one or more similarly supported
    # internal frames explain the chart area more precisely.
    rejected = set()
    for outer_index, outer in enumerate(deduplicated):
        ox0, oy0, ox1, oy1 = outer["pixel_bbox"]
        outer_area = max(1, (ox1 - ox0) * (oy1 - oy0))
        children = []
        for inner_index, inner in enumerate(deduplicated):
            if inner_index == outer_index:
                continue
            ix0, iy0, ix1, iy1 = inner["pixel_bbox"]
            contained = ox0 <= ix0 and oy0 <= iy0 and ox1 >= ix1 and oy1 >= iy1
            if not contained:
                continue
            inner_area = max(1, (ix1 - ix0) * (iy1 - iy0))
            ratio = inner_area / outer_area
            if 0.12 <= ratio <= 0.82 and inner["score"] >= outer["score"] - 0.12:
                children.append(inner_index)
        if len(children) >= 2:
            rejected.add(outer_index)
        elif len(children) == 1:
            child = deduplicated[children[0]]
            if child["score"] >= outer["score"] - 0.06:
                rejected.add(outer_index)

    selected = [
        item for index, item in enumerate(deduplicated)
        if index not in rejected
    ][:max_candidates]
    selected.sort(key=lambda item: (
        item["pixel_bbox"][1], item["pixel_bbox"][0], -item["score"]
    ))
    scale_x = original_width / float(width)
    scale_y = original_height / float(height)
    for item in selected:
        x0, y0, x1, y1 = item["pixel_bbox"]
        original_box = [
            max(0, min(original_width, int(round(x0 * scale_x)))),
            max(0, min(original_height, int(round(y0 * scale_y)))),
            max(0, min(original_width, int(round(x1 * scale_x)))),
            max(0, min(original_height, int(round(y1 * scale_y)))),
        ]
        item["analysis_pixel_bbox"] = item["pixel_bbox"]
        item["pixel_bbox"] = original_box
        item["normalized_bbox"] = [
            original_box[0] / original_width,
            original_box[1] / original_height,
            original_box[2] / original_width,
            original_box[3] / original_height,
        ]
        item["image_size"] = [original_width, original_height]
    return {
        "status": "PLOT_FRAME_CANDIDATES_FOUND" if selected else "NEEDS_REVIEW",
        "reason": (
            "MULTIPLE_SPATIALLY_DISTINCT_PLOT_FRAMES"
            if len(selected) >= 2 else
            "ONE_SUPPORTED_PLOT_FRAME" if len(selected) == 1 else
            "NO_PLOT_FRAME_CANDIDATE_PASSED_GEOMETRY"
        ),
        "image_size": [original_width, original_height],
        "analysis_image_size": [width, height],
        "analysis_scale": analysis_scale,
        "horizontal_candidate_count": len(rows),
        "vertical_candidate_count": len(columns),
        "candidate_count": len(selected),
        "candidates": selected,
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


def _rgb_to_hsv_arrays(values):
    """Convert an Nx3 uint8/int RGB array to hue degrees, saturation and value."""
    import numpy as np

    rgb = values.astype(np.float32) / 255.0
    red, green, blue = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    maximum = rgb.max(axis=1)
    minimum = rgb.min(axis=1)
    delta = maximum - minimum
    safe_delta = np.where(delta > 1e-8, delta, 1.0)
    hue = np.zeros(len(rgb), dtype=np.float32)
    red_max = (maximum == red) & (delta > 1e-8)
    green_max = (maximum == green) & (delta > 1e-8)
    blue_max = (maximum == blue) & (delta > 1e-8)
    hue[red_max] = ((green[red_max] - blue[red_max]) / safe_delta[red_max]) % 6.0
    hue[green_max] = (
        (blue[green_max] - red[green_max]) / safe_delta[green_max] + 2.0
    )
    hue[blue_max] = (
        (red[blue_max] - green[blue_max]) / safe_delta[blue_max] + 4.0
    )
    hue *= 60.0
    saturation = np.divide(
        delta, maximum, out=np.zeros_like(delta), where=maximum > 1e-8
    )
    return hue, saturation, maximum


def _rgb_hue_degrees(color) -> float | None:
    import numpy as np

    values = np.asarray(color, dtype=np.float32).reshape(1, 3)
    hue, saturation, _ = _rgb_to_hsv_arrays(values)
    return float(hue[0]) if float(saturation[0]) > 1e-6 else None


def detect_chromatic_color_families(
    image_path: Path,
    plot_box: tuple[int, int, int, int],
    *,
    max_families: int = 4,
    minimum_family_pixels: int = 24,
    minimum_family_fraction: float = 0.025,
    maximum_distance: float = 52.0,
    hue_tolerance_degrees: float = 12.0,
    minimum_saturation: float = 0.16,
    minimum_value: float = 0.22,
) -> dict:
    """Group chromatic shades by circular HSV hue; candidates still require path validation."""
    if max_families < 1 or minimum_family_pixels < 1:
        raise ValueError("max_families and minimum_family_pixels must be positive")
    if not 0 < minimum_family_fraction <= 1:
        raise ValueError("minimum_family_fraction must be between 0 and 1")
    if not 0 < hue_tolerance_degrees <= 45:
        raise ValueError("hue_tolerance_degrees must be between 0 and 45")
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
    hues, saturations, values = _rgb_to_hsv_arrays(region)
    selected_mask = (
        (saturations >= float(minimum_saturation))
        & (values >= float(minimum_value))
    )
    selected = region[selected_mask]
    selected_hues = hues[selected_mask]
    selected_saturations = saturations[selected_mask]
    selected_values = values[selected_mask]
    total = int(len(selected))
    if total < minimum_family_pixels:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "INSUFFICIENT_CHROMATIC_PIXELS",
            "saturated_pixel_count": total,
            "families": [],
        }

    remaining = np.ones(total, dtype=bool)
    families = []
    bin_width = 3.0
    bin_count = int(round(360.0 / bin_width))
    while int(remaining.sum()) >= minimum_family_pixels and len(families) < max_families:
        remaining_hues = selected_hues[remaining]
        bins = np.floor(remaining_hues / bin_width).astype(int) % bin_count
        counts = np.bincount(bins, minlength=bin_count)
        seed_bin = int(counts.argmax())
        seed_hue = (seed_bin + 0.5) * bin_width
        seed_distance = np.abs((selected_hues - seed_hue + 180.0) % 360.0 - 180.0)
        members = remaining & (seed_distance <= hue_tolerance_degrees)
        if int(members.sum()) < minimum_family_pixels:
            break

        angles = np.deg2rad(selected_hues[members])
        center_hue = float(
            np.rad2deg(np.arctan2(np.sin(angles).mean(), np.cos(angles).mean())) % 360.0
        )
        refined_distance = np.abs(
            (selected_hues - center_hue + 180.0) % 360.0 - 180.0
        )
        refined = remaining & (refined_distance <= hue_tolerance_degrees)
        count = int(refined.sum())
        if count < minimum_family_pixels or count / total < minimum_family_fraction:
            break

        family_pixels = selected[refined]
        color_rgb = [int(round(value)) for value in np.median(family_pixels, axis=0)]
        families.append({
            "color_rgb": color_rgb,
            "color_tolerance": 24,
            "color_match": {
                "space": "HSV_HUE_FAMILY",
                "hue_center_degrees": round(center_hue, 3),
                "hue_tolerance_degrees": float(hue_tolerance_degrees),
                "minimum_saturation": float(max(0.12, minimum_saturation - 0.02)),
                "minimum_value": float(max(0.18, minimum_value - 0.02)),
            },
            "pixel_count": count,
            "pixel_fraction": count / total,
            "hue_spread_degrees": float(np.max(refined_distance[refined])),
            "median_saturation": float(np.median(selected_saturations[refined])),
            "median_value": float(np.median(selected_values[refined])),
            "provisional": True,
        })
        remaining[refined] = False

    families.sort(key=lambda item: (-item["pixel_count"], item["color_rgb"]))
    if not families:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "NO_SEPARABLE_CHROMATIC_FAMILY",
            "saturated_pixel_count": total,
            "families": [],
        }
    return {
        "status": (
            "UNIQUE_CHROMATIC_FAMILY" if len(families) == 1
            else "MULTIPLE_CHROMATIC_FAMILIES"
        ),
        "reason": "HUE_FAMILIES_ARE_CANDIDATES_NOT_CONFIRMED_SERIES",
        "saturated_pixel_count": total,
        "family_count": len(families),
        "families": families,
        "truncated": bool(remaining.sum() >= minimum_family_pixels),
        "color_space": "HSV_HUE_FAMILY",
        "hue_tolerance_degrees": float(hue_tolerance_degrees),
        "provisional": True,
    }


def estimate_ocr_text_ink_color(
    image_path: Path,
    text_rows: list[dict],
    *,
    minimum_pixels_per_label: int = 3,
    minimum_colored_labels: int = 2,
    minimum_saturation: int = 38,
    maximum_label_color_spread: float = 58.0,
) -> dict:
    """Estimate a shared chromatic ink color from OCR-located tick-label pixels.

    This is evidence for matching a curve to a color-coded Y axis, not a generic
    color classifier. At least two OCR boxes must contain consistent chromatic
    glyph pixels. Black/gray labels and inconsistent colors remain unresolved.
    """
    if minimum_pixels_per_label < 1 or minimum_colored_labels < 1:
        raise ValueError("minimum pixel and label counts must be positive")
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "OCR text-color analysis requires Pillow and NumPy: pip install '.[images]'"
        ) from exc

    with Image.open(image_path) as source:
        image = np.asarray(source.convert("RGB"), dtype=np.uint8)
    height, width = image.shape[:2]
    label_colors = []
    label_pixel_counts = []
    for row in text_rows:
        polygon = row.get("polygon")
        try:
            points = [(float(point[0]), float(point[1])) for point in polygon]
        except (TypeError, ValueError, IndexError):
            continue
        if len(points) < 3:
            continue
        x0 = max(0, int(np.floor(min(point[0] for point in points))))
        y0 = max(0, int(np.floor(min(point[1] for point in points))))
        x1 = min(width, int(np.ceil(max(point[0] for point in points))) + 1)
        y1 = min(height, int(np.ceil(max(point[1] for point in points))) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        crop = image[y0:y1, x0:x1].reshape(-1, 3).astype(np.int16)
        saturation = crop.max(axis=1) - crop.min(axis=1)
        brightness = crop.max(axis=1)
        chromatic = crop[(saturation >= minimum_saturation) & (brightness >= 55) & (brightness < 250)]
        if len(chromatic) < minimum_pixels_per_label:
            continue
        # Prefer the dominant quantized ink cluster over a raw median:
        # antialiased glyph edges mix with the white background and can shift
        # the median far away from the actual axis-label color.
        quantization = 16
        quantized = ((chromatic + quantization // 2) // quantization) * quantization
        quantized = np.clip(quantized, 0, 255).astype(np.uint8)
        bins, counts = np.unique(quantized, axis=0, return_counts=True)
        dominant_bin = bins[int(counts.argmax())]
        dominant_pixels = chromatic[np.all(quantized == dominant_bin, axis=1)]
        center = np.median(dominant_pixels.astype(np.float32), axis=0)
        label_colors.append(center)
        label_pixel_counts.append(int(len(dominant_pixels)))

    if len(label_colors) < minimum_colored_labels:
        return {
            "status": "NO_CHROMATIC_TEXT_COLOR",
            "colored_label_count": len(label_colors),
            "required_label_count": minimum_colored_labels,
            "label_pixel_counts": label_pixel_counts,
        }
    centers = np.asarray(label_colors, dtype=np.float32)
    shared = np.median(centers, axis=0)
    distances = np.sqrt(((centers - shared) ** 2).sum(axis=1))
    spread = float(np.max(distances)) if len(distances) else 0.0
    if spread > maximum_label_color_spread:
        return {
            "status": "INCONSISTENT_TEXT_COLORS",
            "colored_label_count": len(label_colors),
            "label_colors_rgb": [[int(round(v)) for v in row] for row in centers],
            "color_spread": spread,
        }
    return {
        "status": "CHROMATIC_TEXT_COLOR_DETECTED",
        "color_rgb": [int(round(value)) for value in shared],
        "hue_degrees": _rgb_hue_degrees(shared),
        "colored_label_count": len(label_colors),
        "label_pixel_counts": label_pixel_counts,
        "color_spread": spread,
        "provisional": True,
    }
