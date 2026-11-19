from __future__ import annotations

import json
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
    Catalog, append_panel_series_csv, write_paper_artifacts,
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
    paper = input_root / "paper-cache"
    paper.mkdir(parents=True)
    (paper / "figure_inventory.json").write_text('{"figures":[]}', encoding="utf-8")
    output_root = tmp_path / "output"

    first = run_corpus(input_root, output_root, discover_papers(input_root), workers=1)
    assert first["completed_with_review"] == 1
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
