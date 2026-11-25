# Focused validation — callout QC full-component bbox contract

Date: 2026-11-25
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/callout-qc-full-component-bbox-contract`
Local HEAD: `4ad9a7303ec281f3baf01b76a9fedc5f6582ffdb`
Validation baseline / parent: `4362cd844a5aa4ed10e244097dc13ac0e99686e3`
Required test-contract commit `d044b9408467648d7bf0861b5d6d10b4cb6ead4a` is an ancestor of HEAD.
Production algorithm version: `0.8.2` (unchanged).

## 1. Scope and protection

Existing project only; no clone/worktree, no OCR rerun, no paper/PDF/SI access, no new dependency,
no extraction and no image regeneration. Before sync the tracked tree was clean; the untracked
`.agents/`, `__pycache__/`, all `test_outputs/`, `stash@{0}`, the `STATUS.md` backup and all prior
review artifacts remain intact. No `reset --hard`, `git clean`, stash pop/drop or `git add -A`.
`main`, all previous fix/review branches, PR #22 and `TASK_PLAN_v1.4.1.md` were not modified.

Diff from parent (`4362cd8…`) contains only:
- `review/callout-qc-full-component-bbox-contract/LOCAL_AGENT_VALIDATION.md` (handoff document);
- `tests/test_core.py` — two bbox expectations changed from `[82,8,126,18]` to `[82,4,127,19]`
  with explanatory comments, plus an added assertion on `source_path_qc_reason`.

Production source diff (`src/`): **0 files**. No algorithm version, threshold, junction rule,
extraction behaviour or scientific expectation was weakened by this validation.

## 2. Focused test (run once, as instructed)

```
python -m pytest "tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations" -o addopts="" -q
```

| Metric | Value |
|---|---|
| Exit code | **1** |
| Result | **1 failed in 3.88s** |
| Collected in this focused run | 1 |
| Full suite rerun | **No** |

Failing node:
`tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`

Exact failure:

```
>  assert excluded_record.get("source_path_qc_reason") == (
       "UNSUPPORTED_JUNCTION_PORT_COUNT"
   ), excluded_record
E  AssertionError: ...
E  assert 'UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW' == 'UNSUPPORTED_JUNCTION_PORT_COUNT'
tests/test_core.py:1798
```

## 3. Bbox contract confirmation

The corrected bbox assertions use the full connected component in both places:

| Location | Expected bbox | Status in this focused run |
|---|---|---|
| `detect_monotonic_color_branches()` → `excluded_partial_branches[0]["bbox"]` | `[82,4,127,19]` | **passed** (execution proceeded past line 1782) |
| `trace_monotonic_color()` QC → `excluded_partial_branches[0]["bbox"]` | `[82,4,127,19]` | not reached in this run because the earlier `source_path_qc_reason` assertion failed; the parent-round direct probe already showed trace QC carrying the same full component bbox `[82,4,127,19]` |

The bbox represents the complete rejected component: rectangle primitive `[82,8,126,18]` plus the
short dashed marks above it (y down to 4, x through 127). This is the object the QC record describes.

The focused test still fails, but on a **different assertion** than the parent run: after the bbox
checks, the test requires `source_path_qc_reason == "UNSUPPORTED_JUNCTION_PORT_COUNT"`, while the
production record reports `"UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW"`. The port-count reason
is preserved in the nested `path_qc.ambiguous_junction_clusters[0].reason`, not in
`source_path_qc_reason`. Per the handoff, this was reported and the run was not repeated; no test
expectation or production code was changed.

## 4. Parent evidence (unchanged, not re-measured here)

From the completed parent validation (`4362cd8…`, see its `validation_report.md`):
- exactly one exclusion record in detector QC and trace QC;
- `source_qc_rejection_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`;
- `source_path_qc_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`;
- nested junction detail: `UNSUPPORTED_JUNCTION_PORT_COUNT`, 7 ports;
- callout component `[82,4,127,19]`, 288 px, classification
  `UNRESOLVED_COMPACT_COMPONENT_RETAINED_IN_REVIEW_QC`;
- waveform `[11,25,179,77]`, **366 ordered coordinates**; callout-area coordinates in the selected
  path: **0**;
- P8 panel a 22,146 red pts/178 segments and 1,835 blue pts/26 segments; panel d 317+319 red and
  317 blue; P3 OCR-associated short strokes kept review-only; no new production filter.

## 5. Four-file full-suite status (explicit reminder)

The four-file suite was **not rerun** in this round. Its last completed result on the parent
remains: **159 collected, 158 passed, 1 failed, 0 skipped, exit code 1, 192.50s**. The single failure
was the now-corrected stale bbox expectation. This focused run validates only the corrected test
contract and is **not** a new four-file full-suite pass. The focused run itself still fails on the
`source_path_qc_reason` value, so the contract is not yet clean.

Parent report:
`https://github.com/Tuzhidingdong/Figure_digitization/blob/4362cd844a5aa4ed10e244097dc13ac0e99686e3/review/callout-qc-remove-pixel-ratio-gate/validation_report.md`

No point-level scientific accuracy claim is made; no independent annotated benchmark exists.

## 6. Upload

Only this `focused_validation_report.md` is committed to
`review/callout-qc-full-component-bbox-contract/` on this branch. No PNG, PDF/SI, raw OCR or
other local artifact is included.
