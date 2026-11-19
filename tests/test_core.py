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


def test_units_battery_comparability_and_pfas_metrics_are_conservative():
    assert convert_dimensionally(60, "s", "min") == 1
    compatible, mismatches = comparable_battery_records(
        {"capacity_basis": "gravimetric", "cell_scope": "full_cell",
         "current_density_basis": "mass", "cycling_protocol": "1C"},
        {"capacity_basis": "areal", "cell_scope": "full_cell",
         "current_density_basis": "mass", "cycling_protocol": "1C"},
    )
    assert not compatible and mismatches == ["capacity_basis"]
    assert pfas_metric_warning("parent_removal", "defluorination") == "PFAS_METRICS_ARE_NOT_INTERCHANGEABLE"
    assert preserve_censored_value("<LOQ")["numeric_value"] is None
    assert preserve_censored_value("<0.1 mg/L")["limit_value"] == 0.1
    assert preserve_censored_value("<0.1 mg/L")["numeric_value"] is None


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
            ("sample-a", "Sample A", "material", "battery", '["A"]', '{"source":"legend"}'),
        )
        catalog.con.execute(
            "INSERT INTO series_subject_links(series_id,entity_id,role_in_series,evidence_json,link_status) VALUES(?,?,?,?,?)",
            ("series-a", "sample-a", "tested_material", '{"source":"legend","page":2}', "ASSIGNED_WITH_EVIDENCE"),
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
    metadata_rows = [
        json.loads(line) for line in (output / "series_metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    first_metadata = next(row for row in metadata_rows if row["series_id"] == "series-a")
    assert any(link["canonical_name"] == "Sample A" for link in first_metadata["subject_links"])
    assert any("electrolyte" in item["name"] for item in first_metadata["conditions"])
    assert first_metadata["input_fingerprint"] == snapshot.input_fingerprint
    assert (output / "warnings.jsonl").is_file()
    assert manifest["streaming"]["point_rows_buffered"] == 1


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
    assert query_rows[0]["series_id"] == "Figure1_a_unassigned"

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
    ledger.start("paper-active")
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

    fake_module = types.ModuleType("rapidocr")
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
    assert [float(row["y_value"]) for row in untouched] == pytest.approx([10.0, 20.0])

    document = json.loads(digitization_path.read_text(encoding="utf-8"))
    record = next(item for item in document["series"] if item["series_id"] == "series-a")
    assert record["metadata"]["x_axis_calibration"]["slope"] == pytest.approx(2.0)
    assert record["metadata"]["y_axis_calibration"]["slope"] == pytest.approx(4.0)
    assert record["review_state"] == "REVIEWED_ACCEPTED"

    catalog = Catalog(tmp_path / "catalog.sqlite")
    stored_metadata = json.loads(catalog.con.execute(
        "SELECT metadata_json FROM series WHERE series_id='series-a'"
    ).fetchone()["metadata_json"])
    assert stored_metadata["x_axis_calibration"]["slope"] == pytest.approx(2.0)
    indexed = catalog.con.execute(
        "SELECT x_value,y_value FROM series_points WHERE series_id='series-a' ORDER BY point_index"
    ).fetchall()
    assert [row["x_value"] for row in indexed] == pytest.approx([0.0, 2.0])
    assert [row["y_value"] for row in indexed] == pytest.approx([0.0, 4.0])
    untouched_index = catalog.con.execute(
        "SELECT x_value,y_value FROM series_points WHERE series_id='series-b' ORDER BY point_index"
    ).fetchall()
    assert [row["x_value"] for row in untouched_index] == pytest.approx([0.0, 1.0])
    assert [row["y_value"] for row in untouched_index] == pytest.approx([10.0, 20.0])
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
