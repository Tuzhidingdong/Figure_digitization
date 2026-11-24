from __future__ import annotations

import json

import pytest
from pathlib import Path

from scientific_figure_data.adapter import discover_papers, snapshot_paper
from scientific_figure_data.calibration import fit_linear_axis, map_pixel
from scientific_figure_data.cli import build_parser
from scientific_figure_data.context_index import PaperContextIndex
from scientific_figure_data.entities import SubjectEntity, link_series_to_subject
from scientific_figure_data.hashing import sha256_file, sha256_stream
from scientific_figure_data.manifest import detect_role
from scientific_figure_data.models import (
    InputArtifact, PaperSnapshot, SeriesPoint, SeriesRecord,
)
from scientific_figure_data.profiles import load_profile
from scientific_figure_data.raster import map_explicit_polyline
from scientific_figure_data.review import apply_review_patch
from scientific_figure_data.semantics import (
    comparable_battery_records, convert_dimensionally, preserve_censored_value,
    pfas_metric_warning, resolve_reference_scale,
)
from scientific_figure_data.storage import (
    Catalog, append_panel_series_csv, connect_catalog, write_paper_artifacts,
)


def make_snapshot(paper_id: str = "paper-1") -> PaperSnapshot:
    return PaperSnapshot(
        paper_id=paper_id, source_dir=paper_id, detected_upstream_version="test",
        adapter_version="test", created_at="2026-01-01T00:00:00+00:00",
        artifacts=[], missing_roles=[], warnings=[], input_fingerprint="a" * 64,
    )


def make_series(series_id: str, measurement_id: str, condition_name: str) -> SeriesRecord:
    return SeriesRecord(
        series_id=series_id, paper_id="paper-1", figure_id="Figure1", panel_id="a",
        technique="CV", domain="battery", label=series_id, x_label="Potential",
        y_label="Current density", x_unit="V", y_unit="mA cm-2",
        measurement_id=measurement_id, y_axis_side="LEFT",
        extraction_method="EXPLICIT_ORDERED_PIXEL_POLYLINE",
        extraction_status="EXTRACTED_PROVISIONAL",
        qc_status="PROVISIONAL_UNCALIBRATED",
        review_state="NEEDS_REVIEW",
        points=[
            SeriesPoint(0, 0.0, 0.0, 10.0, 20.0),
            SeriesPoint(1, 1.0, 1.0, 20.0, 10.0),
        ],
        conditions=[{
            "condition_id": f"{series_id}-condition",
            "name": condition_name,
            "value": "documented",
            "unit": None,
            "evidence": {"source": "figure caption", "page": 2},
        }],
    )


def make_output_with_series(root: Path):
    snapshot = make_snapshot()
    paper_root = root / "papers" / snapshot.paper_id
    first = make_series("series-a", "measurement-a", "electrolyte")
    second = make_series("series-b", "measurement-b", "temperature")
    append_panel_series_csv(paper_root, "Figure1", "a", [first, second])
    for item in (first, second):
        item.metadata["points_count"] = len(item.points)
        item.points.clear()
    figures = [{"figure_id": "Figure1", "page": 2, "caption": "CV curves"}]
    panels = [{"figure_id": "Figure1", "panel_id": "a", "bbox": [0, 0, 1, 1], "status": "EXTRACTED"}]
    artifacts = write_paper_artifacts(root, snapshot, figures, panels, [first, second], "COMPLETED_WITH_REVIEW")
    catalog = Catalog(root / "catalog.sqlite")
    catalog.index_paper(snapshot, figures, panels, [first, second], "COMPLETED_WITH_REVIEW",
                        {"manifest_path": str(paper_root / "paper_manifest.json"),
                         "bundle_path": str(paper_root / "paper_bundle.json")},
                        paper_root=paper_root)
    catalog.close()
    return snapshot, paper_root


def test_sha256_stream_and_file(tmp_path: Path):
    data = b"scientific figure evidence"
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(data)
    import io
    assert sha256_stream(io.BytesIO(data)) == sha256_file(file_path)


def test_adapter_discovers_paper_and_fingerprints_all_files(tmp_path: Path):
    paper = tmp_path / "nested" / "paper-1"
    paper.mkdir(parents=True)
    (paper / "main.pdf").write_bytes(b"%PDF-fake")
    (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    (paper / "main_analysis.md").write_text("Reference vs Ag/AgCl", encoding="utf-8")
    discovered = list(discover_papers(tmp_path))
    assert discovered == [paper]
    snapshot = snapshot_paper(paper, tmp_path)
    assert snapshot.paper_id == "nested__paper-1"
    assert {item.role for item in snapshot.artifacts} >= {"main_pdf", "figure_inventory", "main_text"}
    fingerprint = snapshot.input_fingerprint
    (paper / "main_analysis.md").write_text("Reference vs SHE", encoding="utf-8")
    assert snapshot_paper(paper, tmp_path).input_fingerprint != fingerprint


def test_figure_role_detection_handles_main_and_si():
    assert detect_role("article.pdf") == "main_pdf"
    assert detect_role("supporting_information.pdf") == "si_pdf"
    assert detect_role("extracted_tables/table_1.csv") == "table_data"


def test_context_index_spills_to_sqlite_and_keeps_evidence(tmp_path: Path):
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "main_analysis.md").write_text(
        "Sample A was tested vs. Ag/AgCl.\nResults are mean ± SD, n=3.\n", encoding="utf-8"
    )
    output = tmp_path / "out"
    context = PaperContextIndex.build(paper, output, memory_budget_bytes=1)
    assert context.db_path is not None and context.db_path.is_file()
    references = context.search("reference_electrode")
    assert references and references[0]["source_path"] == "main_analysis.md"
    statistics = context.search("statistics")
    assert statistics


def test_linear_calibration_and_explicit_non_monotonic_order():
    x_cal = fit_linear_axis("x", [{"pixel": 10, "value": 0}, {"pixel": 110, "value": 10}], "V")
    y_cal = fit_linear_axis("y", [{"pixel": 100, "value": 0}, {"pixel": 0, "value": 5}], "mA")
    assert map_pixel(x_cal, 60) == 5
    points = map_explicit_polyline([(10, 50), (80, 40), (40, 30)], x_cal, y_cal)
    assert [point.x for point in points] == [0.0, 7.0, 3.0]
    assert [point.point_index for point in points] == [0, 1, 2]


def test_reference_scale_never_guesses_missing_conditions():
    unresolved = resolve_reference_scale(0.25, "RHE", {"reference_electrode": "Ag/AgCl"})
    assert unresolved["status"] == "REFERENCE_CONVERSION_UNRESOLVED"
    assert unresolved["value"] is None
    details = {
        "reference_electrode": "Ag/AgCl",
        "filling_solution": "KCl",
        "filling_concentration": "3 M",
        "temperature_k": 298.15,
        "electrolyte": "aqueous electrolyte",
        "pH": 7.0,
        "formula_id": "explicit-test-formula",
        "formula_evidence_id": "caption-page-3",
        "scale_factor": 1.0,
        "offset_v": 0.2,
    }
    resolved = resolve_reference_scale(0.25, "test-scale", details)
    assert resolved["status"] == "CONVERTED_WITH_EXPLICIT_EVIDENCE"
    assert resolved["value"] == 0.45
    with pytest.raises(ValueError, match="must be finite"):
        resolve_reference_scale(0.25, "RHE", {**details, "offset_v": float("nan")})


def test_units_battery_comparability_and_pfas_metrics_are_conservative():
    assert convert_dimensionally(60, "s", "min") == 1
    compatible, mismatches = comparable_battery_records(
        {"capacity_basis": "gravimetric", "cell_scope": "full_cell",
         "current_density_basis": "mass", "cycling_protocol": "1C"},
        {"capacity_basis": "areal", "cell_scope": "full_cell",
         "current_density_basis": "mass", "cycling_protocol": "1C"},
    )
    assert not compatible and mismatches == ["capacity_basis"]
    unresolved, unresolved_fields = comparable_battery_records({}, {})
    assert not unresolved
    assert unresolved_fields == [
        "capacity_basis:UNRESOLVED", "cell_scope:UNRESOLVED",
        "current_density_basis:UNRESOLVED", "cycling_protocol:UNRESOLVED",
    ]
    assert comparable_battery_records(
        {"capacity_basis": "Gravimetric", "cell_scope": "full_cell",
         "current_density_basis": "mass", "cycling_protocol": "1C"},
        {"capacity_basis": "gravimetric", "cell_scope": "FULL_CELL",
         "current_density_basis": "mass", "cycling_protocol": "1C"},
    )[0]
    assert pfas_metric_warning("parent_removal", "defluorination") == "PFAS_METRICS_ARE_NOT_INTERCHANGEABLE"
    assert pfas_metric_warning(None, "defluorination") == "PFAS_METRIC_UNRESOLVED"
    lod = preserve_censored_value("<LOD")
    assert lod["raw"] == "<LOD"
    assert lod["comparator"] == "<"
    assert lod["limit_type"] == "LOD"
    assert lod["limit_value"] is None
    assert lod["numeric_value"] is None

    loq = preserve_censored_value("≤ LOQ = 5.0e-2 mg/L")
    assert loq["raw"] == "≤ LOQ = 5.0e-2 mg/L"
    assert loq["comparator"] == "<="
    assert loq["limit_type"] == "LOQ"
    assert loq["limit_value"] == 0.05
    assert loq["unit"] == "mg/L"
    assert loq["numeric_value"] is None

    numeric_limit = preserve_censored_value("<0.1 mg/L")
    assert numeric_limit["limit_value"] == 0.1
    assert numeric_limit["unit"] == "mg/L"
    assert numeric_limit["numeric_value"] is None
    assert preserve_censored_value("ND (<LOD)")["numeric_value"] is None


def test_entity_link_requires_exact_match_and_evidence():
    entity = SubjectEntity("sample-a", "Sample A", "material", "battery", ["A"])
    unresolved = link_series_to_subject("s1", entity, "tested_material", {}, exact_match=True)
    assert unresolved["status"] == "UNASSIGNED"
    linked = link_series_to_subject(
        "s1", entity, "tested_material", {"source": "legend", "page": 2}, exact_match=True
    )
    assert linked["status"] == "ASSIGNED_WITH_EVIDENCE"


def test_profiles_inherit_and_keep_domain_metric_boundaries():
    profile = load_profile("pfas")
    assert profile["domain"] == "pfas"
    assert "parent_compound_time" in profile["techniques"]
    assert profile["rules"]["lod_loq_to_zero"] is False


def test_catalog_conditions_are_joined_to_measurement_not_whole_figure(tmp_path: Path):
    snapshot, paper_root = make_output_with_series(tmp_path)
    catalog = Catalog(tmp_path / "catalog.sqlite")
    electrolyte = catalog.query_series({"condition": "electrolyte"})
    temperature = catalog.query_series({"condition": "temperature"})
    assert [item["series_id"] for item in electrolyte] == ["series-a"]
    assert [item["series_id"] for item in temperature] == ["series-b"]
    points = catalog.con.execute("SELECT COUNT(*) FROM series_points").fetchone()[0]
    assert points == 4
    catalog.close()

    rebuilt = Catalog(tmp_path / "catalog.sqlite")
    result = rebuilt.rebuild_from_artifacts(tmp_path)
    assert result["papers_indexed"] == 1
    assert [item["series_id"] for item in rebuilt.query_series({"condition": "electrolyte"})] == ["series-a"]
    assert rebuilt.con.execute("SELECT COUNT(*) FROM series_points").fetchone()[0] == 4
    rebuilt.close()


def test_review_patch_applies_atomically_updates_bundle_and_catalog(tmp_path: Path):
    snapshot, paper_root = make_output_with_series(tmp_path)
    digitization = paper_root / "digitization.json"
    patch = {
        "schema_version": "1.0",
        "patch_id": "review-patch-001",
        "paper_id": snapshot.paper_id,
        "target_artifact": "digitization.json",
        "original_result_hash": sha256_file(digitization),
        "reviewer": "test-reviewer",
        "changes": [{"series_id": "series-a", "set": {"label": "Corrected sample A"}}],
    }
    patch_path = tmp_path / "review_patch.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    result = apply_review_patch(tmp_path, patch_path)
    assert result["status"] == "REVIEWED_ACCEPTED"
    updated = json.loads(digitization.read_text(encoding="utf-8"))
    reviewed = next(item for item in updated["series"] if item["series_id"] == "series-a")
    assert reviewed["label"] == "Corrected sample A"
    assert reviewed["review_state"] == "REVIEWED_ACCEPTED"
    bundle = json.loads((paper_root / "paper_bundle.json").read_text(encoding="utf-8"))
    assert bundle["content_hashes"]["digitization.json"] == sha256_file(digitization)
    catalog = Catalog(tmp_path / "catalog.sqlite")
    row = catalog.query_series({"paper_id": snapshot.paper_id})[0]
    assert row["label"] == "Corrected sample A"
    assert row["review_state"] == "REVIEWED_ACCEPTED"
    catalog.close()
    assert apply_review_patch(tmp_path, patch_path)["status"] == "ALREADY_APPLIED"


def _seed_chart_classification_for_review(paper_root: Path) -> None:
    digitization_path = paper_root / "digitization.json"
    digitization = json.loads(digitization_path.read_text(encoding="utf-8"))
    for item in digitization["series"]:
        item.setdefault("metadata", {})["chart_family_classification"] = {
            "technique": "CV",
            "chart_family": "NON_MONOTONIC_CURVE",
            "status": "CLASSIFIED_FROM_UPSTREAM_METADATA",
            "confidence": 1.0,
            "evidence": [{"source": "upstream_technique", "value": "CV"}],
        }
    digitization_path.write_text(json.dumps(digitization, indent=2), encoding="utf-8")
    layout_path = paper_root / "panel_layout.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["panels"][0]["chart_family"] = "NON_MONOTONIC_CURVE"
    layout["panels"][0]["chart_family_status"] = "CLASSIFIED_FROM_UPSTREAM_METADATA"
    layout_path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    bundle_path = paper_root / "paper_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    for relative in ("digitization.json", "panel_layout.json"):
        bundle["content_hashes"][relative] = sha256_file(paper_root / relative)
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")


def test_review_patch_manually_revises_chart_family_and_panel_summary(tmp_path: Path):
    snapshot, paper_root = make_output_with_series(tmp_path)
    _seed_chart_classification_for_review(paper_root)
    digitization = paper_root / "digitization.json"
    rationale = "The corrected panel evidence identifies a diffraction spectrum."
    changes = [{
        "series_id": series_id,
        "set": {
            "technique": "XRD",
            "chart_family": "SPECTRUM",
            "classification_evidence": rationale,
        },
    } for series_id in ("series-a", "series-b")]
    patch_path = tmp_path / "classification-review.json"
    patch_path.write_text(json.dumps({
        "schema_version": "1.0", "patch_id": "classification-review-001",
        "paper_id": snapshot.paper_id, "target_artifact": "digitization.json",
        "original_result_hash": sha256_file(digitization), "reviewer": "reviewer-a",
        "changes": changes,
    }), encoding="utf-8")

    result = apply_review_patch(tmp_path, patch_path)
    assert result["status"] == "REVIEWED_ACCEPTED"
    updated = json.loads(digitization.read_text(encoding="utf-8"))
    for item in updated["series"]:
        classification = item["metadata"]["chart_family_classification"]
        assert item["technique"] == "XRD"
        assert classification["chart_family"] == "SPECTRUM"
        assert classification["status"] == "MANUALLY_REVISED"
        assert classification["confidence"] is None
        history = item["metadata"]["chart_family_classification_history"]
        assert history[0]["previous"]["chart_family"] == "NON_MONOTONIC_CURVE"
        assert history[0]["revision"]["rationale"] == rationale
        assert history[0]["revision"]["reviewer"] == "reviewer-a"

    layout_path = paper_root / "panel_layout.json"
    panel = json.loads(layout_path.read_text(encoding="utf-8"))["panels"][0]
    assert panel["chart_family"] == "SPECTRUM"
    assert panel["chart_family_status"] == "REVISED_AFTER_REVIEW"
    bundle = json.loads((paper_root / "paper_bundle.json").read_text(encoding="utf-8"))
    assert bundle["content_hashes"]["digitization.json"] == sha256_file(digitization)
    assert bundle["content_hashes"]["panel_layout.json"] == sha256_file(layout_path)
    assert (paper_root / "versions" / "review-classification-review-001" /
            "panel_layout.before.json").is_file()

    catalog = Catalog(tmp_path / "catalog.sqlite")
    rows = catalog.con.execute(
        "SELECT technique,metadata_json FROM series WHERE paper_id=? ORDER BY series_id",
        (snapshot.paper_id,),
    ).fetchall()
    assert [row["technique"] for row in rows] == ["XRD", "XRD"]
    assert all(
        json.loads(row["metadata_json"])["chart_family_classification"]["chart_family"] == "SPECTRUM"
        for row in rows
    )
    measurements = catalog.con.execute(
        "SELECT technique FROM measurements WHERE paper_id=? ORDER BY technique",
        (snapshot.paper_id,),
    ).fetchall()
    assert [row["technique"] for row in measurements] == ["XRD", "XRD"]
    catalog.close()


