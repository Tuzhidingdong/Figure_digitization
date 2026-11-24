# Partial raster fragment preservation — local validation handoff

Repository: `Tuzhidingdong/Figure_digitization`
Target branch: `fix/partial-raster-fragment-preservation`
Validation baseline commit: `43d1b6c5aca07b9ee22977f0eae360154912a7fe`
Current branch HEAD at handoff: `eaeed9bf6c07fff07b4282f559534bd9338c8876`
Algorithm version: `0.7.0`

This is a candidate implementation. It has **not** been executed in the local Windows environment and is not yet accepted.

## 1. Scope and protected state

Work only in the existing project:
`E:\\Zinc_batters_datas\\Figure_digitization`

Before sync, inspect and record the current branch and `git status`. Preserve all user/local files, including `.agents/`, `__pycache__/`, all `test_outputs/`, the existing `STATUS.md` backup, and `stash@{0}`.

Do not use `git reset --hard`, `git clean`, stash pop/drop, or `git add -A`. Do not overwrite conflicting local edits. Use explicit paths only.

Do not touch:
- `main`;
- `review/real-image-reconstruction-20261124`;
- `fix/junction-local-ambiguity-recovery` (the diagnostic record branch);
- PR #22;
- frozen `TASK_PLAN_v1.4.1.md`.

No PR merge or release is authorized.

## 2. Candidate implementation changes

The code changes are limited to:
- `src/scientific_figure_data/raster.py`
- `src/scientific_figure_data/pipeline.py`
- `src/scientific_figure_data/reconstruction.py`
- `src/scientific_figure_data/storage.py`
- `tests/test_core.py`

Expected behavior:
1. Long local vertical segments and selected short 2-D fragments may be retained as **partial-review geometry**, even when their individual X span is below the full-curve threshold.
2. Partial paths from one ambiguous source component are returned as one grouped result with explicit independent segment ranges. If all surviving branches are partial-review fragments (including disconnected dashed/stroke fragments), they are collected into one review-only segment collection. No bridge or connecting line is invented.
3. A unique complete path may be selected when the only competing branches are explicitly partial-review candidates. Those excluded candidates remain in QC. Multiple complete branches or unknown competing branches still require explicit selection.
4. Compact unsupported 3–7-port junctions remain whole-component review failures; a five-way junction must not become guessed output paths.
5. Pipeline state propagation must preserve `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` / `NEEDS_REVIEW_PARTIAL_PATH`.
6. Overlay and numeric reconstruction render each path segment separately.
7. `panel_series.csv` includes `path_segment_index` to preserve discontinuities.
8. Algorithm version is bumped to `0.7.0`.

## 3. Sync and one-pass tests

Fast-forward/switch only to `fix/partial-raster-fragment-preservation` after confirming the existing worktree can be preserved. Confirm HEAD is `97bdba4ae0953c4e4d5edfe7b75313fe043fb487` or a descendant containing it.

Use the existing Python 3.13.9 environment. First run a syntax/import check, then run the four relevant files once:

```powershell
python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0
```

Record collected/passed/failed/skipped, exit code and duration. Do not enter a repeated broad test loop. If a test fails, inspect the failure and run only the directly relevant focused test once after any necessary correction.

Tests specifically added/updated in `tests/test_core.py`:
- a long isolated vertical trace must produce ordered pixel coordinates with partial-review status;
- the synthetic waveform plus same-colour callout must return the waveform, exclude the callout as a partial branch, and preserve the exclusion in QC;
- a five-way junction must still return zero points and `NEEDS_REVIEW`;
- render output must not draw a line between independent segments;
- CSV rows must retain segment indices.

Do not weaken these scientific assertions to make tests pass.

## 4. Real-image validation — cached OCR only

Use the unchanged original fixtures:
- `tests/fixtures/real_figures/P3_02.png`
- `tests/fixtures/real_figures/P8_06.png`

Use only archived OCR JSON. Do not rerun OCR, open source papers/PDF/SI, or install optional dependencies.

Generate fresh extraction and six comparison images under:
`test_outputs/reconstruction_partial_raster_fragments_20261124/`

Compare against:
- original baseline: `test_outputs/real_image_reconstruction_20261124/`
- prior diagnostic output: `test_outputs/reconstruction_junction_local_20261124/`

Required checks:

### P8_06 panel a
- Red charge/discharge verticals must appear as ordered pixel paths; report segment count and point count.
- Blue `without urea` must produce actual ordered coordinates, not only a color mask.
- Overlay and reconstruction must preserve segment breaks. Verify that no straight line is drawn from the end of one fragment to the beginning of another.
- Red callout rectangle/arrow pixels must not be silently promoted to a complete trace.
- Every partial result must remain `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` / `NEEDS_REVIEW_PARTIAL_PATH`, not a successful extraction.

### P8_06 panel b/d and panel c
- Record whether b/d remain separated and whether their prior axis evidence changes.
- Panel c is **not directly modified by this patch**; report its trace-specification gate and leave it unresolved unless the existing code now supplies grounded monotonic X evidence. Do not invent an X-axis label.

### P3_02
- Check whether the short purple components beyond the previous x≈68–146 range now yield actual ordered fragments.
- Report their segment counts, coordinates/spans, QC status and visual alignment.
- Check orange/red continuity and false joins; keep any local fragments marked for review.

For every series, report point counts, extraction status, QC status, Y-axis assignment and whether `y_value` remains empty when unresolved. Do not claim scientific point-level accuracy without an independent point benchmark.

## 5. Upload and handoff

Upload only these artifacts to the same branch directory:
`review/partial-raster-fragment-preservation/`

Required:
- `P3_02_reconstructed.png`
- `P3_02_side_by_side.png`
- `P3_02_overlay.png`
- `P8_06_reconstructed.png`
- `P8_06_side_by_side.png`
- `P8_06_overlay.png`
- `validation_report.md`
- `manifest.json`

The report must include exact source/output paths, source SHA256, test outcomes, per-series/segment tables, old/new visual differences, and unresolved issues. Manifest must include byte sizes and SHA256 for every artifact.

Use explicit `git add <each exact path>`, commit and push only to `fix/partial-raster-fragment-preservation`. Do not upload PDFs/SI, raw data or unrelated local files.

Return the resulting commit SHA and links to all artifacts. Stop after validation; do not merge, publish, or change protected branches.
