from __future__ import annotations

import json
from pathlib import Path

import pytest


class EmptyContext:
    def search(self, kind, text=""):
        return []


def _ocr_row(text: str, center_x: float, center_y: float, confidence: float = 0.99):
    return {
        "text": text,
        "confidence": confidence,
        "polygon": [
            [center_x - 5, center_y - 4],
            [center_x + 5, center_y - 4],
            [center_x + 5, center_y + 4],
            [center_x - 5, center_y + 4],
        ],
    }


def _make_monotonic_chart(path: Path) -> list[dict]:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 40, 360, 270), outline=(25, 25, 25), width=4)
    points = []
    for x in range(70, 346):
        fraction = (x - 70) / 275
        y = int(220 - 125 * fraction + 15 * (fraction ** 2))
        points.append((x, y))
    draw.line(points, fill=(230, 20, 30), width=3)
    draw.text((155, 294), "Time (s)", fill=(20, 20, 20))
    draw.text((8, 148), "Signal (mA)", fill=(20, 20, 20))
    image.save(path, format="PNG")

    rows = [
        _ocr_row("0", 70, 282),
        _ocr_row("5", 205, 282),
        _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 65),
        _ocr_row("5", 42, 155),
        _ocr_row("0", 42, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
        _ocr_row("Signal (mA)", 18, 155, 0.95),
    ]
    return rows


def test_axis_label_detection_uses_position_and_keeps_unit_evidence():
    from scientific_figure_data.axis_text import extract_axis_labels, split_axis_label_unit

    rows = [
        _ocr_row("Time (s)", 100, 225, 0.98),
        _ocr_row("Current density (A g-1)", 15, 110, 0.97),
        _ocr_row("Potential (V)", 180, 15, 0.98),
        _ocr_row("999", 120, 90, 0.99),
    ]
    result = extract_axis_labels(rows, (30, 30, 190, 190))
    assert result["x_label"] == "Time (s)"
    assert result["y_left_label"] == "Current density (A g-1)"
    assert result["y_right_label"] is None
    assert split_axis_label_unit(result["x_label"]) == ("Time", "s")
    assert split_axis_label_unit(result["y_left_label"]) == ("Current density", "A g-1")


def test_trace_specification_requires_ordered_x_axis_and_numeric_axes(tmp_path: Path):
    from scientific_figure_data.calibration import fit_linear_axis
    from scientific_figure_data.trace_spec import generate_trace_specification

    image = tmp_path / "chart.png"
    image.write_bytes(b"image fixture")
    x_cal = fit_linear_axis("x", [{"pixel": 10, "value": 0}, {"pixel": 90, "value": 10}], "s")
    y_cal = fit_linear_axis("y", [{"pixel": 90, "value": 0}, {"pixel": 10, "value": 5}], "mA")
    color = {"status": "UNIQUE_CHROMATIC_FAMILY", "color_rgb": [230, 20, 30],
             "color_tolerance": 24}

    accepted = generate_trace_specification(
        image, (10, 10, 90, 90), color, x_cal, y_cal, "UNCLASSIFIED", "Cycle number"
    )
    assert accepted["status"] == "READY"
    assert accepted["specification"]["path_order"] == "CONNECTED_2D_PIXEL_PATH_LEFT_TO_RIGHT"

    cv = generate_trace_specification(
        image, (10, 10, 90, 90), color, x_cal, y_cal, "CV", "Potential (V)"
    )
    assert cv["status"] == "NOT_SUPPORTED"
    assert cv["reason"] == "NON_MONOTONIC_PATH_REQUIRES_ORDERED_TRACE_ALGORITHM"

    unordered = generate_trace_specification(
        image, (10, 10, 90, 90), color, x_cal, y_cal, "UNCLASSIFIED", "Capacity (mAh g-1)"
    )
    assert unordered["status"] == "NEEDS_REVIEW"
    assert unordered["reason"] == "X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER"


