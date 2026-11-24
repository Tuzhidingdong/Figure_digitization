# Callout exclusion QC — remove the inappropriate pixel-count ratio gate

Repository: Tuzhidingdong/Figure_digitization
Target branch: fix/callout-qc-remove-pixel-ratio-gate
Validation baseline / parent: 946bff14994243ed88ea3391fe0fd273c48b780f
Minimum required code commit (must be an ancestor of local HEAD): 947141f82a18a6264872c91d7e26ae438144abc5
Algorithm version: 0.8.2

This is a narrow corrective candidate. It has NOT been run in the local Windows environment and is not accepted yet.

## 1. Protected state

Work only in E:\Zinc_batters_datas\Figure_digitization.

Before sync, inspect the current branch and git status. Preserve all local changes and untracked items, including .agents/, __pycache__/, every test_outputs/ directory, old STATUS.md backup, stash@{0}, and all review artifacts.

Do not use git reset --hard, git clean, stash pop/drop or git add -A. Do not overwrite conflicting files. Use explicit paths only.

Do not modify main, review/real-image-reconstruction-20261124, fix/junction-local-ambiguity-recovery, fix/partial-raster-fragment-preservation, fix/partial-branch-qc-preservation, fix/callout-exclusion-record-and-glyph-qc, PR #22, or frozen TASK_PLAN_v1.4.1.md. No PR merge or release is authorized.

## 2. Exact production change

The helper _compact_rejected_review_candidates() records a compact, spatially separate component rejected by the component-level UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW gate, but does not promote it to a curve.

The previous helper also required:
candidate_pixel_count <= 0.30 * selected_path_pixel_count

The latest real failing probe demonstrated why this is invalid for QC bookkeeping:
- selected waveform bbox [11,25,179,77], 366 pixels;
- rejected callout bbox [82,4,127,19], 288 pixels;
- X span 45 <= 168 * 0.40 = 67.2;
- Y span 15 <= 52 * 0.50 = 26;
- non-overlapping bboxes;
- pixel count 288 > 366 * 0.30 = 109.8.

Thus the old pixel-ratio criterion alone suppressed the QC exclusion record. The candidate removes that pixel-ratio selection criterion. Spatial non-overlap and relative bbox width/height constraints remain. Pixel counts are retained in the QC decision_basis for transparency, with pixel_count_ratio_used_for_selection = false.

The helper checks both the component-level rejection reason and nested path-QC reason, and preserves both in:
- source_qc_rejection_reason
- source_path_qc_reason

The underlying path_qc.ambiguous_junction_clusters continues to preserve the specific cluster reason (e.g. UNSUPPORTED_JUNCTION_PORT_COUNT). The record classification remains UNRESOLVED_COMPACT_COMPONENT_RETAINED_IN_REVIEW_QC, not a definite annotation label.

## 3. Regression protection

The direct helper regression now uses the exact observed high-pixel-count case: 288-pixel callout vs 366-pixel thin waveform. It asserts that the record is emitted and the original reasons/details are preserved.

The existing synthetic waveform + callout integration test still asserts:
- waveform ordered coordinates are returned;
- callout coordinates are not returned;
- excluded_partial_branches contains exactly one record;
- the excluded bbox matches the callout;
- the QC reason is PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS.

Algorithm version is bumped to 0.8.2; the report version assertion is updated.

No trace extraction thresholds, junction pairing rules, curve path admission rules, or P3 OCR filters are changed by this patch.

## 4. Sync and one-pass tests

Safely sync/switch to fix/callout-qc-remove-pixel-ratio-gate only after protecting the current worktree. Confirm local HEAD contains 947141f82a18a6264872c91d7e26ae438144abc5.

Use existing Python 3.13.9. Run compile/import checks and execute the four relevant test files ONCE:

    python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0

Expected collected count remains 159 (the existing helper test was strengthened, not duplicated), unless unrelated collection configuration changes. Record actual collected/passed/failed/skipped, exit code, duration and exact node IDs.

