# Callout QC full-component bbox contract — focused validation handoff

Repository: Tuzhidingdong/Figure_digitization
Target branch: fix/callout-qc-full-component-bbox-contract
Validation baseline / parent: 4362cd844a5aa4ed10e244097dc13ac0e99686e3
Required test-contract commit: d044b9408467648d7bf0861b5d6d10b4cb6ead4a
Production algorithm version: 0.8.2 (unchanged)

This is a test-contract correction only. No production source file or extraction behavior changed. The local Windows focused test has not yet been run.

## 1. Protected state

Work only in E:\Zinc_batters_datas\Figure_digitization.

Before syncing, inspect the current branch and git status. Preserve all local changes and untracked items, including .agents/, __pycache__/, all test_outputs/, STATUS.md backup, stash@{0}, and all prior review artifacts.

Do not use git reset --hard, git clean, stash pop/drop, or git add -A. Do not overwrite conflicting local files. Use explicit paths only.

Do not modify main, any previous diagnostic/fix/review branch, PR #22, or TASK_PLAN_v1.4.1.md. Do not merge a PR or publish a release.

## 2. Why the expected bbox is changing

The synthetic test draws:
- a rectangle with primitive bbox [82,8,126,18];
- short dashed annotation marks above it, spanning the component to y=4 and x=127.

The color-component detector rejects these pixels as one connected component and reports the full source component bbox:
[82,4,127,19]

The previous assertion expected only the rectangle primitive bbox. That is not the object represented by the rejected-component QC record. The production behavior is correct to preserve the complete detected component extent. Shrinking this record to [82,8,126,18] would discard evidence about pixels that were part of the rejected component.

This branch updates only the two bbox assertions in:
tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations

Both detector QC and trace QC now assert the full connected-component bbox [82,4,127,19]. A comment explains why. No production source, algorithm version, path extraction threshold, junction rule, or scientific expectation changed.

All meaningful scientific assertions remain:
- exactly one exclusion record;
- full component bbox is retained;
- reason is PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS;
- source_qc_rejection_reason and source_path_qc_reason are preserved;
- nested ambiguous junction detail is retained;
- the waveform returns 366 ordered coordinates;
- callout-area coordinates remain zero.

## 3. Sync and focused validation

Safely sync/switch to fix/callout-qc-full-component-bbox-contract and confirm local HEAD contains d044b9408467648d7bf0861b5d6d10b4cb6ead4a.

Because the preceding full four-file run already passed 158/159 tests and the only failure was this stale bbox expectation, do NOT rerun the full suite. Use existing Python 3.13.9 and perform:
1. compile/import check (optional if no production source changed);
2. run the exact failed node ONCE:

    python -m pytest "tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations" -o addopts="" -q

Record exit code, pass/fail and duration. Do not change production code or weaken any assertion if it fails. If it fails, report the exact actual/expected values and stop; do not enter a test loop.

The already-completed four-file suite result on the parent remains:
159 collected, 158 passed, 1 failed, 0 skipped, exit 1, 192.50 s.
All non-bbox assertions and real-image validation passed. This focused run validates only the corrected assertion contract; do not describe it as a new four-file full-suite pass.

## 4. No real-image rerun required

No production code changed, so do not rerun extraction or regenerate images. Preserve the existing parent validation artifacts and evidence:
- callout QC record emitted once in detector and trace QC;
- source_qc_rejection_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW;
- source_path_qc_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW;
- nested junction detail = UNSUPPORTED_JUNCTION_PORT_COUNT, 7 ports;
- source callout component bbox = [82,4,127,19], 288 px;
- waveform bbox = [11,25,179,77], 366 ordered coordinates;
- callout coordinates in selected path = 0.

P8 panel a/d, P3 OCR-associated review fragments, panel c and unresolved Y-axis mappings remain exactly as recorded in the parent validation report. No point-level accuracy claim is authorized.

## 5. Upload

Upload only:
review/callout-qc-full-component-bbox-contract/focused_validation_report.md

The report should state:
- code/test commit ancestry and local HEAD;
- confirmation only tests/test_core.py changed in this branch;
- focused pytest exact command, exit code and duration;
- whether the corrected bbox contract passed;
- explicit reminder that the 159-test four-file result remains 158/159 from the parent and was not rerun;
- link/reference to the parent validation report.

Use explicit git add for that single report path, commit and push only to fix/callout-qc-full-component-bbox-contract. Do not upload new PNGs, PDFs/SI, raw OCR or unrelated files.

Return final commit SHA, focused-test result and report link. Stop. No merge, release, or protected-branch modification.