def test_reviewed_technique_change_recomputes_preliminary_classification(tmp_path: Path):
    snapshot, paper_root = make_output_with_series(tmp_path)
    _seed_chart_classification_for_review(paper_root)
    digitization = paper_root / "digitization.json"
    patch_path = tmp_path / "reclassify-review.json"
    patch_path.write_text(json.dumps({
        "schema_version": "1.0", "patch_id": "reclassify-review-001",
        "paper_id": snapshot.paper_id, "target_artifact": "digitization.json",
        "original_result_hash": sha256_file(digitization), "reviewer": "reviewer-b",
        "changes": [{
            "series_id": "series-a",
            "set": {"technique": "XRD", "x_label": "2θ (degree)", "y_label": "Intensity"},
        }],
    }), encoding="utf-8")

    result = apply_review_patch(tmp_path, patch_path)
    assert result["status"] == "REVIEWED_ACCEPTED"
    updated = json.loads(digitization.read_text(encoding="utf-8"))
    item = next(series for series in updated["series"] if series["series_id"] == "series-a")
    classification = item["metadata"]["chart_family_classification"]
    assert classification["chart_family"] == "SPECTRUM"
    assert classification["status"] == "RECLASSIFIED_AFTER_REVIEW"
    assert classification["confidence"] is None
    assert classification["revision"]["changed_fields"] == ["technique", "x_label", "y_label"]
    assert classification["revision"]["changed_inputs"]["technique"] == {"before": "CV", "after": "XRD"}
    assert item["metadata"]["reviewed_axis_labels"] == {
        "x_label": "2θ (degree)", "y_label": "Intensity",
        "reviewed_at": classification["revision"]["reviewed_at"],
    }
    panel = json.loads((paper_root / "panel_layout.json").read_text(encoding="utf-8"))["panels"][0]
    assert panel["chart_family"] == "UNCLASSIFIED"
    assert panel["chart_family_status"] == "CONFLICTING_SERIES_CLASSIFICATIONS"
    assert panel["chart_family_conflicts"] == ["NON_MONOTONIC_CURVE", "SPECTRUM"]


def test_review_patch_rejects_manual_chart_family_without_evidence():
    from scientific_figure_data.review import _validate_patch

    patch = {
        "patch_id": "invalid-classification", "paper_id": "paper-1",
        "target_artifact": "digitization.json", "original_result_hash": "a" * 64,
        "changes": [{"series_id": "series-a", "set": {"chart_family": "SPECTRUM"}}],
    }
    with pytest.raises(ValueError, match="classification_evidence"):
        _validate_patch(patch)



def test_stale_review_patch_is_rejected_and_preserved(tmp_path: Path):
    paper_root = tmp_path / "papers" / "paper-1"
    paper_root.mkdir(parents=True)
    target = paper_root / "digitization.json"
    target.write_text('{"paper_id":"paper-1","series":[]}', encoding="utf-8")
    Catalog(tmp_path / "catalog.sqlite").close()
    patch_path = tmp_path / "stale.json"
    patch_path.write_text(json.dumps({
        "patch_id": "stale-patch", "paper_id": "paper-1", "target_artifact": "digitization.json",
        "original_result_hash": "0" * 64,
        "changes": [{"series_id": "does-not-exist", "set": {"label": "not applied"}}],
    }), encoding="utf-8")
    result = apply_review_patch(tmp_path, patch_path)
    assert result["status"] == "PATCH_CONFLICT_STALE_BASE"
    assert (tmp_path / "review" / "conflicts" / "stale-patch.json").is_file()
    assert "not applied" not in target.read_text(encoding="utf-8")


def test_export_populates_standardized_axes_only_for_explicit_supported_targets():
    from scientific_figure_data.exporter import _make_row

    record = {
        "paper_id": "paper-1", "input_fingerprint": "fingerprint",
        "series_id": "series-1", "measurement_id": "measurement-1",
        "figure_id": "Figure1", "panel_id": "a", "technique": "AOP",
        "domain": "aop", "label": "concentration", "x_unit": "s", "y_unit": "mg/L",
        "y_axis_side": "LEFT", "qc_status": "PROVISIONAL_UNCALIBRATED",
        "review_state": "NEEDS_REVIEW", "extraction_status": "EXTRACTED_PROVISIONAL",
        "metadata_json": json.dumps({"standardization": {
            "status": "REQUESTED", "x_target_unit": "min", "y_target_unit": "g/L"
        }}),
    }
    point = {"point_index": 0, "x_value": 60, "y_value": 2500, "pixel_x": 20, "pixel_y": 40}
    row = _make_row(record, point, {"subject_links": [], "conditions": []})

    assert row["x_value"] == row["x_value_raw"] == 60
    assert row["y_value"] == row["y_value_raw"] == 2500
    assert row["x_unit"] == row["x_unit_raw"] == "s"
    assert row["y_unit"] == row["y_unit_raw"] == "mg/L"
    assert row["x_value_standardized"] == pytest.approx(1)
    assert row["y_value_standardized"] == pytest.approx(2.5)
    assert row["x_unit_standardized"] == "min"
    assert row["y_unit_standardized"] == "g/L"
    assert row["x_standardization_status"] == "DETERMINISTIC_DIMENSIONAL_CONVERSION"
    assert row["y_standardization_status"] == "DETERMINISTIC_DIMENSIONAL_CONVERSION"
    assert row["standardization_status"] == "DETERMINISTIC_DIMENSIONAL_CONVERSION"
    assert row["standardization_method_id"] == "DIMENSIONAL_FACTOR_TABLE_V1"
    assert row["standardization_evidence_id"] == "x:unit-factor:s->min;y:unit-factor:mg/L->g/L"
    assert row["compatibility_status"] == "NOT_HARMONIZED"


def test_export_keeps_unsupported_reference_scale_conversion_unresolved_per_axis():
    from scientific_figure_data.exporter import _make_row

    record = {
        "paper_id": "paper-1", "series_id": "series-2", "figure_id": "Figure2",
        "panel_id": "b", "technique": "CV", "domain": "battery",
        "label": "potential/current", "x_unit": "V vs Ag/AgCl", "y_unit": "mg/L",
        "y_axis_side": "LEFT", "qc_status": "PROVISIONAL_UNCALIBRATED",
        "review_state": "NEEDS_REVIEW", "metadata_json": json.dumps({"standardization": {
            "status": "REQUESTED", "x_target_unit": "V vs RHE", "y_target_unit": "g/L"
        }}),
    }
    row = _make_row(record, {"point_index": 0, "x_value": 0.25, "y_value": 1000},
                    {"subject_links": [], "conditions": []})

    assert row["x_value"] == row["x_value_raw"] == 0.25
    assert row["x_value_standardized"] is None
    assert row["x_unit_standardized"] is None
    assert row["x_standardization_status"] == "UNRESOLVED_UNSUPPORTED_CONVERSION"
    assert row["y_value_standardized"] == pytest.approx(1)
    assert row["y_unit_standardized"] == "g/L"
    assert row["y_standardization_status"] == "DETERMINISTIC_DIMENSIONAL_CONVERSION"
    assert row["standardization_status"] == "PARTIAL_DIMENSIONAL_STANDARDIZATION"


def test_export_flags_invalid_explicit_standardization_configuration():
    from scientific_figure_data.exporter import _make_row

    record = {
        "paper_id": "paper-1", "series_id": "series-3", "figure_id": "Figure3",
        "panel_id": "c", "technique": "CV", "domain": "battery",
        "label": "series", "x_unit": "V", "y_unit": "mA", "y_axis_side": "LEFT",
        "qc_status": "PROVISIONAL_UNCALIBRATED", "review_state": "NEEDS_REVIEW",
        "metadata_json": json.dumps({"standardization": {
            "status": "INVALID_CONFIGURATION", "configuration_errors": ["unsupported key: factor"]
        }}),
    }
    row = _make_row(record, {"point_index": 0, "x_value": 0.1, "y_value": 1.0},
                    {"subject_links": [], "conditions": []})
    assert row["standardization_status"] == "INVALID_CONFIGURATION"
    assert row["x_standardization_status"] == "INVALID_CONFIGURATION"
    assert row["y_standardization_status"] == "INVALID_CONFIGURATION"
    assert "STANDARDIZATION_CONFIGURATION_INVALID" in json.loads(row["compatibility_warnings_json"])



def test_cli_exposes_query_export_and_review_apply():
    parser = build_parser()
    query = parser.parse_args(["query", "--output-root", "out", "--technique", "CV", "--analyte", "PFOA"])
    assert query.command == "query" and query.analyte == "PFOA"
    export = parser.parse_args(["export", "--output-root", "out", "--out", "ml", "--reviewed-only"])
    assert export.command == "export" and export.reviewed_only
    review = parser.parse_args(["review", "apply", "--output-root", "out", "--patch", "patch.json"])
    assert review.review_command == "apply"