def test_panel_segmentation_finds_a_two_by_three_grid(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.panel_segmentation import detect_panel_regions

    image_path = tmp_path / "six_panels.png"
    image = Image.new("RGB", (720, 520), "white")
    draw = ImageDraw.Draw(image)
    panel_width, panel_height = 205, 205
    x_positions = (20, 257, 494)
    y_positions = (20, 285)
    for row, top in enumerate(y_positions):
        for column, left in enumerate(x_positions):
            draw.rectangle(
                (left, top, left + panel_width, top + panel_height),
                outline=(20, 20, 20), width=3,
            )
            draw.line(
                (left + 18, top + 160, left + 60, top + 95,
                 left + 110, top + 125, left + 180, top + 55),
                fill=(220, 30 + row * 30, 40 + column * 20), width=3,
            )
    image.save(image_path, format="PNG")

    result = detect_panel_regions(image_path)
    assert result["status"] == "PROVISIONAL_PANELS_DETECTED"
    assert result["panel_count"] == 6
    assert all(panel["segmentation_provenance"] == "AUTO_RASTER_WHITESPACE_SEGMENTATION"
               for panel in result["panels"])


def test_plot_frame_detection_recovers_an_open_l_shaped_axis(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_plot_box_candidates

    image_path = tmp_path / "open_l_axis.png"
    image = Image.new("RGB", (500, 350), "white")
    draw = ImageDraw.Draw(image)
    # A color-coded left Y-axis spine with a black X-axis is common in
    # dual-axis scientific plots; candidate detection must retain it.
    draw.line((60, 40, 60, 300), fill=(225, 25, 35), width=3)
    draw.line((60, 300, 450, 300), fill=(15, 15, 15), width=3)
    draw.line(
        [(x, int(260 - 145 * (x - 75) / 350)) for x in range(75, 436)],
        fill=(225, 25, 35), width=3,
    )
    draw.line(
        [(x, int(275 - 85 * (x - 75) / 350)) for x in range(75, 436)],
        fill=(25, 75, 225), width=3,
    )
    image.save(image_path, format="PNG")

    result = detect_plot_box_candidates(image_path)
    assert result["status"] == "PLOT_FRAME_CANDIDATES_FOUND", result
    candidate = result["candidates"][0]
    assert candidate["candidate_type"] == "OPEN_AXIS_CORNER"
    x0, y0, x1, y1 = candidate["pixel_bbox"]
    assert abs(x0 - 60) <= 4
    assert abs(y0 - 40) <= 4
    assert abs(x1 - 451) <= 4
    assert abs(y1 - 301) <= 4


def test_colored_y_axis_spine_is_distinguished_from_curve_endpoints(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_colored_y_axis_spines

    image_path = tmp_path / "color_coded_y_axis.png"
    image = Image.new("RGB", (500, 350), "white")
    draw = ImageDraw.Draw(image)
    draw.line((60, 40, 60, 300), fill=(225, 25, 35), width=3)
    draw.line((60, 300, 450, 300), fill=(15, 15, 15), width=3)
    draw.line(
        [(x, int(260 - 145 * (x - 75) / 350)) for x in range(75, 436)],
        fill=(225, 25, 35), width=3,
    )
    draw.line(
        [(x, int(275 - 85 * (x - 75) / 350)) for x in range(75, 436)],
        fill=(25, 75, 225), width=3,
    )
    image.save(image_path, format="PNG")

    result = detect_colored_y_axis_spines(image_path, (60, 40, 450, 300))
    left = result["sides"]["LEFT"]
    right = result["sides"]["RIGHT"]
    assert left["status"] == "CHROMATIC_Y_AXIS_SPINE_DETECTED", result
    assert left["vertical_row_coverage"] >= 0.90
    assert left["hue_purity"] >= 0.95
    assert abs((left["hue_center_degrees"] - 0.0 + 180.0) % 360.0 - 180.0) <= 8.0
    assert right["status"] != "CHROMATIC_Y_AXIS_SPINE_DETECTED"

    # A colored axis spine by itself is not a data series and must be excluded
    # from the hue-family inventory used to create trace candidates.
    axis_only_path = tmp_path / "axis_spine_without_curve.png"
    axis_only = Image.new("RGB", (500, 350), "white")
    axis_draw = ImageDraw.Draw(axis_only)
    axis_draw.line((60, 40, 60, 300), fill=(225, 25, 35), width=3)
    axis_draw.line((60, 300, 450, 300), fill=(15, 15, 15), width=3)
    axis_only.save(axis_only_path, format="PNG")
    from scientific_figure_data.plot_region import detect_chromatic_color_families
    family_result = detect_chromatic_color_families(
        axis_only_path, (60, 40, 450, 300)
    )
    assert family_result["status"] == "NEEDS_REVIEW"
    assert family_result["reason"] == "INSUFFICIENT_CHROMATIC_PIXELS"
    assert (
        family_result["axis_spine_exclusion"]["sides"]["LEFT"]["status"]
        == "CHROMATIC_Y_AXIS_SPINE_DETECTED"
    )


def test_downsampled_plot_frame_candidates_map_back_to_original_pixels(
    tmp_path: Path,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_plot_box_candidates

    image_path = tmp_path / "large_open_axis_figure.png"
    image = Image.new("RGB", (2600, 2200), "white")
    draw = ImageDraw.Draw(image)
    draw.line((120, 80, 120, 1980), fill=(20, 20, 20), width=4)
    draw.line((120, 1980, 2460, 1980), fill=(20, 20, 20), width=4)
    draw.line(
        [(x, int(1780 - 650 * (x - 180) / 2200)) for x in range(180, 2420)],
        fill=(225, 25, 35), width=4,
    )
    image.save(image_path, format="PNG")

    result = detect_plot_box_candidates(image_path)
    assert result["status"] == "PLOT_FRAME_CANDIDATES_FOUND", result
    assert result["analysis_scale"] < 1.0
    assert result["analysis_image_size"][0] * result["analysis_image_size"][1] <= 5_000_000
    candidate = next(
        item for item in result["candidates"]
        if item.get("candidate_type") == "OPEN_AXIS_CORNER"
    )
    x0, y0, x1, y1 = candidate["pixel_bbox"]
    assert abs(x0 - 120) <= 8
    assert abs(y0 - 80) <= 8
    assert abs(x1 - 2461) <= 8
    assert abs(y1 - 1981) <= 8
    assert candidate["image_size"] == [2600, 2200]


def test_panel_segmentation_finds_adjacent_plot_frames_without_white_gutters(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.panel_segmentation import detect_panel_regions
    from scientific_figure_data.plot_region import detect_plot_box_candidates

    image_path = tmp_path / "adjacent_plots_no_gutter.png"
    image = Image.new("RGB", (640, 400), "white")
    draw = ImageDraw.Draw(image)

    # The two plot frames share one vertical border. There is no broad white
    # gutter between them, so whitespace-only segmentation must not be relied on.
    draw.rectangle((30, 80, 320, 320), outline=(20, 20, 20), width=3)
    draw.rectangle((320, 80, 610, 320), outline=(20, 20, 20), width=3)
    left_red = [(x, int(270 - 125 * (x - 48) / 250)) for x in range(48, 304)]
    left_blue = [(x, int(285 - 70 * (x - 48) / 250)) for x in range(48, 304)]
    right_red = [(x, int(260 - 90 * (x - 338) / 250)) for x in range(338, 594)]
    right_blue = [(x, int(285 - 145 * (x - 338) / 250)) for x in range(338, 594)]
    draw.line(left_red, fill=(225, 25, 35), width=3)
    draw.line(left_blue, fill=(25, 75, 225), width=3)
    draw.line(right_red, fill=(225, 25, 35), width=3)
    draw.line(right_blue, fill=(25, 75, 225), width=3)

    # Dense low-contrast chart ink avoids a completely empty row/column
    # projection while retaining the true plot-frame geometry.
    for y in range(100, 305, 24):
        draw.line((31, y, 319, y), fill=(240, 240, 240), width=1)
        draw.line((321, y, 609, y), fill=(240, 240, 240), width=1)
    # Thin, low-contrast vertical grid marks keep the horizontal projection
    # occupied too, ensuring this case exercises the frame-candidate fallback.
    draw.line((145, 81, 145, 319), fill=(240, 240, 240), width=8)
    draw.line((465, 81, 465, 319), fill=(240, 240, 240), width=8)
    image.save(image_path, format="PNG")

    detected = detect_plot_box_candidates(image_path)
    assert detected["status"] == "PLOT_FRAME_CANDIDATES_FOUND", detected
    boxes = [item["pixel_bbox"] for item in detected["candidates"]]
    assert any(abs(box[0] - 30) <= 4 and abs(box[2] - 320) <= 4 for box in boxes), boxes
    assert any(abs(box[0] - 320) <= 4 and abs(box[2] - 610) <= 4 for box in boxes), boxes

    segmented = detect_panel_regions(image_path)
    assert segmented["status"] == "PROVISIONAL_PANELS_DETECTED", segmented
    assert segmented["reason"] == "MULTIPLE_PLOT_FRAME_CANDIDATES"
    assert segmented["panel_count"] >= 2
    assert all(
        item["segmentation_provenance"] == "AUTO_PLOT_FRAME_CANDIDATE_SEGMENTATION"
        for item in segmented["panels"]
    )


def test_process_paper_auto_segments_adjacent_panels_before_plot_tracing(
    tmp_path: Path,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-adjacent"
    paper_dir.mkdir(parents=True)
    image_path = paper_dir / "Figure1.png"
    image = Image.new("RGB", (640, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 80, 320, 320), outline=(20, 20, 20), width=3)
    draw.rectangle((320, 80, 610, 320), outline=(20, 20, 20), width=3)
    draw.line(
        [(x, int(270 - 125 * (x - 48) / 250)) for x in range(48, 304)],
        fill=(225, 25, 35), width=3,
    )
    draw.line(
        [(x, int(285 - 70 * (x - 48) / 250)) for x in range(48, 304)],
        fill=(25, 75, 225), width=3,
    )
    draw.line(
        [(x, int(260 - 90 * (x - 338) / 250)) for x in range(338, 594)],
        fill=(225, 25, 35), width=3,
    )
    draw.line(
        [(x, int(285 - 145 * (x - 338) / 250)) for x in range(338, 594)],
        fill=(25, 75, 225), width=3,
    )
    for y in range(100, 305, 24):
        draw.line((31, y, 319, y), fill=(240, 240, 240), width=1)
        draw.line((321, y, 609, y), fill=(240, 240, 240), width=1)
    draw.line((145, 81, 145, 319), fill=(240, 240, 240), width=8)
    draw.line((465, 81, 465, 319), fill=(240, 240, 240), width=8)
    image.save(image_path, format="PNG")

    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({
            "figures": [{
                "figure_id": "Figure1",
                "image_path": "Figure1.png",
                "caption": "Two adjacent time-series panels with no white gutter.",
                "panels": [],
            }]
        }),
        encoding="utf-8",
    )

    result = process_paper(
        input_root,
        Path("paper-adjacent"),
        tmp_path / "output",
        options={"ocr": False, "memory_limit_mb": 1024},
    )

    assert result["panel_count"] >= 2
    assert result["figure_count"] == 1
    paper_output = tmp_path / "output" / "papers" / "paper-adjacent"
    inventory = json.loads((paper_output / "figure_inventory.json").read_text(encoding="utf-8"))
    layout = json.loads((paper_output / "panel_layout.json").read_text(encoding="utf-8"))
    detected = inventory["figures"][0]["panel_segmentation"]
    assert detected["reason"] == "MULTIPLE_PLOT_FRAME_CANDIDATES"
    auto_panels = [
        item for item in layout["panels"]
        if item["segmentation_provenance"] == "AUTO_PLOT_FRAME_CANDIDATE_SEGMENTATION"
    ]
    assert len(auto_panels) >= 2
    assert all(item["evidence_image_path"] for item in auto_panels)
    assert all(item["plot_box"] for item in auto_panels)
    assert all(
        item["plot_box_coordinate_space"] == "PANEL_IMAGE_PIXELS"
        for item in auto_panels
    )


def test_process_paper_auto_traces_and_reconstructs_monotonic_raster_curve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from scientific_figure_data import ocr
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-a"
    paper_dir.mkdir(parents=True)
    image_path = paper_dir / "Figure1.png"
    ocr_rows = _make_monotonic_chart(image_path)
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({
            "figures": [{
                "figure_id": "Figure1",
                "image_path": "Figure1.png",
                "caption": "A monotonic time-series chart.",
                "panels": [],
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "run_ocr", lambda path: ocr_rows)

    output_root = tmp_path / "output"
    result = process_paper(
        input_root,
        Path("paper-a"),
        output_root,
        options={"ocr": True, "memory_limit_mb": 1024},
    )

    assert result["panel_count"] == 1
    assert result["series_count"] == 1
    series = result["series"][0]
    assert series["extraction_method"] == "raster_color_connected_path"
    assert series["extraction_status"] == "EXTRACTED_PROVISIONAL"
    assert series["metadata"]["points_count"] > 100
    assert series["metadata"]["trace_specification"]["status"] == "READY"
    assert series["metadata"]["trace_specification"]["input_provenance"]["automation_status"] == "FULLY_AUTOMATIC"
    assert series["metadata"]["x_calibration"]["anchors"]
    assert series["metadata"]["y_calibration"]["anchors"]
    assert series["metadata"]["reconstruction"]["status"] == "RENDERED"

    paper_output = output_root / "papers" / "paper-a"
    assert (paper_output / "reconstructed").is_dir()
    assert (paper_output / "comparisons" / "ALL_PANELS_COMPARISON.png").is_file()
    csv_files = list((paper_output / "series").glob("**/panel_series.csv"))
    assert csv_files
    assert result["panel_comparison"]["status"] == "WRITTEN"


def test_process_paper_does_not_route_cv_into_monotonic_raster_tracer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from scientific_figure_data import ocr
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-cv"
    paper_dir.mkdir(parents=True)
    image_path = paper_dir / "FigureCV.png"
    rows = _make_monotonic_chart(image_path)
    rows[-2] = _ocr_row("Potential (V)", 205, 305, 0.99)
    rows[-1] = _ocr_row("Current density (A g-1)", 18, 155, 0.99)
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({
            "figures": [{
                "figure_id": "FigureCV",
                "image_path": "FigureCV.png",
                "caption": "Cyclic voltammetry.",
                "panels": [],
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "run_ocr", lambda path: rows)

    result = process_paper(
        input_root, Path("paper-cv"), tmp_path / "output",
        options={"ocr": True, "memory_limit_mb": 1024},
    )
    item = result["series"][0]
    assert item["metadata"]["chart_family_classification"]["technique"] == "CV"
    assert item["metadata"]["trace_specification"]["status"] == "NOT_SUPPORTED"
    assert item["metadata"]["points_count"] == 0



def test_process_paper_records_ocr_failure_and_continues_with_panel_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from scientific_figure_data import ocr
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-ocr-failure"
    paper_dir.mkdir(parents=True)
    image_path = paper_dir / "Figure1.png"
    _make_monotonic_chart(image_path)
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({
            "figures": [{
                "figure_id": "Figure1",
                "image_path": "Figure1.png",
                "caption": "A monotonic time-series chart.",
                "panels": [],
            }]
        }),
        encoding="utf-8",
    )

    def fail_ocr(_image_path: Path):
        raise TypeError("RapidOCR engine_type must be an Enum")

    monkeypatch.setattr(ocr, "run_ocr", fail_ocr)
    result = process_paper(
        input_root,
        Path("paper-ocr-failure"),
        tmp_path / "output",
        options={"ocr": True, "memory_limit_mb": 1024},
    )

    assert result["status"] == "COMPLETED_WITH_REVIEW"
    assert result["job_state"] == "NEEDS_REVIEW"
    assert result["panel_count"] == 1
    panel_ocr = result["panels"][0]["ocr_status"]
    assert panel_ocr["status"] == "FAILED"
    assert panel_ocr["error_type"] == "TypeError"
    assert "Enum" in panel_ocr["message"]
    assert result["series"][0]["metadata"]["ocr_status"] == panel_ocr
    assert any(
        warning.startswith("OCR_FAILED:Figure1/")
        for warning in result["snapshot"]["warnings"]
    )


def test_chromatic_color_family_detector_separates_two_distinct_curve_colors(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_chromatic_color_families

    path = tmp_path / "two_colors.png"
    image = Image.new("RGB", (320, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 20, 285, 180), outline=(20, 20, 20), width=3)
    red = [(x, int(145 - 80 * (x - 40) / 230)) for x in range(40, 276)]
    blue = [(x, int(155 - 55 * (x - 40) / 230)) for x in range(40, 276)]
    draw.line(red, fill=(225, 30, 35), width=3)
    draw.line(blue, fill=(25, 70, 220), width=3)
    image.save(path)

    result = detect_chromatic_color_families(path, (30, 20, 285, 180))
    assert result["status"] == "MULTIPLE_CHROMATIC_FAMILIES"
    assert result["family_count"] == 2
    colors = result["families"]
    assert any(c["color_rgb"][0] > 150 and c["color_rgb"][2] < 80 for c in colors)
    assert any(c["color_rgb"][2] > 150 and c["color_rgb"][0] < 80 for c in colors)


def test_numeric_axis_anchor_extraction_preserves_both_y_sides():
    from scientific_figure_data.axis_text import extract_numeric_axis_anchors

    rows = [
        _ocr_row("10", 42, 65), _ocr_row("5", 42, 155), _ocr_row("0", 42, 255),
        _ocr_row("100", 378, 65), _ocr_row("50", 378, 155), _ocr_row("0", 378, 255),
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
    ]
    result = extract_numeric_axis_anchors(rows, (55, 40, 360, 270))
    assert len(result["x_anchors"]) == 3
    assert len(result["y_left_anchors"]) == 3
    assert len(result["y_right_anchors"]) == 3


def test_process_paper_automatically_extracts_two_monotonic_color_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data import ocr
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-two-color"
    paper_dir.mkdir(parents=True)
    image_path = paper_dir / "Figure1.png"
    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 40, 360, 270), outline=(25, 25, 25), width=4)
    red, blue = [], []
    for x in range(70, 346):
        fraction = (x - 70) / 275
        red.append((x, int(220 - 110 * fraction)))
        blue.append((x, int(238 - 65 * fraction)))
    draw.line(red, fill=(230, 20, 30), width=3)
    draw.line(blue, fill=(20, 65, 225), width=3)
    draw.text((155, 294), "Time (s)", fill=(20, 20, 20))
    draw.text((8, 148), "Signal (mA)", fill=(20, 20, 20))
    image.save(image_path)

    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 65), _ocr_row("5", 42, 155), _ocr_row("0", 42, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
        _ocr_row("Signal (mA)", 18, 155, 0.95),
    ]
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({"figures": [{
            "figure_id": "Figure1", "image_path": "Figure1.png",
            "caption": "Two monotonic time-series curves.", "panels": [],
        }]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "run_ocr", lambda path: rows)

    result = process_paper(
        input_root, Path("paper-two-color"), tmp_path / "output",
        options={"ocr": True, "memory_limit_mb": 1024},
    )
    assert result["series_count"] == 2
    assert all(item["metadata"]["trace_specification"]["status"] == "READY"
               for item in result["series"])
    assert all(item["metadata"]["trace_specification"]["input_provenance"]["automation_status"]
               == "FULLY_AUTOMATIC" for item in result["series"])
    assert all(item["metadata"]["points_count"] >= 100 for item in result["series"])
    assert len({tuple(item["metadata"]["color_detection"]["color_rgb"])
                for item in result["series"]}) == 2


def test_dual_y_axis_calibrations_are_retained_without_guessing_series_side(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.pipeline import _extract_panel

    image_path = tmp_path / "dual_axis.png"
    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 40, 360, 270), outline=(25, 25, 25), width=4)
    draw.line([(70, 220), (120, 190), (170, 165), (220, 140), (270, 115), (345, 80)],
              fill=(230, 20, 30), width=3)
    image.save(image_path)
    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 65), _ocr_row("5", 42, 155), _ocr_row("0", 42, 255),
        _ocr_row("100", 378, 65), _ocr_row("50", 378, 155), _ocr_row("0", 378, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
    ]
    context = type("EmptyContext", (), {"search": lambda self, kind, text="": []})()
    result = _extract_panel(
        image_path, "paper", "Figure1", "a", {}, {"caption": "Time series"},
        {}, context, None, ocr_evidence=rows,
    )
    metadata = result[0].metadata
    assert set(metadata["y_axis_calibrations"]) == {"LEFT", "RIGHT"}
    assert metadata["series_axis_assignment"]["status"] == "AMBIGUOUS_DUAL_Y_AXIS"
    assert metadata["series_axis_assignment"]["selected_side"] is None
    assert metadata["trace_specification"]["status"] == "READY"
    assert metadata["trace_specification"]["specification"]["numeric_mapping_status"] == "PARTIALLY_CALIBRATED"
    assert metadata["trace_specification"]["input_provenance"]["automation_status"] == "FULLY_AUTOMATIC_GEOMETRY_ONLY"
    assert metadata["calibration_errors"]["y"] == "AMBIGUOUS_DUAL_Y_AXIS_SERIES_ASSOCIATION"
    assert len(result[0].points) >= 100
    assert all(point.x is not None and point.y is None for point in result[0].points)
    assert all(point.pixel_x is not None and point.pixel_y is not None for point in result[0].points)


def test_multicolor_curves_match_color_coded_dual_y_axis_tick_labels(tmp_path: Path):
    from PIL import Image, ImageDraw, ImageFont
    from scientific_figure_data.pipeline import _extract_panel

    image_path = tmp_path / "color_coded_dual_axis.png"
    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((55, 40, 360, 270), outline=(25, 25, 25), width=4)

    red_curve, blue_curve = [], []
    for x in range(70, 346):
        fraction = (x - 70) / 275
        red_curve.append((x, int(220 - 110 * fraction)))
        blue_curve.append((x, int(238 - 65 * fraction)))
    draw.line(red_curve, fill=(230, 20, 30), width=3)
    draw.line(blue_curve, fill=(20, 65, 225), width=3)

    def draw_tick(text: str, center_x: int, center_y: int, color: tuple[int, int, int]):
        bounds = draw.textbbox((0, 0), text, font=font)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        left = int(round(center_x - width / 2))
        top = int(round(center_y - height / 2))
        draw.text((left - bounds[0], top - bounds[1]), text, fill=color, font=font)
        return {
            "text": text,
            "confidence": 0.99,
            "polygon": [
                [left, top], [left + width, top],
                [left + width, top + height], [left, top + height],
            ],
        }

    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        draw_tick("10", 42, 65, (230, 20, 30)),
        draw_tick("5", 42, 155, (230, 20, 30)),
        draw_tick("0", 42, 255, (230, 20, 30)),
        draw_tick("100", 378, 65, (20, 65, 225)),
        draw_tick("50", 378, 155, (20, 65, 225)),
        draw_tick("0", 378, 255, (20, 65, 225)),
        _ocr_row("Time (s)", 205, 305, 0.96),
        _ocr_row("Left response (mA)", 14, 155, 0.96),
        _ocr_row("Right response (mAh)", 402, 155, 0.96),
    ]
    image.save(image_path)

    from scientific_figure_data.plot_region import estimate_ocr_text_ink_color
    left_ink = estimate_ocr_text_ink_color(image_path, rows[3:6])
    right_ink = estimate_ocr_text_ink_color(image_path, rows[6:9])
    assert left_ink["status"] == "CHROMATIC_TEXT_COLOR_DETECTED", left_ink
    assert right_ink["status"] == "CHROMATIC_TEXT_COLOR_DETECTED", right_ink

    context = type("EmptyContext", (), {"search": lambda self, kind, text="": []})()
    records = _extract_panel(
        image_path, "paper", "Figure1", "a", {},
        {"caption": "Two monotonic time-series curves with two Y axes."},
        {}, context, None, ocr_evidence=rows,
    )
    assert len(records) == 2
    by_side = {record.y_axis_side: record for record in records}
    assert set(by_side) == {"LEFT", "RIGHT"}, [
        {
            "side": record.y_axis_side,
            "y_axis_calibrations": record.metadata.get("y_axis_calibrations"),
            "series_axis_assignment": record.metadata.get("series_axis_assignment"),
            "y_axis_text_color_association": record.metadata.get("y_axis_text_color_association"),
            "color_detection": record.metadata.get("color_detection"),
            "trace_specification": record.metadata.get("trace_specification"),
            "calibration_errors": record.metadata.get("calibration_errors"),
        }
        for record in records
    ]
    assert all(len(record.points) >= 100 for record in records)
    assert all(record.metadata["trace_specification"]["status"] == "READY"
               for record in records)
    assert all(
        record.metadata["series_axis_assignment"]["status"] in {
            "COLOR_MATCHED_TO_Y_AXIS_TEXT",
            "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
        }
        for record in records
    )
    assert all(
        record.metadata["y_axis_text_color_association"]["status"] in {
            "MATCHED", "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
        }
        for record in records
    )


def test_multicolor_curves_match_colored_y_spines_with_black_tick_labels(
    tmp_path: Path,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data.pipeline import _extract_panel

    image_path = tmp_path / "colored_y_spines_black_ticks.png"
    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)

    # Tick labels are black OCR evidence. Only the two Y-axis spines are
    # color-coded, matching their respective red/blue curves.
    draw.line((54, 40, 54, 270), fill=(230, 20, 30), width=3)
    draw.line((54, 40, 360, 40), fill=(25, 25, 25), width=4)
    draw.line((54, 270, 360, 270), fill=(25, 25, 25), width=4)
    draw.line((360, 40, 360, 270), fill=(20, 65, 225), width=3)

    red_curve, blue_curve = [], []
    for x in range(70, 346):
        fraction = (x - 70) / 275
        red_curve.append((x, int(220 - 110 * fraction)))
        blue_curve.append((x, int(238 - 65 * fraction)))
    draw.line(red_curve, fill=(230, 20, 30), width=3)
    draw.line(blue_curve, fill=(20, 65, 225), width=3)
    image.save(image_path)

    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 65), _ocr_row("5", 42, 155), _ocr_row("0", 42, 255),
        _ocr_row("100", 378, 65), _ocr_row("50", 378, 155), _ocr_row("0", 378, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
    ]
    context = type("EmptyContext", (), {"search": lambda self, kind, text="": []})()
    records = _extract_panel(
        image_path, "paper", "Figure1", "a",
        {"plot_box": [55, 40, 360, 270]},
        {"caption": "Two monotonic time-series curves with dual Y axes."},
        {}, context, None, ocr_evidence=rows,
    )
    assert len(records) == 2
    by_side = {record.y_axis_side: record for record in records}
    assert set(by_side) == {"LEFT", "RIGHT"}, [
        {
            "side": record.y_axis_side,
            "assignment": record.metadata.get("series_axis_assignment"),
            "association": record.metadata.get("y_axis_text_color_association"),
            "color": record.metadata.get("color_detection"),
        }
        for record in records
    ]
    for record in records:
        assignment = record.metadata["series_axis_assignment"]
        association = record.metadata["y_axis_text_color_association"]
        assert assignment["status"] in {
            "COLOR_MATCHED_TO_Y_AXIS_TEXT",
            "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
        }
        assert association["status"] in {
            "MATCHED", "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
        }
        matched_sources = {
            item["source"]
            for side in association["side_color_evidence"].values()
            for item in side["candidate_inks"]
        }
        assert "AXIS_SPINE" in matched_sources
        assert len(record.points) >= 100, {
            "side": record.y_axis_side,
            "trace_specification": record.metadata.get("trace_specification"),
            "raster_qc": record.metadata.get("raster_qc"),
            "color_detection": record.metadata.get("color_detection"),
            "calibration_errors": record.metadata.get("calibration_errors"),
        }
        if record.y_axis_side == "LEFT":
            assert 55 in record.metadata["raster_qc"]["edge_axis_columns_removed"]
        assert all(point.x is not None and point.y is not None for point in record.points)


def test_hue_family_detector_groups_antialiased_shades_and_traces_pixel_geometry(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_chromatic_color_families
    from scientific_figure_data.raster import trace_monotonic_color

    path = tmp_path / "hue_family_shades.png"
    image = Image.new("RGB", (340, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 18, 315, 205), outline=(20, 20, 20), width=3)
    red_shades = [(253, 11, 12), (252, 69, 69), (253, 120, 120), (253, 185, 184)]
    for x in range(35, 306):
        fraction = (x - 35) / 270
        y = int(166 - 95 * fraction + 8 * fraction * fraction)
        for offset, color in enumerate(red_shades):
            image.putpixel((x, y + offset), color)
    blue = [(x, int(178 - 65 * (x - 35) / 270)) for x in range(35, 306)]
    draw.line(blue, fill=(20, 65, 225), width=3)
    image.save(path)

    detected = detect_chromatic_color_families(path, (28, 22, 312, 202))
    assert detected["status"] == "MULTIPLE_CHROMATIC_FAMILIES"
    assert detected["family_count"] == 2
    red_family = next(
        item for item in detected["families"]
        if item["color_match"]["hue_center_degrees"] < 20
        or item["color_match"]["hue_center_degrees"] > 340
    )
    points, qc = trace_monotonic_color(
        str(path), tuple(red_family["color_rgb"]), red_family["color_tolerance"],
        None, None, plot_box=(28, 22, 312, 202),
        color_match=red_family["color_match"],
    )
    assert qc["status"] == "EXTRACTED_PROVISIONAL", qc
    assert qc["geometry_only"] is True
    assert len(points) >= 200
    assert all(point.x is None and point.y is None for point in points)
    assert all(point.pixel_x is not None and point.pixel_y is not None for point in points)


def test_branch_detector_recovers_secondary_persistent_band_when_single_band_is_modal(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.raster import (
        detect_monotonic_color_branches, trace_monotonic_color,
    )

    image_path = tmp_path / "persistent_secondary_branch.png"
    image = Image.new("RGB", (360, 220), "white")
    draw = ImageDraw.Draw(image)
    color = (220, 35, 45)
    draw.line((32, 72, 328, 72), fill=color, width=3)
    # The second branch is present over only part of the X range, so a
    # single-band mode is still the most frequent per-column observation.
    draw.line((185, 132, 328, 132), fill=color, width=3)
    image.save(image_path)

    plot_box = (20, 20, 340, 180)
    detected = detect_monotonic_color_branches(
        str(image_path), color, 12, plot_box=plot_box,
    )
    assert detected["status"] == "MULTIPLE_MONOTONIC_COLOR_BRANCHES", detected
    assert detected["branch_count"] == 2, detected
    assert len(detected["branches"]) == 2, detected
    assert detected["branches"][0]["x_span"] > 200, detected
    assert detected["branches"][1]["x_span"] > 100, detected

    points, qc = trace_monotonic_color(
        str(image_path), color, 12, None, None,
        plot_box=plot_box, branch_index=1, branch_count=2,
    )
    assert qc["status"] == "EXTRACTED_PROVISIONAL", qc
    assert len(points) >= 100
    assert all(point.pixel_x is not None and point.pixel_y is not None for point in points)


def test_pipeline_expands_five_color_families_into_numeric_series(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.pipeline import _extract_panel

    image_path = tmp_path / "five_color_numeric_time_series.png"
    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)
    plot_box = (54, 40, 360, 270)
    draw.line((54, 40, 54, 270), fill=(20, 20, 20), width=3)
    draw.line((54, 270, 360, 270), fill=(20, 20, 20), width=3)

    colors = [
        (230, 20, 30),
        (230, 125, 25),
        (25, 170, 75),
        (20, 65, 225),
        (160, 35, 200),
    ]
    for index, color in enumerate(colors):
        base_y = 225 - index * 34
        curve = [
            (
                x,
                int(base_y - 18 * (x - 70) / 275 + 2 * ((x - 70) / 275) ** 2),
            )
            for x in range(70, 346)
        ]
        draw.line(curve, fill=color, width=3)
    image.save(image_path)

    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 55), _ocr_row("5", 42, 150), _ocr_row("0", 42, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
    ]
    context = type("EmptyContext", (), {"search": lambda self, kind, text="": []})()
    records = _extract_panel(
        image_path, "paper", "Figure1", "a",
        {"plot_box": list(plot_box)},
        {"caption": "Five independent colored time-series curves."},
        {}, context, None, ocr_evidence=rows,
    )

    assert len(records) == 5, [
        {
            "status": record.metadata.get("color_detection"),
            "trace": record.metadata.get("trace_specification"),
            "qc": record.metadata.get("raster_qc"),
        }
        for record in records
    ]
    assert len({tuple(record.metadata["color_detection"]["color_rgb"]) for record in records}) == 5
    for record in records:
        assert record.points and len(record.points) >= 200, {
            "series_id": record.series_id,
            "color": record.metadata.get("color_detection"),
            "trace": record.metadata.get("trace_specification"),
            "raster_qc": record.metadata.get("raster_qc"),
        }
        assert record.metadata["trace_specification"]["status"] in {
            "READY", "READY_WITH_REVIEW",
        }
        assert all(point.x is not None and point.y is not None for point in record.points)


def test_multicolor_family_inventory_supports_more_than_four_curves(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_chromatic_color_families

    image_path = tmp_path / "five_color_curves.png"
    image = Image.new("RGB", (400, 260), "white")
    draw = ImageDraw.Draw(image)
    colors = [
        (230, 30, 35),
        (230, 120, 25),
        (30, 170, 60),
        (25, 90, 225),
        (160, 35, 205),
    ]
    for index, color in enumerate(colors):
        base_y = 48 + index * 34
        points = [
            (x, int(base_y - 14 * (x - 35) / 330 + 2 * ((x - 35) / 330) ** 2))
            for x in range(35, 366)
        ]
        draw.line(points, fill=color, width=3)
    image.save(image_path, format="PNG")

    result = detect_chromatic_color_families(
        image_path, (20, 20, 380, 230)
    )
    assert result["status"] == "MULTIPLE_CHROMATIC_FAMILIES", result
    assert result["family_count"] == 5, result
    assert result["truncated"] is False
    hues = sorted(
        item["color_match"]["hue_center_degrees"]
        for item in result["families"]
    )
    assert len(hues) == len(set(round(value / 10) for value in hues))


def test_geometry_only_trace_specification_does_not_require_a_y_axis_mapping(tmp_path: Path):
    from scientific_figure_data.calibration import fit_linear_axis
    from scientific_figure_data.trace_spec import generate_trace_specification

    image = tmp_path / "chart.png"
    image.write_bytes(b"image fixture")
    x_cal = fit_linear_axis("x", [{"pixel": 10, "value": 0}, {"pixel": 90, "value": 10}], "s")
    color = {
        "status": "UNIQUE_CHROMATIC_FAMILY",
        "color_rgb": [230, 20, 30],
        "color_tolerance": 24,
        "color_match": {
            "space": "HSV_HUE_FAMILY",
            "hue_center_degrees": 0.0,
            "hue_tolerance_degrees": 12.0,
            "minimum_saturation": 0.14,
            "minimum_value": 0.20,
        },
    }

    result = generate_trace_specification(
        image, (10, 10, 90, 90), color, x_cal, None,
        "UNCLASSIFIED", "Time (s)", allow_geometry_only=True,
    )
    assert result["status"] == "READY"
    spec = result["specification"]
    assert spec["numeric_mapping_status"] == "PARTIALLY_CALIBRATED"
    assert spec["x_calibration"]["status"] == "CALIBRATED_NUMERIC"
    assert spec["y_calibration"] is None
    assert spec["color_match"]["space"] == "HSV_HUE_FAMILY"


def test_geometry_only_series_gets_overlay_but_no_numeric_reconstruction(tmp_path: Path):
    from PIL import Image
    from scientific_figure_data.models import SeriesPoint, SeriesRecord
    from scientific_figure_data.reconstruction import render_series_artifacts

    source = tmp_path / "source.png"
    Image.new("RGB", (100, 80), "white").save(source)
    item = SeriesRecord(
        series_id="geometry-only", paper_id="paper", figure_id="Figure1", panel_id="a",
        technique=None, domain=None, label=None, x_label="Time", y_label="Unassigned",
        x_unit="s", y_unit=None,
        points=[
            SeriesPoint(0, 0.0, None, 10.0, 60.0),
            SeriesPoint(1, 1.0, None, 40.0, 45.0),
            SeriesPoint(2, 2.0, None, 70.0, 25.0),
        ],
    )
    result = render_series_artifacts(item, source, tmp_path / "rendered")
    assert result["status"] == "GEOMETRY_ONLY_OVERLAY"
    assert Path(result["overlay_path"]).is_file()
    assert result["numeric_reconstruction_status"] == "NOT_CREATED_NUMERIC_MAPPING_UNRESOLVED"
    assert not list((tmp_path / "rendered").glob("*_reconstructed.png"))


def test_color_coded_axis_titles_can_resolve_dual_y_axis_mapping(tmp_path: Path):
    from PIL import Image, ImageDraw, ImageFont
    from scientific_figure_data.pipeline import _extract_panel

    image_path = tmp_path / "axis_title_colors.png"
    image = Image.new("RGB", (440, 340), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((55, 40, 360, 270), outline=(25, 25, 25), width=4)
    red_curve, blue_curve = [], []
    for x in range(70, 346):
        fraction = (x - 70) / 275
        red_curve.append((x, int(220 - 110 * fraction)))
        blue_curve.append((x, int(238 - 65 * fraction)))
    draw.line(red_curve, fill=(230, 20, 30), width=3)
    draw.line(blue_curve, fill=(20, 65, 225), width=3)

    def colored_row(text, x, y, color):
        bounds = draw.textbbox((0, 0), text, font=font)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        draw.text((x, y), text, fill=color, font=font)
        return {
            "text": text,
            "confidence": 0.99,
            "polygon": [
                [x, y], [x + width, y],
                [x + width, y + height], [x, y + height],
            ],
        }

    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 65), _ocr_row("5", 42, 155), _ocr_row("0", 42, 255),
        _ocr_row("100", 378, 65), _ocr_row("50", 378, 155), _ocr_row("0", 378, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
        colored_row("Left (mA)", 0, 148, (230, 20, 30)),
        colored_row("Right (mAh)", 365, 148, (20, 65, 225)),
    ]
    image.save(image_path)
    context = type("EmptyContext", (), {"search": lambda self, kind, text="": []})()
    records = _extract_panel(
        image_path, "paper", "Figure1", "a", {},
        {"caption": "Dual-axis time series."}, {}, context, None,
        ocr_evidence=rows,
    )
    assert len(records) == 2
    by_side = {item.y_axis_side: item for item in records}
    assert set(by_side) == {"LEFT", "RIGHT"}
    assert all(
        item.metadata["series_axis_assignment"]["status"] in {
            "COLOR_MATCHED_TO_Y_AXIS_TEXT",
            "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
        }
        for item in records
    )
    assert all(len(item.points) >= 100 for item in records), [
        {
            "series_id": item.series_id,
            "point_count": len(item.points),
            "raster_qc": item.metadata.get("raster_qc"),
            "trace_specification": item.metadata.get("trace_specification"),
        }
        for item in records
    ]



def test_achromatic_family_traces_gray_solid_and_dashed_as_separate_series(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_achromatic_trace_family
    from scientific_figure_data.raster import (
        detect_monotonic_color_branches, trace_monotonic_color,
    )

    image_path = tmp_path / "gray_solid_dashed_and_grid.png"
    image = Image.new("RGB", (420, 280), "white")
    draw = ImageDraw.Draw(image)
    # The crop contains the true plot boundaries. They must not be proposed
    # as trace paths after the narrow boundary exclusion.
    draw.rectangle((30, 25, 390, 245), outline=(25, 25, 25), width=3)
    plot_box = (30, 25, 390, 245)

    solid = [
        (x, int(177 - 25 * (x - 48) / 310))
        for x in range(48, 360)
    ]
    draw.line(solid, fill=(112, 112, 112), width=3)

    # Same neutral hue, but a separate dashed trace. Gaps are source gaps:
    # the extractor may group the fragments, but may not paint/interpolate them.
    def dash_y(x):
        return int(119 - 13 * (x - 54) / 292)
    for start in range(54, 348, 25):
        end = min(start + 17, 348)
        draw.line(
            [(x, dash_y(x)) for x in range(start, end)],
            fill=(142, 142, 142), width=3,
        )

    # A genuine neutral horizontal grid line is intentionally included.
    # It can be inventoried, but the extracted result must remain review-only.
    draw.line((35, 76, 385, 76), fill=(194, 194, 194), width=2)
    image.save(image_path)

    family = detect_achromatic_trace_family(image_path, plot_box)
    assert family["status"] == "UNIQUE_ACHROMATIC_FAMILY", family
    assert family["families"][0]["family_type"] == "ACHROMATIC"
    match = family["families"][0]
    detected = detect_monotonic_color_branches(
        str(image_path), tuple(match["color_rgb"]), match["color_tolerance"],
        plot_box=plot_box, color_match=match["color_match"],
        preserve_partial_fragments=True,
    )
    assert detected["status"] == "MULTIPLE_MONOTONIC_COLOR_BRANCHES", detected
    assert detected["branch_count"] == 3, detected
    assert detected["partial_fragment_tracking"]["track_count"] >= 1
    assert detected["partial_fragment_tracking"]["inter_fragment_pixels_inserted"] == 0

    branch_rows = detected["branches"]
    dashed_index = next(
        index for index, row in enumerate(branch_rows)
        if len(row.get("path_segments", [])) >= 3
    )
    dash_points, dash_qc = trace_monotonic_color(
        str(image_path), tuple(match["color_rgb"]), match["color_tolerance"],
        None, None, plot_box=plot_box, color_match=match["color_match"],
        branch_index=dashed_index, branch_count=len(branch_rows),
        preserve_partial_fragments=True,
    )
    assert dash_qc["status"] == "EXTRACTED_PROVISIONAL_NEEDS_REVIEW", dash_qc
    assert dash_qc["path_segment_count"] >= 3, dash_qc
    assert dash_qc["partial_fragment_tracking"]["inter_fragment_pixels_inserted"] == 0
    assert len(dash_points) == sum(
        segment["point_count"] for segment in dash_qc["path_segments"]
    )

    grid_index = next(
        index for index, row in enumerate(branch_rows)
        if row["x_span"] >= 0.60 * (plot_box[2] - plot_box[0])
        and row["y_span"] <= 2
    )
    _, grid_qc = trace_monotonic_color(
        str(image_path), tuple(match["color_rgb"]), match["color_tolerance"],
        None, None, plot_box=plot_box, color_match=match["color_match"],
        branch_index=grid_index, branch_count=len(branch_rows),
        preserve_partial_fragments=True,
    )
    assert grid_qc["status"] == "EXTRACTED_PROVISIONAL_NEEDS_REVIEW", grid_qc
    assert grid_qc["achromatic_geometry_review"]["horizontal_gridline_like"] is True
    assert grid_qc["review_required"] is True


def test_achromatic_candidate_does_not_claim_a_curve_when_neutral_pixels_are_absent(
    tmp_path: Path,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_achromatic_trace_family

    image_path = tmp_path / "chromatic_only.png"
    image = Image.new("RGB", (220, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.line((20, 120, 200, 35), fill=(225, 25, 35), width=3)
    image.save(image_path)

    result = detect_achromatic_trace_family(image_path, (10, 10, 210, 150))
    assert result["status"] == "NEEDS_REVIEW"
    assert result["reason"] == "INSUFFICIENT_ACHROMATIC_TRACE_PIXELS"
    assert result["families"] == []


def test_trace_specification_accepts_achromatic_candidate_family(tmp_path: Path):
    from scientific_figure_data.calibration import fit_linear_axis
    from scientific_figure_data.trace_spec import generate_trace_specification

    image = tmp_path / "achromatic-chart.png"
    image.write_bytes(b"image fixture")
    x_cal = fit_linear_axis(
        "x", [{"pixel": 10, "value": 0}, {"pixel": 90, "value": 10}], "s"
    )
    y_cal = fit_linear_axis(
        "y", [{"pixel": 90, "value": 0}, {"pixel": 10, "value": 5}], "mA"
    )
    achromatic = {
        "status": "UNIQUE_ACHROMATIC_FAMILY",
        "color_rgb": [128, 128, 128],
        "color_tolerance": 0,
        "color_match": {
            "space": "ACHROMATIC_LUMINANCE_RANGE",
            "maximum_chroma": 24,
            "minimum_luminance": 28,
            "maximum_luminance": 210,
        },
    }

    accepted = generate_trace_specification(
        image, (10, 10, 90, 90), achromatic, x_cal, y_cal,
        "UNCLASSIFIED", "Time (s)", allow_geometry_only=True,
    )
    assert accepted["status"] == "READY", accepted
    assert accepted["specification"]["specification_type"] == (
        "ACHROMATIC_CONNECTED_2D_RASTER_PATH"
    )
    assert accepted["specification"]["trace_family_type"] == "ACHROMATIC"
    assert accepted["specification"]["color_match"]["space"] == (
        "ACHROMATIC_LUMINANCE_RANGE"
    )


def test_process_paper_expands_chromatic_and_achromatic_series_in_one_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data import ocr
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper_dir = input_root / "paper-mixed-multiseries"
    paper_dir.mkdir(parents=True)
    image_path = paper_dir / "Figure1.png"
    image = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 40, 360, 270), outline=(25, 25, 25), width=3)

    red = [
        (x, int(222 - 104 * (x - 70) / 275))
        for x in range(70, 346)
    ]
    gray_solid = [
        (x, int(186 - 29 * (x - 70) / 275))
        for x in range(70, 346)
    ]
    draw.line(red, fill=(230, 20, 30), width=3)
    draw.line(gray_solid, fill=(112, 112, 112), width=3)

    def gray_dash_y(x):
        return int(136 - 18 * (x - 70) / 275)

    for start in range(74, 342, 23):
        end = min(start + 15, 346)
        draw.line(
            [(x, gray_dash_y(x)) for x in range(start, end)],
            fill=(144, 144, 144), width=3,
        )
    draw.text((155, 294), "Time (s)", fill=(20, 20, 20))
    draw.text((8, 148), "Signal (mA)", fill=(20, 20, 20))
    image.save(image_path)

    rows = [
        _ocr_row("0", 70, 282), _ocr_row("5", 205, 282), _ocr_row("10", 345, 282),
        _ocr_row("10", 42, 65), _ocr_row("5", 42, 155), _ocr_row("0", 42, 255),
        _ocr_row("Time (s)", 205, 305, 0.96),
        _ocr_row("Signal (mA)", 18, 155, 0.95),
    ]
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({"figures": [{
            "figure_id": "Figure1", "image_path": "Figure1.png",
            "caption": "Mixed chromatic and achromatic monotonic curves.",
            "panels": [],
        }]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "run_ocr", lambda path: rows)

    result = process_paper(
        input_root, Path("paper-mixed-multiseries"), tmp_path / "output",
        options={"ocr": True, "memory_limit_mb": 1024},
    )
    assert result["series_count"] == 3, result
    family_types = [
        item["metadata"]["trace_specification"]["specification"]["trace_family_type"]
        for item in result["series"]
    ]
    assert family_types.count("CHROMATIC") == 1, family_types
    assert family_types.count("ACHROMATIC") == 2, family_types
    assert all(item["metadata"]["points_count"] >= 50 for item in result["series"])
    dashed = [
        item for item in result["series"]
        if item["metadata"]["trace_specification"]["specification"]["trace_family_type"]
        == "ACHROMATIC"
        and item["metadata"].get("raster_qc", {}).get("path_segment_count", 0) >= 3
    ]
    assert len(dashed) == 1, result
    assert dashed[0]["extraction_status"] == (
        "EXTRACTED_PROVISIONAL_NEEDS_REVIEW"
    )
