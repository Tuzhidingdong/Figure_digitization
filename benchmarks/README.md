# Gold Benchmark protocol (V2.1)

The Gold Benchmark is a paper-level, evidence-grounded acceptance gate. It is not populated with fabricated test-paper labels. Humans annotate a small frozen benchmark; production papers are not routed to manual review by this benchmark.

## Minimum coverage

The gate remains **NOT_EVALUATED** until the frozen gold set contains all of the following:

- At least 9 paired papers, with at least 3 papers each from Battery, AOP and PFAS.
- At least 30 figure-caption pairs.
- At least 60 panels.
- At least 30 distinct sample identities.
- At least 60 explicit, legible legend-to-sample opportunities.
- At least 50 synthesis-condition assertions and 50 experimental-condition assertions.

Insufficient data does not lower thresholds and does not produce a pass.

## Frozen split

Split by paper, stratified by domain, into approximately 70% development and 30% blind held-out. Every figure, panel, sample, series and condition from a paper stays in that paper's partition. The held-out partition is not used for prompt/rule/threshold tuning. With the minimum of three papers per domain, integer allocation is two development papers and one held-out paper per domain.

## Metric definitions and gates

| Metric | Definition | Gate |
|---|---|---:|
| Figure-caption precision | Correct predicted figure-caption pairs / all predicted pairs | ≥ 98% |
| Figure-caption recall | Correct predicted pairs / all gold pairs | ≥ 95% |
| False cross-association | Any predicted pair not in gold | 0 |
| Panel split/clause precision | Correct panel-clause assignments / all predicted assignments | ≥ 95% |
| Panel split/clause recall | Correct assignments / all gold assignments | ≥ 90% |
| Wrong panel assignment rate | Wrong predicted panel assignments / all predicted assignments | ≤ 2% |
| Sample identity/merge precision | Correct same-sample mention pairs / predicted same-sample pairs | ≥ 95% |
| Sample identity/merge recall | Correct same-sample mention pairs / gold same-sample pairs | ≥ 80% |
| False sample merges | Predicted entity groups containing mentions from multiple gold samples | 0 |
| Series-to-sample precision | Correct links / all predicted links, on explicit legible legend opportunities | ≥ 92% |
| Series-to-sample recall | Correct links / all gold explicit opportunities | ≥ 75% |
| Wrong series link rate | Incorrect predicted links / all predicted links | ≤ 3% |
| Condition kind+scope precision | Correct condition type and scope / predicted condition assertions | ≥ 95% |
| Condition kind+scope recall | Correct assertions / all gold assertions | ≥ 70% |
| False scope attachment rate | Incorrectly attached scope assertions / all predicted scope assertions | ≤ 3% |
| Curve NRMSE | RMSE divided by gold range, only with independent numerical ground truth | ≤ 2.5% |

An unresolved prediction is not counted as correct; its gold item remains in the recall denominator. An empty prediction set cannot pass a non-empty gold task. If there is no independent numerical curve ground truth, NRMSE is explicitly NOT_EVALUATED rather than inferred from image pixels.

## Running

Prepare two versioned JSON files: a gold manifest and a prediction report containing development and blind-held-out metrics. Do not store confidential paper files or personal data in the repository. The evaluator returns `NOT_EVALUATED` if the coverage floor or blind held-out report is missing.

```powershell
sfd benchmark --manifest gold_manifest.json --predictions prediction_metrics.json --output gold_benchmark_report.json
```

The benchmark harness is deterministic and does not call an LLM. The metrics are software acceptance evidence, not a substitute for domain-expert review of annotations or independent ground truth.
