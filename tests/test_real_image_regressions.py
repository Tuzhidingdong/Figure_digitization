from __future__ import annotations

import json
from pathlib import Path

import pytest

from scientific_figure_data.panel_segmentation import detect_panel_regions
from scientific_figure_data.plot_region import detect_plot_box_candidates


# These are byte-identical copies of the two published CLI input figures.
FIXTURES = Path(__file__).parent / "fixtures" / "real_figures"


def test_p8_real_image_axis_ticks_keep_x_endpoints_out_of_y_axes() -> None:
    """Real P8_06 tick labels at plot corners must stay on their own axes."""
    from scientific_figure_data.axis_text import extract_numeric_axis_anchors

    cached = json.loads(
        (FIXTURES / "P8_06_ocr.json").read_text(encoding="utf-8")
    )["rows"]
    panel_bbox = (955, 544, 1391, 895)
    x0, y0, x1, y1 = panel_bbox
    local_rows = []
    for row in cached:
        polygon = row.get("polygon")
        if not isinstance(polygon, list) or not polygon:
            continue
        points = [(float(point[0]), float(point[1])) for point in polygon]
        center_x = sum(point[0] for point in points) / len(points)
        center_y = sum(point[1] for point in points) / len(points)
        if not (x0 <= center_x < x1 and y0 <= center_y < y1):
            continue
        local = dict(row)
        local["polygon"] = [
            [point[0] - x0, point[1] - y0] for point in points
        ]
        local_rows.append(local)

    anchors = extract_numeric_axis_anchors(
        local_rows, (53, 50, 383, 301)
    )
    assert [item["value"] for item in anchors["x_anchors"]] == [
        0.0, 50.0, 100.0, 150.0,
    ], anchors
    assert [item["value"] for item in anchors["y_left_anchors"]] == [
        100.0, 80.0, 60.0, 40.0, 20.0, 0.0,
    ], anchors
    assert [item["value"] for item in anchors["y_right_anchors"]] == [
        20.0, 15.0, 10.0,
    ], anchors


@pytest.mark.parametrize(
    ("filename", "minimum_panels"),
    [
        ("P8_06.png", 4),
        ("P3_02.png", 5),
    ],
)
def test_real_scientific_figures_are_not_collapsed_to_one_panel(
    filename: str, minimum_panels: int,
) -> None:
    """Each actual subplot in the real scientific figure must be separated."""
    image_path = FIXTURES / filename
    assert image_path.is_file(), f"Missing real-image fixture: {image_path}"

    result = detect_panel_regions(image_path)
    print(f"REAL_IMAGE_PANEL_DIAGNOSTIC {filename}: {json.dumps(result, sort_keys=True)}")

    panels = result.get("panels", [])
    assert len(panels) >= minimum_panels, (
        f"{filename} still collapses to {len(panels)} automatic panel(s); "
        f"detector result={json.dumps(result, sort_keys=True)}"
    )
    if filename == "P8_06.png":
        width, height = result["image_size"]
        frames = [
            panel.get("plot_frame_bbox_pixels")
            for panel in panels
            if isinstance(panel.get("plot_frame_bbox_pixels"), list)
        ]
        top_frames = [
            box for box in frames
            if (box[1] + box[3]) / 2 < height * 0.55
        ]
        lower_frames = [
            box for box in frames
            if (box[1] + box[3]) / 2 >= height * 0.55
        ]
        lower_centers = sorted(
            ((box[0] + box[2]) / (2.0 * width)) for box in lower_frames
        )
        assert len(top_frames) == 1 and len(lower_frames) == 3, (
            f"P8_06 must resolve one upper and three lower plots; "
            f"frames={frames}"
        )
        assert (
            0.08 < lower_centers[0] < 0.36
            and 0.36 < lower_centers[1] < 0.68
            and 0.68 < lower_centers[2] < 0.96
        ), f"P8_06 lower plot frames are not spatially distinct: {frames}"
    for panel in panels:
        bbox = panel.get("bbox")
        assert isinstance(bbox, list) and len(bbox) == 4, panel
        x0, y0, x1, y1 = bbox
        assert 0 <= x0 < x1 <= result["image_size"][0], panel
        assert 0 <= y0 < y1 <= result["image_size"][1], panel


