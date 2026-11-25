from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Any, Iterable

DOMAINS = ("Battery", "AOP", "PFAS")
MINIMUM_COVERAGE = {
    "paired_papers": 9,
    "papers_per_domain": 3,
    "figure_caption_pairs": 30,
    "panels": 60,
    "distinct_samples": 30,
    "explicit_legend_opportunities": 60,
    "synthesis_condition_assertions": 50,
    "experiment_condition_assertions": 50,
}
THRESHOLDS = {
    "figure_caption_precision": 0.98,
    "figure_caption_recall": 0.95,
    "panel_split_precision": 0.95,
    "panel_split_recall": 0.90,
    "panel_wrong_assignment_rate_max": 0.02,
    "sample_merge_precision": 0.95,
    "sample_merge_recall": 0.80,
    "sample_false_merges": 0,
    "series_subject_precision": 0.92,
    "series_subject_recall": 0.75,
    "series_wrong_link_rate_max": 0.03,
    "condition_scope_precision": 0.95,
    "condition_scope_recall": 0.70,
    "condition_false_scope_attachments_max": 0.03,
    "curve_nrmse_max": 0.025,
}


def split_gold_papers(
    papers: list[dict[str, Any]], seed: str = "sfd-v2.1-gold-split",
) -> dict[str, Any]:
    """Deterministic domain-stratified split at paper level; never split figures within papers."""
    by_domain: dict[str, list[str]] = defaultdict(list)
    for paper in papers:
        domain = str(paper.get("domain") or "")
        paper_id = str(paper.get("paper_id") or "")
        if domain not in DOMAINS or not paper_id:
            continue
        by_domain[domain].append(paper_id)
    missing_domains = [domain for domain in DOMAINS if len(set(by_domain[domain])) < 3]
    if missing_domains:
        return {
            "status": "NOT_EVALUATED",
            "reason": "INSUFFICIENT_PAPERS_PER_DOMAIN",
            "missing_domains": missing_domains,
            "development_paper_ids": [],
            "blind_held_out_paper_ids": [],
        }
    development: list[str] = []
    held_out: list[str] = []
    for domain in DOMAINS:
        ids = sorted(set(by_domain[domain]))
        ids.sort(key=lambda paper_id: hashlib.sha256(
            f"{seed}|{domain}|{paper_id}".encode("utf-8")
        ).hexdigest())
        dev_count = max(1, min(len(ids) - 1, round(len(ids) * 0.70)))
        development.extend(ids[:dev_count])
        held_out.extend(ids[dev_count:])
    if set(development) & set(held_out):
        raise AssertionError("Gold benchmark paper split leaked across partitions")
    return {
        "status": "READY",
        "seed": seed,
        "development_paper_ids": sorted(development),
        "blind_held_out_paper_ids": sorted(held_out),
        "paper_level_only": True,
    }


def precision_recall(
    gold_items: Iterable[Any], predicted_items: Iterable[Any],
) -> dict[str, Any]:
    gold = set(gold_items)
    predicted = set(predicted_items)
    true_positive = len(gold & predicted)
    false_positive = len(predicted - gold)
    false_negative = len(gold - predicted)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else (
        0.0 if gold else None
    )
    recall = true_positive / len(gold) if gold else None
    return {
        "gold_count": len(gold), "predicted_count": len(predicted),
        "true_positive": true_positive, "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision, "recall": recall,
    }


def evaluate_relation(
    gold_pairs: Iterable[tuple[str, str]],
    predicted_records: Iterable[dict[str, Any]],
    left_key: str, right_key: str, status_key: str = "status",
) -> dict[str, Any]:
    """UNRESOLVED predictions are omitted from predictions but remain in the gold denominator."""
    predictions = set()
    unresolved = 0
    for item in predicted_records:
        if str(item.get(status_key, "")).upper() in {"UNRESOLVED", "UNASSIGNED", "BLOCKED"}:
            unresolved += 1
            continue
        left, right = item.get(left_key), item.get(right_key)
        if left is not None and right is not None:
            predictions.add((str(left), str(right)))
    result = precision_recall(
        ((str(a), str(b)) for a, b in gold_pairs), predictions,
    )
    result["unresolved_prediction_count"] = unresolved
    return result


def evaluate_sample_merges(
    gold_mention_to_sample: dict[str, str],
    predicted_mention_to_entity: dict[str, str | None],
) -> dict[str, Any]:
    """Measure same-sample mention pairs and explicitly count cross-sample false merges."""
    gold_pairs = set()
    mentions = sorted(gold_mention_to_sample)
    for index, left in enumerate(mentions):
        for right in mentions[index + 1:]:
            if gold_mention_to_sample[left] == gold_mention_to_sample[right]:
                gold_pairs.add((left, right))
    predicted_groups: dict[str, list[str]] = defaultdict(list)
    for mention, entity_id in predicted_mention_to_entity.items():
        if entity_id:
            predicted_groups[str(entity_id)].append(str(mention))
    predicted_pairs = set()
    false_merges = 0
    for group in predicted_groups.values():
        known_gold_ids = {
            gold_mention_to_sample[item] for item in group if item in gold_mention_to_sample
        }
        if len(known_gold_ids) > 1:
            false_merges += 1
        for index, left in enumerate(sorted(group)):
            for right in sorted(group)[index + 1:]:
                predicted_pairs.add((left, right))
    metrics = precision_recall(gold_pairs, predicted_pairs)
    metrics["false_merge_groups"] = false_merges
    metrics["false_merge_rate"] = (
        false_merges / len(predicted_groups) if predicted_groups else 0.0
    )
    return metrics


