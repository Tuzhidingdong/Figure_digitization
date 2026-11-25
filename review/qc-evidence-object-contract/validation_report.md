# QC evidence object contract — validation report

Date: 2026-11-25
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/qc-evidence-object-contract`
Local HEAD: `4495a4a5d945ff7fcacc427e0f0dfd6a16c12f4c`
Validation baseline / parent: `053dad76ff879428c59e2c27b594cc39cd991bcf`
Required test-contract commit `7299378c0664ee956847557a77637503d7f8edd2` is an ancestor of HEAD.
Production algorithm version: `0.8.2` (unchanged).

## 1. Protected state and diff scope

Existing project only; no clone/worktree. Before sync the tracked tree was clean and only
`.agents/`, `__pycache__/` and `test_outputs/` were untracked. `stash@{0}`, the `STATUS.md` backup,
all historical `test_outputs/` directories and all prior review artifacts are intact. No
`reset --hard`, `git clean`, stash pop/drop or `git add -A`. `main`, all earlier fix/review branches,
PR #22 and the frozen `TASK_PLAN_v1.4.1.md` were not modified. No production source file was edited.

Diff from parent (`053dad7…`):
- `review/qc-evidence-object-contract/LOCAL_AGENT_VALIDATION.md` — handoff document;
- `tests/test_core.py` — record-location correction in
  `test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`.

Production source diff (`src/`): **0 files**. Extraction thresholds, junction rules, version and
all scientific invariants are unchanged.

Compile/import checks: `compileall -q src/scientific_figure_data` exit 0; core module imports exit 0
on Python 3.13.9.

## 2. One-pass four-file test (executed once on final HEAD)

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0
```

| Metric | Value |
|---|---|
| Collected / executed | **159** |
| Passed | **159** |
| Failed | **0** |
| Skipped | **0** |
| Exit code | **0** |
| Duration | **197.12 s** (0:03:17) |
| Failed node IDs | none |
| Log | `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_qc_evidence_object.log` |

No focused test was run separately and no second broad suite was executed. The parent result
(159 collected / 158 passed / 1 failed / exit 1 / 192.50 s) is superseded by this single run.

## 3. Full evidence object vs review summary — agreed contract

**Full evidence object** — `detected["excluded_partial_branches"][0]` (and identically
`trace_qc["excluded_partial_branches"][0]`). The test now reads the nested evidence from here:

| Field | Value asserted |
|---|---|
| `bbox` | `[82,4,127,19]` (full connected component, rectangle plus upper dashes) |
| `source_qc_rejection_reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` |
| `source_path_qc_reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` |
| `path_qc.reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` |
| `path_qc.ambiguous_junction_clusters[0].reason` | `UNSUPPORTED_JUNCTION_PORT_COUNT` |
| `junction_pixels` / `port_count` / `len(ports)` | 33 / 7 / 7 |

**Review summary object** — the matching item in `detected["rejected_components"]` with
`rejection_reason = PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS`. The test now checks
only its public summary fields: `bbox` equal to the full evidence bbox, both `source_*_reason`
fields, and `classification = UNRESOLVED_COMPACT_COMPONENT_RETAINED_IN_REVIEW_QC`. It no longer
requires this deliberately compact summary to duplicate the full `path_qc` payload.

Data invariants that remain asserted and now pass: exactly one exclusion record in detector and
trace QC; waveform ordered coordinates with preserved vertical portions; callout-region pixels
absent from the selected path (0 points); full component bbox preserved. No scientific assertion
was weakened — the correction only reads the nested evidence from the object that actually carries
it, and validates the summary on its own terms.

## 4. Real-image evidence — inherited, not re-validated this round

This branch changes only a test file and the handoff document. **No OCR, extraction, digitization or
image generation was rerun**, and no visual result is claimed as freshly verified here. The
following figures are inherited from the parent validation runs and remain unchanged because
production code did not change:

- P8 panel a red 22,146 points / 178 segments; blue `without urea` 1,835 points / 26 segments;
- P8 panel d 317 + 319 red branches and 317 blue branch, second red branch `NEEDS_REVIEW_PARTIAL_PATH`;
- P3 OCR-associated short strokes remain review-only with no production filter;
- P3 Y assignment `UNASSIGNED`, panel b `UNRESOLVED`, panel c X-semantics gate, and all
  `review_state = NEEDS_REVIEW` remain unresolved as previously reported;
- no independent annotated point benchmark exists, so no point-level accuracy claim is made.

Parent report (evidence source):
`https://github.com/Tuzhidingdong/Figure_digitization/blob/053dad76ff879428c59e2c27b594cc39cd991bcf/review/callout-qc-reason-field-contract/focused_validation_report.md`

## 5. Upload

Only this `validation_report.md` is committed to `review/qc-evidence-object-contract/` on this
branch. No PNG, PDF/SI, raw OCR, unrelated output or temporary file is included. No merge, release
or protected-branch modification was performed.