def test_ml_export_streams_points_with_subject_condition_and_provenance(tmp_path: Path):
    from scientific_figure_data.exporter import export_dataset

    snapshot, paper_root = make_output_with_series(tmp_path)
    catalog = Catalog(tmp_path / "catalog.sqlite")
    with catalog.con:
        catalog.con.execute(
            "INSERT INTO entities(entity_id,canonical_name,entity_type,domain,aliases_json,evidence_json) VALUES(?,?,?,?,?,?)",
            ("paper-1__sample-a", "Sample A", "material", "battery", '["A"]', '{"source":"legend"}'),
        )
        catalog.con.execute(
            "INSERT INTO series_subject_links(series_id,entity_id,role_in_series,evidence_json,link_status,identity_scope) VALUES(?,?,?,?,?,?)",
            ("series-a", "paper-1__sample-a", "tested_material", '{"source":"legend","page":2}', "ASSIGNED_WITH_EVIDENCE", "PAPER"),
        )
    output = tmp_path / "ml-export"
    manifest = export_dataset(
        catalog, tmp_path, output, {"paper_id": snapshot.paper_id, "technique": "CV"},
        include_review_required=True, fmt="csv", series_batch_size=1,
    )
    catalog.close()
    assert manifest["series_count"] == 2
    assert manifest["point_count"] == 4
    import csv
    with (output / "dataset.csv").open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    first = next(row for row in rows if row["series_id"] == "series-a")
    assert first["input_fingerprint"] == snapshot.input_fingerprint
    assert first["qc_status"] == "PROVISIONAL_UNCALIBRATED"
    assert first["standardization_status"] == "NOT_PERFORMED"
    assert first["x_value_standardized"] == ""
    assert first["y_value_standardized"] == ""
    assert first["x_unit_standardized"] == ""
    assert first["standardization_method_id"] == ""
    assert first["x_standardization_status"] == "NOT_REQUESTED"
    assert first["y_standardization_status"] == "NOT_REQUESTED"
    assert first["compatibility_status"] == "NOT_HARMONIZED"
    assert json.loads(first["subject_entity_ids_json"]) == ["paper-1__sample-a"]
    point_subjects = json.loads(first["subject_links_json"])
    assert point_subjects[0]["canonical_name"] == "Sample A"
    point_conditions = json.loads(first["conditions_json"])
    assert any(item["name"] == "electrolyte" for item in point_conditions)
    assert first["x_value_raw"] == first["x_value"]
    assert first["x_unit_raw"] == first["x_unit"]
    assert "pixel_x" in first and "y_err_low" in first
    metadata_rows = [
        json.loads(line) for line in (output / "series_metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    first_metadata = next(row for row in metadata_rows if row["series_id"] == "series-a")
    assert any(link["canonical_name"] == "Sample A" for link in first_metadata["subject_links"])
    assert any("electrolyte" in item["name"] for item in first_metadata["conditions"])
    assert first_metadata["input_fingerprint"] == snapshot.input_fingerprint
    assert first_metadata["standardization_status"] == "NOT_PERFORMED"
    assert first_metadata["subject_links"][0]["evidence"]["source"] == "legend"
    assert isinstance(first_metadata["conditions"][0]["value"], dict)
    assert manifest["schema_version"] == "1.2"
    assert manifest["row_granularity"] == "one_row_per_digitized_series_point"
    assert manifest["raw_value_policy"]
    assert (output / "warnings.jsonl").is_file()
    assert manifest["streaming"]["point_rows_buffered"] == 1
    assert first["point_index"].isdigit()
    assert first["x_value"] != ""
    assert first["pixel_x"] == "" or first["pixel_x"] is not None

    json_output = tmp_path / "ml-export-json"
    json_catalog = Catalog(tmp_path / "catalog.sqlite")
    json_manifest = export_dataset(
        json_catalog, tmp_path, json_output,
        {"paper_id": snapshot.paper_id, "technique": "CV"},
        include_review_required=True, fmt="json", series_batch_size=1,
    )
    json_catalog.close()
    json_rows = json.loads((json_output / "dataset.json").read_text(encoding="utf-8"))
    json_first = next(row for row in json_rows if row["series_id"] == "series-a")
    assert json_manifest["format"] == "json"
    assert isinstance(json_first["point_index"], int)
    assert isinstance(json_first["x_value"], float)
    assert isinstance(json_first["y_value"], float)
    assert json_first["subject_entity_ids_json"] == first["subject_entity_ids_json"]


def test_catalog_streaming_query_has_no_fixed_10000_series_limit(tmp_path: Path):
    snapshot = make_snapshot()
    catalog = Catalog(tmp_path / "catalog.sqlite")
    with catalog.con:
        catalog.register_paper(snapshot, "COMPLETED")
        for index in range(10025):
            series_id = f"series-{index:05d}"
            catalog.con.execute(
                """INSERT INTO series(series_id,paper_id,figure_id,panel_id,measurement_id,technique,domain,
                   label,x_unit,y_unit,y_axis_side,extraction_status,qc_status,review_state,metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (series_id, snapshot.paper_id, "Figure1", "a", f"m-{index}", "CV", "battery",
                 series_id, "V", "mA", "LEFT", "NEEDS_REVIEW", "PROVISIONAL_UNCALIBRATED",
                 "NEEDS_REVIEW", "{}"),
            )
            catalog.con.execute(
                "INSERT OR REPLACE INTO measurements VALUES(?,?,?,?,?,?)",
                (f"m-{index}", snapshot.paper_id, "Figure1", "CV", "battery", "{}"),
            )
    rows = sum(1 for _ in catalog.iter_query_series({"paper_id": snapshot.paper_id}, batch_size=127))
    assert rows == 10025
    assert len(catalog.query_series({"paper_id": snapshot.paper_id}, limit=10000)) == 10000
    catalog.close()


def test_end_to_end_cli_streaming_workflow_without_pdf_or_gpu(tmp_path: Path, capsys):
    from scientific_figure_data.cli import main

    input_root = tmp_path / "chem-literature"
    paper = input_root / "paper-001"
    paper.mkdir(parents=True)
    inventory = paper / "figure_inventory.json"
    inventory.write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "page": 1,
            "caption": "Electrochemical response",
            "shared_legends": ["Sample A"],
            "panels": [{
                "panel_id": "a",
                "technique": "CV",
                "domain": "battery",
                "bbox": [0.1, 0.1, 0.9, 0.9],
            }],
        }]
    }), encoding="utf-8")
    (paper / "main_analysis.md").write_text(
        "Sample A was measured in aqueous electrolyte.\n", encoding="utf-8"
    )
    original_hash = sha256_file(inventory)
    output_root = tmp_path / "scientific-figure-data"

    assert main(["scan", "--input-root", str(input_root), "--output-root", str(output_root)]) == 0
    capsys.readouterr()
    manifest_lines = (output_root / "corpus_manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == 1
    assert json.loads(manifest_lines[0])["paper_id"] == "paper-001"

    assert main([
        "run", "--all", "--input-root", str(input_root), "--output-root", str(output_root), "--dry-run"
    ]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["planned_papers"] == 1

    assert main([
        "run", "--all", "--input-root", str(input_root), "--output-root", str(output_root),
        "--workers", "1", "--memory-limit", "512", "--max-render-pixels", "1000000",
    ]) == 0
    run_report = json.loads(capsys.readouterr().out)
    assert run_report["completed_with_review"] == 1
    assert run_report["default_llm_tokens"] == 0

    assert main(["status", "--output-root", str(output_root)]) == 0
    assert "NEEDS_REVIEW" in capsys.readouterr().out

    assert main(["query", "--output-root", str(output_root), "--technique", "CV"]) == 0
    query_rows = json.loads(capsys.readouterr().out)
    assert len(query_rows) == 1
    assert query_rows[0]["series_id"] == "paper-001__Figure1_a_unassigned"

    export_dir = tmp_path / "ml-output"
    assert main([
        "export", "--output-root", str(output_root), "--out", str(export_dir),
        "--technique", "CV", "--format", "csv",
    ]) == 0
    export_manifest = json.loads(capsys.readouterr().out)
    assert export_manifest["series_count"] == 1
    assert (export_dir / "dataset.csv").is_file()
    assert (export_dir / "series_metadata.jsonl").is_file()

    assert main(["index", "rebuild", "--output-root", str(output_root)]) == 0
    assert json.loads(capsys.readouterr().out)["papers_indexed"] == 1
    assert main([
        "validate", "--output-root", str(output_root), "--input-root", str(input_root)
    ]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["status"] == "OK"
    assert sha256_file(inventory) == original_hash


def test_scheduler_resume_reuses_completed_paper_stage(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers
    from scientific_figure_data.scheduler import run_corpus

    input_root = tmp_path / "input"
    paper = input_root / "nested" / "paper-cache"
    paper.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    output_root = tmp_path / "output"

    first = run_corpus(input_root, output_root, discover_papers(input_root), workers=1)
    assert first["completed_with_review"] == 1
    canonical_id = "nested__paper-cache"
    con = connect_catalog(output_root / "catalog.sqlite")
    job = con.execute("SELECT paper_id,state FROM jobs").fetchone()
    indexed = con.execute("SELECT paper_id FROM papers").fetchone()
    assert job["paper_id"] == canonical_id
    assert indexed["paper_id"] == canonical_id
    con.close()

    second = run_corpus(input_root, output_root, discover_papers(input_root), workers=1)
    assert second["cached"] == 1
    assert second["completed_with_review"] == 1


def test_pdfium_native_object_inventory_passes_and_closes_textpage(monkeypatch):
    import importlib
    import types
    from scientific_figure_data.pdf_backend import PdfPageView

    class FakeTextPage:
        closed = False

        def get_text_range(self):
            return "0 1 2 3"

        def close(self):
            self.closed = True

    textpage = FakeTextPage()

    class FakeTextObject:
        type = 1
        level = 0

        def get_bounds(self):
            return (10.0, 20.0, 110.0, 120.0)

        def extract(self):
            assert not textpage.closed
            return textpage.get_text_range()

        def get_font_size(self):
            return 7.0

        def get_font(self):
            return None

    class FakePage:
        received_textpage = None

        def get_textpage(self):
            return textpage

        def get_width(self):
            return 200.0

        def get_height(self):
            return 300.0

        def get_rotation(self):
            return 0

        def get_objects(self, max_depth, textpage):
            self.received_textpage = textpage
            return iter([FakeTextObject()])

    raw_module = types.SimpleNamespace(
        FPDF_PAGEOBJ_TEXT=1,
        FPDF_PAGEOBJ_PATH=2,
        FPDF_PAGEOBJ_IMAGE=3,
        FPDF_PAGEOBJ_SHADING=4,
        FPDF_PAGEOBJ_FORM=5,
    )
    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "pypdfium2.raw":
            return raw_module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    page = FakePage()
    result = PdfPageView(page, object()).inspect_native_objects()

    assert page.received_textpage is textpage
    assert textpage.closed is True
    assert result["object_inventory_status"] == "OK"
    assert result["native_text"] == "0 1 2 3"
    assert result["objects"][0]["text"] == "0 1 2 3"
    assert result["objects"][0]["font_size"] == 7.0
    assert result["objects"][0]["bounds_pdf"] == [10.0, 20.0, 110.0, 120.0]


def test_backend_probe_without_pdfs_is_explicit_and_does_not_select_backend(tmp_path: Path, monkeypatch, capsys):
    from scientific_figure_data.backend_probe import main

    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    report = json.loads((tmp_path / "backend_probe_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "NO_INPUT_PDFS"
    assert "pypdfium2" in report["candidate_modules"]
    assert "pdfminer" in report["candidate_modules"]
    assert "pikepdf" in report["candidate_modules"]
    assert "backend" not in report
    capsys.readouterr()


def test_entity_and_analyte_queries_use_exact_normalized_aliases(tmp_path: Path):
    snapshot = make_snapshot()
    sample = make_series("sample-series", "measurement-sample", "electrolyte")
    sample.subject_links = [{
        "entity_id": "sample-a",
        "canonical_name": "Sample A",
        "entity_type": "material",
        "aliases": ["SA"],
        "role_in_series": "tested_material",
        "status": "ASSIGNED_WITH_EVIDENCE",
        "evidence": {"source": "legend", "page": 2},
    }]
    analyte = make_series("pfoa-series", "measurement-pfoa", "pH")
    analyte.subject_links = [{
        "entity_id": "pfoa",
        "canonical_name": "Perfluorooctanoic acid",
        "entity_type": "analyte",
        "aliases": ["PFOA", "perfluorooctanoate"],
        "role_in_series": "target_analyte",
        "status": "ASSIGNED_WITH_EVIDENCE",
        "evidence": {"source": "caption", "page": 3},
    }]
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.index_paper(
        snapshot,
        [{"figure_id": "Figure1", "page": 2, "caption": "Test"}],
        [{"figure_id": "Figure1", "panel_id": "a", "bbox": [0, 0, 1, 1]}],
        [sample, analyte],
        "COMPLETED_WITH_REVIEW",
    )
    assert [row["series_id"] for row in catalog.query_series({"entity": "SA"})] == ["sample-series"]
    assert catalog.query_series({"entity": "Sample"}) == []
    assert [row["series_id"] for row in catalog.query_series({"analyte": "PFOA"})] == ["pfoa-series"]
    assert catalog.query_series({"analyte": "PFO"}) == []
    catalog.close()


def test_job_ledger_recovers_only_expired_running_leases(tmp_path: Path):
    from scientific_figure_data.models import JobState
    from scientific_figure_data.scheduler import JobLedger

    ledger = JobLedger(tmp_path / "catalog.sqlite", lease_seconds=600)
    assert ledger.prepare("paper-active") is True
    ledger.start("paper-active", "test-worker-slot-1", "a" * 64)
    running_row = ledger.con.execute(
        "SELECT worker_id,started_at,input_fingerprint FROM jobs WHERE paper_id='paper-active'"
    ).fetchone()
    assert running_row["worker_id"] == "test-worker-slot-1"
    assert running_row["started_at"]
    assert running_row["input_fingerprint"] == "a" * 64
    assert ledger.prepare("paper-active") is False
    with ledger.con:
        ledger.con.execute(
            "UPDATE jobs SET lease_expires_at=0 WHERE paper_id=?",
            ("paper-active",),
        )
    assert ledger.prepare("paper-active") is True
    state = ledger.con.execute(
        "SELECT state FROM jobs WHERE paper_id=?", ("paper-active",)
    ).fetchone()["state"]
    event = ledger.con.execute(
        "SELECT event_type FROM job_events WHERE paper_id=? ORDER BY event_id DESC LIMIT 1",
        ("paper-active",),
    ).fetchone()["event_type"]
    assert state == JobState.RETRY_WAIT.value
    assert event == "INTERRUPTED_RECOVERY"
    ledger.close()


def test_reviewed_series_is_locked_until_explicit_force_recompute(tmp_path: Path):
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper = input_root / "paper-locked"
    paper.mkdir(parents=True)
    inventory = paper / "figure_inventory.json"
    inventory.write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "panels": [{"panel_id": "a", "technique": "CV", "domain": "battery"}],
        }]
    }), encoding="utf-8")
    output_root = tmp_path / "output"

    first = process_paper(input_root, Path("paper-locked"), output_root)
    assert first["cached"] is False
    paper_root = output_root / "papers" / "paper-locked"
    digitization_path = paper_root / "digitization.json"
    digitization = json.loads(digitization_path.read_text(encoding="utf-8"))
    assert digitization["series"]
    digitization["series"][0]["review_state"] = "REVIEWED_ACCEPTED"
    digitization["series"][0]["extraction_status"] = "REVIEWED_ACCEPTED"
    digitization_path.write_text(json.dumps(digitization, indent=2), encoding="utf-8")

    bundle_path = paper_root / "paper_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["content_hashes"]["digitization.json"] = sha256_file(digitization_path)
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    accepted_hash = sha256_file(digitization_path)

    (paper / "main_analysis.md").write_text("New upstream context changed the input fingerprint.\n", encoding="utf-8")
    locked = process_paper(input_root, Path("paper-locked"), output_root)
    assert locked["job_state"] == "BLOCKED"
    assert locked["status"] == "BLOCKED_REVIEW_LOCKED"
    assert sha256_file(digitization_path) == accepted_hash

    forced = process_paper(
        input_root, Path("paper-locked"), output_root,
        options={"force_recompute_reviewed": True},
    )
    assert forced["cached"] is False
    assert forced["job_state"] == "NEEDS_REVIEW"
    backups = list((paper_root / "versions").glob("pre-recompute-*"))
    assert backups
    assert any((backup / "digitization.json").is_file() for backup in backups)


def test_rapidocr_uses_cpu_single_thread_and_reuses_engine(monkeypatch, tmp_path: Path):
    import sys
    import types
    from scientific_figure_data import ocr

    class FakeRapidOCR:
        constructions = 0
        calls = 0
        parameters = None

        def __init__(self, params):
            type(self).constructions += 1
            type(self).parameters = params

        def __call__(self, image_path):
            type(self).calls += 1
            return types.SimpleNamespace(
                boxes=[[[1.0, 2.0], [20.0, 2.0], [20.0, 8.0], [1.0, 8.0]]],
                txts=("Sample A",),
                scores=(0.98,),
            )

    from enum import Enum

    class FakeEngineType(Enum):
        ONNXRUNTIME = "onnxruntime"

    fake_module = types.ModuleType("rapidocr")
    fake_module.EngineType = FakeEngineType
    fake_module.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(sys.modules, "rapidocr", fake_module)
    ocr.reset_ocr_engine_for_tests()
    image_path = tmp_path / "panel.png"
    image_path.write_bytes(b"fake image")
    try:
        first = ocr.run_ocr(image_path)
        second = ocr.run_ocr(image_path)
        assert first == second
        assert first[0]["text"] == "Sample A"
        assert first[0]["confidence"] == 0.98
        assert first[0]["polygon"][0] == [1.0, 2.0]
        assert FakeRapidOCR.constructions == 1
        assert FakeRapidOCR.calls == 2
        assert FakeRapidOCR.parameters["EngineConfig.onnxruntime.intra_op_num_threads"] == 1
        assert FakeRapidOCR.parameters["EngineConfig.onnxruntime.inter_op_num_threads"] == 1
        assert FakeRapidOCR.parameters["EngineConfig.onnxruntime.use_cuda"] is False
        for stage in ("Det", "Cls", "Rec"):
            assert FakeRapidOCR.parameters[f"{stage}.engine_type"] is FakeEngineType.ONNXRUNTIME
    finally:
        ocr.reset_ocr_engine_for_tests()


def _vector_path_object(object_index, points, *, color=(30, 90, 180, 255), closed=False):
    segments = []
    for index, point in enumerate(points):
        segments.append({
            "index": index,
            "type": 2 if index == 0 else 0,
            "type_name": "MOVE_TO" if index == 0 else "LINE_TO",
            "point_pdf": list(point),
            "closes_subpath": bool(closed and index == len(points) - 1),
        })
    return {
        "object_index": object_index,
        "object_type": "PATH",
        "bounds_pdf": [
            min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points),
        ],
        "segments": segments,
        "segment_count": len(segments),
        "line_only_path": True,
        "contains_closed_subpath": closed,
        "path_style": {
            "stroke_rgba": list(color),
            "fill_rgba": None,
            "stroke_width_pdf": 0.8,
            "fill_mode": 0,
            "stroke_enabled": True,
        },
    }


def test_vector_path_candidates_reject_axes_and_keep_curve_order():
    from scientific_figure_data.vector_paths import choose_vector_paths

    curve_points = [
        (10, 15), (20, 20), (30, 25), (40, 28),
        (50, 32), (60, 40), (70, 50), (80, 60),
    ]
    native = {"objects": [
        _vector_path_object(1, [(5, 5), (95, 5), (95, 95), (5, 95)], closed=True),
        _vector_path_object(2, [(0, 10), (100, 10)]),  # horizontal axis/gridline
        _vector_path_object(3, curve_points),
    ]}
    selected, result = choose_vector_paths(native, (0, 0, 100, 100))
    assert result["status"] == "UNIQUE_LOW_AMBIGUITY_CANDIDATE"
    assert [item.object_index for item in selected] == [3]
    assert list(selected[0].points_pdf) == curve_points


def test_vector_path_candidates_route_bezier_and_ambiguous_candidates_to_review():
    from scientific_figure_data.vector_paths import choose_vector_paths

    points = [(10 + index * 10, 15 + index * 5) for index in range(8)]
    first = _vector_path_object(1, points)
    second = _vector_path_object(2, [(x, y + 8) for x, y in points])
    native = {"objects": [first, second]}
    selected, result = choose_vector_paths(native, (0, 0, 100, 100))
    assert not selected
    assert result["status"] == "NEEDS_REVIEW"
    assert result["reason"] == "MULTIPLE_VECTOR_CANDIDATES"

    bezier = _vector_path_object(3, points)
    bezier["segments"][3]["type_name"] = "BEZIER_TO"
    native = {"objects": [bezier]}
    selected, result = choose_vector_paths(native, (0, 0, 100, 100))
    assert not selected
    assert result["reason"] == "NO_VECTOR_CANDIDATE"


def test_pdf_vector_path_is_mapped_into_crop_pixels_and_calibrated_in_original_order(tmp_path: Path):
    from scientific_figure_data.pipeline import _extract_panel
    from scientific_figure_data.vector_paths import choose_vector_paths, pdf_points_to_crop_pixels

    points_pdf = [
        (10, 20), (20, 30), (30, 40), (40, 45),
        (50, 50), (60, 55), (70, 60), (80, 70),
    ]
    native = {"objects": [_vector_path_object(7, points_pdf)]}
    native_path = tmp_path / "native.json"
    native_path.write_text(json.dumps(native), encoding="utf-8")
    crop_mapping = {
        "crop_left_pdf": 0.0, "crop_top_pdf": 100.0,
        "render_scale": 2.0, "page_rotation_degrees": 0,
    }
    mapped = pdf_points_to_crop_pixels(
        points_pdf, crop_left_pdf=0.0, crop_top_pdf=100.0, render_scale=2.0
    )
    assert mapped[0] == (20.0, 160.0)
    assert mapped[-1] == (160.0, 60.0)

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "native-cv-trace",
        "technique": "CV",
        "domain": "battery",
        "data_family": "CV",
        "plot_bbox_pdf": [0, 0, 100, 100],
        "vector_object_indices": [7],
        "x_axis_anchors": [{"pixel": 20, "value": -1}, {"pixel": 160, "value": 1}],
        "y_axis_anchors": [{"pixel": 160, "value": -10}, {"pixel": 60, "value": 10}],
        "x_unit": "V",
        "y_unit": "mA cm-2",
    }
    panel = {"technique": "CV", "domain": "battery"}
    figure = {"technique": "CV", "domain": "battery"}
    records = _extract_panel(
        None, "paper-1", "Figure1", "a", panel, figure,
        {"figures": {"Figure1": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), 4, {"artifact": "evidence/page_0004_native.json"},
        [], "a" * 64, "b" * 64, native_path, crop_mapping,
    )
    assert len(records) == 1
    record = records[0]
    assert record.extraction_method == "PDFIUM_NATIVE_VECTOR_POLYLINE"
    assert record.extraction_status == "EXTRACTED_PROVISIONAL"
    assert [point.point_index for point in record.points] == list(range(8))
    assert [point.pixel_x for point in record.points] == [point[0] for point in mapped]
    assert record.points[0].x == pytest.approx(-1.0)
    assert record.points[-1].x == pytest.approx(1.0)
    assert record.evidence[0]["source_pdf_sha256"] == "a" * 64


def test_numeric_axis_text_requires_margin_position_confidence_and_monotonicity():
    from scientific_figure_data.axis_text import extract_numeric_axis_anchors

    def row(text, cx, cy, confidence=0.98):
        return {
            "text": text,
            "confidence": confidence,
            "polygon": [[cx - 3, cy - 3], [cx + 3, cy - 3],
                        [cx + 3, cy + 3], [cx - 3, cy + 3]],
        }

    rows = [
        row("0", 30, 130), row("5", 100, 130), row("10", 170, 130),
        row("0", 20, 120), row("5", 20, 70), row("10", 20, 20),
        row("999", 90, 60),  # inside-plot number; must not become an axis tick
        row("15", 100, 132, confidence=0.40),  # low confidence
        row("Voltage", 100, 150),
    ]
    parsed = extract_numeric_axis_anchors(rows, (30, 20, 170, 120))
    assert [item["value"] for item in parsed["x_anchors"]] == [0.0, 5.0, 10.0]
    assert [item["value"] for item in parsed["y_left_anchors"]] == [10.0, 5.0, 0.0]
    assert not parsed["y_right_anchors"]
    assert parsed["status"] == "NUMERIC_TICKS_CANDIDATES_FOUND"


def test_numeric_axis_text_rejects_non_monotonic_tick_candidates():
    from scientific_figure_data.axis_text import extract_numeric_axis_anchors

    rows = []
    for text, x in (("0", 30), ("10", 90), ("5", 150)):
        rows.append({
            "text": text,
            "confidence": 0.99,
            "polygon": [[x - 2, 125], [x + 2, 125], [x + 2, 130], [x - 2, 130]],
        })
    parsed = extract_numeric_axis_anchors(rows, (20, 20, 160, 120))
    assert parsed["x_anchors"] == []
    assert parsed["status"] == "NO_CONFIDENT_NUMERIC_TICKS"


def test_ocr_axis_anchors_feed_calibration_without_llm(tmp_path: Path):
    from scientific_figure_data.pipeline import _extract_panel

    def row(text, cx, cy):
        return {
            "text": text, "confidence": 0.99,
            "polygon": [[cx - 3, cy - 3], [cx + 3, cy - 3],
                        [cx + 3, cy + 3], [cx - 3, cy + 3]],
        }

    ocr_rows = [
        row("0", 30, 130), row("5", 100, 130), row("10", 170, 130),
        row("0", 20, 120), row("5", 20, 70), row("10", 20, 20),
    ]

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "ocr-axis-series",
        "technique": "GCD", "domain": "battery",
        "plot_box": [30, 20, 170, 120],
        "pixel_points": [[30, 120], [100, 70], [170, 20]],
        "x_unit": "min", "y_unit": "V",
    }
    records = _extract_panel(
        None, "paper-1", "Figure2", "a",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery"},
        {"figures": {"Figure2": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), 5, None, ocr_rows, "c" * 64, "d" * 64,
    )
    assert records[0].extraction_status == "EXTRACTED_PROVISIONAL"
    assert records[0].metadata["x_calibration"]["anchors"][0]["value"] == 0.0
    assert records[0].metadata["y_calibration"]["anchors"][0]["value"] == 10.0
    assert records[0].metadata["axis_text_evidence"]["provisional"] is True


def test_unresolved_dual_axis_keeps_vector_geometry_and_calibrated_x(tmp_path: Path):
    from scientific_figure_data.pipeline import _extract_panel

    points_pdf = [
        (10, 20), (20, 30), (30, 40), (40, 45),
        (50, 50), (60, 55), (70, 60), (80, 70),
    ]
    native_path = tmp_path / "dual-axis-native.json"
    native_path.write_text(json.dumps({
        "objects": [_vector_path_object(11, points_pdf)]
    }), encoding="utf-8")

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "dual-axis-curve",
        "technique": "GCD", "domain": "battery",
        "data_family": "TIME_SERIES",
        "plot_bbox_pdf": [0, 0, 100, 100],
        "vector_object_indices": [11],
        "x_axis_anchors": [{"pixel": 20, "value": 0}, {"pixel": 160, "value": 7}],
        # Y anchors intentionally unresolved: left/right assignment is ambiguous.
    }
    records = _extract_panel(
        None, "paper-1", "Figure3", "b",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery"},
        {"figures": {"Figure3": {"panels": {"b": {"series": [definition]}}}}},
        EmptyContext(), 6, None, [], "e" * 64, "f" * 64, native_path,
        {"crop_left_pdf": 0, "crop_top_pdf": 100, "render_scale": 2,
         "page_rotation_degrees": 0},
    )
    record = records[0]
    assert record.y_axis_side == "UNASSIGNED"
    assert record.extraction_method == "PDFIUM_NATIVE_VECTOR_POLYLINE"
    assert record.extraction_status == "GEOMETRY_ONLY_NEEDS_REVIEW"
    assert len(record.points) == 8
    assert all(point.x is not None for point in record.points)
    assert all(point.y is None for point in record.points)
    assert all(point.pixel_y is not None for point in record.points)


def test_native_pdf_text_tick_anchors_are_mapped_without_ocr():
    from scientific_figure_data.axis_text import extract_native_numeric_axis_anchors

    def text_obj(index, text, x, y):
        return {
            "object_index": index, "object_type": "TEXT", "text": text,
            "bounds_pdf": [x - 2, y - 2, x + 2, y + 2],
            "font_size": 7.0, "font_name": "Arial",
        }

    native = {"objects": [
        text_obj(1, "0", 30, 10), text_obj(2, "5", 100, 10), text_obj(3, "10", 170, 10),
        text_obj(4, "0", 10, 30), text_obj(5, "5", 10, 70), text_obj(6, "10", 10, 110),
        text_obj(7, "999", 90, 70),  # inside plot: not an axis tick
        text_obj(8, "CV", 100, 145),
    ]}
    parsed = extract_native_numeric_axis_anchors(
        native, (20, 20, 180, 120),
        {"crop_left_pdf": 0, "crop_top_pdf": 150, "render_scale": 2},
    )
    assert [item["value"] for item in parsed["x_anchors"]] == [0.0, 5.0, 10.0]
    assert [item["pixel"] for item in parsed["x_anchors"]] == [60.0, 200.0, 340.0]
    assert [item["value"] for item in parsed["y_left_anchors"]] == [10.0, 5.0, 0.0]
    assert [item["pixel"] for item in parsed["y_left_anchors"]] == [80.0, 160.0, 240.0]
    assert parsed["source"] == "PDF_NATIVE_TEXT"


def test_pipeline_uses_native_tick_text_before_manual_or_ocr_ticks(tmp_path: Path):
    from scientific_figure_data.pipeline import _extract_panel

    def text_obj(index, text, x, y):
        return {
            "object_index": index, "object_type": "TEXT", "text": text,
            "bounds_pdf": [x - 2, y - 2, x + 2, y + 2],
            "font_size": 7.0, "font_name": "Arial",
        }

    native_path = tmp_path / "native-axis.json"
    native_path.write_text(json.dumps({"objects": [
        text_obj(1, "0", 30, 10), text_obj(2, "5", 100, 10), text_obj(3, "10", 170, 10),
        text_obj(4, "0", 10, 30), text_obj(5, "5", 10, 70), text_obj(6, "10", 10, 110),
    ]}), encoding="utf-8")

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "native-text-axis-series", "technique": "GCD", "domain": "battery",
        "plot_bbox_pdf": [20, 20, 180, 120],
        "pixel_points": [[60, 240], [200, 160], [340, 80]],
        "x_unit": "min", "y_unit": "V",
    }
    records = _extract_panel(
        None, "paper-1", "Figure4", "a",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery"},
        {"figures": {"Figure4": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), 7, {"artifact": "native-axis.json"}, [],
        "a" * 64, "b" * 64, native_path,
        {"crop_left_pdf": 0, "crop_top_pdf": 150, "render_scale": 2,
         "page_rotation_degrees": 0},
    )
    record = records[0]
    assert record.extraction_status == "EXTRACTED_PROVISIONAL"
    assert record.metadata["axis_text_evidence"]["source"] == "PDF_NATIVE_TEXT"
    assert [point.x for point in record.points] == pytest.approx([0, 5, 10])
    assert [point.y for point in record.points] == pytest.approx([0, 5, 10])


def test_review_axis_anchor_patch_recalibrates_panel_csv_and_sqlite(tmp_path: Path):
    snapshot, paper_root = make_output_with_series(tmp_path)
    digitization_path = paper_root / "digitization.json"
    panel_csv = paper_root / "series" / "Figure1__a" / "panel_series.csv"
    patch = {
        "schema_version": "1.0",
        "patch_id": "axis-review-001",
        "paper_id": snapshot.paper_id,
        "target_artifact": "digitization.json",
        "original_result_hash": sha256_file(digitization_path),
        "reviewer": "axis-reviewer",
        "changes": [{
            "series_id": "series-a",
            "set": {
                "x_axis_anchors": [
                    {"pixel": 10.0, "value": 0.0},
                    {"pixel": 20.0, "value": 2.0},
                ],
                "y_axis_anchors": [
                    {"pixel": 20.0, "value": 0.0},
                    {"pixel": 10.0, "value": 4.0},
                ],
            },
        }],
    }
    patch_path = tmp_path / "axis-patch.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    result = apply_review_patch(tmp_path, patch_path)
    assert result["status"] == "REVIEWED_ACCEPTED"

    import csv
    with panel_csv.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    corrected = [row for row in rows if row["series_id"] == "series-a"]
    untouched = [row for row in rows if row["series_id"] == "series-b"]
    assert [float(row["x_value"]) for row in corrected] == pytest.approx([0.0, 2.0])
    assert [float(row["y_value"]) for row in corrected] == pytest.approx([0.0, 4.0])
    assert [float(row["x_value"]) for row in untouched] == pytest.approx([0.0, 1.0])
    assert [float(row["y_value"]) for row in untouched] == pytest.approx([0.0, 1.0])

    document = json.loads(digitization_path.read_text(encoding="utf-8"))
    record = next(item for item in document["series"] if item["series_id"] == "series-a")
    assert record["metadata"]["x_axis_calibration"]["slope"] == pytest.approx(0.2)
    assert record["metadata"]["y_axis_calibration"]["slope"] == pytest.approx(-0.4)
    assert record["review_state"] == "REVIEWED_ACCEPTED"

    catalog = Catalog(tmp_path / "catalog.sqlite")
    stored_metadata = json.loads(catalog.con.execute(
        "SELECT metadata_json FROM series WHERE series_id='series-a'"
    ).fetchone()["metadata_json"])
    assert stored_metadata["x_axis_calibration"]["slope"] == pytest.approx(0.2)
    indexed = catalog.con.execute(
        "SELECT x_value,y_value FROM series_points WHERE series_id='series-a' ORDER BY point_index"
    ).fetchall()
    assert [row["x_value"] for row in indexed] == pytest.approx([0.0, 2.0])
    assert [row["y_value"] for row in indexed] == pytest.approx([0.0, 4.0])
    untouched_index = catalog.con.execute(
        "SELECT x_value,y_value FROM series_points WHERE series_id='series-b' ORDER BY point_index"
    ).fetchall()
    assert [row["x_value"] for row in untouched_index] == pytest.approx([0.0, 1.0])
    assert [row["y_value"] for row in untouched_index] == pytest.approx([0.0, 1.0])
    catalog.close()

    bundle = json.loads((paper_root / "paper_bundle.json").read_text(encoding="utf-8"))
    assert bundle["content_hashes"]["digitization.json"] == sha256_file(digitization_path)
    assert bundle["content_hashes"]["series/Figure1__a/panel_series.csv"] == sha256_file(panel_csv)


def test_review_anchor_patch_rejects_duplicate_and_nonfinite_pixels():
    from scientific_figure_data.review import _validate_patch

    base = {
        "patch_id": "bad-axis",
        "paper_id": "paper-1",
        "target_artifact": "digitization.json",
        "original_result_hash": "a" * 64,
        "changes": [{
            "series_id": "series-a",
            "set": {"x_axis_anchors": [
                {"pixel": 1.0, "value": 0.0},
                {"pixel": 1.0, "value": 1.0},
            ]},
        }],
    }
    with pytest.raises(ValueError, match="unique"):
        _validate_patch(base)
    base["changes"][0]["set"]["x_axis_anchors"][1]["pixel"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        _validate_patch(base)


def test_adapter_does_not_mistake_corpus_root_pdf_for_one_paper(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers

    root = tmp_path / "corpus"
    root.mkdir()
    (root / "loose-root.pdf").write_bytes(b"%PDF-root")
    paper_one = root / "paper-001"
    paper_one.mkdir()
    (paper_one / "main.pdf").write_bytes(b"%PDF-one")
    (paper_one / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    assets = paper_one / "assets"
    assets.mkdir()
    (assets / "embedded.pdf").write_bytes(b"%PDF-embedded")
    paper_two = root / "paper-002"
    paper_two.mkdir()
    (paper_two / "main_analysis.md").write_text("Extracted text", encoding="utf-8")

    assert list(discover_papers(root)) == [paper_one, paper_two]


def test_adapter_allows_a_single_pdf_paper_at_the_root(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers, snapshot_paper

    root = tmp_path / "one-paper"
    root.mkdir()
    (root / "article.pdf").write_bytes(b"%PDF-root-only")
    discovered = list(discover_papers(root))
    assert discovered == [root]
    snapshot = snapshot_paper(root, root)
    assert snapshot.paper_id == "root-paper"


def test_canonical_paper_id_is_stable_and_windows_safe():
    from scientific_figure_data.manifest import storage_paper_id

    assert storage_paper_id("nested/paper-001") == "nested__paper-001"
    assert storage_paper_id("nested\\paper-001") == "nested__paper-001"
    assert storage_paper_id("NUL") == "_NUL"
    assert storage_paper_id("a" * 140).startswith("a" * 100 + "_")


def test_chart_classifier_uses_explicit_technique_and_axis_semantics():
    from scientific_figure_data.chart_classifier import classify_chart_family

    raman = classify_chart_family("Raman")
    assert raman["technique"] == "Raman"
    assert raman["chart_family"] == "SPECTRUM"
    assert raman["y_signal_mode"] == "SERIES_RELATIVE_SIGNAL"

    cv = classify_chart_family(None, "Potential (V)", "Current density", "Cyclic voltammetry")
    assert cv["technique"] == "CV"
    assert cv["chart_family"] == "NON_MONOTONIC_CURVE"

    kinetics = classify_chart_family(None, "Time (min)", "C/C0")
    assert kinetics["chart_family"] == "TIME_SERIES"

    ambiguous = classify_chart_family(None, "Wavenumber (cm-1)", "Absorbance")
    assert ambiguous["chart_family"] == "UNCLASSIFIED"
    assert ambiguous["status"] == "NEEDS_REVIEW"

    # Page-level text and incidental words in a caption must not route SEM/body
    # text into the CV curve extractor.
    sem = classify_chart_family(
        None, None, None, "SEM images of zinc deposition",
        "Potential was applied during electrochemical plating",
    )
    assert sem["chart_family"] == "UNCLASSIFIED"
    body_reference = classify_chart_family(
        None, None, None,
        "Figure 5d, the cell can operate at a potential for 250 cycles",
    )
    assert body_reference["chart_family"] == "UNCLASSIFIED"

    axis_cv = classify_chart_family(None, "Potential (V)", "Current density (A g-1)")
    assert axis_cv["technique"] == "CV"
    assert axis_cv["status"] == "PROVISIONAL_AXIS_SEMANTIC_CLASSIFICATION"


def test_plot_region_detector_finds_unique_rectangular_frame_and_rejects_borderless_image(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_plot_box

    image = Image.new("RGB", (300, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 260, 170), outline=(20, 20, 20), width=2)
    image_path = tmp_path / "plot-frame.png"
    image.save(image_path)
    result = detect_plot_box(image_path)
    assert result["status"] == "PROVISIONAL_PLOT_BOX"
    assert result["pixel_bbox"] == [40, 30, 260, 170]

    blank_path = tmp_path / "no-frame.png"
    Image.new("RGB", (300, 200), "white").save(blank_path)
    blank = detect_plot_box(blank_path)
    assert blank["status"] == "NEEDS_REVIEW"


def test_plot_frame_scan_downsamples_before_rgb_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_plot_box_candidates

    # 5.72 MP grayscale source: conversion must occur only after the bounded
    # analysis resize, rather than allocating a full-size RGB copy first.
    image = Image.new("L", (2600, 2200), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 160, 2420, 2040), outline=0, width=8)
    image_path = tmp_path / "large-grayscale-plot.png"
    image.save(image_path)

    original_convert = Image.Image.convert
    converted_sizes: list[tuple[int, int]] = []

    def record_conversion(self, *args, **kwargs):
        converted_sizes.append(self.size)
        return original_convert(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "convert", record_conversion)
    result = detect_plot_box_candidates(image_path)

    assert result["analysis_scale"] < 1.0
    analysis_width, analysis_height = result["analysis_image_size"]
    assert analysis_width * analysis_height <= 5_000_000
    assert converted_sizes
    assert all(width * height <= 5_000_000 for width, height in converted_sizes)


def test_single_trace_color_detection_rejects_multicolor_plot(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.plot_region import detect_single_trace_color

    single = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(single)
    draw.line((10, 60, 190, 30), fill=(220, 20, 30), width=2)
    one_path = tmp_path / "one-color.png"
    single.save(one_path)
    detected = detect_single_trace_color(one_path, (0, 0, 200, 120))
    assert detected["status"] == "UNIQUE_CHROMATIC_FAMILY"
    assert detected["color_rgb"][0] > 150

    multi = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(multi)
    draw.line((10, 35, 190, 25), fill=(220, 20, 30), width=2)
    draw.line((10, 90, 190, 100), fill=(20, 60, 220), width=2)
    multi_path = tmp_path / "two-colors.png"
    multi.save(multi_path)
    rejected = detect_single_trace_color(multi_path, (0, 0, 200, 120))
    assert rejected["status"] == "NEEDS_REVIEW"
    assert rejected["reason"] == "MULTIPLE_CHROMATIC_FAMILIES"


def test_pipeline_auto_detects_simple_single_color_time_series_without_override(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.pipeline import _extract_panel

    image = Image.new("RGB", (300, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 260, 170), outline=(20, 20, 20), width=2)
    draw.line((45, 135, 85, 120, 125, 105, 165, 90, 205, 75, 255, 50),
              fill=(220, 20, 30), width=2)
    image_path = tmp_path / "panel.png"
    image.save(image_path)

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "auto-gcd",
        "technique": "GCD",
        "domain": "battery",
        "x_label": "Time (min)",
        "y_label": "Voltage (V)",
        "x_axis_anchors": [
            {"pixel": 40, "value": 0},
            {"pixel": 260, "value": 100},
        ],
        "y_axis_anchors": [
            {"pixel": 170, "value": 0},
            {"pixel": 30, "value": 5},
        ],
        # Deliberately no plot_box, color_rgb or pixel_points.
    }
    records = _extract_panel(
        image_path, "paper-auto", "Figure1", "a",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery", "caption": "Galvanostatic charge-discharge"},
        {"figures": {"Figure1": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), None,
    )
    assert len(records) == 1
    record = records[0]
    assert record.extraction_method == "raster_color_connected_path"
    assert record.extraction_status == "EXTRACTED_PROVISIONAL"
    assert len(record.points) >= 150
    assert record.metadata["plot_detection"]["status"] == "PROVISIONAL_PLOT_BOX"
    assert record.metadata["color_detection"]["status"] == "UNIQUE_CHROMATIC_FAMILY"
    assert record.metadata["chart_family_classification"]["chart_family"] == "TIME_SERIES"
    assert record.points[0].x == pytest.approx((45 - 40) * 100 / 220)
    assert record.points[-1].x == pytest.approx((255 - 40) * 100 / 220)


def test_pipeline_routes_multicolor_raster_curves_to_review_without_guessing(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.pipeline import _extract_panel

    image = Image.new("RGB", (300, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 260, 170), outline=(20, 20, 20), width=2)
    draw.line((45, 60, 255, 50), fill=(220, 20, 30), width=2)
    draw.line((45, 140, 255, 150), fill=(20, 60, 220), width=2)
    image_path = tmp_path / "multi-panel.png"
    image.save(image_path)

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "ambiguous-gcd",
        "technique": "GCD",
        "domain": "battery",
        "x_axis_anchors": [{"pixel": 40, "value": 0}, {"pixel": 260, "value": 100}],
        "y_axis_anchors": [{"pixel": 170, "value": 0}, {"pixel": 30, "value": 5}],
    }
    record = _extract_panel(
        image_path, "paper-auto", "Figure2", "a",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery"},
        {"figures": {"Figure2": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), None,
    )[0]
    assert not record.points
    assert record.extraction_status == "NEEDS_REVIEW"
    assert record.metadata["color_detection"]["reason"] == "MULTIPLE_CHROMATIC_FAMILIES"


def test_process_paper_pdf_crop_transform_uses_current_page_rotation_and_vector_pixels(
    tmp_path: Path, monkeypatch
):
    from contextlib import contextmanager
    from PIL import Image
    import scientific_figure_data.pipeline as pipeline

    input_root = tmp_path / "input"
    paper = input_root / "paper-pdf"
    paper.mkdir(parents=True)
    (paper / "article.pdf").write_bytes(b"%PDF-fake-for-backend-adapter")
    (paper / "figure_inventory.json").write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "page": 1,
            "caption": "Cyclic voltammetry",
            "bbox": [0, 0, 1, 1],
            "panels": [{"panel_id": "a", "technique": "CV", "domain": "battery",
                        "bbox": [0, 0, 1, 1]}],
        }]
    }), encoding="utf-8")
    points_pdf = [
        (10, 20), (20, 30), (30, 40), (40, 45),
        (50, 50), (60, 55), (70, 60), (80, 70),
    ]
    native_page = {
        "backend": "pypdfium2", "native_text": "", "object_inventory_status": "OK",
        "object_count": 1, "object_type_counts": {"PATH": 1},
        "objects": [_vector_path_object(7, points_pdf)],
    }

    class FakePage:
        size = (100.0, 100.0)
        rotation_degrees = 0

        def inspect_native_objects(self, **kwargs):
            return native_page

        def render(self, scale=1.5):
            return Image.new("RGB", (round(100 * scale), round(100 * scale)), "white")

    class FakeDocument:
        def __len__(self):
            return 1

        @contextmanager
        def page(self, number):
            assert number == 1
            yield FakePage()

    class FakeBackend:
        @contextmanager
        def open(self, path):
            assert path.name == "article.pdf"
            yield FakeDocument()

    monkeypatch.setattr(pipeline, "PdfiumBackend", FakeBackend)
    output_root = tmp_path / "output"
    definition = {
        "series_id": "pdf-vector-curve",
        "technique": "CV", "domain": "battery", "data_family": "CV",
        "plot_bbox_pdf": [0, 0, 100, 100],
        "vector_object_indices": [7],
        "x_axis_anchors": [{"pixel": 15, "value": -1}, {"pixel": 120, "value": 1}],
        "y_axis_anchors": [{"pixel": 120, "value": -10}, {"pixel": 45, "value": 10}],
        "x_unit": "s", "y_unit": "mA cm-2",
        "standardization": {"x_target_unit": "min"},
    }
    override = {"figures": {"Figure1": {"panels": {"a": {"series": [definition]}}}}}
    override_path = paper / "digitization_overrides.json"
    override_path.write_text(json.dumps(override), encoding="utf-8")

    result = pipeline.process_paper(input_root, Path("paper-pdf"), output_root)
    assert result["status"] == "COMPLETED_WITH_REVIEW"
    assert result["series_count"] == 1
    record = result["series"][0]
    assert record["extraction_method"] == "PDFIUM_NATIVE_VECTOR_POLYLINE"
    assert record["metadata"]["standardization"] == {
        "status": "REQUESTED", "x_target_unit": "min", "y_target_unit": None,
    }
    mapping = record["metadata"]["crop_mapping"]
    assert mapping["page_rotation_degrees"] == 0
    assert mapping["render_scale"] == pytest.approx(1.5)
    assert mapping["crop_left_pdf"] == pytest.approx(0)
    assert mapping["crop_top_pdf"] == pytest.approx(100)
    native_artifact = output_root / "papers" / "paper-pdf" / "evidence" / "page_0001_native.json"
    assert native_artifact.is_file()
    panel_image = output_root / "papers" / "paper-pdf" / "evidence" / "Figure1_a.png"
    assert panel_image.is_file()
    assert (output_root / "papers" / "paper-pdf" / "series" /
            "Figure1__a" / "panel_series.csv").is_file()


def test_same_color_disconnected_paths_are_kept_as_separate_series(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.raster import (
        detect_monotonic_color_branches, trace_monotonic_color,
    )

    image = Image.new("RGB", (120, 70), "white")
    draw = ImageDraw.Draw(image)
    draw.line((5, 15, 115, 15), fill=(200, 30, 40), width=2)
    draw.line((5, 48, 115, 48), fill=(200, 30, 40), width=2)
    image_path = tmp_path / "same-color-two-curves.png"
    image.save(image_path)

    detected = detect_monotonic_color_branches(
        str(image_path), (200, 30, 40), 5, plot_box=(0, 0, 120, 70)
    )
    assert detected["status"] == "MULTIPLE_MONOTONIC_COLOR_BRANCHES", detected
    assert detected["branch_count"] == 2, detected
    for branch_index, expected_y in enumerate((15, 48)):
        points, qc = trace_monotonic_color(
            str(image_path), (200, 30, 40), 5, None, None,
            plot_box=(0, 0, 120, 70), branch_index=branch_index, branch_count=2,
        )
        assert qc["status"] == "EXTRACTED_PROVISIONAL", qc
        assert len(points) >= 100
        assert all(abs(point.pixel_y - expected_y) <= 1 for point in points)
        assert all(
            right.pixel_x >= left.pixel_x - 1
            for left, right in zip(points, points[1:])
        )


def test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations(
    tmp_path: Path,
):
    from PIL import Image, ImageDraw
    from scientific_figure_data.raster import (
        detect_monotonic_color_branches, trace_monotonic_color,
    )

    color = (210, 25, 35)
    image = Image.new("RGB", (190, 110), "white")
    draw = ImageDraw.Draw(image)
    waveform = [
        (10, 25), (42, 25), (42, 76), (76, 76), (76, 25),
        (110, 25), (110, 76), (144, 76), (144, 25), (180, 25),
    ]
    draw.line(waveform, fill=color, width=3)
    # A closed callout box and short dashed annotation marks share the curve hue.
    draw.rectangle((82, 8, 126, 18), outline=color, width=2)
    for x in range(84, 124, 8):
        draw.line((x, 4, min(x + 3, 124), 4), fill=color, width=2)
    image_path = tmp_path / "waveform-with-callout.png"
    image.save(image_path)

    detected = detect_monotonic_color_branches(
        str(image_path), color, 6, plot_box=(4, 2, 186, 84)
    )
    assert detected["status"] == "SINGLE_MONOTONIC_COLOR_BAND", detected
    assert detected["branch_count"] == 1, detected
    points, qc = trace_monotonic_color(
        str(image_path), color, 6, None, None, plot_box=(4, 2, 186, 84)
    )
    assert qc["status"] == "EXTRACTED_PROVISIONAL", qc
    assert len(points) > 150
    assert min(point.pixel_y for point in points) <= 26
    assert max(point.pixel_y for point in points) >= 75
    assert any(
        max(point.pixel_x for point in points[index:index + 16])
        - min(point.pixel_x for point in points[index:index + 16]) <= 1
        and max(point.pixel_y for point in points[index:index + 16])
        - min(point.pixel_y for point in points[index:index + 16]) >= 10
        for index in range(max(0, len(points) - 15))
    )
    assert not any(8 <= point.pixel_y <= 18 for point in points)


def test_2d_path_tracer_separates_same_color_crossing_into_two_paths(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.raster import (
        detect_monotonic_color_branches, trace_monotonic_color,
    )

    color = (205, 25, 35)
    image = Image.new("RGB", (120, 90), "white")
    draw = ImageDraw.Draw(image)
    draw.line((8, 12, 110, 76), fill=color, width=3)
    draw.line((8, 76, 110, 12), fill=color, width=3)
    image_path = tmp_path / "crossing-same-color-paths.png"
    image.save(image_path)

    detected = detect_monotonic_color_branches(
        str(image_path), color, 6, plot_box=(2, 2, 116, 86)
    )
    assert detected["status"] == "MULTIPLE_MONOTONIC_COLOR_BRANCHES", detected
    assert detected["branch_count"] == 2, detected
    slopes = []
    for branch_index in range(2):
        points, qc = trace_monotonic_color(
            str(image_path), color, 6, None, None,
            plot_box=(2, 2, 116, 86), branch_index=branch_index, branch_count=2,
        )
        assert qc["status"] == "EXTRACTED_PROVISIONAL", qc
        assert len(points) >= 80
        assert all(
            right.pixel_x >= left.pixel_x - 1
            for left, right in zip(points, points[1:])
        )
        slopes.append(points[-1].pixel_y - points[0].pixel_y)
    assert slopes[0] * slopes[1] < 0, slopes


def test_2d_path_tracer_rejects_ambiguous_three_way_junction(tmp_path: Path):
    from PIL import Image, ImageDraw
    from scientific_figure_data.raster import trace_monotonic_color

    color = (205, 25, 35)
    image = Image.new("RGB", (120, 110), "white")
    draw = ImageDraw.Draw(image)
    center = (60, 48)
    draw.line((center[0], center[1], 15, 22), fill=color, width=3)
    draw.line((center[0], center[1], 105, 22), fill=color, width=3)
    draw.line((center[0], center[1], 60, 100), fill=color, width=3)
    image_path = tmp_path / "ambiguous-same-color-junction.png"
    image.save(image_path)

    points, qc = trace_monotonic_color(
        str(image_path), color, 6, None, None, plot_box=(2, 2, 116, 106)
    )
    assert points == [], qc
    assert qc["status"] == "NEEDS_REVIEW"
    rejected = qc["component_detection"]["rejected_components"]
    assert rejected
    assert any(
        item.get("rejection_reason") == "AMBIGUOUS_JUNCTION_CONTINUATION"
        for item in rejected
    )


def test_cli_resume_processes_first_time_then_skips_unchanged_and_reprocesses_changed(
    tmp_path: Path, capsys
):
    from scientific_figure_data.cli import main

    input_root = tmp_path / "chem-literature"
    paper = input_root / "nested" / "paper-001"
    paper.mkdir(parents=True)
    inventory = paper / "figure_inventory.json"
    inventory.write_text('{"figures":[]}', encoding="utf-8")
    output_root = tmp_path / "output"

    # First --resume with no prior catalog is an initial corpus run.
    assert main([
        "run", "--resume", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["completed_with_review"] == 1
    assert first["papers_seen"] == 1
    assert first["resume_cached_skipped"] == 0

    # An unchanged completed paper is excluded before a worker is started.
    assert main([
        "run", "--resume", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["completed"] == 0
    assert second["completed_with_review"] == 0
    assert second["resume_cached_skipped"] == 1
    assert second["papers_seen"] == 1

    # Any changed upstream artifact invalidates that paper's stage fingerprint.
    analysis = paper / "main_analysis.md"
    analysis.write_text("A newly extracted MAIN/SI context line.\n", encoding="utf-8")
    assert main([
        "run", "--resume", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 0
    third = json.loads(capsys.readouterr().out)
    assert third["completed_with_review"] == 1
    assert third["resume_cached_skipped"] == 0
    assert third["papers_seen"] == 1


def test_cli_resume_reprocesses_a_corrupted_bundle_artifact(tmp_path: Path, capsys):
    from scientific_figure_data.cli import main

    input_root = tmp_path / "input"
    paper = input_root / "paper-corrupt"
    paper.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "panels": [{"panel_id": "a", "technique": "GCD", "domain": "battery"}],
        }]
    }), encoding="utf-8")
    output_root = tmp_path / "output"
    assert main([
        "run", "--all", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 0
    capsys.readouterr()

    canonical_file = output_root / "papers" / "paper-corrupt" / "figure_inventory.json"
    original_canonical = canonical_file.read_text(encoding="utf-8")
    canonical_file.write_text(original_canonical + "\n", encoding="utf-8")
    assert main([
        "run", "--resume", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["completed_with_review"] == 1
    assert resumed["resume_cached_skipped"] == 0


def test_reviewed_bundle_integrity_failure_blocks_and_force_recompute_creates_version(
    tmp_path: Path
):
    from scientific_figure_data.pipeline import process_paper

    snapshot, paper_root = make_output_with_series(tmp_path)
    input_root = tmp_path / "input"
    source_paper = input_root / snapshot.paper_id
    source_paper.mkdir(parents=True)
    (source_paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")

    digitization_path = paper_root / "digitization.json"
    digitization = json.loads(digitization_path.read_text(encoding="utf-8"))
    digitization["series"][0]["review_state"] = "REVIEWED_ACCEPTED"
    digitization["series"][0]["extraction_status"] = "REVIEWED_ACCEPTED"
    digitization_path.write_text(json.dumps(digitization, ensure_ascii=False, indent=2), encoding="utf-8")

    bundle_path = paper_root / "paper_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["content_hashes"]["digitization.json"] = sha256_file(digitization_path)
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    panel_csv = paper_root / "series" / "Figure1__a" / "panel_series.csv"
    panel_csv.write_text("tampered point data\n", encoding="utf-8")
    accepted_digitization_hash = sha256_file(digitization_path)
    corrupted_csv_hash = sha256_file(panel_csv)

    blocked = process_paper(input_root, Path(snapshot.paper_id), tmp_path)
    assert blocked["job_state"] == "BLOCKED"
    assert blocked["reason"] == "REVIEWED_ARTIFACT_INTEGRITY_FAILURE"
    assert sha256_file(digitization_path) == accepted_digitization_hash
    assert sha256_file(panel_csv) == corrupted_csv_hash

    forced = process_paper(
        input_root, Path(snapshot.paper_id), tmp_path,
        options={"force_recompute_reviewed": True},
    )
    assert forced["cached"] is False
    backups = list((paper_root / "versions").glob("pre-recompute-*"))
    assert backups
    assert any((backup / "digitization.json").is_file() for backup in backups)


def test_processing_stage_fingerprint_includes_algorithm_profile_and_options(
    tmp_path: Path, monkeypatch
):
    import scientific_figure_data.pipeline as pipeline

    snapshot = make_snapshot()
    paper_dir = tmp_path / "input" / "paper-1"
    paper_dir.mkdir(parents=True)
    output_root = tmp_path / "output"
    monkeypatch.setattr(pipeline, "algorithm_implementation_fingerprint", lambda: "algorithm-A")
    monkeypatch.setattr(pipeline, "profile_registry_fingerprint", lambda: "profile-A")
    base = pipeline.processing_stage_state(snapshot, paper_dir, output_root, {"ocr": False})

    monkeypatch.setattr(pipeline, "algorithm_implementation_fingerprint", lambda: "algorithm-B")
    changed_algorithm = pipeline.processing_stage_state(snapshot, paper_dir, output_root, {"ocr": False})
    assert changed_algorithm["stage_fingerprint"] != base["stage_fingerprint"]

    monkeypatch.setattr(pipeline, "algorithm_implementation_fingerprint", lambda: "algorithm-A")
    monkeypatch.setattr(pipeline, "profile_registry_fingerprint", lambda: "profile-B")
    changed_profile = pipeline.processing_stage_state(snapshot, paper_dir, output_root, {"ocr": False})
    assert changed_profile["stage_fingerprint"] != base["stage_fingerprint"]

    monkeypatch.setattr(pipeline, "profile_registry_fingerprint", lambda: "profile-A")
    changed_options = pipeline.processing_stage_state(snapshot, paper_dir, output_root, {
        "ocr": True, "render_scale": 2.0,
    })
    assert changed_options["stage_fingerprint"] != base["stage_fingerprint"]


def test_bundle_integrity_check_detects_manifested_file_tampering(tmp_path: Path):
    from scientific_figure_data.pipeline import bundle_is_intact

    snapshot, paper_root = make_output_with_series(tmp_path)
    assert bundle_is_intact(paper_root) is True
    panel_csv = paper_root / "series" / "Figure1__a" / "panel_series.csv"
    original = panel_csv.read_text(encoding="utf-8")
    panel_csv.write_text(original + "tampered\n", encoding="utf-8")
    assert bundle_is_intact(paper_root) is False


def test_cli_resume_does_not_take_over_active_running_job(tmp_path: Path, capsys):
    from scientific_figure_data.cli import main
    from scientific_figure_data.scheduler import JobLedger

    input_root = tmp_path / "input"
    paper = input_root / "paper-active"
    paper.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    output_root = tmp_path / "output"
    ledger = JobLedger(output_root / "catalog.sqlite", lease_seconds=900)
    ledger.prepare("paper-active")
    ledger.start("paper-active")
    ledger.close()

    assert main([
        "run", "--resume", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["active_jobs_skipped"] == 1
    assert report["completed"] == 0
    ledger = JobLedger(output_root / "catalog.sqlite")
    state = ledger.con.execute(
        "SELECT state FROM jobs WHERE paper_id='paper-active'"
    ).fetchone()["state"]
    assert state == "RUNNING"
    ledger.close()


def test_reviewed_result_with_tampered_bundle_is_blocked_without_file_mutation(tmp_path: Path):
    from scientific_figure_data.pipeline import process_paper

    snapshot, paper_root = make_output_with_series(tmp_path)
    input_root = tmp_path / "input"
    source = input_root / snapshot.paper_id
    source.mkdir(parents=True)
    (source / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    digitization_path = paper_root / "digitization.json"
    digitization = json.loads(digitization_path.read_text(encoding="utf-8"))
    digitization["series"][0]["review_state"] = "REVIEWED_ACCEPTED"
    digitization_path.write_text(json.dumps(digitization, indent=2), encoding="utf-8")

    bundle_path = paper_root / "paper_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["content_hashes"]["digitization.json"] = sha256_file(digitization_path)
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    csv_path = paper_root / "series" / "Figure1__a" / "panel_series.csv"
    csv_path.write_text(csv_path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    digitization_hash = sha256_file(digitization_path)
    csv_hash = sha256_file(csv_path)

    result = process_paper(input_root, Path(snapshot.paper_id), tmp_path)
    assert result["job_state"] == "BLOCKED"
    assert result["reason"] == "REVIEWED_ARTIFACT_INTEGRITY_FAILURE"
    assert sha256_file(digitization_path) == digitization_hash
    assert sha256_file(csv_path) == csv_hash


def test_adapter_recognizes_nested_manifest_only_paper_without_pdf(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers

    root = tmp_path / "corpus"
    root.mkdir()
    (root / "manifest.json").write_text('{"corpus":true}', encoding="utf-8")
    first = root / "paper-a"
    first.mkdir()
    (first / "manifest.json").write_text('{"upstream_version":"chem-literature-1"}', encoding="utf-8")
    second = root / "paper-b"
    second.mkdir()
    (second / "evidence_index.json").write_text('{"items":[]}', encoding="utf-8")
    assert list(discover_papers(root)) == [first, second]


def _make_vector_test_image(tmp_path: Path, name: str = "hybrid.png"):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 90, 90), outline=(15, 15, 15), width=2)
    draw.line((15, 80, 25, 72, 35, 64, 45, 56, 55, 48, 65, 40, 75, 32, 85, 20),
              fill=(220, 20, 30), width=2)
    path = tmp_path / name
    image.save(path)
    return path


def _make_vector_test_native(tmp_path: Path, include_second: bool = False):
    points = [(15, 20), (25, 28), (35, 36), (45, 44),
              (55, 52), (65, 60), (75, 68), (85, 80)]
    objects = [_vector_path_object(101, points, color=(220, 20, 30, 255))]
    if include_second:
        other = [(15, 70), (25, 65), (35, 60), (45, 55),
                 (55, 50), (65, 45), (75, 40), (85, 30)]
        objects.append(_vector_path_object(102, other, color=(20, 80, 210, 255)))
    path = tmp_path / ("native-multi.json" if include_second else "native-single.json")
    path.write_text(json.dumps({"objects": objects}), encoding="utf-8")
    return path


def test_hybrid_pipeline_prioritizes_native_vector_even_when_raster_color_is_detected(tmp_path: Path):
    from scientific_figure_data.pipeline import _extract_panel

    image_path = _make_vector_test_image(tmp_path)
    native_path = _make_vector_test_native(tmp_path)

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "hybrid-native",
        "technique": "GCD", "domain": "battery", "data_family": "TIME_SERIES",
        "x_axis_anchors": [{"pixel": 15, "value": 0}, {"pixel": 85, "value": 10}],
        "y_axis_anchors": [{"pixel": 80, "value": 0}, {"pixel": 20, "value": 5}],
    }
    record = _extract_panel(
        image_path, "p", "Figure1", "a",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery"},
        {"figures": {"Figure1": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), 1,
        {"native_text_preview": ""},
        [], "a" * 64, "b" * 64,
        native_path,
        {"crop_left_pdf": 0, "crop_top_pdf": 100, "render_scale": 1,
         "page_rotation_degrees": 0},
    )[0]
    assert record.extraction_method == "PDFIUM_NATIVE_VECTOR_POLYLINE"
    assert record.metadata["vector_object_index"] == 101
    assert record.metadata["color_detection"]["status"] == "UNIQUE_CHROMATIC_FAMILY"
    assert len(record.points) == 8


def test_hybrid_pipeline_falls_back_to_unique_raster_when_vector_candidates_are_ambiguous(
    tmp_path: Path
):
    from scientific_figure_data.pipeline import _extract_panel

    image_path = _make_vector_test_image(tmp_path, "hybrid-fallback.png")
    native_path = _make_vector_test_native(tmp_path, include_second=True)

    class EmptyContext:
        def search(self, kind, text=""):
            return []

    definition = {
        "series_id": "hybrid-raster-fallback",
        "technique": "GCD", "domain": "battery", "data_family": "TIME_SERIES",
        "x_axis_anchors": [{"pixel": 15, "value": 0}, {"pixel": 85, "value": 10}],
        "y_axis_anchors": [{"pixel": 80, "value": 0}, {"pixel": 20, "value": 5}],
    }
    record = _extract_panel(
        image_path, "p", "Figure2", "a",
        {"technique": "GCD", "domain": "battery"},
        {"technique": "GCD", "domain": "battery"},
        {"figures": {"Figure2": {"panels": {"a": {"series": [definition]}}}}},
        EmptyContext(), 1,
        {"native_text_preview": ""},
        [], "c" * 64, "d" * 64,
        native_path,
        {"crop_left_pdf": 0, "crop_top_pdf": 100, "render_scale": 1,
         "page_rotation_degrees": 0},
    )[0]
    assert record.extraction_method == "raster_color_connected_path"
    assert record.metadata["vector_fallback"] == "UNIQUE_RASTER_COLOR_FAMILY_AVAILABLE"
    assert record.metadata["vector_selection"]["reason"] == "MULTIPLE_VECTOR_CANDIDATES"
    assert len(record.points) > 0


def test_scheduler_recovers_broken_worker_and_retries_paper(monkeypatch, tmp_path: Path):
    from concurrent.futures import Future
    from concurrent.futures.process import BrokenProcessPool

    import scientific_figure_data.scheduler as scheduler
    from scientific_figure_data.models import JobState

    input_root = tmp_path / "input"
    paper = input_root / "paper-crash"
    paper.mkdir(parents=True)
    output_root = tmp_path / "output"

    class FakeExecutor:
        created = 0

        def __init__(self, **kwargs):
            self.instance = FakeExecutor.created
            FakeExecutor.created += 1

        def submit(self, *args, **kwargs):
            future = Future()
            if self.instance == 0:
                future.set_exception(BrokenProcessPool("injected worker crash"))
            else:
                future.set_result({"job_state": JobState.BLOCKED.value})
            return future

        def shutdown(self, wait=True, cancel_futures=False):
            return None

    monkeypatch.setattr(scheduler, "ProcessPoolExecutor", FakeExecutor)
    report = scheduler.run_corpus(
        input_root, output_root, [paper], workers=1, max_attempts=2,
        lease_seconds=30, options={"memory_limit_mb": 0},
    )

    assert report["retried"] == 1
    assert report["blocked_review_locked"] == 1
    assert report["failed"] == 0
    ledger = scheduler.JobLedger(output_root / "catalog.sqlite")
    row = ledger.con.execute(
        "SELECT state,attempt_count FROM jobs WHERE paper_id='paper-crash'"
    ).fetchone()
    assert row["state"] == JobState.BLOCKED.value
    assert row["attempt_count"] == 2
    event_types = [
        row["event_type"] for row in ledger.con.execute(
            "SELECT event_type FROM job_events WHERE paper_id='paper-crash' ORDER BY event_id"
        )
    ]
    assert "RETRY_WAIT" in event_types
    assert JobState.BLOCKED.value in event_types
    ledger.close()


def test_scheduler_stops_after_broken_worker_retry_exhaustion(monkeypatch, tmp_path: Path):
    from concurrent.futures import Future
    from concurrent.futures.process import BrokenProcessPool

    import scientific_figure_data.scheduler as scheduler
    from scientific_figure_data.models import JobState

    input_root = tmp_path / "input"
    paper = input_root / "paper-permanent"
    paper.mkdir(parents=True)
    output_root = tmp_path / "output"

    class AlwaysBrokenExecutor:
        def __init__(self, **kwargs):
            pass

        def submit(self, *args, **kwargs):
            future = Future()
            future.set_exception(BrokenProcessPool("injected persistent crash"))
            return future

        def shutdown(self, wait=True, cancel_futures=False):
            return None

    monkeypatch.setattr(scheduler, "ProcessPoolExecutor", AlwaysBrokenExecutor)
    report = scheduler.run_corpus(
        input_root, output_root, [paper], workers=1, max_attempts=2,
        lease_seconds=30, options={"memory_limit_mb": 0},
    )

    assert report["retried"] == 1
    assert report["failed"] == 1
    ledger = scheduler.JobLedger(output_root / "catalog.sqlite")
    row = ledger.con.execute(
        "SELECT state,attempt_count,last_error FROM jobs WHERE paper_id='paper-permanent'"
    ).fetchone()
    assert row["state"] == JobState.FAILED_PERMANENT.value
    assert row["attempt_count"] == 2
    assert "BrokenProcessPool" in row["last_error"]
    ledger.close()


def test_review_patch_rolls_back_files_when_catalog_transaction_fails(tmp_path: Path):
    import sqlite3

    snapshot, paper_root = make_output_with_series(tmp_path)
    digitization = paper_root / "digitization.json"
    panel_csv = paper_root / "series" / "Figure1__a" / "panel_series.csv"
    bundle = paper_root / "paper_bundle.json"
    before_hashes = {
        "digitization": sha256_file(digitization),
        "panel_csv": sha256_file(panel_csv),
        "bundle": sha256_file(bundle),
        "panel_layout": sha256_file(paper_root / "panel_layout.json"),
    }

    patch_path = tmp_path / "rollback.json"
    patch_path.write_text(json.dumps({
        "schema_version": "1.0",
        "patch_id": "rollback-injected",
        "paper_id": snapshot.paper_id,
        "target_artifact": "digitization.json",
        "original_result_hash": before_hashes["digitization"],
        "reviewer": "fault-injection-test",
        "changes": [{
            "series_id": "series-a",
            "set": {
                "label": "Must roll back",
                "chart_family": "SPECTRUM",
                "classification_evidence": "Injected transaction failure after classification revision.",
                "points": [{
                    "point_index": 0, "x": 9.0, "y": 8.0,
                    "pixel_x": 10.0, "pixel_y": 20.0,
                }],
            },
        }],
    }), encoding="utf-8")

    connection = connect_catalog(tmp_path / "catalog.sqlite")
    connection.execute(
        """CREATE TRIGGER fail_review_commit BEFORE INSERT ON applied_patches
           BEGIN SELECT RAISE(ABORT, 'injected catalog failure'); END"""
    )
    connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="injected catalog failure"):
        apply_review_patch(tmp_path, patch_path)

    assert sha256_file(digitization) == before_hashes["digitization"]
    assert sha256_file(panel_csv) == before_hashes["panel_csv"]
    assert sha256_file(bundle) == before_hashes["bundle"]
    assert sha256_file(paper_root / "panel_layout.json") == before_hashes["panel_layout"]

    catalog = Catalog(tmp_path / "catalog.sqlite")
    row = catalog.query_series({"paper_id": snapshot.paper_id})[0]
    assert row["label"] == "series-a"
    assert row["review_state"] == "NEEDS_REVIEW"
    assert catalog.con.execute(
        "SELECT COUNT(*) FROM applied_patches WHERE patch_id='rollback-injected'"
    ).fetchone()[0] == 0
    catalog.close()



def test_scheduler_pauses_dispatch_when_free_disk_is_low(monkeypatch, tmp_path: Path):
    import scientific_figure_data.scheduler as scheduler

    input_root = tmp_path / "input"
    paper = input_root / "paper-waiting"
    paper.mkdir(parents=True)
    output_root = tmp_path / "output"

    class FakeUsage:
        total = 1000
        used = 990
        free = 10

    class MustNotStartExecutor:
        def __init__(self, **kwargs):
            pass

        def submit(self, *args, **kwargs):
            raise AssertionError("No worker may start below the configured disk threshold")

        def shutdown(self, wait=True, cancel_futures=False):
            return None

    monkeypatch.setattr(scheduler, "ProcessPoolExecutor", MustNotStartExecutor)
    monkeypatch.setattr(scheduler.shutil, "disk_usage", lambda path: FakeUsage())
    report = scheduler.run_corpus(
        input_root, output_root, [paper], workers=1, max_attempts=1,
        lease_seconds=30, options={"min_free_disk_mb": 1},
    )

    assert report["paused_for_resource_pressure"] is True
    assert report["resource_pressure_reason"] == "FREE_DISK_BELOW_1_MB"
    assert report["minimum_free_disk_bytes_observed"] == 10
    assert report["failed"] == 0
    assert report["papers_seen"] == 0



def test_process_paper_preserves_all_upstream_paths_and_hashes(tmp_path: Path):
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "upstream"
    paper = input_root / "paper-immutable"
    tables = paper / "extracted_tables"
    tables.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "panels": [{"panel_id": "a", "technique": "CV", "domain": "battery"}],
        }]
    }), encoding="utf-8")
    (paper / "main_analysis.md").write_text("Existing upstream context.\n", encoding="utf-8")
    (tables / "table_1.csv").write_text("sample,value\nA,1\n", encoding="utf-8")

    def tree_snapshot():
        paths = {
            item.relative_to(input_root).as_posix()
            for item in input_root.rglob("*")
        }
        hashes = {
            item.relative_to(input_root).as_posix(): sha256_file(item)
            for item in input_root.rglob("*") if item.is_file()
        }
        return paths, hashes

    before_paths, before_hashes = tree_snapshot()
    process_paper(input_root, Path("paper-immutable"), tmp_path / "downstream")
    after_paths, after_hashes = tree_snapshot()

    assert after_paths == before_paths
    assert after_hashes == before_hashes



def test_context_index_reuses_unchanged_cache_and_invalidates_changed_sources(tmp_path: Path):
    from scientific_figure_data.context_index import PaperContextIndex

    paper = tmp_path / "paper"
    paper.mkdir()
    source = paper / "main_analysis.md"
    source.write_text("Sample-A is tested against Ag/AgCl.\n", encoding="utf-8")
    output = tmp_path / "output" / "context"

    first = PaperContextIndex.build(paper, output, memory_budget_bytes=1)
    assert first.db_path is not None
    first_db_hash = sha256_file(first.db_path)
    first_fingerprint = first.fingerprint

    second = PaperContextIndex.build(paper, output, memory_budget_bytes=1)
    assert second.fingerprint == first_fingerprint
    assert second.db_path == first.db_path
    assert sha256_file(second.db_path) == first_db_hash
    assert second.search("sample_alias", "Sample-A")

    source.write_text("Sample-A is tested against Ag/AgCl.\nSample-B is used as control.\n",
                      encoding="utf-8")
    third = PaperContextIndex.build(paper, output, memory_budget_bytes=1)
    assert third.fingerprint != first_fingerprint
    assert third.search("sample_alias", "Sample-B")



def test_same_figure_series_link_to_distinct_subjects_and_query_shared_sample_techniques(tmp_path: Path):
    snapshot = make_snapshot("paper-shared-samples")
    xrd_sample_a = make_series("xrd-sample-a", "measurement-xrd-a", "temperature")
    xrd_sample_a.technique = "XRD"
    cv_sample_a = make_series("cv-sample-a", "measurement-cv-a", "scan rate")
    cv_sample_a.technique = "CV"
    cv_sample_b = make_series("cv-sample-b", "measurement-cv-b", "scan rate")
    cv_sample_b.technique = "CV"
    for item in (xrd_sample_a, cv_sample_a, cv_sample_b):
        item.paper_id = snapshot.paper_id

    sample_a_link = {
        "entity_id": "sample-a",
        "canonical_name": "Sample A",
        "entity_type": "material",
        "aliases": ["SA"],
        "role_in_series": "measured_sample",
        "status": "ASSIGNED_WITH_EVIDENCE",
        "evidence": {"source": "figure legend", "page": 2, "text": "Sample A"},
    }
    sample_b_link = {
        "entity_id": "sample-b",
        "canonical_name": "Sample B",
        "entity_type": "material",
        "aliases": ["SB"],
        "role_in_series": "measured_sample",
        "status": "ASSIGNED_WITH_EVIDENCE",
        "evidence": {"source": "figure legend", "page": 2, "text": "Sample B"},
    }
    xrd_sample_a.subject_links = [sample_a_link]
    cv_sample_a.subject_links = [sample_a_link]
    cv_sample_b.subject_links = [sample_b_link]

    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.index_paper(
        snapshot,
        [{"figure_id": "Figure1", "page": 2, "caption": "XRD and CV of two samples"}],
        [{"figure_id": "Figure1", "panel_id": "a", "bbox": [0, 0, 1, 1]}],
        [xrd_sample_a, cv_sample_a, cv_sample_b],
        "COMPLETED_WITH_REVIEW",
    )

    sample_a = catalog.query_series({"entity": "SA"})
    assert {(row["series_id"], row["technique"]) for row in sample_a} == {
        ("xrd-sample-a", "XRD"), ("cv-sample-a", "CV")
    }
    sample_b = catalog.query_series({"entity": "SB"})
    assert {(row["series_id"], row["technique"]) for row in sample_b} == {
        ("cv-sample-b", "CV")
    }

    associations_a = catalog.series_associations("xrd-sample-a")
    associations_b = catalog.series_associations("cv-sample-b")
    assert associations_a["subject_links"][0]["entity_id"] == "paper-shared-samples__sample-a"
    assert associations_b["subject_links"][0]["entity_id"] == "paper-shared-samples__sample-b"
    assert associations_a["subject_links"][0]["identity_scope"] == "PAPER"
    assert associations_a["subject_links"][0]["evidence_json"] != associations_b["subject_links"][0]["evidence_json"]
    catalog.close()



def test_run_report_distinguishes_selected_cached_and_filtered_papers(tmp_path: Path):
    from scientific_figure_data.scheduler import run_corpus

    input_root = tmp_path / "input"
    papers = [input_root / f"paper-{index}" for index in range(2)]
    for paper in papers:
        paper.mkdir(parents=True)
    output_root = tmp_path / "output"

    report = run_corpus(
        input_root, output_root, iter(papers), workers=1, max_attempts=1,
        lease_seconds=30,
        options={
            "memory_limit_mb": 0,
            "discovered_papers": 5,
            "eligible_papers": 2,
            "skipped_by_selection": 3,
            "resume_cached_skipped": 0,
        },
    )

    assert report["discovered_papers"] == 5
    assert report["eligible_papers"] == 2
    assert report["skipped_by_selection"] == 3
    assert report["skipped_cached_unchanged"] == 0
    assert report["skipped_papers"] == 3
    assert report["algorithm_version"] == "0.6.0"
    assert len(report["algorithm_implementation_fingerprint"]) == 64
    assert len(report["profile_config_fingerprint"]) == 64
    assert len(report["qc_threshold_fingerprint"]) == 64
    assert report["qc_threshold_status"] == "PROVISIONAL_UNCALIBRATED"



def test_scheduler_pauses_dispatch_when_available_memory_is_low(monkeypatch, tmp_path: Path):
    import scientific_figure_data.scheduler as scheduler

    input_root = tmp_path / "input"
    paper = input_root / "paper-memory-pressure"
    paper.mkdir(parents=True)
    output_root = tmp_path / "output"

    class MustNotStartExecutor:
        def __init__(self, **kwargs):
            pass

        def submit(self, *args, **kwargs):
            raise AssertionError("No worker may start below the configured memory threshold")

        def shutdown(self, wait=True, cancel_futures=False):
            return None

    monkeypatch.setattr(scheduler, "ProcessPoolExecutor", MustNotStartExecutor)
    monkeypatch.setattr(scheduler, "_free_memory_bytes", lambda: 10)
    monkeypatch.setattr(scheduler, "_free_disk_bytes", lambda path: 10**12)
    report = scheduler.run_corpus(
        input_root, output_root, [paper], workers=1, max_attempts=1,
        lease_seconds=30,
        options={"min_free_memory_mb": 1, "min_free_disk_mb": 0},
    )

    assert report["paused_for_resource_pressure"] is True
    assert report["resource_pressure_reason"] == "FREE_MEMORY_BELOW_1_MB"
    assert report["minimum_free_memory_bytes_observed"] == 10
    assert report["failed"] == 0
    assert report["papers_seen"] == 0



def test_adapter_rejects_paper_id_normalization_collisions(tmp_path: Path):
    from scientific_figure_data.adapter import ensure_unique_paper_ids

    nested = tmp_path / "nested" / "paper"
    literal = tmp_path / "nested__paper"
    for paper in (nested, literal):
        paper.mkdir(parents=True)
        (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="Paper ID normalization collision"):
        list(ensure_unique_paper_ids(discover_papers(tmp_path), tmp_path))



def test_root_paper_job_and_artifact_ids_match(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers
    from scientific_figure_data.scheduler import JobLedger, run_corpus

    input_root = tmp_path / "input"
    input_root.mkdir()
    (input_root / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    output_root = tmp_path / "output"

    report = run_corpus(
        input_root, output_root, discover_papers(input_root), workers=1,
        max_attempts=1, lease_seconds=30, options={"memory_limit_mb": 0},
    )

    job = JobLedger(output_root / "catalog.sqlite")
    row = job.con.execute("SELECT paper_id,state,input_fingerprint,worker_id,started_at,worker_pid FROM jobs").fetchone()
    assert row["paper_id"] == "root-paper"
    assert row["state"] == "NEEDS_REVIEW"
    assert row["input_fingerprint"]
    assert row["worker_id"].startswith("pool-")
    assert row["started_at"]
    assert isinstance(row["worker_pid"], int)
    assert report["completed_with_review"] == 1
    assert report["completed_papers"] == 0
    assert report["review_required_papers"] == 1
    assert report["permanently_failed_papers"] == 0
    assert report["blocked_review_locked_papers"] == 0
    assert report["retried_papers"] == 0
    assert report["parent_cpu_seconds"] >= 0
    assert report["completed_worker_cpu_seconds"] >= 0
    assert report["combined_cpu_seconds"] >= report["parent_cpu_seconds"]
    assert report["average_cpu_cores"] >= 0
    assert report["total_paper_evidence_bytes"] >= 0
    assert report["total_context_index_bytes"] >= 0
    assert report["peak_budgeted_paper_storage_bytes"] >= 0
    assert report["total_returned_paper_output_bytes"] >= report["peak_single_paper_output_bytes"] >= 0
    assert "not OS temporary-directory peak usage" in report["disk_usage_measurement_scope"]
    assert report["sfd_temp_peak_bytes"] >= 0
    assert report["sfd_temp_bytes_before_cleanup"] >= 0
    assert report["sfd_temp_cleanup_succeeded"] is True
    assert report["sfd_worker_temp_isolation_verified"] is True
    assert report["worker_log_directory"]
    assert Path(report["worker_log_directory"]).is_dir()
    assert report["worker_shutdown"]
    assert all(item["status"] == "WORKERS_REAPED" for item in report["worker_shutdown"])
    assert not (output_root / report["sfd_temp_directory_relative"]).exists()
    paper_root = output_root / "papers" / "root-paper"
    assert (paper_root / "paper_manifest.json").is_file()
    job.close()



def test_snapshot_detects_nested_upstream_version_directly_from_artifact_path(tmp_path: Path):
    paper = tmp_path / "nested" / "paper-versioned"
    manifest_dir = paper / "metadata" / "nested"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text(json.dumps({
        "metadata": {"producer": {"name": "chem-literature", "version": "2.4.1"}}
    }), encoding="utf-8")
    (paper / "other" / "metadata").mkdir(parents=True)
    (paper / "other" / "metadata" / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0"}), encoding="utf-8"
    )
    (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")

    snapshot = snapshot_paper(paper, tmp_path)

    assert snapshot.detected_upstream_version == "chem-literature 2.4.1"
    versioned_artifact = next(
        item for item in snapshot.artifacts
        if item.path.endswith("metadata/nested/manifest.json")
    )
    assert versioned_artifact.role == "evidence_index"



def test_series_ids_are_globally_unique_across_papers_with_same_figure_panel(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers
    from scientific_figure_data.scheduler import run_corpus

    input_root = tmp_path / "corpus"
    for paper_name in ("paper-A", "paper-B"):
        paper = input_root / paper_name
        paper.mkdir(parents=True)
        (paper / "figure_inventory.json").write_text(json.dumps({
            "figures": [{
                "figure_id": "Figure1",
                "panels": [{"panel_id": "a", "technique": "CV", "domain": "battery"}],
            }]
        }), encoding="utf-8")

    output_root = tmp_path / "output"
    report = run_corpus(
        input_root, output_root, discover_papers(input_root), workers=1,
        max_attempts=1, lease_seconds=30, options={"memory_limit_mb": 0},
    )

    catalog = Catalog(output_root / "catalog.sqlite")
    rows = catalog.con.execute(
        "SELECT series_id,paper_id,figure_id,panel_id FROM series ORDER BY paper_id"
    ).fetchall()
    assert len(rows) == 2
    assert len({row["series_id"] for row in rows}) == 2
    assert {row["paper_id"] for row in rows} == {"paper-A", "paper-B"}
    assert all(row["figure_id"] == "Figure1" and row["panel_id"] == "a" for row in rows)
    assert report["failed"] == 0
    assert report["completed_with_review"] == 2
    catalog.close()



@pytest.mark.parametrize("relationship", ["same", "ancestor", "descendant"])
def test_scheduler_rejects_overlapping_input_output_roots(tmp_path: Path, relationship: str):
    from scientific_figure_data.scheduler import run_corpus

    input_root = tmp_path / "source"
    input_root.mkdir()
    source_file = input_root / "figure_inventory.json"
    source_file.write_text('{"figures":[]}', encoding="utf-8")
    source_hash = sha256_file(source_file)

    if relationship == "same":
        output_root = input_root
    elif relationship == "ancestor":
        output_root = tmp_path
    else:
        output_root = input_root / "downstream"

    with pytest.raises(ValueError, match="non-overlapping directory trees"):
        run_corpus(input_root, output_root, [], workers=1)

    assert source_file.is_file()
    assert sha256_file(source_file) == source_hash



def test_series_qc_report_keeps_independent_provisional_dimensions():
    from scientific_figure_data.qc import build_series_qc_report

    series = make_series("qc-series", "qc-measurement", "electrolyte")
    series.points = [
        SeriesPoint(0, 0.0, 0.0, 10.0, 20.0),
        SeriesPoint(1, 1.0, 0.5, 20.0, 15.0),
        SeriesPoint(2, 0.5, 1.0, 15.0, 10.0),
    ]
    series.y_axis_side = "UNASSIGNED"
    series.metadata = {
        "data_family": "CV",
        "x_calibration": {
            "status": "CALIBRATED_NUMERIC", "anchors": [{"pixel": 10, "value": 0}, {"pixel": 20, "value": 1}],
            "rmse": 0.02, "unit": "V",
        },
        "y_calibration": {"status": "SERIES_RELATIVE_SIGNAL", "anchors": [], "rmse": 0.0, "unit": None},
        "raster_qc": {"matched_columns": 20, "matched_pixel_fraction": 0.2, "max_gap_columns": 1},
        "chart_family_classification": {"status": "DETERMINISTIC_PRECLASSIFIED"},
    }
    series.subject_links = [{
        "status": "ASSIGNED_WITH_EVIDENCE", "entity_id": "paper-1__sample-a",
        "evidence": {"source": "figure legend", "page": 2},
    }]
    series.conditions = [{"name": "electrolyte", "value": "1 M"}]

    report = build_series_qc_report(
        series,
        {"bbox": [0.1, 0.1, 0.9, 0.9], "shared_legend_refs": [{"text": "Sample A", "scope": "FIGURE"}]},
        {
            "status": "PROVISIONAL_UNCALIBRATED",
            "minimum_calibration_anchors": 2,
            "minimum_trace_points": 8,
            "minimum_trace_pixel_fraction": 0.15,
        },
    )

    assert report["status"] == "PROVISIONAL_UNCALIBRATED"
    assert report["assessment_mode"] == "INDEPENDENT_DIMENSIONS_NO_AGGREGATE_SCORE"
    assert report["axes"]["x"]["status"] == "CALIBRATION_EVIDENCE_PRESENT"
    assert report["axes"]["y"]["status"] == "RELATIVE_SIGNAL"
    assert report["calibration_state"] == "X_NUMERIC_Y_RELATIVE_SIGNAL"
    assert report["components"]["axis_calibration"] == "X_NUMERIC_Y_RELATIVE_SIGNAL"
    assert report["trace_metrics"]["x_direction_changes"] == 1
    assert report["trace_metrics"]["path_constraint"] == "ORDERED_NON_MONOTONIC_ALLOWED"
    assert report["components"]["subject_link"] == "ASSIGNED_WITH_EVIDENCE"
    assert report["components"]["condition_interpretation"] == "EVIDENCE_ATTACHED"
    assert report["components"]["legend_association"] == "EVIDENCE_ATTACHED"
    assert report["aggregate_score"] is None
    assert report["scientific_acceptance"] == "NOT_ASSESSED_WITHOUT_ANNOTATED_REAL_PAPER_BENCHMARK"



def test_qc_distinguishes_numeric_axis_calibration_from_uncalibrated_thresholds():
    from scientific_figure_data.qc import build_series_qc_report

    series = make_series("numeric-qc", "numeric-measurement", "electrolyte")
    series.metadata = {
        "x_calibration": {
            "status": "CALIBRATED_NUMERIC",
            "anchors": [{"pixel": 0, "value": 0}, {"pixel": 100, "value": 1}],
            "rmse": 0.0, "unit": "V",
        },
        "y_calibration": {
            "status": "CALIBRATED_NUMERIC",
            "anchors": [{"pixel": 100, "value": -1}, {"pixel": 0, "value": 1}],
            "rmse": 0.0, "unit": "A/g",
        },
    }
    report = build_series_qc_report(series, {}, {
        "status": "PROVISIONAL_UNCALIBRATED",
        "minimum_calibration_anchors": 2,
        "minimum_trace_points": 2,
        "minimum_trace_pixel_fraction": 0.0,
    })

    assert report["axes"]["x"]["status"] == "CALIBRATION_EVIDENCE_PRESENT"
    assert report["axes"]["y"]["status"] == "CALIBRATION_EVIDENCE_PRESENT"
    assert report["calibration_state"] == "BOTH_AXES_NUMERICALLY_CALIBRATED"
    assert report["components"]["axis_calibration"] == "BOTH_AXES_NUMERICALLY_CALIBRATED"
    # Axis calibration is not equivalent to benchmark-calibrated scientific QC.
    assert report["status"] == "PROVISIONAL_UNCALIBRATED"


def test_pipeline_persists_qc_dimensions_for_extracted_series(tmp_path: Path):
    from scientific_figure_data.pipeline import process_paper

    input_root = tmp_path / "input"
    paper = input_root / "paper-qc"
    paper.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "page": 1,
            "caption": "CV of Sample A",
            "technique": "CV",
            "domain": "battery",
            "panels": [{
                "panel_id": "a", "technique": "CV", "domain": "battery",
                "bbox": [0.1, 0.1, 0.9, 0.9],
            }],
        }]
    }), encoding="utf-8")
    (paper / "digitization_overrides.json").write_text(json.dumps({
        "schema_version": "1.0",
        "figures": {
            "Figure1": {
                "panels": {
                    "a": {
                        "series": [{
                            "series_id": "sample-a-cv",
                            "label": "Sample A",
                            "technique": "CV",
                            "domain": "battery",
                            "data_family": "CV",
                            "pixel_points": [[10, 20], [20, 10], [15, 5]],
                            "x_axis_anchors": [{"pixel": 10, "value": 0}, {"pixel": 20, "value": 1}],
                            "y_axis_anchors": [{"pixel": 20, "value": 0}, {"pixel": 5, "value": 1}],
                            "x_unit": "V",
                            "y_unit": "mA cm-2",
                            "y_axis_side": "LEFT",
                            "subject_links": [{
                                "entity": {
                                    "entity_id": "sample-a",
                                    "canonical_name": "Sample A",
                                    "entity_type": "material",
                                },
                                "role_in_series": "tested_material",
                                "exact_match": True,
                                "evidence": {"source": "panel legend", "page": 1},
                            }],
                            "conditions": [{
                                "name": "electrolyte", "value": "1 M",
                                "evidence": {"source": "panel caption", "page": 1},
                            }],
                        }]
                    }
                }
            }
        },
    }), encoding="utf-8")

    result = process_paper(input_root, Path("paper-qc"), tmp_path / "output",
                           {"memory_limit_mb": 0})
    assert result["series_count"] == 1
    assert result["series"][0]["metadata"]["points_count"] == 3
    metadata = result["series"][0]["metadata"]
    assert metadata["qc_report"]["status"] == "PROVISIONAL_UNCALIBRATED"
    assert metadata["qc_report"]["aggregate_score"] is None
    assert metadata["qc_report"]["trace_metrics"]["point_count"] == 3
    assert metadata["qc_report"]["trace_metrics"]["x_direction_changes"] == 1
    assert metadata["qc_components"]["subject_link"] == "ASSIGNED_WITH_EVIDENCE"
    assert metadata["qc_components"]["condition_interpretation"] == "EVIDENCE_ATTACHED"



def test_standardize_measurement_value_preserves_original_and_refuses_guesses():
    from scientific_figure_data.semantics import standardize_measurement_value

    converted = standardize_measurement_value(2500, "mg/L", "g/L")
    assert converted["original_value"] == 2500
    assert converted["original_unit"] == "mg/L"
    assert converted["standardized_value"] == 2.5
    assert converted["standardized_unit"] == "g/L"
    assert converted["standardization_status"] == "DETERMINISTIC_DIMENSIONAL_CONVERSION"
    assert converted["method_id"] == "DIMENSIONAL_FACTOR_TABLE_V1"
    assert converted["evidence_id"] == "unit-factor:mg/L->g/L"

    unresolved = standardize_measurement_value(0.25, "V vs Ag/AgCl", "V vs RHE")
    assert unresolved["original_value"] == 0.25
    assert unresolved["standardized_value"] is None
    assert unresolved["standardization_status"] == "UNRESOLVED_UNSUPPORTED_CONVERSION"


def test_new_domain_profile_can_be_added_without_core_engine_changes(tmp_path: Path):
    profile_root = tmp_path / "profiles"
    common = profile_root / "common_chemistry"
    custom = profile_root / "electrocatalysis"
    common.mkdir(parents=True)
    custom.mkdir(parents=True)
    (common / "profile.yaml").write_text(
        "name: common_chemistry\nversion: '1.0'\ninherits: []\ndomain: chemistry\n",
        encoding="utf-8",
    )
    (common / "techniques.yaml").write_text(
        "techniques:\n  XRD: {family: spectrum}\nmetrics:\n  shared: [temperature]\n",
        encoding="utf-8",
    )
    (custom / "profile.yaml").write_text(
        "name: electrocatalysis\nversion: '1.0'\ninherits: [common_chemistry]\ndomain: electrocatalysis\n",
        encoding="utf-8",
    )
    (custom / "techniques.yaml").write_text(
        "techniques:\n  LSV: {family: non_monotonic_curve, preserve_point_order: true}\n"
        "metrics:\n  distinct: [overpotential, tafel_slope]\n",
        encoding="utf-8",
    )
    profile = load_profile("electrocatalysis", profile_root)
    assert profile["domain"] == "electrocatalysis"
    assert profile["techniques"]["XRD"]["family"] == "spectrum"
    assert profile["techniques"]["LSV"]["preserve_point_order"] is True
    assert profile["metrics"]["shared"] == ["temperature"]
    assert profile["metrics"]["distinct"] == ["overpotential", "tafel_slope"]



def test_scan_collision_cleans_temporary_manifest_and_preserves_previous_scan(tmp_path: Path, capsys):
    from scientific_figure_data.cli import main

    input_root = tmp_path / "input"
    nested = input_root / "nested" / "paper"
    collision = input_root / "nested__paper"
    nested.mkdir(parents=True)
    collision.mkdir(parents=True)
    for paper in (nested, collision):
        (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")

    output_root = tmp_path / "output"
    output_root.mkdir()
    final_stream = output_root / "corpus_manifest.jsonl"
    final_stream.write_text('{"previous":"valid"}\n', encoding="utf-8")
    previous_manifest = final_stream.read_bytes()

    assert main([
        "scan", "--input-root", str(input_root), "--output-root", str(output_root)
    ]) == 2
    error = capsys.readouterr().err
    assert "Paper ID normalization collision" in error
    assert final_stream.read_bytes() == previous_manifest
    assert not (output_root / "corpus_manifest.jsonl.tmp").exists()


def test_corrupt_paper_inventory_does_not_stop_other_papers(tmp_path: Path):
    from scientific_figure_data.adapter import discover_papers
    from scientific_figure_data.scheduler import JobLedger, run_corpus

    input_root = tmp_path / "input"
    corrupt = input_root / "paper-corrupt"
    valid = input_root / "paper-valid"
    corrupt.mkdir(parents=True)
    valid.mkdir(parents=True)
    (corrupt / "figure_inventory.json").write_text("{invalid json", encoding="utf-8")
    (valid / "figure_inventory.json").write_text(json.dumps({
        "figures": [{
            "figure_id": "Figure1",
            "panels": [{"panel_id": "a", "technique": "CV", "domain": "battery"}],
        }]
    }), encoding="utf-8")
    output_root = tmp_path / "output"

    report = run_corpus(
        input_root, output_root, discover_papers(input_root), workers=1,
        max_attempts=1, lease_seconds=30, options={"memory_limit_mb": 0},
    )

    assert report["papers_seen"] == 2
    assert report["completed_with_review"] == 2
    ledger = JobLedger(output_root / "catalog.sqlite")
    rows = {
        row["paper_id"]: row["state"]
        for row in ledger.con.execute("SELECT paper_id,state FROM jobs")
    }
    assert rows == {"paper-corrupt": "NEEDS_REVIEW", "paper-valid": "NEEDS_REVIEW"}
    assert (output_root / "papers" / "paper-corrupt" / "paper_manifest.json").is_file()
    assert (output_root / "papers" / "paper-valid" / "paper_manifest.json").is_file()
    ledger.close()



def test_calibrated_qc_thresholds_require_benchmark_and_algorithm_provenance(tmp_path: Path):
    from scientific_figure_data.qc import load_thresholds

    path = tmp_path / "uncited-calibrated.json"
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "status": "CALIBRATED",
        "thresholds": {
            "maximum_axis_anchor_rmse": 0.1,
            "minimum_trace_points": 8,
            "minimum_trace_pixel_fraction": 0.15,
            "maximum_overlay_distance": 2.0,
            "minimum_curve_coverage": 0.8,
        },
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="benchmark and thresholds mappings|benchmark provenance"):
        load_thresholds(path)


def test_calibrated_qc_thresholds_accept_complete_versioned_benchmark(tmp_path: Path):
    from scientific_figure_data.qc import load_thresholds

    path = tmp_path / "calibrated.json"
    config = {
        "schema_version": "1.0",
        "status": "CALIBRATED",
        "benchmark": {
            "dataset_manifest": "benchmarks/real-paper-dataset.json",
            "annotation_manifest": "benchmarks/annotations-v1.json",
            "paper_count": 5,
            "figure_count": 24,
            "calibrated_at": "2026-11-20T00:00:00Z",
            "calibration_method": "held-out annotated figure validation",
            "algorithm_version": "0.1.0",
            "profile_version": "sha256:profile-fingerprint",
        },
        "thresholds": {
            "maximum_axis_anchor_rmse": 0.1,
            "minimum_trace_points": 8,
            "minimum_trace_pixel_fraction": 0.15,
            "maximum_overlay_distance": 2.0,
            "minimum_curve_coverage": 0.8,
            "additional_domain_rules": {"battery": {"max_capacity_range_error": 0.1}},
        },
    }
    path.write_text(json.dumps(config), encoding="utf-8")
    assert load_thresholds(path) == config


def test_calibrated_qc_thresholds_reject_invalid_numeric_ranges(tmp_path: Path):
    from scientific_figure_data.qc import load_thresholds

    config = {
        "schema_version": "1.0",
        "status": "CALIBRATED",
        "benchmark": {
            "dataset_manifest": "dataset.json", "annotation_manifest": "annotations.json",
            "paper_count": 1, "figure_count": 1, "calibrated_at": "2026-11-20",
            "calibration_method": "test", "algorithm_version": "0.1.0",
            "profile_version": "sha256:profile",
        },
        "thresholds": {
            "maximum_axis_anchor_rmse": 0.1, "minimum_trace_points": 1,
            "minimum_trace_pixel_fraction": 1.5, "maximum_overlay_distance": 2.0,
            "minimum_curve_coverage": 0.8,
        },
    }
    path = tmp_path / "bad-calibrated.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="outside its permitted range"):
        load_thresholds(path)


def test_qc_reports_panel_segmentation_state_separately_from_chart_family():
    from scientific_figure_data.qc import build_series_qc_report

    series = make_series("segmentation-series", "segmentation-measurement", "battery")
    panel = {
        "bbox": None,
        "segmentation_status": "WHOLE_FIGURE_NOT_SEGMENTED",
        "segmentation_provenance": "SINGLE_PANEL_FALLBACK",
        "bbox_provenance": "NOT_PROVIDED",
        "segmentation_confidence": None,
        "segmentation_confidence_status": "NOT_CALIBRATED",
    }

    report = build_series_qc_report(series, panel)

    assert report["panel_segmentation"] == {
        "status": "WHOLE_FIGURE_NOT_SEGMENTED",
        "provenance": "SINGLE_PANEL_FALLBACK",
        "bbox_provenance": "NOT_PROVIDED",
        "boundary_present": False,
        "confidence": None,
        "confidence_status": "NOT_CALIBRATED",
    }
    assert report["components"]["panel_segmentation"] == "UNKNOWN"
    assert report["components"]["chart_family"] == "UNKNOWN"




def test_aop_metric_guard_keeps_removal_kinetics_and_mineralization_distinct():
    from scientific_figure_data.semantics import aop_metric_warning, domain_semantic_warnings

    assert aop_metric_warning("removal_efficiency", "rate_constant") == (
        "AOP_METRICS_ARE_NOT_INTERCHANGEABLE"
    )
    assert domain_semantic_warnings("aop", {}) == ["AOP_METRIC_UNRESOLVED"]
    assert domain_semantic_warnings(
        "aop",
        {"measurement_semantics": {
            "metric": "parent_concentration",
            "comparison_target_metric": "mineralization",
        }},
    ) == ["AOP_METRICS_ARE_NOT_INTERCHANGEABLE"]


def test_pfas_metric_guard_is_applied_to_export_metadata():
    from scientific_figure_data.semantics import domain_semantic_warnings

    assert domain_semantic_warnings("pfas", {}) == ["PFAS_METRIC_UNRESOLVED"]
    assert domain_semantic_warnings(
        "pfas",
        {"measurement_semantics": {
            "metric": "parent_removal",
            "comparison_target_metric": "defluorination",
        }},
    ) == ["PFAS_METRICS_ARE_NOT_INTERCHANGEABLE"]


def test_battery_capacity_export_requires_explicit_comparability_bases():
    from scientific_figure_data.semantics import domain_semantic_warnings

    warnings = domain_semantic_warnings(
        "battery", {"measurement_semantics": {"metric": "specific_capacity"}}
    )

    assert warnings == [
        "BATTERY_BASIS_UNRESOLVED:capacity_basis",
        "BATTERY_BASIS_UNRESOLVED:cell_scope",
        "BATTERY_BASIS_UNRESOLVED:current_density_basis",
        "BATTERY_BASIS_UNRESOLVED:cycling_protocol",
    ]




def test_battery_capacity_warnings_do_not_apply_to_spectral_characterization():
    from scientific_figure_data.semantics import domain_semantic_warnings

    assert domain_semantic_warnings("battery", {}, technique="XRD") == []
    assert domain_semantic_warnings("battery", {}, technique="GCD") == [
        "BATTERY_MEASUREMENT_METRIC_UNRESOLVED"
    ]




def test_reference_conversion_preserves_all_required_conditions_and_formula_parameters():
    from scientific_figure_data.semantics import resolve_reference_scale

    details = {
        "reference_electrode": "Ag/AgCl",
        "filling_solution": "KCl",
        "filling_concentration": "3 M",
        "temperature_k": 298.15,
        "electrolyte": "1 M KOH",
        "pH": 14.0,
        "formula_id": "formula-1",
        "formula_evidence_id": "source-equation-1",
        "scale_factor": 1.0,
        "offset_v": 0.197,
    }
    result = resolve_reference_scale(0.5, "RHE", details)

    assert result["status"] == "CONVERTED_WITH_EXPLICIT_EVIDENCE"
    assert result["conditions"]["pH"] == 14.0
    assert result["conversion"] == {"scale_factor": 1.0, "offset_v": 0.197}
    assert result["formula_id"] == "formula-1"
    assert result["formula_evidence_id"] == "source-equation-1"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_dimensional_standardization_rejects_non_finite_values(value):
    from scientific_figure_data.semantics import (
        convert_dimensionally, standardize_measurement_value,
    )

    with pytest.raises(ValueError, match="finite"):
        convert_dimensionally(value, "mg/L", "g/L")

    result = standardize_measurement_value(value, "mg/L", "g/L")
    assert result["standardized_value"] is None
    assert result["standardization_status"] == "UNRESOLVED_NON_FINITE_VALUE"




def test_export_compatibility_warnings_include_explicit_pfas_metric_guard():
    from scientific_figure_data.exporter import _series_compatibility_warnings
    from scientific_figure_data.semantics import pfas_metric_warning

    expected = pfas_metric_warning("parent_removal", "defluorination")
    assert expected is not None
    record = {
        "domain": "pfas", "technique": "parent_compound_time",
        "qc_status": "CALIBRATED", "review_state": "REVIEWED_ACCEPTED",
        "y_axis_side": "LEFT",
    }
    associations = {
        "subject_links": [{"link_status": "ASSIGNED_WITH_EVIDENCE"}],
        "conditions": [{"name": "pH"}],
    }
    metadata = {"measurement_semantics": {
        "metric": "parent_removal",
        "comparison_target_metric": "defluorination",
    }}

    warnings = _series_compatibility_warnings(record, associations, metadata)

    assert warnings == [expected]


def test_series_override_preserves_explicit_measurement_semantics():
    from scientific_figure_data.pipeline import _series_overrides

    payload = {
        "figures": {
            "F1": {
                "panels": {
                    "a": {
                        "series": [{
                            "series_id": "s1",
                            "measurement_semantics": {
                                "metric": "specific_capacity",
                                "capacity_basis": "gravimetric",
                                "cell_scope": "half_cell",
                                "current_density_basis": "active_material_mass",
                                "cycling_protocol": "constant_current",
                            },
                        }]
                    }
                }
            }
        }
    }

    semantics = _series_overrides(payload, "F1", "a")[0]["measurement_semantics"]

    assert semantics["capacity_basis"] == "gravimetric"
    assert semantics["cell_scope"] == "half_cell"
    assert semantics["current_density_basis"] == "active_material_mass"
    assert semantics["cycling_protocol"] == "constant_current"




def test_scheduler_isolates_snapshot_preflight_failure_and_continues_corpus(
    tmp_path: Path, monkeypatch,
):
    import scientific_figure_data.scheduler as scheduler_module
    from scientific_figure_data.adapter import discover_papers
    from scientific_figure_data.scheduler import JobLedger, run_corpus

    input_root = tmp_path / "input"
    bad = input_root / "a-bad-paper"
    good = input_root / "b-good-paper"
    bad.mkdir(parents=True)
    good.mkdir(parents=True)
    (bad / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    (good / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")

    original_snapshot = scheduler_module.snapshot_paper

    def fail_only_bad(paper, root):
        if paper.name == "a-bad-paper":
            raise PermissionError("synthetic unreadable upstream manifest")
        return original_snapshot(paper, root)

    monkeypatch.setattr(scheduler_module, "snapshot_paper", fail_only_bad)
    output_root = tmp_path / "output"

    report = run_corpus(
        input_root, output_root, discover_papers(input_root), workers=1,
        max_attempts=1, lease_seconds=30,
        options={"memory_limit_mb": 0, "min_free_memory_mb": 0, "min_free_disk_mb": 0},
    )

    ledger = JobLedger(output_root / "catalog.sqlite")
    rows = {
        row["paper_id"]: dict(row)
        for row in ledger.con.execute(
            "SELECT paper_id,state,last_error FROM jobs"
        ).fetchall()
    }
    assert rows["a-bad-paper"]["state"] == "FAILED_PERMANENT"
    assert "INPUT_SNAPSHOT_FAILED: PermissionError" in rows["a-bad-paper"]["last_error"]
    assert rows["b-good-paper"]["state"] == "NEEDS_REVIEW"
    assert report["failed"] == 1
    assert report["completed_with_review"] == 1
    ledger.close()




def test_condition_query_matches_both_condition_name_and_value(tmp_path: Path):
    snapshot, paper_root = make_output_with_series(tmp_path)
    catalog = Catalog(tmp_path / "catalog.sqlite")
    with catalog.con:
        catalog.con.execute(
            "UPDATE conditions SET value_json=? WHERE name='temperature'",
            (json.dumps({"value": 298.15, "unit": "K"}),),
        )

    by_name = catalog.query_series({"condition": "temperature"})
    by_value = catalog.query_series({"condition": "298.15"})
    by_unit = catalog.query_series({"condition": "K"})

    assert [row["series_id"] for row in by_name] == ["series-b"]
    assert [row["series_id"] for row in by_value] == ["series-b"]
    assert [row["series_id"] for row in by_unit] == ["series-b"]
    catalog.close()




def test_scheduler_retries_broken_process_pool_submission_a_finite_number_of_times(
    tmp_path: Path, monkeypatch,
):
    import scientific_figure_data.scheduler as scheduler_module
    from concurrent.futures.process import BrokenProcessPool
    from scientific_figure_data.adapter import discover_papers
    from scientific_figure_data.scheduler import JobLedger, run_corpus

    class BrokenSubmitExecutor:
        def __init__(self, *args, **kwargs):
            self.shutdown_calls = 0

        def submit(self, *args, **kwargs):
            raise BrokenProcessPool("synthetic broken submit")

        def shutdown(self, wait=False, cancel_futures=False):
            self.shutdown_calls += 1

    input_root = tmp_path / "input"
    paper = input_root / "paper-a"
    paper.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    monkeypatch.setattr(scheduler_module, "ProcessPoolExecutor", BrokenSubmitExecutor)

    output_root = tmp_path / "output"
    report = run_corpus(
        input_root, output_root, discover_papers(input_root), workers=1,
        max_attempts=2, lease_seconds=30,
        options={"memory_limit_mb": 0, "min_free_memory_mb": 0, "min_free_disk_mb": 0},
    )

    ledger = JobLedger(output_root / "catalog.sqlite")
    row = ledger.con.execute(
        "SELECT state,attempt_count,last_error FROM jobs WHERE paper_id='paper-a'"
    ).fetchone()
    assert row["state"] == "FAILED_PERMANENT"
    assert row["attempt_count"] == 2
    assert "WORKER_POOL_SUBMIT_FAILED" in row["last_error"]
    assert report["retried_papers"] == 1
    assert report["permanently_failed_papers"] == 1
    ledger.close()


def test_bounded_executor_shutdown_reaps_only_its_own_workers():
    from scientific_figure_data.scheduler import _shutdown_executor_bounded

    class FakeProcess:
        def __init__(self, pid: int, terminate_exits: bool, kill_exits: bool):
            self.pid = pid
            self.exitcode = None
            self.alive = True
            self.terminate_exits = terminate_exits
            self.kill_exits = kill_exits
            self.terminate_calls = 0
            self.kill_calls = 0

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminate_calls += 1
            if self.terminate_exits:
                self.alive = False
                self.exitcode = -15

        def kill(self):
            self.kill_calls += 1
            if self.kill_exits:
                self.alive = False
                self.exitcode = -9

    class FakeExecutor:
        def __init__(self, processes):
            self._processes = {item.pid: item for item in processes}
            self.shutdown_arguments = None

        def shutdown(self, wait=True, cancel_futures=False):
            self.shutdown_arguments = (wait, cancel_futures)
            self._processes[111].alive = False
            self._processes[111].exitcode = 0

    graceful = FakeProcess(111, terminate_exits=False, kill_exits=False)
    stubborn = FakeProcess(222, terminate_exits=False, kill_exits=True)
    executor = FakeExecutor([graceful, stubborn])

    report = _shutdown_executor_bounded(executor, grace_seconds=0)

    assert executor.shutdown_arguments == (False, True)
    assert report["status"] == "WORKERS_REAPED"
    by_pid = {item["pid"]: item for item in report["workers"]}
    assert by_pid[111]["action"] == "EXITED_GRACEFULLY"
    assert by_pid[222]["action"] == "KILL_SENT"
    assert graceful.terminate_calls == 0
    assert graceful.kill_calls == 0
    assert stubborn.kill_calls == 1
    assert all(not item["still_alive"] for item in report["workers"])



def _parent_exit_probe_worker(pid_file: str):
    import os
    import time
    from pathlib import Path

    Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(12)


def _parent_exit_probe_pool_owner(root: str):
    import os
    import time
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path
    from scientific_figure_data.scheduler import _worker_initializer

    root_path = Path(root)
    temp_directory = root_path / "worker-temp"
    log_directory = root_path / "worker-logs"
    temp_directory.mkdir(parents=True, exist_ok=True)
    log_directory.mkdir(parents=True, exist_ok=True)
    pid_file = root_path / "worker.pid"
    executor = ProcessPoolExecutor(
        max_workers=1,
        initializer=_worker_initializer,
        initargs=(str(temp_directory), str(log_directory)),
    )
    executor.submit(_parent_exit_probe_worker, str(pid_file))
    deadline = time.monotonic() + 12
    while not pid_file.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not pid_file.is_file():
        os._exit(7)
    # Simulate the precise failure mode: the executor owner vanishes while
    # a worker is still inside a long-running task and without normal shutdown.
    os._exit(0)


def test_worker_exits_when_its_scheduler_parent_disappears(tmp_path: Path):
    import multiprocessing
    import os
    import time

    context = multiprocessing.get_context("spawn")
    owner = context.Process(
        target=_parent_exit_probe_pool_owner,
        args=(str(tmp_path),),
    )
    owner.start()
    owner.join(timeout=18)
    if owner.is_alive():
        owner.terminate()
        owner.join(timeout=3)
        raise AssertionError("test pool owner failed to exit within the bounded window")
    assert owner.exitcode == 0, f"test pool owner exited with {owner.exitcode}"

    pid_file = tmp_path / "worker.pid"
    assert pid_file.is_file(), "worker did not report its PID before parent exit"
    worker_pid = int(pid_file.read_text(encoding="utf-8").strip())

    def is_process_alive(pid: int) -> bool:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            open_process.restype = wintypes.HANDLE
            get_exit_code = kernel32.GetExitCodeProcess
            get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_exit_code.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL

            handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                error = ctypes.get_last_error()
                if error in {87, 1168}:  # ERROR_INVALID_PARAMETER / ERROR_NOT_FOUND
                    return False
                raise OSError(error, f"OpenProcess failed for PID {pid}")
            try:
                exit_code = wintypes.DWORD()
                if not get_exit_code(handle, ctypes.byref(exit_code)):
                    raise ctypes.WinError(ctypes.get_last_error())
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                close_handle(handle)

        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if not is_process_alive(worker_pid):
            break
        time.sleep(0.1)
    else:
        raise AssertionError(
            f"orphan worker PID {worker_pid} remained alive after its parent exited"
        )
    assert not is_process_alive(worker_pid), (
        f"orphan worker PID {worker_pid} remained alive after its parent exited"
    )

