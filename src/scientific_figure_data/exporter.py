from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path
from typing import Any

from .hashing import atomic_write_json
from .storage import Catalog

FIELDS = [
    "paper_id", "input_fingerprint", "series_id", "measurement_id", "figure_id", "panel_id",
    "technique", "domain", "series_label", "point_index",
    "x_value", "x_label", "y_value", "x_unit", "y_unit",
    "x_value_raw", "x_label_raw", "y_value_raw", "x_unit_raw", "y_unit_raw",
    "standardization_status", "y_axis_side",
    "pixel_x", "pixel_y", "y_err_low", "y_err_high", "err_type",
    "subject_entity_ids_json", "subject_links_json", "conditions_json",
    "compatibility_status", "compatibility_warnings_json",
    "qc_status", "review_state", "extraction_status",
    "source_manifest", "source_digitization",
]


def _decode_json(value: Any, fallback: Any):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _normalized_associations(associations: dict) -> dict:
    subjects = []
    for item in associations.get("subject_links", []):
        subjects.append({
            "entity_id": item.get("entity_id"),
            "canonical_name": item.get("canonical_name"),
            "entity_type": item.get("entity_type"),
            "domain": item.get("domain"),
            "aliases": _decode_json(item.get("aliases_json"), []),
            "role_in_series": item.get("role_in_series"),
            "link_status": item.get("link_status"),
            "evidence": _decode_json(item.get("evidence_json"), {}),
        })
    conditions = []
    for item in associations.get("conditions", []):
        conditions.append({
            "condition_id": item.get("condition_id"),
            "name": item.get("name"),
            "value": _decode_json(item.get("value_json"), {}),
            "evidence": _decode_json(item.get("evidence_json"), {}),
        })
    return {"subject_links": subjects, "conditions": conditions}


def _series_compatibility_warnings(record: dict, associations: dict, metadata: dict) -> list[str]:
    warnings = []
    if record.get("qc_status") == "PROVISIONAL_UNCALIBRATED":
        warnings.append("QC_PROVISIONAL_UNCALIBRATED")
    if record.get("review_state") != "REVIEWED_ACCEPTED":
        warnings.append("NOT_REVIEWED_ACCEPTED")
    if record.get("y_axis_side") == "UNASSIGNED":
        warnings.append("DUAL_AXIS_UNASSIGNED")
    subject_links = associations.get("subject_links", [])
    if not subject_links or all(
        item.get("link_status") != "ASSIGNED_WITH_EVIDENCE" for item in subject_links
    ):
        warnings.append("SUBJECT_LINK_UNASSIGNED")
    if not associations.get("conditions"):
        warnings.append("CONDITIONS_NOT_LINKED")
    if "REFERENCE_CONVERSION_UNRESOLVED" in json.dumps(metadata, ensure_ascii=False):
        warnings.append("REFERENCE_CONVERSION_UNRESOLVED")
    explicit = metadata.get("compatibility_warnings", [])
    if isinstance(explicit, list):
        for warning in explicit:
            if isinstance(warning, str) and warning not in warnings:
                warnings.append(warning)
    return warnings


def _make_row(record: dict, point: dict, associations: dict) -> dict[str, Any]:
    metadata = _decode_json(record.get("metadata_json"), {})
    warnings = _series_compatibility_warnings(record, associations, metadata)
    subject_ids = sorted({
        item["entity_id"] for item in associations.get("subject_links", [])
        if item.get("entity_id")
    })
    x_value = point.get("x_value")
    x_label = point.get("x_label")
    y_value = point.get("y_value")
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
        "point_index": point.get("point_index"),
        "x_value": x_value,
        "x_label": x_label,
        "y_value": y_value,
        "x_unit": record["x_unit"],
        "y_unit": record["y_unit"],
        "x_value_raw": x_value,
        "x_label_raw": x_label,
        "y_value_raw": y_value,
        "x_unit_raw": record["x_unit"],
        "y_unit_raw": record["y_unit"],
        "standardization_status": "NOT_PERFORMED",
        "y_axis_side": record["y_axis_side"],
        "pixel_x": point.get("pixel_x"),
        "pixel_y": point.get("pixel_y"),
        "y_err_low": point.get("y_err_low"),
        "y_err_high": point.get("y_err_high"),
        "err_type": point.get("err_type") or "UNKNOWN",
        "subject_entity_ids_json": json.dumps(subject_ids, ensure_ascii=False, sort_keys=True),
        "subject_links_json": json.dumps(
            associations.get("subject_links", []), ensure_ascii=False, sort_keys=True
        ),
        "conditions_json": json.dumps(
            associations.get("conditions", []), ensure_ascii=False, sort_keys=True
        ),
        "compatibility_status": "NOT_HARMONIZED",
        "compatibility_warnings_json": json.dumps(warnings, ensure_ascii=False),
        "qc_status": record["qc_status"],
        "review_state": record["review_state"],
        "extraction_status": record.get("extraction_status"),
        "source_manifest": f"papers/{record['paper_id']}/paper_manifest.json",
        "source_digitization": f"papers/{record['paper_id']}/digitization.json",
    }


