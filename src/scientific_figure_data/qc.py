from __future__ import annotations

import json
from pathlib import Path

PROVISIONAL = {
    "schema_version": "1.0",
    "status": "PROVISIONAL_UNCALIBRATED",
    "notes": "Engineering defaults only; not calibrated against annotated real papers.",
    "minimum_calibration_anchors": 2,
    "maximum_axis_anchor_rmse": None,
    "minimum_trace_points": 8,
    "minimum_trace_pixel_fraction": 0.15,
    "allow_automatic_same_color_crossing": False,
    "allow_automatic_marker_disambiguation": False,
}


def load_thresholds(path: Path | None = None) -> dict:
    if path and path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            config = json.load(handle) if path.suffix.lower() == ".json" else None
        if config is not None:
            return config
    return dict(PROVISIONAL)


def write_provisional_thresholds(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # YAML is kept human-editable; no runtime YAML dependency is required.
    lines = [
        "schema_version: '1.0'",
        "status: PROVISIONAL_UNCALIBRATED",
        "notes: Engineering defaults only; not calibrated against annotated real papers.",
        "minimum_calibration_anchors: 2",
        "minimum_trace_points: 8",
        "minimum_trace_pixel_fraction: 0.15",
        "allow_automatic_same_color_crossing: false",
        "allow_automatic_marker_disambiguation: false",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
