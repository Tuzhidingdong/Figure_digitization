from __future__ import annotations

import json
from pathlib import Path

import pytest

from scientific_figure_data.panel_segmentation import detect_panel_regions


FIXTURES = Path(__file__).parent / "fixtures" / "real_figures"


@pytest.mark.parametrize(
    ("filename", "minimum_panels"),
    [
        ("P8_06.png", 2),
        ("P3_02.png", 2),
    ],
)
def test_real_scientific_figures_are_not_collapsed_to_one_panel(
    filename: str, minimum_panels: int,
) -> None:
    """Regression evidence: real multi-chart figures must expose multiple regions."""
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