Do not weaken the callout QC, P8 panel-d 2-red/1-blue, P8 panel-a segment, five-way junction, full-span partial-QC branch, or compact ring/glyph unit assertions.

Do not run a broad test loop. If the exact callout test fails, inspect it and perform at most one focused rerun after an authorized correction. If the suite passes, do not rerun it.

## 5. Real-image validation — cached OCR only

Use unchanged fixtures:
- tests/fixtures/real_figures/P3_02.png
- tests/fixtures/real_figures/P8_06.png

Use cached OCR JSON only. Do not rerun OCR, read papers/PDF/SI, or install dependencies.

Fresh output:
test_outputs/reconstruction_callout_qc_bbox_only_20261124/

Compare with:
test_outputs/reconstruction_partial_branch_qc_20261124/
and previous validation outputs, all preserved.

### P8_06
- Panel-a red 22,146 points / 178 segments and blue without urea 1,835 points / 26 segments must remain.
- Preserve each segment boundary, no invented connectors.
- The rejected callout must stay out of curve points while appearing as one exclusion QC record with:
  - source_qc_rejection_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW
  - source_path_qc_reason equal to the nested path-QC reason (report its actual value)
  - original ambiguous cluster detail preserved.
- Panel d remains two red branches (317 + 319 points) and one blue branch (317 points); the second red remains partial-review.

### P3_02 — no new filtering in this patch

The previous P3 diagnostic established:
- Orange _color_01_branch_03: 41 points, source bbox [1036,125,1076,126], chord/length 0.951, 4 direction changes; fully overlaps OCR box Bulk Te—Discharge (confidence 0.89585).
- Purple _color_03_branch_03: 14 points, source bbox [1181,125,1194,126], chord/length 0.940, 1 direction change; overlaps OCR boxes Charge (0.98309) and Bulk Te—Discharge (0.89585).
- These are not geometrically closed paths (chord/length is near 1); OCR overlap suggests legend/text-associated strokes, but does not prove whether they are legend swatches, underlines or glyph strokes.

Do not add any production filter in this round. Keep them review-only and report whether their geometry/counts remain unchanged. Do not delete paths solely because a broad OCR text bbox overlaps them. A future OCR-assisted review flag would need to distinguish line swatches and genuine curves crossing text.

The previous more loop-like candidate _color_01_branch_04 (28 points, chord/length 0.235, bbox [1052,97,1060,105]) overlaps Te NSs—Discharge; also leave it review-only unless independently validated.

Purple coverage beyond x≈280 remains unresolved. Do not infer coordinates from mask pixels.

### All panels

Report per-series points/segments, extraction status, QC status, axis assignment and unresolved numeric fields. Panel c remains blocked by the existing X-semantics gate unless current evidence supports monotonic X; do not invent labels. No point-level accuracy claim without an independent point benchmark.

## 6. Upload

Upload only these items to:
review/callout-qc-remove-pixel-ratio-gate/

Required:
- P3_02_reconstructed.png
- P3_02_side_by_side.png
- P3_02_overlay.png
- P8_06_reconstructed.png
- P8_06_side_by_side.png
- P8_06_overlay.png
- validation_report.md
- manifest.json

The report must include exact test totals and failures; the exact 288/366-pixel callout case; emitted exclusion QC with both source reason fields; confirmation that callout pixels remain absent from curve coordinates; P8 panel-a/d point and segment counts; P3 OCR-associated candidates and explicit non-filtering decision; remaining unresolved items.

Manifest must include byte sizes and SHA256 for every uploaded file.

Use explicit git add exact-path commands, commit/push only to fix/callout-qc-remove-pixel-ratio-gate. Do not upload PDFs/SI, raw OCR JSON, unrelated outputs or temporary files.

Return final commit SHA, artifact links, exact one-pass test results and the emitted exclusion QC record. Stop after validation; do not merge, publish or touch protected branches.
