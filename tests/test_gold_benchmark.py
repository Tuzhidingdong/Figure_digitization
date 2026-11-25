from __future__ import annotations

from scientific_figure_data.benchmark import (
    evaluate_condition_scope,
    evaluate_condition_kind_scope,
    evaluate_gold_benchmark,
    evaluate_relation,
    evaluate_sample_merges,
    split_gold_papers,
    curve_nrmse,
)


def _papers():
    return [
        {"paper_id": f"{domain}-{index}", "domain": domain}
        for domain in ("Battery", "AOP", "PFAS") for index in range(3)
    ]


def _coverage():
    return {
        "paired_papers": 9, "figure_caption_pairs": 30, "panels": 60,
        "distinct_samples": 30, "explicit_legend_opportunities": 60,
        "synthesis_condition_assertions": 50, "experiment_condition_assertions": 50,
    }


def _passing_metrics():
    return {
        "figure_caption": {
            "precision": 0.99, "recall": 0.96, "false_cross_associations": 0,
        },
        "panel_split": {
            "precision": 0.96, "recall": 0.91, "wrong_assignment_rate": 0.01,
        },
        "sample_merge": {
            "precision": 0.96, "recall": 0.81, "false_merge_groups": 0,
        },
        "series_subject": {
            "precision": 0.93, "recall": 0.76, "wrong_link_rate": 0.02,
            "predicted_count": 20,
        },
        "condition_scope": {
            "precision": 0.96, "recall": 0.71, "false_scope_attachment_rate": 0.02,
        },
        "curve_nrmse": {
            "status": "NOT_EVALUATED",
            "reason": "NO_INDEPENDENT_NUMERICAL_GROUND_TRUTH",
        },
    }


def test_paper_level_split_is_deterministic_and_leak_free():
    first = split_gold_papers(_papers())
    second = split_gold_papers(_papers())
    assert first == second
    assert first["status"] == "READY"
    assert not (
        set(first["development_paper_ids"])
        & set(first["blind_held_out_paper_ids"])
    )
    assert len(first["development_paper_ids"]) == 6
    assert len(first["blind_held_out_paper_ids"]) == 3


def test_unresolved_predictions_reduce_recall_instead_of_disappearing():
    metrics = evaluate_relation(
        [("f1", "c1"), ("f2", "c2")],
        [
            {"figure_id": "f1", "caption_id": "c1", "status": "MATCHED"},
            {"figure_id": "f2", "caption_id": None, "status": "UNRESOLVED"},
        ],
        "figure_id", "caption_id",
    )
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 0.5
    assert metrics["unresolved_prediction_count"] == 1


def test_sample_false_merge_is_counted_even_when_links_are_source_backed():
    metrics = evaluate_sample_merges(
        {"mention-a1": "sample-a", "mention-a2": "sample-a", "mention-b1": "sample-b"},
        {
            "mention-a1": "entity-1",
            "mention-a2": "entity-1",
            "mention-b1": "entity-1",
        },
    )
    assert metrics["false_merge_groups"] == 1
    assert metrics["precision"] == 1 / 3


def test_condition_scope_false_attachment_is_explicit():
    metrics = evaluate_condition_scope(
        {"condition-a": "SYNTHESIS", "condition-b": "EXPERIMENT"},
        {"condition-a": "EXPERIMENT", "condition-b": "EXPERIMENT"},
    )
    assert metrics["false_scope_attachments"] == 1
    assert metrics["false_scope_attachment_rate"] == 0.5


def test_curve_nrmse_is_not_evaluated_without_independent_truth():
    result = curve_nrmse([1.0, 2.0], None)
    assert result["status"] == "NOT_EVALUATED"


def test_insufficient_gold_coverage_cannot_pass_even_with_perfect_predictions():
    report = evaluate_gold_benchmark(
        {"papers": _papers(), "coverage_counts": {"paired_papers": 9}},
        {"blind_held_out_metrics": _passing_metrics()},
    )
    assert report["status"] == "NOT_EVALUATED"
    assert "figure_caption_pairs" in report["missing_coverage"]


def test_empty_series_predictions_cannot_vacuously_pass():
    metrics = _passing_metrics()
    metrics["series_subject"] = {
        "precision": None, "recall": 0.0, "wrong_link_rate": 1.0,
        "predicted_count": 0,
    }
    report = evaluate_gold_benchmark(
        {"papers": _papers(), "coverage_counts": _coverage()},
        {"development_metrics": {}, "blind_held_out_metrics": metrics},
    )
    assert report["status"] == "FAIL"
    assert report["gates"]["series_subject_precision"] is False
    assert report["gates"]["series_wrong_link_rate"] is False


def test_benchmark_requires_blind_held_out_metrics():
    report = evaluate_gold_benchmark(
        {"papers": _papers(), "coverage_counts": _coverage()},
        {"development_metrics": _passing_metrics()},
    )
    assert report["status"] == "NOT_EVALUATED"
    assert report["reason"] == "BLIND_HELD_OUT_METRICS_NOT_SUPPLIED"



def test_condition_kind_and_scope_are_evaluated_jointly():
    metrics = evaluate_condition_kind_scope(
        {
            "condition-a": ("TEMPERATURE", "SYNTHESIS"),
            "condition-b": ("SCAN_RATE", "EXPERIMENT"),
        },
        {
            "condition-a": ("TEMPERATURE", "SYNTHESIS"),
            "condition-b": ("CURRENT_DENSITY", "EXPERIMENT"),
        },
    )
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["false_scope_attachments"] == 1
