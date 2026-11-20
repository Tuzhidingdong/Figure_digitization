from __future__ import annotations

import runpy
from pathlib import Path


_AUDIT = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "audit_dependency_licenses.py")
)
_deduplicate_records = _AUDIT["_deduplicate_records"]


def _package(name: str, license_text: str = "MIT") -> dict:
    return {
        "name": name,
        "version": "1.2.3",
        "status": "RAW_LICENSE_FIELD_REQUIRES_REVIEW",
        "license_expression": None,
        "license_text": license_text,
        "license_classifiers": [],
        "license_file_names": ["LICENSE"],
        "requires_dist": ["dependency>=1"],
        "project_urls": [],
    }


def test_dependency_license_inventory_deduplicates_normalized_distribution_names():
    records, duplicate_count = _deduplicate_records([
        _package("scientific_figure_data"),
        _package("scientific-figure-data"),
    ])

    assert duplicate_count == 1
    assert len(records) == 1
    assert records[0]["metadata_record_count"] == 2
    assert records[0]["status"] == "RAW_LICENSE_FIELD_REQUIRES_REVIEW"


def test_dependency_license_inventory_flags_conflicting_duplicate_metadata():
    records, duplicate_count = _deduplicate_records([
        _package("example-package", "MIT"),
        _package("example.package", "Apache-2.0"),
    ])

    assert duplicate_count == 1
    assert len(records) == 1
    assert records[0]["status"] == "CONFLICTING_DISTRIBUTION_METADATA_REQUIRES_REVIEW"
    assert records[0]["metadata_conflicts"]["license_text"] == ["Apache-2.0", "MIT"]
