from __future__ import annotations

import os
import tempfile
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
    ocr_rows: list[dict] | None = None,
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
        ocr_masked_pixels = 0
        if isinstance(ocr_rows, list) and ocr_rows:
            # Text boxes can bridge otherwise clear inter-panel gutters in
            # projection-based segmentation. Remove only their local ink from
            # the geometry mask; the source pixels and OCR evidence remain
            # untouched for later panel extraction.
            for row in ocr_rows:
                if not isinstance(row, dict):
                    continue
                polygon = row.get("polygon")
                if not isinstance(polygon, list) or len(polygon) < 4:
                    continue
                try:
                    points = [
                        (float(point[0]), float(point[1]))
                        for point in polygon
                        if isinstance(point, (list, tuple)) and len(point) >= 2
                    ]
                    if len(points) < 4:
                        continue
                    x0 = max(0, int(np.floor(min(point[0] for point in points))) - 1)
                    y0 = max(0, int(np.floor(min(point[1] for point in points))) - 1)
                    x1 = min(width, int(np.ceil(max(point[0] for point in points))) + 2)
                    y1 = min(height, int(np.ceil(max(point[1] for point in points))) + 2)
                except (TypeError, ValueError, OverflowError, IndexError):
                    continue
                if x1 > x0 and y1 > y0:
                    before = int(mask[y0:y1, x0:x1].sum())
                    mask[y0:y1, x0:x1] = False
                    ocr_masked_pixels += before

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
    leaves.sort(key=lambda item: (item[0][1], item[0][0]))
    panels = []
    for index, (box, score) in enumerate(leaves, 1):
        x0, y0, x1, y1 = box
        box_width = x1 - x0
        box_height = y1 - y0
        area_fraction = (box_width * box_height) / float(width * height)
        # Panel rows can be intentionally short (e.g. a narrow upper plot
        # stacked above another plot inside one labeled panel). Reject tiny
        # fragments by area and minimum dimension, not by requiring every
        # panel to occupy 18% of the full figure in both directions.
        if (
            box_width < width * 0.06
            or box_height < height * 0.06
            or area_fraction < 0.045
        ):
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

    # Expand whitespace leaves through the inter-row gutter to retain
    # X-axis tick labels and titles that sit just below the plot frame. Keep
    # adjacent panels non-overlapping by stopping at the next row's start.
    for panel in panels:
        box = panel.get("bbox")
        if not isinstance(box, list) or len(box) != 4:
            continue
        x0, y0, x1, y1 = [int(value) for value in box]
        following_rows = []
        for other in panels:
            if other is panel:
                continue
            ox0, oy0, ox1, oy1 = [int(value) for value in other["bbox"]]
            if oy0 < y1:
                continue
            overlap_x = max(0, min(x1, ox1) - max(x0, ox0))
            denominator = max(1, min(x1 - x0, ox1 - ox0))
            if overlap_x / denominator >= 0.50:
                following_rows.append(oy0)
        if following_rows:
            panel["bbox"] = [x0, y0, x1, min(height, min(following_rows))]

    # Run plot-frame fallback whenever whitespace splitting did not produce
    # at least two geometrically usable panels. The pre-filter leaf count is
    # not sufficient: recursive splits can yield several text-sized fragments
    # that are all rejected by the minimum panel geometry gate.
    leaf_diagnostics = []
    for box, score in leaves:
        x0, y0, x1, y1 = box
        width_fraction = (x1 - x0) / float(width)
        height_fraction = (y1 - y0) / float(height)
        area_fraction = width_fraction * height_fraction
        rejected = (
            width_fraction < 0.06
            or height_fraction < 0.06
            or area_fraction < 0.045
        )
        leaf_diagnostics.append({
            "bbox": [int(x0), int(y0), int(x1), int(y1)],
            "score": float(score),
            "width_fraction": width_fraction,
            "height_fraction": height_fraction,
            "area_fraction": area_fraction,
            "rejected_by_minimum_geometry": rejected,
        })

    # Whitespace leaves can still be composite rows/columns: a full-width
    # leaf may contain several plot frames, while a wide short leaf may be one
    # of multiple vertically stacked plots. Do not stop at the first two
    # leaves in those cases; send them through the independent plot-frame scan.
    contains_composite_region = any(
        (panel["bbox"][2] - panel["bbox"][0]) >= width * 0.55
        or (panel["bbox"][3] - panel["bbox"][1]) >= height * 0.72
        for panel in panels
    )
    if len(panels) >= 2 and not contains_composite_region:
        return {
            "status": "PROVISIONAL_PANELS_DETECTED",
            "reason": "BROAD_WHITESPACE_GUTTERS_AFTER_OCR_MASK" if ocr_masked_pixels else "BROAD_WHITESPACE_GUTTERS",
            "image_size": [width, height],
            "ocr_layout_evidence": {
                "status": "APPLIED" if ocr_masked_pixels else "NOT_AVAILABLE",
                "masked_ink_pixel_count": ocr_masked_pixels,
                "ocr_row_count": len(ocr_rows) if isinstance(ocr_rows, list) else 0,
            },
            "panel_count": len(panels),
            "panels": panels,
            "provisional": True,
        }

    from .plot_region import detect_plot_box, detect_plot_box_candidates

    frame_detections = []
    frames = []

    def add_frame(candidate: dict, offset_x: int = 0, offset_y: int = 0,
                  source_region: list[int] | None = None) -> None:
        bbox = candidate.get("pixel_bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return
        try:
            x0, y0, x1, y1 = [int(value) for value in bbox]
        except (TypeError, ValueError, OverflowError):
            return
        x0, y0, x1, y1 = (
            x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y
        )
        if x1 <= x0 or y1 <= y0:
            return
        item = dict(candidate)
        item["pixel_bbox"] = [x0, y0, x1, y1]
        item["image_size"] = [width, height]
        item["normalized_bbox"] = [
            x0 / width, y0 / height, x1 / width, y1 / height
        ]
        if source_region is not None:
            item["source_region_bbox"] = list(source_region)
        frames.append(item)

    # A conservative full-image rectangular detector can retain a large plot
    # that spans most of the figure. It complements, rather than replaces,
    # local multi-frame scans because a dense row of subplots can hide its
    # vertical dividers in the whole-image projection.
    full_plot_detection = detect_plot_box(image_path)
    if full_plot_detection.get("status") == "PROVISIONAL_PLOT_BOX":
        add_frame({
            "pixel_bbox": full_plot_detection.get("pixel_bbox"),
            "score": full_plot_detection.get("score", 0.0),
            "candidate_type": "FULL_IMAGE_RECTANGULAR_FRAME",
            "side_coverage": full_plot_detection.get("side_coverage", {}),
            "provisional": True,
        })

    # Scan independent horizontal bands and overlapping column tiles. Real
    # papers often place three compact plots on one row; a single full-width
    # projection lets vertical traces in one panel monopolize the strongest
    # axis columns and hide the middle panel.
    scan_regions: set[tuple[int, int, int, int]] = set()
    if full_plot_detection.get("status") == "PROVISIONAL_PLOT_BOX":
        _, full_y0, _, full_y1 = [
            int(value) for value in full_plot_detection["pixel_bbox"]
        ]
        # A full-size plot frame is authoritative for its own band. Only scan
        # the figure area below it, avoiding false sub-panels carved out of the
        # same plot (a single time-series chart must remain a single panel).
        lower_y0 = max(int(round(height * 0.50)), full_y1 + int(round(height * 0.04)))
        if height - lower_y0 >= height * 0.18:
            scan_y_bands = [(lower_y0, height)]
        else:
            scan_y_bands = []
    else:
        scan_y_bands = [
            (0, int(round(height * 0.52))),
            (int(round(height * 0.45)), height),
        ]

    # Also retain sufficiently large non-trivial recursive whitespace leaves.
    for box, _ in leaves:
        x0, y0, x1, y1 = [int(value) for value in box]
        if (
            x1 - x0 >= width * 0.18 and y1 - y0 >= height * 0.18
            and not (x0 == 0 and y0 == 0 and x1 == width and y1 == height)
        ):
            scan_regions.add((x0, y0, x1, y1))

    column_windows = (
        # Isolated near-third columns keep neighboring plot traces and tick
        # marks from crowding the axis candidate ranking for a narrow panel.
        (0.00, 0.36), (0.32, 0.68), (0.64, 1.00),
        # Wider overlapping windows retain plots that span more than one
        # column, such as a two-axis comparison panel in the lower figure row.
        (0.00, 0.44), (0.28, 0.72), (0.56, 1.00),
        (0.00, 0.68), (0.32, 1.00),
    )
    for band_y0, band_y1 in scan_y_bands:
        band_height = band_y1 - band_y0
        if band_height < height * 0.18:
            continue
        for left_fraction, right_fraction in column_windows:
            region_x0 = int(round(width * left_fraction))
            region_x1 = int(round(width * right_fraction))
            if region_x1 - region_x0 >= width * 0.18:
                scan_regions.add((region_x0, band_y0, region_x1, band_y1))

    with Image.open(image_path) as source:
        for region_x0, region_y0, region_x1, region_y1 in sorted(
            scan_regions, key=lambda box: (box[1], box[0], box[3], box[2])
        ):
            region_width = region_x1 - region_x0
            region_height = region_y1 - region_y0
            if (
                region_width < width * 0.18
                or region_height < height * 0.18
                or (region_x0 == 0 and region_y0 == 0
                    and region_x1 == width and region_y1 == height)
            ):
                continue

            crop = source.crop((region_x0, region_y0, region_x1, region_y1))
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".png", prefix="figure-panel-scan-", delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                crop.save(temporary_path, format="PNG")
                local_detection = detect_plot_box_candidates(temporary_path)
                local_candidates = local_detection.get("candidates", [])
                frame_detections.append({
                    "region_bbox": [
                        region_x0, region_y0, region_x1, region_y1
                    ],
                    "image_size": [region_width, region_height],
                    "detection_mode": "STANDARD",
                    "detection": local_detection,
                })
                if not local_candidates:
                    # Compact/multi-trace panels may have weak borders or
                    # several colored vertical features. Retry only this
                    # bounded crop with a more permissive line search; global
                    # defaults and single-plot behavior remain unchanged.
                    relaxed_detection = detect_plot_box_candidates(
                        temporary_path,
                        max_candidates=16,
                        minimum_line_fraction=0.06,
                        minimum_adjacent_coverage=0.34,
                        max_axis_lines=48,
                    )
                    local_candidates = relaxed_detection.get("candidates", [])
                    frame_detections.append({
                        "region_bbox": [
                            region_x0, region_y0, region_x1, region_y1
                        ],
                        "image_size": [region_width, region_height],
                        "detection_mode": "RELAXED_BORDER_RETRY",
                        "detection": relaxed_detection,
                    })
                for candidate in local_candidates:
                    add_frame(
                        candidate, region_x0, region_y0,
                        [region_x0, region_y0, region_x1, region_y1],
                    )
            finally:
                crop.close()
                if temporary_path is not None:
                    try:
                        temporary_path.unlink()
                    except OSError:
                        pass

    def intersection_over_union(first, second):
        ax0, ay0, ax1, ay1 = first
        bx0, by0, bx1, by1 = second
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        intersection = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        area_a = max(1, ax1 - ax0) * max(1, ay1 - ay0)
        area_b = max(1, bx1 - bx0) * max(1, by1 - by0)
        return intersection / max(1, area_a + area_b - intersection)

    # Prefer large, conservative frames and then append region-local frames.
    # Suppress local fragments fully explained by a larger enclosing plot.
    frames.sort(key=lambda item: (
        -(
            (item["pixel_bbox"][2] - item["pixel_bbox"][0])
            * (item["pixel_bbox"][3] - item["pixel_bbox"][1])
        ),
        -float(item.get("score", 0.0)),
    ))
    deduplicated = []
    for candidate in frames:
        box = candidate["pixel_bbox"]
        candidate_area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        explained_by_outer = False
        for prior in deduplicated:
            prior_box = prior["pixel_bbox"]
            if intersection_over_union(box, prior_box) >= 0.55:
                explained_by_outer = True
                break
            px0, py0, px1, py1 = prior_box
            if px0 <= box[0] and py0 <= box[1] and px1 >= box[2] and py1 >= box[3]:
                explained_by_outer = True
                break
            # A candidate whose center is inside a previously accepted plot
            # and whose area is mostly covered is an internal trace/grid
            # fragment, not a separate panel.
            cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            if (
                px0 <= cx <= px1 and py0 <= cy <= py1
                and intersection_over_union(box, prior_box) > 0.12
            ):
                explained_by_outer = True
                break
        if not explained_by_outer:
            deduplicated.append(candidate)

    # A wide local frame may actually be a row/column group containing
    # multiple adjacent plots. Refine it with a second, region-local whitespace
    # projection: the full-figure split cannot see these gutters when another
    # panel occupies the same x/y projection elsewhere in the image.
    refined_frames = []
    for candidate in deduplicated:
        x0, y0, x1, y1 = candidate["pixel_bbox"]
        box_width, box_height = x1 - x0, y1 - y0
        if (
            candidate.get("candidate_type") == "FULL_IMAGE_RECTANGULAR_FRAME"
            or box_width * box_height < width * height * 0.12
        ):
            refined_frames.append(candidate)
            continue
        split = _best_split(
            mask,
            (x0, y0, x1, y1),
            max(4, int(round(min(box_width, box_height) * 0.008))),
            max(projection_threshold, 0.006),
            0.22,
        )
        if split is None:
            refined_frames.append(candidate)
            continue
        children = []
        for child_box in split["boxes"]:
            cx0, cy0, cx1, cy1 = [int(value) for value in child_box]
            child_width, child_height = cx1 - cx0, cy1 - cy0
            if (
                child_width < width * 0.18
                or child_height < height * 0.18
                or child_width * child_height < width * height * 0.045
            ):
                continue
            child = dict(candidate)
            child["pixel_bbox"] = [cx0, cy0, cx1, cy1]
            child["candidate_type"] = "PLOT_FRAME_SPLIT_BY_LOCAL_GUTTER"
            child["parent_plot_frame_bbox"] = [x0, y0, x1, y1]
            child["local_gutter_axis"] = split["axis"]
            child["local_gutter_score"] = round(float(split["score"]), 4)
            child["score"] = min(
                0.95, float(candidate.get("score", 0.0)) + 0.03
            )
            child["image_size"] = [width, height]
            child["normalized_bbox"] = [
                cx0 / width, cy0 / height, cx1 / width, cy1 / height,
            ]
            children.append(child)
        if len(children) >= 2:
            refined_frames.extend(children)
        else:
            refined_frames.append(candidate)
    # Re-deduplicate after local-gutter refinement. The local tile scans
    # can contribute small fragments from the same frame that was just split
    # into its real child panels. Those fragments were not contained by the
    # parent candidate during the first pass, so they must be suppressed now.
    refined_frames.sort(key=lambda item: -(
        (item["pixel_bbox"][2] - item["pixel_bbox"][0])
        * (item["pixel_bbox"][3] - item["pixel_bbox"][1])
    ))
    deduplicated = []
    for candidate in refined_frames:
        box = candidate["pixel_bbox"]
        candidate_area = max(
            1, (box[2] - box[0]) * (box[3] - box[1])
        )
        explained_by_refined_panel = False
        for prior in deduplicated:
            prior_box = prior["pixel_bbox"]
            prior_area = max(
                1, (prior_box[2] - prior_box[0])
                * (prior_box[3] - prior_box[1])
            )
            if prior_area < candidate_area * 1.12:
                continue
            ix0, iy0 = max(box[0], prior_box[0]), max(box[1], prior_box[1])
            ix1, iy1 = min(box[2], prior_box[2]), min(box[3], prior_box[3])
            covered = (
                max(0, ix1 - ix0) * max(0, iy1 - iy0)
            ) / float(candidate_area)
            if covered >= 0.88:
                explained_by_refined_panel = True
                break
        if not explained_by_refined_panel:
            deduplicated.append(candidate)

    # Join adjacent frame fragments that share the same top/bottom extent.
    # Internal vertical grid lines can be ranked ahead of a faint outer side,
    # splitting one real panel into two touching rectangles. A tiny pixel gap
    # is allowed for anti-aliased or interrupted borders, but distinct panels
    # separated by a visible gutter remain independent.
    stitch_gap = max(6, int(round(width * 0.008)))
    stitched = list(deduplicated)
    changed = True
    while changed:
        changed = False
        for first_index in range(len(stitched)):
            if changed:
                break
            first = stitched[first_index]
            ax0, ay0, ax1, ay1 = first["pixel_bbox"]
            for second_index in range(first_index + 1, len(stitched)):
                second = stitched[second_index]
                bx0, by0, bx1, by1 = second["pixel_bbox"]
                overlap_y = max(0, min(ay1, by1) - max(ay0, by0))
                min_height = max(1, min(ay1 - ay0, by1 - by0))
                if overlap_y / min_height < 0.90:
                    continue
                if abs(ay0 - by0) > max(8, int(round(height * 0.015))):
                    continue
                if abs(ay1 - by1) > max(8, int(round(height * 0.015))):
                    continue
                gap = max(0, max(ax0, bx0) - min(ax1, bx1))
                if gap > stitch_gap:
                    continue
                union_box = [
                    min(ax0, bx0), min(ay0, by0),
                    max(ax1, bx1), max(ay1, by1),
                ]
                merged = dict(first)
                merged["pixel_bbox"] = union_box
                merged["score"] = min(
                    float(first.get("score", 0.0)),
                    float(second.get("score", 0.0)),
                )
                merged["candidate_type"] = "STITCHED_ADJACENT_FRAME_SEGMENTS"
                merged["stitched_from"] = [
                    list(first["pixel_bbox"]), list(second["pixel_bbox"])
                ]
                merged["image_size"] = [width, height]
                merged["normalized_bbox"] = [
                    union_box[0] / width, union_box[1] / height,
                    union_box[2] / width, union_box[3] / height,
                ]
                stitched[first_index] = merged
                stitched.pop(second_index)
                changed = True
                break
    deduplicated = stitched

    # If local scans and the conservative full-frame scan do not expose at
    # least two panels, retain the original whole-image multi-frame fallback.
    global_frame_detection = None
    if len(deduplicated) < 2:
        global_frame_detection = detect_plot_box_candidates(image_path)
        for candidate in global_frame_detection.get("candidates", []):
            add_frame(candidate)
        for candidate in frames:
            box = candidate["pixel_bbox"]
            explained = False
            for prior in deduplicated:
                prior_box = prior["pixel_bbox"]
                if intersection_over_union(box, prior_box) >= 0.55:
                    explained = True
                    break
                if (
                    prior_box[0] <= box[0] and prior_box[1] <= box[1]
                    and prior_box[2] >= box[2] and prior_box[3] >= box[3]
                ):
                    explained = True
                    break
            if not explained:
                deduplicated.append(candidate)

    frames = deduplicated[:12]
    frames.sort(key=lambda item: (
        item["pixel_bbox"][1], item["pixel_bbox"][0]
    ))

    frame_detection = {
        "status": "PLOT_FRAME_CANDIDATES_FOUND" if frames else "NEEDS_REVIEW",
        "reason": "REGION_LOCAL_AND_FULL_IMAGE_FRAME_SCAN",
        "image_size": [width, height],
        "candidate_count": len(frames),
        "candidates": frames,
        "full_image_plot_detection": full_plot_detection,
        "global_multi_frame_detection": global_frame_detection,
        "region_detections": frame_detections,
        "provisional": True,
    }

    panel_rows = []
    for index, candidate in enumerate(frames, 1):
        x0, y0, x1, y1 = [int(value) for value in candidate["pixel_bbox"]]
        frame_width, frame_height = x1 - x0, y1 - y0
        margin_x = min(
            max(8, round(frame_width * 0.16)), max(8, round(width * 0.12))
        )
        margin_y = min(
            max(8, round(frame_height * 0.20)), max(8, round(height * 0.14))
        )
        panel_x0, panel_y0 = max(0, x0 - margin_x), max(0, y0 - margin_y)
        panel_x1, panel_y1 = min(width, x1 + margin_x), min(height, y1 + margin_y)

        for other_index, other in enumerate(frames):
            if other_index == index - 1:
                continue
            ox0, oy0, ox1, oy1 = [int(value) for value in other["pixel_bbox"]]
            overlap_y = max(0, min(y1, oy1) - max(y0, oy0))
            overlap_x = max(0, min(x1, ox1) - max(x0, ox0))
            if overlap_y >= 0.30 * min(frame_height, oy1 - oy0):
                shared_margin = max(
                    4, round(min(frame_width, ox1 - ox0) * 0.06)
                )
                if ox1 <= x0:
                    panel_x0 = max(
                        panel_x0, (ox1 + x0) // 2 - shared_margin
                    )
                elif ox0 >= x1:
                    panel_x1 = min(
                        panel_x1, (x1 + ox0) // 2 + shared_margin
                    )
            if overlap_x >= 0.30 * min(frame_width, ox1 - ox0):
                shared_margin = max(
                    4, round(min(frame_height, oy1 - oy0) * 0.06)
                )
                if oy1 <= y0:
                    panel_y0 = max(
                        panel_y0, (oy1 + y0) // 2 - shared_margin
                    )
                elif oy0 >= y1:
                    panel_y1 = min(
                        panel_y1, (y1 + oy0) // 2 + shared_margin
                    )

        if panel_x1 <= panel_x0 or panel_y1 <= panel_y0:
            continue
        panel_rows.append({
            "panel_id": f"auto-frame-{index:02d}",
            "label": None,
            "bbox": [panel_x0, panel_y0, panel_x1, panel_y1],
            "bbox_coordinate_space": "IMAGE_PIXELS",
            "plot_box": [
                x0 - panel_x0, y0 - panel_y0,
                x1 - panel_x0, y1 - panel_y0,
            ],
            "plot_box_coordinate_space": "PANEL_IMAGE_PIXELS",
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
            "whitespace_split_diagnostic": {
                "leaf_count": len(leaves),
                "usable_panel_count": len(panels),
                "leaf_diagnostics": leaf_diagnostics,
            },
            "panels": panel_rows,
            "provisional": True,
        }

    if len(frames) == 1:
        candidate = frames[0]
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
        "reason": (
            "SPLIT_REGIONS_FAILED_MINIMUM_GEOMETRY"
            if leaves else "NO_WHITESPACE_GUTTER_OR_PLOT_FRAME_CANDIDATES"
        ),
        "image_size": [width, height],
        "whitespace_split_diagnostic": {
            "leaf_count": len(leaves),
            "usable_panel_count": len(panels),
            "leaf_diagnostics": leaf_diagnostics,
        },
        "plot_frame_detection": frame_detection,
        "panels": [],
    }
