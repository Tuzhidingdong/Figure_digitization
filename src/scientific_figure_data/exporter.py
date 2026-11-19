from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import atomic_write_json
from .storage import Catalog

FIELDS = [
    "paper_id", "input_fingerprint", "series_id", "measurement_id", "figure_id", "panel_id",
    "technique", "domain", "series_label", "x_value", "x_label", "y_value",
    "x_unit", "y_unit", "y_axis_side", "subject_links_json", "conditions_json",
    "series_metadata_json", "qc_status", "review_state",
    "source_manifest", "source_digitization",
]


def _point_rows(points_path: Path, series_id: str):
    with points_path.open("r", newline="", encoding="utf-8") as handle:
        for point in csv.DictReader(handle):
            if point["series_id"] == series_id:
                yield point


def _make_row(record: dict, point: dict, associations: dict) -> dict[str, Any]:
    return {
        "paper_id": record["paper_id"],
        "input_fingerprint": record.get("input_fingerprint"),
        "series_id": record["series_id"],
        "measurement_id": record.get("measurement_id"),
        "figure_id": record["figure_id"],
        "panel_id": record["panel_id"],
        "technique": record["technique"],
        "domain": record["domain"],
        "series_label": record["label"],
        "x_value": point.get("x_value"),
        "x_label": point.get("x_label"),
        "y_value": point.get("y_value"),
        "x_unit": record["x_unit"],
        "y_unit": record["y_unit"],
        "y_axis_side": record["y_axis_side"],
        "subject_links_json": json.dumps(associations.get("subject_links", []), ensure_ascii=False),
        "conditions_json": json.dumps(associations.get("conditions", []), ensure_ascii=False),
        "series_metadata_json": record.get("metadata_json") or "{}",
        "qc_status": record["qc_status"],
        "review_state": record["review_state"],
        "source_manifest": f"papers/{record['paper_id']}/paper_manifest.json",
        "source_digitization": f"papers/{record['paper_id']}/digitization.json",
    }


def export_dataset(catalog: Catalog, output_root: Path, destination: Path,
                   filters: dict, include_review_required: bool = True,
                   fmt: str = "csv", series_batch_size: int = 250) -> dict:
    selected_filters = dict(filters)
    if not include_review_required:
        selected_filters["review_state"] = "REVIEWED_ACCEPTED"

    destination.mkdir(parents=True, exist_ok=True)
    data_path = destination / ("dataset.csv" if fmt == "csv" else "dataset.json")
    warning_path = destination / "warnings.jsonl"
    series_count = 0
    point_count = 0
    warning_counts: dict[str, int] = {}
    warning_samples: list[dict] = []

    if fmt not in {"csv", "json"}:
        raise ValueError("format must be csv or json")

    def add_warning(series_id: str, code: str, detail: str | None = None):
        warning_counts[code] = warning_counts.get(code, 0) + 1
        warning = {"series_id": series_id, "warning": code}
        if detail:
            warning["detail"] = detail
        if len(warning_samples) < 500:
            warning_samples.append(warning)
        warning_stream.write(json.dumps(warning, ensure_ascii=False) + "\n")

    with warning_path.open("w", encoding="utf-8") as warning_stream:
        if fmt == "csv":
            data_stream = data_path.open("w", newline="", encoding="utf-8")
        else:
            data_stream = data_path.open("w", encoding="utf-8")
        try:
            csv_writer = csv.DictWriter(data_stream, fieldnames=FIELDS) if fmt == "csv" else None
            if csv_writer:
                csv_writer.writeheader()
            else:
                data_stream.write("[")
            first_json_row = True
            for record in catalog.iter_query_series(selected_filters, batch_size=series_batch_size):
                series_count += 1
                if record["y_axis_side"] == "UNASSIGNED":
                    add_warning(record["series_id"], "DUAL_AXIS_UNASSIGNED")
                if record["qc_status"] == "PROVISIONAL_UNCALIBRATED":
                    add_warning(record["series_id"], "QC_PROVISIONAL_UNCALIBRATED")
                if record["review_state"] != "REVIEWED_ACCEPTED":
                    add_warning(record["series_id"], "NOT_REVIEWED_ACCEPTED")
                associations = catalog.series_associations(record["series_id"])
                if not associations["subject_links"] or all(
                    link.get("link_status") != "ASSIGNED_WITH_EVIDENCE"
                    for link in associations["subject_links"]
                ):
                    add_warning(record["series_id"], "SUBJECT_LINK_UNASSIGNED")
                if not associations["conditions"]:
                    add_warning(record["series_id"], "CONDITIONS_NOT_LINKED")
                metadata = json.loads(record.get("metadata_json") or "{}")
                if "REFERENCE_CONVERSION_UNRESOLVED" in json.dumps(metadata):
                    add_warning(record["series_id"], "REFERENCE_CONVERSION_UNRESOLVED")
                points_path = (
                    output_root / "papers" / record["paper_id"] / "series" /
                    f"{record['figure_id']}__{record['panel_id']}" / "panel_series.csv"
                )
                if not points_path.is_file():
                    add_warning(record["series_id"], "CANONICAL_POINTS_FILE_MISSING")
                    continue
                for point in _point_rows(points_path, record["series_id"]):
                    row = _make_row(record, point, associations)
                    if csv_writer:
                        csv_writer.writerow(row)
                    else:
                        if not first_json_row:
                            data_stream.write(",")
                        data_stream.write(json.dumps(row, ensure_ascii=False))
                        first_json_row = False
                    point_count += 1
            if fmt == "json":
                data_stream.write("]\n")
            data_stream.flush()
        finally:
            data_stream.close()

    manifest = {
        "schema_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "format": fmt,
        "filters": selected_filters,
        "include_review_required": include_review_required,
        "series_count": series_count,
        "point_count": point_count,
        "data_file": data_path.name,
        "warnings_file": warning_path.name,
        "warning_counts": warning_counts,
        "warning_sample_count": len(warning_samples),
        "warning_samples": warning_samples,
        "compatibility_policy": (
            "No automatic merging or conversion across unresolved reference scales, units, "
            "capacity bases, cell scopes, analyte metrics, or experimental conditions."
        ),
        "qc_policy": (
            "Only REVIEWED_ACCEPTED records are included when include_review_required=false. "
            "Unreviewed rows remain explicitly flagged otherwise."
        ),
        "streaming": {
            "series_batch_size": series_batch_size,
            "point_rows_buffered": 1,
            "warnings_written_incrementally": True,
        },
    }
    atomic_write_json(destination / "export_manifest.json", manifest)
    return manifest
