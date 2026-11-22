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
    assert accepted["specification"]["path_order"] == "X_MONOTONIC"

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
    assert series["extraction_method"] == "raster_color_column_median"
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
