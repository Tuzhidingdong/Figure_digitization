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
    if not path or not path.is_file():
        return dict(PROVISIONAL)
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            config = json.load(handle)
        else:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("PyYAML is required to read YAML QC thresholds") from exc
            config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("QC threshold file must contain a mapping")
    status = config.get("status")
    if status not in {"PROVISIONAL_UNCALIBRATED", "CALIBRATED"}:
        raise ValueError("QC thresholds must explicitly declare PROVISIONAL_UNCALIBRATED or CALIBRATED")
    return config


def write_provisional_thresholds(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
