# Partial branch QC preservation — local validation handoff

Repository: `Tuzhidingdong/Figure_digitization`
Target branch: `fix/partial-branch-qc-preservation`
Validation baseline / parent: `804c0931f0d9ed4e632680b61fcbdc214399eb5c`
Minimum required code commit (must be an ancestor of local HEAD): `aa3618cfa01cf31d512f8778c1dfbcb508d886fc`
Algorithm version: `0.8.0`

This is a candidate corrective patch. It has **not** been run in the local Windows environment and is not accepted yet.

## 1. Protected state

Work only in:
`E:\\Zinc_batters_datas\\Figure_digitization`

Before sync, inspect branch and `git status`. Preserve local modifications and all untracked items, including `.agents/`, `__pycache__/`, all `test_outputs/`, the old `STATUS.md` backup and `stash@{0}`.

Do not use `git reset --hard`, `git clean`, stash pop/drop or `git add -A`. Do not overwrite conflicting local files. Use explicit file paths only.

Do not modify:
- `main`;
- `review/real-image-reconstruction-20261124`;
- `fix/junction-local-ambiguity-recovery`;
- `fix/partial-raster-fragment-preservation` (the previous candidate and its report);
- PR #22;
- frozen `TASK_PLAN_v1.4.1.md`.

No PR merge or release is authorized.

## 2. What changed from the previous candidate

Files changed in this patch:
- `src/scientific_figure_data/raster.py`
- `src/scientific_figure_data/pipeline.py`
- `tests/test_core.py`

### A. Branch selection no longer hides a long full-span curve because its QC is partial

A path with `path_kind = FULL_X_SPAN_PATH` remains a distinct branch candidate even when its own QC status is `PARTIAL_PATHS_NEEDS_REVIEW` (for example, a long curve with one unpaired spur). Only explicit `LOCAL_*` review-fragment groups may be auto-excluded next to a unique full-span path.

This specifically addresses the P8 panel-d regression: the second red curve (319 points, bbox previously `[58,75,375,83]`) was previously hidden in `excluded_partial_branches` because it had an unpaired spur. It must be restored as a separate branch/series, while retaining its partial-review status.

### B. Compact rejected callout candidates are visible in exclusion QC

When exactly one full-span path exists, a spatially separate compact component rejected with `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` may be recorded in `excluded_partial_branches` and `rejected_components` as:

`PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS`

The record retains the original QC reason, bbox, pixel count and a review-only classification. This is **not** a claim that the component is definitely an annotation. It must not be plotted as a data path.

This specifically addresses the synthetic waveform + callout regression: the 366-point waveform should be returned; the callout should remain at 0 points; its rejected geometry should be explicitly visible in the exclusion QC.

### C. Local 2-D fragment admission is narrower

Short 2-D fragments must be line-like (X span at least 2.5 times Y span) and contain at least 24 source pixels. Compact ring-like glyphs must not be promoted as partial trace segments. Long vertical fragment retention remains in place.

### D. Version and regression tests

Algorithm version is bumped from `0.7.0` to `0.8.0`. The old version assertion in `tests/test_core.py` is updated accordingly; this is a version-contract update, not a scientific expectation change.

New/updated regression protections:
- callout exclusion reason and original unsupported-junction QC reason are both asserted;
- direct tracer QC also reports the excluded callout candidate;
- a long full-span path with partial QC is not auto-excluded;
- a compact ring glyph is not retained as a local 2-D trace fragment;
- the existing real P8 panel-d regression must still detect two red branches and one blue band.

## 3. Sync and one-pass tests

After safely syncing the target branch, confirm the local HEAD contains the required code commit `aa3618cfa01cf31d512f8778c1dfbcb508d886fc` in its ancestry. The required parent is `804c0931f0d9ed4e632680b61fcbdc214399eb5c`.

Use the existing Python 3.13.9 environment. Run syntax/import checks, then execute the four relevant files **once**:

```powershell
python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0
```

Record collected/passed/failed/skipped, exit code, duration and exact failing node IDs. Do not enter a repeated broad-test loop. If a failure occurs, inspect it and perform at most one directly relevant focused rerun after any correction.

Do not weaken the callout rejection, full-span branch retention, five-way junction, or path-segment assertions.

## 4. Real-image checks — cached OCR only

Use unchanged fixtures:
- `tests/fixtures/real_figures/P3_02.png`
- `tests/fixtures/real_figures/P8_06.png`

Use archived OCR JSON only. Do not rerun OCR, open source papers/PDF/SI, or install dependencies.

Generate fresh output in:
`test_outputs/reconstruction_partial_branch_qc_20261124/`

Compare with:
- previous candidate output: `test_outputs/reconstruction_partial_raster_fragments_20261124/`
- previous diagnostic output: `test_outputs/reconstruction_junction_local_20261124/`
- original baseline: `test_outputs/real_image_reconstruction_20261124/`

Required checks:

### P8_06 panel a
- Red ordered geometry and blue `without urea` ordered geometry remain present.
- All partial fragments remain review-only with independent segment boundaries.
- No connectors are drawn across segment boundaries.
- The red callout/arrow candidate is not plotted, and its rejected geometry appears in exclusion QC when the unique full-span path rule applies.

### P8_06 panel d
- Restore **two independent red branches plus one blue branch**.
- The second red branch must be present in the series output, not only in `excluded_partial_branches`.
- If its junction QC remains partial, preserve `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` / `NEEDS_REVIEW_PARTIAL_PATH`; do not relabel it as fully accepted.
- Preserve the blue/right-axis and red/left-axis evidence and compare point counts with the previous run.

### P3_02
- Check whether the orange and purple ring-like artefacts from the previous candidate are absent.
- Retain legitimate elongated local fragments; record any reduction in purple coverage and inspect x≈355–390.
- Do not claim curve recovery based on mask pixels alone: report ordered coordinate counts and bboxes.

### All panels
- Report series/point/segment counts, extraction status, QC status, Y-axis assignment, and whether `y_value` is empty when mapping is unresolved.
- Panel c remains unresolved unless the existing evidence grounds a monotonic X-axis; do not invent labels.
- No scientific point-level accuracy claim without an independent annotated point benchmark.

## 5. Upload

Upload only these items to:
`review/partial-branch-qc-preservation/`

Required:
- `P3_02_reconstructed.png`
- `P3_02_side_by_side.png`
- `P3_02_overlay.png`
- `P8_06_reconstructed.png`
- `P8_06_side_by_side.png`
- `P8_06_overlay.png`
- `validation_report.md`
- `manifest.json`

The report must contain exact source/output paths, input SHA256, the one-pass test results, per-panel series/segment tables, P8 panel-d red branch evidence, compact-callout QC evidence, P3 artefact comparison and remaining limitations. Manifest must record byte sizes and SHA256 for every uploaded file.

Use explicit `git add <exact-path>`, commit and push only to `fix/partial-branch-qc-preservation`. Do not upload PDFs/SI, raw OCR, unrelated local data or temporary files.

Return the final commit SHA and all artifact links. Stop after validation; do not merge, publish or touch protected branches.