def export_dataset(catalog: Catalog, output_root: Path, destination: Path,
                   filters: dict, include_review_required: bool = True,
                   fmt: str = "csv", series_batch_size: int = 250) -> dict:
    selected_filters = dict(filters)
    if not include_review_required:
        selected_filters["review_state"] = "REVIEWED_ACCEPTED"

    if fmt not in {"csv", "json"}:
        raise ValueError("format must be csv or json")
    destination.mkdir(parents=True, exist_ok=True)
    data_path = destination / ("dataset.csv" if fmt == "csv" else "dataset.json")
    series_metadata_path = destination / "series_metadata.jsonl"
    warning_path = destination / "warnings.jsonl"
    series_count = 0
    point_count = 0
    warning_counts: dict[str, int] = {}
    warning_samples: list[dict] = []

    def add_warning(series_id: str, code: str, detail: str | None = None):
        warning_counts[code] = warning_counts.get(code, 0) + 1
        warning = {"series_id": series_id, "warning": code}
        if detail:
            warning["detail"] = detail
        if len(warning_samples) < 500:
            warning_samples.append(warning)
        warning_stream.write(json.dumps(warning, ensure_ascii=False) + "\n")

    with warning_path.open("w", encoding="utf-8") as warning_stream, \
         series_metadata_path.open("w", encoding="utf-8") as metadata_stream:
        data_stream = (
            data_path.open("w", newline="", encoding="utf-8")
            if fmt == "csv" else data_path.open("w", encoding="utf-8")
        )
        try:
            csv_writer = csv.DictWriter(data_stream, fieldnames=FIELDS) if fmt == "csv" else None
            if csv_writer:
                csv_writer.writeheader()
            else:
                data_stream.write("[")
            first_json_row = True
            series_iterator = catalog.iter_query_series(selected_filters, batch_size=series_batch_size)

            def panel_key(row):
                return (row["paper_id"], row["figure_id"], row["panel_id"])

            for key, grouped_records in groupby(series_iterator, key=panel_key):
                panel_records = list(grouped_records)
                record_map = {record["series_id"]: record for record in panel_records}
                associations_map = {}
                for record in panel_records:
                    series_count += 1
                    raw_associations = catalog.series_associations(record["series_id"])
                    associations = _normalized_associations(raw_associations)
                    associations_map[record["series_id"]] = associations
                    series_metadata = _decode_json(record.get("metadata_json"), {})
                    warnings = _series_compatibility_warnings(record, associations, series_metadata)
                    for warning in warnings:
                        add_warning(record["series_id"], warning)

                    metadata_record = {
                        "export_schema_version": "1.1",
                        "paper_id": record["paper_id"],
                        "input_fingerprint": record.get("input_fingerprint"),
                        "series_id": record["series_id"],
                        "measurement_id": record.get("measurement_id"),
                        "figure_id": record["figure_id"],
                        "panel_id": record["panel_id"],
                        "technique": record.get("technique"),
                        "domain": record.get("domain"),
                        "label": record.get("label"),
                        "x_unit": record.get("x_unit"),
                        "y_unit": record.get("y_unit"),
                        "x_unit_raw": record.get("x_unit"),
                        "y_unit_raw": record.get("y_unit"),
                        "standardization_status": "NOT_PERFORMED",
                        "y_axis_side": record.get("y_axis_side"),
                        "subject_links": associations["subject_links"],
                        "conditions": associations["conditions"],
                        "series_metadata": series_metadata,
                        "qc_status": record.get("qc_status"),
                        "review_state": record.get("review_state"),
                        "extraction_status": record.get("extraction_status"),
                        "compatibility_status": "NOT_HARMONIZED",
                        "compatibility_warnings": warnings,
                        "source_manifest": f"papers/{record['paper_id']}/paper_manifest.json",
                        "source_digitization": f"papers/{record['paper_id']}/digitization.json",
                    }
                    metadata_stream.write(json.dumps(metadata_record, ensure_ascii=False) + "\n")

                paper_id, figure_id, panel_id = key
                points_path = (
                    output_root / "papers" / paper_id / "series" /
                    f"{figure_id}__{panel_id}" / "panel_series.csv"
                )
                if not points_path.is_file():
                    for series_id in record_map:
                        add_warning(series_id, "CANONICAL_POINTS_FILE_MISSING")
                    continue
                with points_path.open("r", newline="", encoding="utf-8") as points_stream:
                    for point in csv.DictReader(points_stream):
                        record = record_map.get(point["series_id"])
                        if record is None:
                            continue
                        row = _make_row(record, point, associations_map[record["series_id"]])
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
        "schema_version": "1.1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "row_granularity": "one_row_per_digitized_series_point",
        "raw_value_policy": (
            "x_value/y_value are reconstructed on the extracted axis scale with the stored "
            "original units. *_raw columns repeat those values explicitly. No dimensional or "
            "reference-scale normalization is performed by export."
        ),
        "subject_condition_policy": (
            "Every point row carries its series-level subject links and measurement conditions "
            "as JSON; series_metadata.jsonl remains a companion audit record."
        ),
        "format": fmt,
        "filters": selected_filters,
        "include_review_required": include_review_required,
        "series_count": series_count,
        "point_count": point_count,
        "data_file": data_path.name,
        "series_metadata_file": series_metadata_path.name,
        "warnings_file": warning_path.name,
        "warning_counts": warning_counts,
        "warning_sample_count": len(warning_samples),
        "warning_samples": warning_samples,
        "compatibility_policy": (
            "No automatic merging or conversion across unresolved reference scales, units, "
            "capacity bases, cell scopes, analyte metrics, or experimental conditions. "
            "Rows carry compatibility_status=NOT_HARMONIZED until a separate validated "
            "harmonization stage is implemented."
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
