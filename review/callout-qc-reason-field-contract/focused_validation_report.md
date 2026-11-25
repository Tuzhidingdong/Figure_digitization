# Focused validation — callout QC reason-field contract

Date: 2026-11-25
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/callout-qc-reason-field-contract`
Local HEAD: `aee0c2c8983edecc149e090a41d7aa381bf3ef38`
Validation baseline / parent: `0b85ebf26f7b7f190e74002a9b0b9ff453ca370e`
Required test-contract commit `4b88bcdd7a85f8ee778aae4af0487c0cf2ff41c5` is an ancestor of HEAD.
Production algorithm version: `0.8.2` (unchanged).

## 1. Scope and protection

Existing project only; no clone/worktree, no OCR rerun, no paper/PDF/SI access, no dependency install,
no extraction and no image regeneration. Before sync the tracked tree was clean; the untracked
`.agents/`, `__pycache__/`, every `test_outputs/`, `stash@{0}`, the `STATUS.md` backup and all prior
review artifacts are intact. No `reset --hard`, `git clean`, stash pop/drop or `git add -A`.
`main`, all previous fix/review branches, PR #22 and the frozen `TASK_PLAN_v1.4.1.md` were not touched.

Diff from parent (`0b85ebf…`) contains only:
- `review/callout-qc-reason-field-contract/LOCAL_AGENT_VALIDATION.md` (this handoff);
- `tests/test_core.py` — `source_path_qc_reason` expectation corrected to
  `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`, plus a new assertion reading the nested
  `path_qc.ambiguous_junction_clusters[0].reason`.

Production source diff (`src/`): **0 files**. No extraction threshold, junction rule, reason-field
hierarchy or scientific expectation was changed by production code in this round.

## 2. Focused test (run once, as instructed)

```
python -m pytest "tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations" -o addopts="" -q
```

| Metric | Value |
|---|---|
| Exit code | **1** |
| Result | **1 failed in 2.59s** |
| Full four-file suite rerun | **No** |

The focused test still fails. Exact failure:

```
>       assert excluded_record["path_qc"]["ambiguous_junction_clusters"][0]["reason"] == (
            "UNSUPPORTED_JUNCTION_PORT_COUNT"
        ), excluded_record
E       KeyError: 'path_qc'
tests/test_core.py:1804
```

The earlier assertions in the same test now pass, including:
- `SINGLE_MONOTONIC_COLOR_BAND`, `branch_count == 1`;
- exactly one exclusion record in detector QC;
- full connected-component bbox `[82,4,127,19]`;
- `rejection_reason == PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS`;
- `source_qc_rejection_reason == UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`;
- `source_path_qc_reason == UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`.

## 3. Reason hierarchy and record-location mismatch

The reason hierarchy on the **excluded partial branch record** (verified in the parent round's direct
probe) is:

| Level | Field | Value |
|---|---|---|
| public component rejection | `source_qc_rejection_reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` |
| enclosing path QC reason | `source_path_qc_reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` |
| nested junction diagnosis | `path_qc.ambiguous_junction_clusters[0].reason` | `UNSUPPORTED_JUNCTION_PORT_COUNT` (33 junction pixels, 7 ports) |

The current failure is a **record-location mismatch**, not a wrong reason value: the
`excluded_record` selected from `detected["rejected_components"]` is the appended review-summary
entry, which carries `source_*_reason`, `bbox`, `pixel_count`, `classification`, `decision_basis`
and a `path_count`, but **not** the nested `path_qc` object. The nested `path_qc` (with the port-count
cluster reason) lives on the full rejected component entry and on
`excluded_partial_branches[0]` in the detector QC, as recorded in the parent validation.

Per the handoff, the exact assertion and actual/expected situation were recorded and no further
test was run. No production code or test expectation was changed to make the test pass.

## 4. Parent evidence (unchanged, not re-measured here)

From the completed parent validation (`4362cd8…` / `0b85ebf…` reports):
- detector and trace QC each carry exactly one exclusion record with full component bbox
  `[82,4,127,19]` and 288 px;
- waveform `[11,25,179,77]` → **366 ordered coordinates**; callout-region coordinates in the
  selected path: **0**;
- nested ambiguous junction detail: `UNSUPPORTED_JUNCTION_PORT_COUNT`, 7 ports;
- P8 panel a 22,146 red pts/178 segments and 1,835 blue pts/26 segments; panel d 317+319 red and
  317 blue; P3 OCR-associated short strokes kept review-only with no production filter.

Parent report:
`https://github.com/Tuzhidingdong/Figure_digitization/blob/4362cd844a5aa4ed10e244097dc13ac0e99686e3/review/callout-qc-remove-pixel-ratio-gate/validation_report.md`

## 5. Four-file full-suite status (explicit reminder)

The four-file suite was **not rerun** in this round. Its last completed result on the parent remains:
**159 collected, 158 passed, 1 failed, 0 skipped, exit code 1, 192.50s**. This focused run validates
only the corrected reason-field test contract and is **not** a new four-file full-suite pass; the
focused run itself still fails on the nested-`path_qc` lookup. No point-level scientific accuracy
claim is made; no independent annotated benchmark exists.

## 6. Upload

Only this `focused_validation_report.md` is committed to
`review/callout-qc-reason-field-contract/` on this branch. No PNG, PDF/SI, raw OCR or unrelated
artifact is included.
