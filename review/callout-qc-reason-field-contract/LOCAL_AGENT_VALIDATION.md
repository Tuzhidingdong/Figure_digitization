# Callout QC reason-field hierarchy — focused test-contract correction

Repository: Tuzhidingdong/Figure_digitization
Target branch: fix/callout-qc-reason-field-contract
Validation baseline / parent: 0b85ebf26f7b7f190e74002a9b0b9ff453ca370e
Required test change: 4b88bcdd7a85f8ee778aae4af0487c0cf2ff41c5
Production algorithm version: 0.8.2 (unchanged)

This is a test-only correction. No production source or extraction behavior changed. The local focused test has not yet been run.

## 1. Protected state

Work only in E:\Zinc_batters_datas\Figure_digitization.

Before sync, inspect the current branch and git status. Preserve local changes and untracked files, including .agents/, __pycache__/, all test_outputs/, STATUS.md backup, stash@{0}, and every prior review artifact.

Do not use git reset --hard, git clean, stash pop/drop or git add -A. Do not overwrite conflicting local files. Use explicit paths only.

Do not modify main, prior diagnostic/fix/review branches, PR #22, or TASK_PLAN_v1.4.1.md. No merge or release is authorized.

## 2. Correct reason-field hierarchy

The excluded record has three distinct levels of reason evidence:

1. source_qc_rejection_reason is the public/component rejection reason:
   UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW

2. source_path_qc_reason mirrors the enclosing rejected component's nested path_qc.reason:
   UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW

3. The more specific junction diagnosis is nested in:
   path_qc.ambiguous_junction_clusters[0].reason
   value: UNSUPPORTED_JUNCTION_PORT_COUNT

The previous test incorrectly expected level 3's value in level 2's field. The production record is correct; do not change production code or flatten/duplicate the reason hierarchy.

This branch changes only the erroneous assertion in:
tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations

It now asserts source_path_qc_reason equals the enclosing path_qc.reason value and separately asserts the nested ambiguous_junction_clusters[0].reason equals UNSUPPORTED_JUNCTION_PORT_COUNT.

The full connected-component bbox expectation remains [82,4,127,19] in both detector and trace QC.

All other assertions remain unchanged:
- exactly one exclusion record;
- expected PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS rejection reason;
- source_qc_rejection_reason preserved;
- full rejected-component bbox retained;
- waveform ordered coordinates are returned;
- callout-region coordinates remain zero;
- trace QC carries the same full component bbox.

## 3. Sync and focused validation

Safely sync/switch to fix/callout-qc-reason-field-contract only after preserving the current worktree. Confirm local HEAD contains 4b88bcdd7a85f8ee778aae4af0487c0cf2ff41c5.

No production file changed. Use the existing Python 3.13.9 environment and run the exact previously failing focused test ONCE:

    python -m pytest "tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations" -o addopts="" -q

Record exit code, pass/fail and duration. Do not run the four-file full suite again; the parent has 159 collected, 158 passed, 1 failed, 0 skipped, exit 1, 192.50 s. Do not run a repeated test loop.

If the focused test fails, record the exact assertion and actual/expected values, then stop. Do not change production code or weaken assertions.

If the focused test passes, report only that this focused test passed. Do not claim a new four-file suite pass.

## 4. No real-image rerun

No production code or algorithm version changed. Do not rerun OCR, extraction or image generation.

Preserve the previous validated evidence:
- one detector and trace exclusion record;
- waveform 366 ordered coordinates;
- callout selected-path coordinates 0;
- complete rejected-component bbox [82,4,127,19];
- source_qc_rejection_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW;
- source_path_qc_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW;
- nested ambiguous_junction_clusters[0].reason = UNSUPPORTED_JUNCTION_PORT_COUNT;
- P8 panel-a and panel-d counts and P3 OCR-associated review-only fragments as recorded in the parent validation.

Parent report:
https://github.com/Tuzhidingdong/Figure_digitization/blob/4362cd844a5aa4ed10e244097dc13ac0e99686e3/review/callout-qc-remove-pixel-ratio-gate/validation_report.md

The parent four-file result remains 158/159 and was not rerun here. No point-level accuracy claim is authorized.

## 5. Upload

Upload only:
review/callout-qc-reason-field-contract/focused_validation_report.md

The report should record:
- local HEAD and ancestry of 4b88bcdd7a85f8ee778aae4af0487c0cf2ff41c5;
- confirmation only tests/test_core.py changed in this branch (plus this handoff);
- exact focused command, exit code, pass/fail and duration;
- exact source/path/cluster reason hierarchy;
- explicit note that the four-file suite was not rerun and remains 158/159 on the parent.

Use explicit git add for that single report file and commit/push only to fix/callout-qc-reason-field-contract. Do not upload new images, PDFs/SI, raw OCR or unrelated artifacts.

Return final commit SHA, focused result and report link. Stop. No merge, release, or protected-branch modification.
