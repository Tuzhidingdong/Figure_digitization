from __future__ import annotations

import json
from pathlib import Path

import pytest

from scientific_figure_data.panel_segmentation import detect_panel_regions


# These are byte-identical copies of the two published CLI input figures.
FIXTURES = Path(__file__).parent / "fixtures" / "real_figures"


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
                "trace_reason": row.get("metadata", {})
                    .get("trace_specification", {}).get("reason"),
                "axis_assignment": row.get("metadata", {})
                    .get("series_axis_assignment"),
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
