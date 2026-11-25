from __future__ import annotations

import json
from pathlib import Path

import pytest

from scientific_figure_data.entities import assert_acyclic_process_graph
from scientific_figure_data.models import PaperSnapshot
from scientific_figure_data.storage import Catalog, connect_catalog


def test_process_dag_accepts_ordered_steps_and_rejects_cycles():
    assert_acyclic_process_graph([
        ("precursor", "hydrothermal"),
        ("hydrothermal", "calcination"),
    ])
    with pytest.raises(ValueError, match="cycle"):
        assert_acyclic_process_graph([
            ("precursor", "hydrothermal"),
            ("hydrothermal", "calcination"),
            ("calcination", "precursor"),
        ])


def test_catalog_migrates_v21_tables_and_wal_pragmas(tmp_path: Path):
    connection = connect_catalog(tmp_path / "catalog.sqlite")
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        expected = {
            "subject_entities", "subject_entity_aliases", "synthesis_processes",
            "sample_process_steps", "series_measurement_links", "evidence_items",
            "cross_validation_results",
        }
        actual = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert expected.issubset(actual)
        series_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(series)")
        }
        assert {"scale_type", "baseline_comparable", "offset_value"} <= series_columns
    finally:
        connection.close()


def test_catalog_indexes_semantic_subject_process_condition_and_measurement(tmp_path: Path):
    output_root = tmp_path / "output"
    paper_root = output_root / "papers" / "paper-1"
    paper_root.mkdir(parents=True)
    snapshot = PaperSnapshot(
        paper_id="paper-1", source_dir="paper-1",
        detected_upstream_version="1.1.0", adapter_version="2.1",
        created_at="2026-11-25T00:00:00Z",
    )
    documents = {
        "sample_registry.json": {
            "subjects": [{
                "subject_entity_id": "subject-a", "canonical_name": "Sample A",
                "entity_kind": "SAMPLE", "aliases": ["Sample A", "SA"],
                "resolution_status": "PROVISIONAL_TEXT_CANDIDATE",
                "evidence": [{
                    "evidence_id": "evidence-a", "source_type": "EXTRACTED_TEXT",
                    "source_path": "main_analysis.md", "line_number": 4,
                    "snippet": "Sample A was synthesized.",
                }],
            }],
            "sample_process_steps": [{
                "sample_id": "subject-a", "process_id": "process-a",
                "step_order": 1, "step_role": "CALCINATION",
                "evidence_id": "evidence-a", "scope_status": "SOURCE_BACKED_CANDIDATE",
            }],
            "series_subject_links": [{
                "series_id": "series-a", "subject_entity_id": "subject-a",
                "subject_role": "ACTIVE_MATERIAL", "link_status": "MATCHED_EXACT_ALIAS",
                "evidence_ids": ["evidence-a"],
            }],
        },
        "synthesis_processes.json": {
            "processes": [{
                "process_id": "process-a", "method_text": "calcined at 300 °C",
                "condition_ids": ["condition-s"], "evidence_ids": ["evidence-a"],
                "process_status": "CANDIDATE",
            }],
            "sample_process_steps": [{
                "sample_id": "subject-a", "process_id": "process-a",
                "step_order": 1, "step_role": "CALCINATION",
                "evidence_id": "evidence-a", "scope_status": "SOURCE_BACKED_CANDIDATE",
            }],
            "conditions": [{
                "condition_id": "condition-s", "condition_scope": "SYNTHESIS",
                "scope_entity_id": "process-a", "raw_text": "300 °C",
                "value": {
                    "raw_text": "300 °C", "value_kind": "QUANTITY", "operator": "EQ",
                    "numeric_values": [300.0], "text_values": [], "unit_raw": "°C",
                    "unit_canonical": "degC", "uncertainty": None,
                    "normalization_basis": None, "parse_status": "PARSED",
                },
                "evidence_ids": ["evidence-a"], "parse_status": "PARSED",
            }],
        },
        "experiments.json": {
            "measurements": [{
                "measurement_id": "measurement-a", "paper_id": "paper-1",
                "figure_id": "Figure1", "technique": "CV",
                "scope_status": "CAPTION_CANDIDATE", "evidence_ids": ["evidence-a"],
                "condition_ids": [],
            }],
            "series_measurement_links": [{
                "series_id": "series-a", "measurement_id": "measurement-a",
                "measurement_role": "MEASUREMENT_RESULT",
                "link_status": "CANDIDATE_TECHNIQUE_MATCH", "evidence_ids": ["evidence-a"],
            }],
            "conditions": [],
        },
        "cross_validation.json": {
            "results": [{
                "series_id": "series-a", "status": "UNRESOLVED",
                "checks": [], "unresolved_fields": ["image_calibration"],
            }],
        },
    }
    for name, value in documents.items():
        (paper_root / name).write_text(json.dumps(value), encoding="utf-8")

    catalog = Catalog(output_root / "catalog.sqlite")
    try:
        catalog.index_paper(
            snapshot, figures=[], panels=[], series=[], status="COMPLETED_WITH_REVIEW",
            paper_root=paper_root,
        )
        assert catalog.con.execute(
            "SELECT canonical_name FROM subject_entities WHERE paper_id='paper-1'"
        ).fetchone()[0] == "Sample A"
        assert catalog.con.execute(
            "SELECT alias_norm FROM subject_entity_aliases WHERE alias='SA'"
        ).fetchone()[0] == "sa"
        assert catalog.con.execute(
            "SELECT step_role FROM sample_process_steps"
        ).fetchone()[0] == "CALCINATION"
        assert catalog.con.execute(
            "SELECT condition_scope,scope_entity_id FROM conditions"
        ).fetchone()[0] == "SYNTHESIS"
        assert catalog.con.execute(
            "SELECT technique FROM measurements WHERE measurement_id LIKE '%measurement-a'"
        ).fetchone()[0] == "CV"
        assert catalog.con.execute(
            "SELECT status FROM cross_validation_results"
        ).fetchone()[0] == "UNRESOLVED"
    finally:
        catalog.close()


def test_v21_schema_declares_required_semantic_contracts():
    schema_path = Path(__file__).parents[1] / "schemas" / "v2.1_semantic_contract.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    assert {
        "ConditionValue", "SubjectEntity", "SampleProcessStep", "SeriesSubjectLink",
        "SeriesMeasurementLink", "StackedAxisSemantics", "EvidenceItem",
        "CrossValidationResult",
    } <= set(definitions)
    stacked = definitions["StackedAxisSemantics"]
    assert stacked["allOf"][0]["then"]["properties"]["baseline_comparable"]["const"] is False
