# QC evidence object contract — local validation handoff

Repository: Tuzhidingdong/Figure_digitization
Target branch: fix/qc-evidence-object-contract
Validation baseline / parent: 053dad76ff879428c59e2c27b594cc39cd991bcf
Required test-contract commit: 7299378c0664ee956847557a77637503d7f8edd2
Production algorithm version: 0.8.2 (unchanged)

This branch corrects the integration-test object reference to match the already implemented QC data contract. No production source file or extraction behavior is changed. Local Windows validation has not yet been run.

## 1. Protected state

Work only in E:\Zinc_batters_datas\Figure_digitization.

Before syncing, inspect the current branch and git status. Preserve all local changes and untracked items, including .agents/, __pycache__/, every test_outputs/ directory, STATUS.md backup, stash@{0}, and all existing review artifacts.

Do not use git reset --hard, git clean, stash pop/drop, or git add -A. Do not overwrite conflicting local files. Use explicit paths only.

Do not modify main, any previous diagnostic/fix/review branch, PR #22, or frozen TASK_PLAN_v1.4.1.md. No merge or release is authorized.

## 2. Agreed QC data contract

The production implementation intentionally exposes two related but distinct objects:

### Full evidence object

Location:
detected["excluded_partial_branches"][0]

This object retains:
- full connected-component bbox [82,4,127,19];
- source_qc_rejection_reason;
- source_path_qc_reason;
- full nested path_qc;
- path_qc.ambiguous_junction_clusters, including the 33-pixel / 7-port unsupported junction detail;
- review-only classification and decision basis.

The same full evidence object is also retained under:
trace_qc["excluded_partial_branches"][0].

### Review summary object

Location:
the matching item in detected["rejected_components"] whose rejection_reason is PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS.

This is deliberately a concise review summary. It provides the exclusion reason, bbox, source reasons, classification and summary fields. It does NOT promise to duplicate the complete path_qc payload.

Do not change production code to copy large nested path_qc objects into this summary. Do not change the runtime contract simply to satisfy the former incorrect test lookup.

## 3. Test correction in this branch

Only tests/test_core.py is changed.

The integration test now:
1. Reads the complete exclusion record from detected["excluded_partial_branches"][0].
2. Checks its source reason fields and enclosing path_qc.reason.
3. Checks path_qc.ambiguous_junction_clusters[0] for:
   - reason = UNSUPPORTED_JUNCTION_PORT_COUNT;
   - junction_pixels = 33;
   - port_count = 7;
   - seven port coordinates.
4. Reads the matching rejected_components item separately and validates only its public summary fields (bbox, source reasons and classification).
5. Checks the trace QC exclusion record independently, including full bbox and nested junction detail.
6. Retains the existing curve/data invariants:
   - waveform has ordered coordinates and preserves vertical segments;
   - callout-region pixels do not enter the selected waveform path;
   - exactly one exclusion record is emitted;
   - bbox is the full connected component [82,4,127,19].

This corrects a record-location mismatch in the test. It does not weaken scientific assertions and does not alter production code or algorithm version.

## 4. Sync and one full validation run

Safely sync/switch to fix/qc-evidence-object-contract only after protecting the current worktree. Confirm local HEAD contains 7299378c0664ee956847557a77637503d7f8edd2.

Use the existing Python 3.13.9 environment. Run compile/import checks, then execute the four relevant test files exactly ONCE on this final candidate HEAD:

    python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0

Record:
- actual collected / passed / failed / skipped;
- exit code;
- duration;
- exact failed node IDs and relevant assertion details if anything fails.

Previous full-suite parent result was 159 collected, 158 passed, 1 failed, 0 skipped, exit 1, 192.50 s. The sole known failure was the incorrect lookup of path_qc on a review-summary record. Do not assume the result is now passing; report the actual new run.

Do not run the focused test separately. Do not run a second broad test suite. If the one full run fails, inspect and report the failure, then STOP without adding another patch or repeating tests. Do not weaken scientific assertions.

## 5. No production image rerun

This branch changes only the test file and handoff document. No production source changed. Therefore:
- do not rerun OCR;
- do not rerun digitization;
- do not regenerate comparison images;
- do not re-upload the previous six images.

Carry forward prior real-image evidence without claiming it was freshly revalidated on this test-only branch:
- P8 panel a red: 22,146 points / 178 segments;
- P8 panel a blue without urea: 1,835 points / 26 segments;
- P8 panel d: 317 + 319 red and 317 blue;
- P3 OCR-associated strokes remain review-only;
- P3 Y assignment, P8 panel b/c and scientific point-level accuracy remain unresolved as documented.

## 6. Upload and stop

Upload only:
review/qc-evidence-object-contract/validation_report.md

The report must record:
- local HEAD and required commit ancestry;
- diff scope (tests/test_core.py plus this handoff only; src/ diff 0);
- exact one-pass four-file command and result;
- full evidence object versus review summary contract;
- explicit statement that no image/OCR rerun occurred and previous visual metrics are inherited evidence, not a new run.

Use explicit git add for this single report file. Commit and push only to fix/qc-evidence-object-contract. Do not use git add -A.

Return commit SHA and report link. Stop. No merge, release, production code changes, or protected-branch changes.