def test_p8_real_figure_pipeline_uses_panel_local_ocr_and_dual_y_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the real published P8_06 input through the production paper pipeline.

    OCR rows are replayed from the already archived first run and translated
    into each automatically generated panel crop. This keeps the test
    deterministic and tests coordinate provenance/algorithm behavior without
    rerunning an OCR engine.
    """
    import shutil
    from PIL import Image

    from scientific_figure_data import ocr
    from scientific_figure_data.panel_segmentation import detect_panel_regions
    from scientific_figure_data.pipeline import process_paper

    fixture_root = Path(__file__).parent / "fixtures" / "real_figures"
    source_image = fixture_root / "P8_06.png"
    cached_ocr = json.loads(
        (fixture_root / "P8_06_ocr.json").read_text(encoding="utf-8")
    )["rows"]

    segmentation = detect_panel_regions(source_image)
    panel_map = {
        panel["panel_id"]: panel
        for panel in segmentation.get("panels", [])
    }
    assert len(panel_map) >= 4, segmentation

    # Focused diagnostic: P8_06 panel d contains vertically stacked plot
    # content. Inspect its local frame candidates before changing production
    # segmentation/trace thresholds.
    p8_d_panel = next(
        (
            panel for panel in panel_map.values()
            if panel.get("bbox")
            and panel["bbox"][0] > segmentation["image_size"][0] * 0.55
            and panel["bbox"][1] > segmentation["image_size"][1] * 0.50
        ),
        None,
    )
    nested_plot_diagnostic = {"status": "P8_D_PANEL_NOT_FOUND", "candidates": []}
    if p8_d_panel is not None:
        p8_d_crop = tmp_path / "p8_d_panel_crop.png"
        with Image.open(source_image) as source:
            source.crop(tuple(p8_d_panel["bbox"])).save(p8_d_crop)

        # Inspect whether the red hue family contains multiple distinguishable
        # shades and whether blue marker columns are genuinely thick or merely
        # a connected sequence of small scatter markers.
        import numpy as np
        from scientific_figure_data.plot_region import _rgb_to_hsv_arrays
        with Image.open(p8_d_crop) as crop_image:
            crop_rgb = np.asarray(crop_image.convert("RGB"), dtype=np.uint8)
        plot_rgb = crop_rgb[50:301, 53:383]
        flat_rgb = plot_rgb.reshape(-1, 3)
        plot_hue, plot_sat, plot_val = _rgb_to_hsv_arrays(flat_rgb)
        color_probe = {}
        for family_name, hue_center in (("red", 356.085), ("blue", 209.087)):
            distance = np.abs((plot_hue - hue_center + 180.0) % 360.0 - 180.0)
            family_mask = (
                (distance <= 12.0) & (plot_sat >= 0.14) & (plot_val >= 0.20)
            ).reshape(plot_rgb.shape[:2])
            selected = plot_rgb[family_mask]
            bins = {}
            for color in selected:
                key = tuple(int(value // 16) for value in color)
                bins[key] = bins.get(key, 0) + 1
            top_bins = sorted(
                bins.items(), key=lambda item: (-item[1], item[0])
            )[:12]
            columns = {}
            for x in (54, 80, 120, 160, 200, 240, 280, 320, 350, 378):
                ys = np.flatnonzero(family_mask[:, x - 53])
                segments = []
                for y_value in ys:
                    y_int = int(y_value) + 50
                    if not segments or y_int - segments[-1][-1] > 2:
                        segments.append([y_int])
                    else:
                        segments[-1].append(y_int)
                columns[str(x)] = {
                    "count": int(len(ys)),
                    "span": int(ys.max() - ys.min()) if len(ys) else 0,
                    "segments": [
                        [segment[0], segment[-1]] for segment in segments
                    ],
                }
            color_probe[family_name] = {
                "pixel_count": int(selected.shape[0]),
                "rgb_bins_16": [
                    {"bin": list(key), "count": count}
                    for key, count in top_bins
                ],
                "saturation_quantiles": (
                    np.quantile(plot_sat[family_mask.reshape(-1)], [0.1, 0.5, 0.9]).round(3).tolist()
                    if len(selected) else []
                ),
                "value_quantiles": (
                    np.quantile(plot_val[family_mask.reshape(-1)], [0.1, 0.5, 0.9]).round(3).tolist()
                    if len(selected) else []
                ),
                "columns": columns,
            }
        print(
            "REAL_IMAGE_P8_D_COLOR_PROBE "
            + json.dumps(color_probe, sort_keys=True)
        )
        nested_plot_diagnostic = {
            "panel_bbox": p8_d_panel["bbox"],
            "default": detect_plot_box_candidates(p8_d_crop),
            "relaxed": detect_plot_box_candidates(
                p8_d_crop,
                max_candidates=24,
                minimum_line_fraction=0.06,
                minimum_adjacent_coverage=0.34,
                max_axis_lines=48,
            ),
        }
    print(
        "REAL_IMAGE_NESTED_PLOT_DIAGNOSTIC "
        + json.dumps(nested_plot_diagnostic, sort_keys=True)
    )

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-p8-real"
    paper_dir.mkdir(parents=True)
    shutil.copy2(source_image, paper_dir / "P8_06.png")
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({
            "figures": [{
                "figure_id": "P8_06",
                "image_path": "P8_06.png",
                "panels": [],
            }]
        }),
        encoding="utf-8",
    )

    def cached_panel_ocr(panel_image_path: Path) -> list[dict]:
        stem = Path(panel_image_path).stem
        matched_panel = next(
            (
                panel for panel_id, panel in panel_map.items()
                if stem.endswith("_" + panel_id)
            ),
            None,
        )
        if matched_panel is None:
            return []
        x0, y0, x1, y1 = matched_panel["bbox"]
        local_rows = []
        for row in cached_ocr:
            polygon = row.get("polygon")
            if not isinstance(polygon, list) or not polygon:
                continue
            try:
                points = [
                    (float(point[0]), float(point[1]))
                    for point in polygon
                ]
            except (TypeError, ValueError, IndexError):
                continue
            center_x = sum(point[0] for point in points) / len(points)
            center_y = sum(point[1] for point in points) / len(points)
            if not (x0 <= center_x < x1 and y0 <= center_y < y1):
                continue
            local_row = dict(row)
            local_row["polygon"] = [
                [point[0] - x0, point[1] - y0]
                for point in points
            ]
            local_rows.append(local_row)
        return local_rows

    # Verify the translated OCR coordinates used by the pipeline for panel d.
    # This isolates whether right-axis tick labels are lost in crop mapping or
    # rejected by the numeric-anchor classifier.
    if p8_d_panel is not None:
        p8_local_rows = cached_panel_ocr(
            Path("diagnostic_" + p8_d_panel["panel_id"])
        )
        from scientific_figure_data.axis_text import extract_numeric_axis_anchors
        p8_anchor_probe = extract_numeric_axis_anchors(
            p8_local_rows, (53, 50, 383, 301)
        )
        p8_right_numeric_rows = []
        for row in p8_local_rows:
            polygon = row.get("polygon") or []
            if not polygon:
                continue
            cx = sum(float(point[0]) for point in polygon) / len(polygon)
            cy = sum(float(point[1]) for point in polygon) / len(polygon)
            if cx >= 380:
                p8_right_numeric_rows.append({
                    "text": row.get("text"),
                    "confidence": row.get("confidence"),
                    "center": [cx, cy],
                })
        print(
            "REAL_IMAGE_P8_D_AXIS_OCR_PROBE "
            + json.dumps({
                "row_count": len(p8_local_rows),
                "right_edge_rows": p8_right_numeric_rows,
                "anchors": p8_anchor_probe,
            }, sort_keys=True)
        )

    monkeypatch.setattr(ocr, "run_ocr", cached_panel_ocr)
    output_root = tmp_path / "output"
    result = process_paper(
        input_root,
        Path("paper-p8-real"),
        output_root,
        options={
            "ocr": True,
            "memory_limit_mb": 1024,
            "temp_disk_limit_mb": 512,
        },
    )

    paper_output = output_root / "papers" / result["snapshot"]["paper_id"]
    layout = json.loads(
        (paper_output / "panel_layout.json").read_text(encoding="utf-8")
    )
    digitization = json.loads(
        (paper_output / "digitization.json").read_text(encoding="utf-8")
    )
    panel_rows = layout.get("panels", [])
    series_rows = digitization.get("series", [])
    p8_bottom_right = {
        panel["panel_id"]
        for panel in panel_rows
        if panel.get("bbox")
        and panel["bbox"][0] + panel["bbox"][2] > 1.35 * segmentation["image_size"][0]
        and panel["bbox"][1] > 0.52 * segmentation["image_size"][1]
    }
    p8_dual_axis_series = [
        row for row in series_rows if row.get("panel_id") in p8_bottom_right
    ]
    summary = {
        "pipeline_result": {
            key: result.get(key)
            for key in ("status", "figure_count", "panel_count", "series_count")
        },
        "panels": [
            {
                "panel_id": row.get("panel_id"),
                "bbox": row.get("bbox"),
                "plot_box": row.get("plot_box"),
                "ocr_status": row.get("ocr_status"),
            }
            for row in panel_rows
        ],
        "series": [
            {
                "panel_id": row.get("panel_id"),
                "y_axis_side": row.get("y_axis_side"),
                "point_count": len(row.get("points", [])),
                "extraction_status": row.get("extraction_status"),
                "trace_status": row.get("metadata", {})
                    .get("trace_specification", {}).get("status"),
                "trace_reason": row.get("metadata", {})
                    .get("trace_specification", {}).get("reason"),
                "trace_specification": row.get("metadata", {})
                    .get("trace_specification"),
                "raster_qc": row.get("metadata", {}).get("raster_qc"),
                "axis_text_evidence": row.get("metadata", {})
                    .get("axis_text_evidence"),
                "calibration_errors": row.get("metadata", {})
                    .get("calibration_errors"),
                "x_calibration": row.get("metadata", {}).get("x_calibration"),
                "y_calibration": row.get("metadata", {}).get("y_calibration"),
                "plot_box_pixels": row.get("metadata", {}).get("plot_box_pixels"),
                "axis_assignment": row.get("metadata", {})
                    .get("series_axis_assignment"),
                "x_label": row.get("x_label"),
                "y_label": row.get("y_label"),
                "chart_family": row.get("metadata", {})
                    .get("chart_family_classification"),
                "axis_label_evidence": row.get("metadata", {})
                    .get("axis_label_evidence"),
                "axis_text_color_association": row.get("metadata", {})
                    .get("y_axis_text_color_association"),
                "x_axis_anchors": row.get("metadata", {})
                    .get("x_axis_anchors"),
                "y_axis_anchors": row.get("metadata", {})
                    .get("y_axis_anchors_by_side"),
                "color_detection": row.get("metadata", {})
                    .get("color_detection"),
                "color_families": row.get("metadata", {})
                    .get("color_family_detection"),
                "y_calibrations": list(row.get("metadata", {})
                    .get("y_axis_calibrations", {})),
            }
            for row in series_rows
        ],
    }

    assert result.get("panel_count", 0) >= 4, json.dumps(summary, sort_keys=True)
    assert len(panel_rows) >= 4, json.dumps(summary, sort_keys=True)
    assert all(row.get("plot_box") for row in panel_rows), json.dumps(summary, sort_keys=True)
    assert p8_bottom_right, json.dumps(summary, sort_keys=True)
    assert p8_dual_axis_series, json.dumps(summary, sort_keys=True)
    assert {row.get("y_axis_side") for row in p8_dual_axis_series} >= {
        "LEFT", "RIGHT",
    }, json.dumps(summary, sort_keys=True)
    assert any(row.get("points") for row in p8_dual_axis_series), json.dumps(summary, sort_keys=True)