def evaluate_condition_scope(
    gold_scopes: dict[str, str], predicted_scopes: dict[str, str | None],
) -> dict[str, Any]:
    correct = set()
    false_scope = 0
    predicted = set()
    unresolved = 0
    for condition_id, scope in predicted_scopes.items():
        if scope is None or str(scope).upper() in {"UNRESOLVED", "UNKNOWN"}:
            unresolved += 1
            continue
        pair = (str(condition_id), str(scope).upper())
        predicted.add(pair)
        if condition_id in gold_scopes and str(gold_scopes[condition_id]).upper() != pair[1]:
            false_scope += 1
        if condition_id in gold_scopes and str(gold_scopes[condition_id]).upper() == pair[1]:
            correct.add(pair)
    gold = {(str(key), str(value).upper()) for key, value in gold_scopes.items()}
    metrics = precision_recall(gold, predicted)
    metrics["false_scope_attachments"] = false_scope
    metrics["unresolved_prediction_count"] = unresolved
    metrics["false_scope_attachment_rate"] = (
        false_scope / max(1, len(predicted))
    )
    return metrics


def curve_nrmse(
    predicted: list[float] | None, independent_ground_truth: list[float] | None,
) -> dict[str, Any]:
    if not independent_ground_truth:
        return {"status": "NOT_EVALUATED", "reason": "NO_INDEPENDENT_NUMERICAL_GROUND_TRUTH"}
    if predicted is None or len(predicted) != len(independent_ground_truth) or not predicted:
        return {"status": "INVALID_COMPARISON", "nrmse": None}
    truth = [float(value) for value in independent_ground_truth]
    values = [float(value) for value in predicted]
    scale = max(truth) - min(truth)
    if scale <= 0:
        return {"status": "INVALID_GROUND_TRUTH_RANGE", "nrmse": None}
    mse = sum((left - right) ** 2 for left, right in zip(values, truth)) / len(truth)
    return {"status": "EVALUATED", "nrmse": math.sqrt(mse) / scale}


def evaluate_gold_benchmark(
    manifest: dict[str, Any], predictions: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate only when the frozen gold coverage floor is met; never lower floors to force a pass."""
    counts = manifest.get("coverage_counts", {})
    missing = {
        key: {"required": required, "observed": int(counts.get(key, 0))}
        for key, required in MINIMUM_COVERAGE.items()
        if int(counts.get(key, 0)) < required
    }
    split = split_gold_papers(manifest.get("papers", []))
    if missing or split["status"] != "READY":
        return {
            "status": "NOT_EVALUATED",
            "reason": "INSUFFICIENT_GOLD_BENCHMARK_COVERAGE",
            "missing_coverage": missing,
            "paper_split": split,
            "thresholds": dict(THRESHOLDS),
            "metrics": {},
        }

    metrics = predictions.get("metrics", {})
    gates = {}
    gates["figure_caption_precision"] = (
        metrics.get("figure_caption", {}).get("precision", 0) >= THRESHOLDS["figure_caption_precision"]
    )
    gates["figure_caption_recall"] = (
        metrics.get("figure_caption", {}).get("recall", 0) >= THRESHOLDS["figure_caption_recall"]
    )
    gates["panel_split_precision"] = (
        metrics.get("panel_split", {}).get("precision", 0) >= THRESHOLDS["panel_split_precision"]
    )
    gates["panel_split_recall"] = (
        metrics.get("panel_split", {}).get("recall", 0) >= THRESHOLDS["panel_split_recall"]
    )
    gates["sample_merge_precision"] = (
        metrics.get("sample_merge", {}).get("precision", 0) >= THRESHOLDS["sample_merge_precision"]
    )
    gates["sample_merge_recall"] = (
        metrics.get("sample_merge", {}).get("recall", 0) >= THRESHOLDS["sample_merge_recall"]
    )
    gates["sample_false_merges_zero"] = (
        metrics.get("sample_merge", {}).get("false_merge_groups", 0) == 0
    )
    gates["series_subject_precision"] = (
        metrics.get("series_subject", {}).get("precision", 0) >= THRESHOLDS["series_subject_precision"]
    )
    gates["series_subject_recall"] = (
        metrics.get("series_subject", {}).get("recall", 0) >= THRESHOLDS["series_subject_recall"]
    )
    gates["condition_scope_precision"] = (
        metrics.get("condition_scope", {}).get("precision", 0) >= THRESHOLDS["condition_scope_precision"]
    )
    gates["condition_scope_recall"] = (
        metrics.get("condition_scope", {}).get("recall", 0) >= THRESHOLDS["condition_scope_recall"]
    )
    gates["condition_false_scope_attachment"] = (
        metrics.get("condition_scope", {}).get("false_scope_attachment_rate", 1)
        <= THRESHOLDS["condition_false_scope_attachments_max"]
    )
    curve = metrics.get("curve_nrmse", {})
    gates["curve_nrmse"] = (
        curve.get("status") == "EVALUATED"
        and curve.get("nrmse") is not None
        and curve["nrmse"] <= THRESHOLDS["curve_nrmse_max"]
    ) if curve.get("status") == "EVALUATED" else None

    required_gates = [value for value in gates.values() if value is not None]
    status = "PASS" if required_gates and all(required_gates) else "FAIL"
    return {
        "status": status,
        "paper_split": split,
        "thresholds": dict(THRESHOLDS),
        "metrics": metrics,
        "gates": gates,
        "held_out_tuning_policy": "BLIND_HELD_OUT_NOT_USED_FOR_TUNING",
    }
