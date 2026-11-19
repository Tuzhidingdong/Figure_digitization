from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .hashing import atomic_write_json
from .storage import Catalog


def export_dataset(catalog: Catalog, output_root: Path, destination: Path,
                   filters: dict, include_review_required: bool = True,
                   fmt: str = "csv") -> dict:
    records = catalog.query_series(filters, limit=10000)
    if not include_review_required:
        records = [r for r in records if r["review_state"] == "REVIEWED_ACCEPTED"]
    rows = []
    warnings = []
    for record in records:
        if record["y_axis_side"] == "UNASSIGNED":
            warnings.append({"series_id": record["series_id"], "warning": "DUAL_AXIS_UNASSIGNED"})
        if record["qc_status"] == "PROVISIONAL_UNCALIBRATED":
            warnings.append({"series_id": record["series_id"], "warning": "QC_PROVISIONAL_UNCALIBRATED"})
        if record["review_state"] != "REVIEWED_ACCEPTED":
            warnings.append({"series_id": record["series_id"], "warning": "NOT_REVIEWED_ACCEPTED"})
        points_path = output_root / "papers" / record["paper_id"] / "series" / (
            f"{record['figure_id']}__{record['panel_id']}") / "panel_series.csv"
        if not points_path.is_file():
            warnings.append({"series_id": record["series_id"], "warning": "CANONICAL_POINTS_FILE_MISSING"})
            continue
        with points_path.open("r", newline="", encoding="utf-8") as handle:
            for point in csv.DictReader(handle):
                if point["series_id"] != record["series_id"]:
                    continue
                rows.append({
                    "paper_id": record["paper_id"], "series_id": record["series_id"],
                    "figure_id": record["figure_id"], "panel_id": record["panel_id"],
                    "technique": record["technique"], "domain": record["domain"],
                    "series_label": record["label"], "x_value": point["x_value"],
                    "x_label": point["x_label"], "y_value": point["y_value"],
                    "x_unit": record["x_unit"], "y_unit": record["y_unit"],
                    "y_axis_side": record["y_axis_side"], "qc_status": record["qc_status"],
                    "review_state": record["review_state"],
                    "source_manifest": f"papers/{record['paper_id']}/paper_manifest.json",
                    "source_digitization": f"papers/{record['paper_id']}/digitization.json",
                })
    destination.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        data_path = destination / "dataset.csv"
        fields = list(rows[0].keys()) if rows else [
            "paper_id", "series_id", "figure_id", "panel_id", "technique", "domain",
            "series_label", "x_value", "x_label", "y_value", "x_unit", "y_unit",
            "y_axis_side", "qc_status", "review_state", "source_manifest", "source_digitization"
        ]
        with data_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "json":
        data_path = destination / "dataset.json"
        atomic_write_json(data_path, rows)
    else:
        raise ValueError("format must be csv or json")
    manifest = {
        "schema_version": "1.0", "exported_at": datetime.now(timezone.utc).isoformat(),
        "format": fmt, "filters": filters, "include_review_required": include_review_required,
        "series_count": len(records), "point_count": len(rows), "data_file": data_path.name,
        "compatibility_policy": "No automatic merging or conversion across unresolved scales, units, or metric bases.",
        "warnings": warnings,
        "qc_policy": "Only REVIEWED_ACCEPTED records are included when include_review_required=false.",
    }
    atomic_write_json(destination / "export_manifest.json", manifest)
    return manifest
