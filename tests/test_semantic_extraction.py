from __future__ import annotations

from types import SimpleNamespace

from scientific_figure_data.semantic_extraction import (
    build_semantic_package,
    extract_quantity_expressions,
    parse_condition_value,
    segment_caption,
)


def test_condition_value_preserves_ranges_lists_censored_and_uncertainty():
    ranged = parse_condition_value("200–300 °C")
    assert ranged.value_kind == "QUANTITY"
    assert ranged.operator == "RANGE"
    assert ranged.numeric_values == [200.0, 300.0]
    assert ranged.unit_canonical == "degC"

    censored = parse_condition_value("<0.05 mg L−1")
    assert censored.operator == "LT"
    assert censored.numeric_values == [0.05]
    assert censored.unit_canonical == "mg/L"

    uncertainty = parse_condition_value("1.5 ± 0.1 M")
    assert uncertainty.numeric_values == [1.5]
    assert uncertainty.uncertainty["value"] == 0.1
    assert uncertainty.unit_canonical == "mol/L"

    values = parse_condition_value("10, 20, 50, 100 mV s−1")
    assert values.value_kind == "LIST"
    assert values.operator == "LIST"
    assert values.numeric_values == [10.0, 20.0, 50.0, 100.0]


def test_quantity_extractor_splits_temperature_and_duration():
    values = extract_quantity_expressions("Sample A was calcined at 300 °C for 2 h.")
    assert [item["raw_text"] for item in values] == ["300 °C", "2 h"]


def test_caption_segmenter_preserves_shared_and_panel_clauses():
    segments = segment_caption("Figure 4. Shared protocol. (a) Sample A CV. (b) Sample B EIS.")
    assert segments[0]["scope"] == "FIGURE_SHARED"
    assert [(item["panel_id"], item["raw_text"]) for item in segments[1:]] == [
        ("a", "Sample A CV."), ("b", "Sample B EIS."),
    ]


class _Context:
    def __init__(self):
        self.samples = [
            {
                "value": "Sample A", "source_path": "main_analysis.md",
                "line_number": 10,
                "snippet": "Sample A was synthesized hydrothermally at 200 °C for 2 h.",
            },
        ]
        self.statements = self.samples + [
            {
                "value": "CV", "source_path": "main_analysis.md",
                "line_number": 20,
                "snippet": "Sample A was measured by cyclic voltammetry at a scan rate of 5 mV/s.",
            },
        ]

    def search(self, kind: str, text: str = "", limit: int = 100):
        source = self.samples if kind == "sample_alias" else self.statements
        return [
            item for item in source
            if text.casefold() in item.get("value", item.get("snippet", "")).casefold()
            or text.casefold() in item.get("snippet", "").casefold()
        ][:limit]


def test_two_pass_registry_exact_links_and_unresolved_visual_only_candidate():
    records = [
        SimpleNamespace(
            series_id="series-a", paper_id="paper-a", figure_id="Figure1",
            panel_id="a", label="Sample A", technique="CV",
            subject_links=[], conditions=[], metadata={}, measurement_id=None,
        ),
        SimpleNamespace(
            series_id="series-b", paper_id="paper-a", figure_id="Figure1",
            panel_id="b", label="Sample B", technique="EIS",
            subject_links=[], conditions=[], metadata={}, measurement_id=None,
        ),
    ]
    result = build_semantic_package(
        "paper-a", "fingerprint-a",
        [{"figure_id": "Figure1", "caption": "Figure 1. (a) Sample A CV curves. (b) EIS curves."}],
        [], records, _Context(),
    )

    assert result["sample_registry"]["pass1_status"] == "PROVISIONAL"
    assert result["sample_registry"]["pass2_status"] == "COMPLETED_ONCE"
    assert result["sample_registry"]["pass2_new_visual_names"] == ["Sample B"]
    assert result["sample_registry"]["subjects"][0]["entity_kind"] == "SAMPLE"
    assert result["series_subject_links"][0]["link_status"] == "MATCHED_EXACT_ALIAS"
    assert result["series_subject_links"][1]["link_status"] == "UNRESOLVED_IMAGE_ONLY"
    assert any(item["condition_scope"] == "SYNTHESIS" for item in result["conditions"])
    assert records[0].metadata["semantic_pass2_fingerprint"]



def test_explicit_offset_stacked_spectrum_forces_non_comparable_baseline():
    record = SimpleNamespace(
        series_id="series-stacked", paper_id="paper-a", figure_id="Figure2",
        panel_id="a", label="Sample A", technique="Raman",
        subject_links=[], conditions=[], metadata={
            "vertical_offset_stacked_detected": True,
            "y_signal_mode": "SERIES_RELATIVE_SIGNAL",
        }, measurement_id=None, y_unit=None,
    )
    result = build_semantic_package(
        "paper-a", "fingerprint-b",
        [{"figure_id": "Figure2", "caption": "Raman spectra."}],
        [], [record], _Context(),
    )
    assert record.scale_type == "ARBITRARY_OFFSET_STACKED"
    assert record.baseline_comparable is False
    assert result["cross_validation"]["status"] in {
        "COMPLETED_WITH_UNRESOLVED", "CONSISTENT_WITH_AVAILABLE_EVIDENCE",
    }



def test_sentence_scoping_does_not_attach_following_experiment_to_sample_synthesis():
    context = _Context()
    context.statements = [{
        "value": "Sample A",
        "source_path": "main_analysis.md",
        "line_number": 30,
        "snippet": (
            "Sample A was synthesized hydrothermally at 200 °C for 2 h. "
            "The cell was tested at 1 A g−1."
        ),
    }]
    record = SimpleNamespace(
        series_id="series-a", paper_id="paper-a", figure_id="Figure1",
        panel_id="a", label="Sample A", technique="CV",
        subject_links=[], conditions=[], metadata={}, measurement_id=None,
        y_unit="mA",
    )
    result = build_semantic_package(
        "paper-a", "fingerprint-sentence",
        [{"figure_id": "Figure1", "caption": "CV curves of Sample A."}],
        [], [record], context,
    )
    assert [item["raw_text"] for item in result["conditions"]] == [
        "200 °C", "2 h",
    ]
    assert {item["condition_name"] for item in result["conditions"]} == {
        "temperature", "duration",
    }
    assert all(item["condition_scope"] == "SYNTHESIS" for item in result["conditions"])
