# Junction-local ambiguity recovery — local validation handoff

Target repository: `Tuzhidingdong/Figure_digitization`
Target branch: `fix/junction-local-ambiguity-recovery`
Expected source HEAD at handoff: `fcd96f5b02652328e9346294f7ecc3e9675ba7c1`
Base: `d7a53c624382865783dc821b546d6c46a746947e`

## Safety and sync

1. In the existing project at `E:\\Zinc_batters_datas\\Figure_digitization`, inspect `git status` and current branch before fetching.
2. Preserve all local uncommitted files, `.agents/`, `__pycache__/`, all existing `test_outputs/`, the existing `STATUS.md` backup and `stash@{0}`. Do not reset, clean, stash-pop/drop, or use `git add -A`.
3. Fetch and fast-forward/switch to this branch only after confirming the worktree can be preserved. Do not touch `main`, `review/real-image-reconstruction-20261124`, frozen `TASK_PLAN_v1.4.1.md), or merge/publish PR #22.
4. Confirm HEAD exactly equals the expected source HEAD above before testing. If local uncommitted changes conflict, stop and report; do not overwrite them.

## What changed

In `src/scientific_figure_data/raster.py`, ambiguous junction clusters are now treated as hard local breakpoints rather than causing the entire connected component to return zero paths. Unambiguous graph segments terminating at genuine raster endpoints or ambiguous-cluster ports can be retained. No connection is invented across an ambiguous cluster. Partial results explicitly carry:
- `PARTIAL_PATHS_NEEDS_REVIEW` in path QC;
- `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` in trace status;
- `NEEDS_REVIEW_PARTIAL_PATH` in QC status;
- the ambiguous cluster details and review flag.

This is a candidate fix, not yet accepted. Check downstream status handling carefully: partial paths must never be represented as fully successful extraction.

## Required one-pass validation

Use the existing Python 3.13.9 environment and archived OCR JSON only. Do not rerun OCR, install optional dependencies, or inspect source papers/PDF/SI.

Run once, recording collected/passed/failed/skipped counts, exit code and duration:
- `tests/test_core.py`
- `tests/test_automatic_digitization.py`
- `tests/test_real_image_regressions.py`
- `tests/test_upstream_compat.py`

Add or adjust focused regression tests as needed, especially:
- a synthetic skeleton/component with one ambiguous junction and at least one otherwise unambiguous long path: retain the safe segment(s), preserve a local break, never invent a bridge;
- the P8_06 panel-a red trace: verify vertical charge/discharge portions are retained as path geometry where supported, and ambiguous crossing regions remain review-required;
- the P8_06 panel-a blue `without urea`: verify actual ordered path coordinates are produced, not merely nonzero color pixels;
- P3_02 orange/purple coverage and independent path separation;
- no test may count `NEEDS_REVIEW` or partial-review status as full extraction success.

Re-run only failed/fixed focused tests once if necessary. Do not enter a repeated broad test loop.

## Real-image visual regression

Use original fixtures:
- `tests/fixtures/real_figures/P3_02.png`
- `tests/fixtures/real_figures/P8_06.png`

Use their archived OCR JSON. Generate six new images from the current source and actual newly generated CSV/JSON:
- P3_02 reconstructed, side-by-side, overlay;
- P8_06 reconstructed, side-by-side, overlay.

Compare against the archived old output from `test_outputs/real_image_reconstruction_20261124/` and explicitly report:
- P3 orange/red/purple path continuity, coverage and false joins;
- P8 panel-a red vertical segments, red annotation-box contamination, and blue `without urea` actual path;
- P8 panels b/c unresolved reasons;
- P8 panel-d pink/blue separation and left/right axis evidence;
- all series point counts, path/QC/review states, Y-axis assignment, and whether `y_value` remains empty when axis assignment is unresolved.

Do not claim scientific point accuracy without an independently annotated point benchmark. Do not call partial-review output successful.

## Upload review artifacts to GitHub

Commit only the requested visual review artifacts and concise report to this exact directory on this same branch:

`review/junction-local-ambiguity-recovery/`

Required contents:
- `P3_02_reconstructed.png`
- `P3_02_side_by_side.png`
- `P3_02_overlay.png`
- `P8_06_reconstructed.png`
- `P8_06_side_by_side.png`
- `P8_06_overlay.png`
- `validation_report.md` (test counts, source/output absolute paths, SHA256, per-series table, old/new comparisons, unresolved issues)
- `manifest.json` (artifact paths, byte sizes, SHA256, source image SHA256, run metadata)

Use explicit `git add` paths only; never `git add -A`. Commit and push to `fix/junction-local-ambiguity-recovery`. Do not upload raw source PDFs/SI or unrelated local files.

## Handoff

Return the pushed commit SHA, exact GitHub URLs for the six images/report/manifest, test summary, and a clear pass/partial/fail visual verdict. Stop after reporting; do not merge PRs or continue feature development.
