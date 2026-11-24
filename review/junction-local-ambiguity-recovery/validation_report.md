# Junction-local ambiguity recovery — local validation report

Date: 2026-11-24
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/junction-local-ambiguity-recovery`
HEAD at validation: `41cf3d44aacb6fa6a2c3b2ad91a71863d8055ec0`
Required fix commit `de0bc4f59402cce4d6e6d484984feda020202614` is an ancestor of HEAD (verified).
Base: `d7a53c624382865783dc821b546d6c46a746947e`.

## 1. Safety / scope

Used the existing project at `E:\Zinc_batters_datas\Figure_digitization`; no clone or worktree.
Before fetch: branch `feat/real-image-regression-diagnostics` @ `d7a53c62`, clean tracked tree,
only untracked `.agents/`, `__pycache__/`, `test_outputs/`.
No `reset --hard`, `git clean`, stash pop/drop or `git add -A`. `stash@{0}` and
`STATUS.md.prePR22.local_20261123.bak` are intact. `main`, the previous review branch,
PR #22, `TASK_PLAN_v1.4.1.md` and all source/config/test files were left untouched.
Only explicit `git add <path>` was used for the artifacts in this directory.

## 2. Targeted tests (Python 3.13.9, one pass)

Command:

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py \
  tests/test_real_image_regressions.py tests/test_upstream_compat.py \
  -o addopts="" -q --durations=0
```

| Metric | Value |
|---|---|
| Collected / executed | 153 |
| Passed | 151 |
| Failed | 2 |
| Skipped | 0 |
| Exit code | 1 |
| Duration | 166.86 s |
| Log | `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_junction_20261124.log` |

The two failures are **stale baseline test expectations**, not silent successes:

1. `tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`
   expected `SINGLE_MONOTONIC_COLOR_BAND` / 1 branch / `EXTRACTED_PROVISIONAL`.
   Current code deliberately returns `MULTIPLE_MONOTONIC_COLOR_BRANCHES` with two branches —
   the waveform (clean path) and the callout box (retained only as
   `PARTIAL_PATHS_NEEDS_REVIEW`), and returns **0 points / NEEDS_REVIEW** when no branch is
   explicitly selected. No annotation pixel was traced.
2. `tests/test_core.py::test_2d_path_tracer_rejects_unsupported_five_way_junction`
   expected `qc["component_detection"]["rejected_components"]`; the new QC schema has
   `qc["branches"]` with `NEEDS_REVIEW` / `MULTIPLE_DISCONNECTED_PATHS_REQUIRE_SEPARATE_SERIES`
   and four disconnected partial branches, and still returns **0 points**. No bridge was invented.

Per the handoff instruction, those two focused tests were temporarily adjusted to the new
intended contract and re-run **once**: `2 passed in 0.89 s`, exit code 0
(log `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_focused_rerun.log`).
The temporary test edits were then restored from the pre-edit copy; the tracked tree is clean
again and **no test change is included in this commit**. The full four-file suite was not re-run.

## 3. Real-image extraction (fresh, cached OCR only)

- Script: `test_outputs/reconstruction_junction_local_20261124/extract_only.py`
- Fresh output: `test_outputs/reconstruction_junction_local_20261124/extraction/`
- OCR: archived `tests/fixtures/real_figures/P3_02_ocr.json` and `P8_06_ocr.json`; `ocr.run_ocr` monkey-patched. No OCR model, paper, PDF or SI was opened.
- Both runs: `status = COMPLETED_WITH_REVIEW`; P3 6 panels / 21 series records, P8 4 panels / 14 series records.

| Source | Path | SHA256 |
|---|---|---|
| P3_02 | `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P3_02.png` | `9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e` |
| P8_06 | `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P8_06.png` | `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549` |

Authoritative point tables (plotted directly from these CSVs; no interpolation or invented values):

- `...\reconstruction_junction_local_20261124\extraction\P3_02\output\papers\paper-p3-real__01_preprocessing\series\MAIN_FIG_P3_02__auto-03\panel_series.csv`
- `...\reconstruction_junction_local_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-02\panel_series.csv`
- `...\reconstruction_junction_local_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-04\panel_series.csv`

Companion `digitization.json` / `panel_layout.json` in the same paper directories carry series
colour, calibration, path QC, extraction/review state and panel boxes. Renderer:
`...\reconstruction_junction_local_20261124\render_reconstructions.py`; manifest:
`...\reconstruction_junction_local_20261124\reconstruction_manifest.json`.

## 4. Per-series results

### P3_02 — panel `auto-03` (16 series, 1248 points)

| Series suffix | Points | RGB | Y side | Mapping status | Extraction / review state |
|---|---|---|---|---|---|
| `_color_01_branch_01..06` | 86 / 67 / 41 / 51 / 287 / 31 | `[242,132,64]` orange | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / NEEDS_REVIEW |
| `_color_02_branch_01..07` | 179 / 28 / 59 / 49 / 157 / 41 / 53 | `[231,46,47]` red | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / NEEDS_REVIEW |
| `_color_03_branch_01..02` | 35 / 44 | `[130,56,131]` purple | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / NEEDS_REVIEW |
| `_color_04` | 40 | `[172,71,103]` pink | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / NEEDS_REVIEW |

Every point has empty `y_value`; max adjacent `|Δpixel_y| = 1 px` for all 16 series; no `>20 px`
jumps. Panels `auto-01/02/04/05/06` have zero points.

### P8_06 — 11 series with data, 1739 points

| Panel | Series suffix | Points | RGB | Y side | Mapping status | Extraction / review state |
|---|---|---|---|---|---|---|
| auto-frame-02 (b) | `_color_01_branch_01..03` | 125 / 153 / 146 | `[237,74,79]` red | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / NEEDS_REVIEW |
| auto-frame-02 (b) | `_color_02_branch_01..05` | 42 / 50 / 112 / 48 / 110 | `[69,133,192]` blue | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / NEEDS_REVIEW |
| auto-frame-04 (d) | `_color_01_branch_01` | 317 | `[245,167,172]` pink | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | EXTRACTED_PROVISIONAL / NEEDS_REVIEW |
| auto-frame-04 (d) | `_color_01_branch_02` | 319 | `[245,167,172]` pink | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | EXTRACTED_PROVISIONAL / NEEDS_REVIEW |
| auto-frame-04 (d) | `_color_02` | 317 | `[17,100,172]` blue | RIGHT | COLOR_MATCHED_TO_Y_AXIS_TEXT | EXTRACTED_PROVISIONAL / NEEDS_REVIEW |

Zero-point series: `auto-frame-01` red and blue; `auto-frame-03` placeholder.
`auto-frame-02` has no X/Y calibration at all, so all 786 points have empty `y_value`.
Panel-d series have numeric `y_value`; left-axis assignment is by exclusion (weaker evidence),
right-axis by colour-to-axis-text matching. **All series remain `NEEDS_REVIEW`; none is a
successful extraction.**

## 5. Old/new visual comparison

Baseline for comparison: `test_outputs/real_image_reconstruction_20261124/` (kept intact).
Previous 2D-trace run: `test_outputs/real_image_reconstruction_after_2d_trace_20261124/` (kept intact).

### P3_02

| Metric | Original baseline | Previous 2D run | This run |
|---|---|---|---|
| Series with points / total points | 6 / 1100 | 12 / 810 | **16 / 1248** |
| Max adjacent `|Δpixel_y|` | 159 px (91 jumps > 20 px) | 1 px | **1 px** |
| Orange columns covered | 333 | 129 (196 px gap) | **325 (no gap)** |
| Red columns covered | 332 | 322 (3 px gap) | **324 (3 px gap)** |
| Purple columns covered | 180 | 76 | **76 (unchanged)** |
| Pink columns covered | 0 | 36 | 36 |

Orange and red path continuity/coverage recovered substantially; no same-colour zigzag, no
box-like artefacts, no cross-curve joins visible in the overlay. Purple remains truncated to
`x=68–146`; the original purple curve continues to about `x=390`. This is a **partial pass**.

### P8_06

| Panel | Original baseline | Previous 2D run | This run |
|---|---|---|---|
| a red | 1237 pts incl. ~2.2/2.6 V annotation spikes | 0 pts (junction ambiguity) | **0 pts** |
| a blue `without urea` | 0 pts (6566 px detected) | 0 pts | **0 pts** |
| b red | 0 pts | 0 pts | **424 pts (3 fragments), geometry only** |
| b blue | 0 pts | 362 pts | 362 pts, geometry only |
| c | 0 pts | 0 pts | 0 pts |
| d | 986 pts (329/328/329) | 953 pts (317/319/317) | 953 pts (unchanged) |

Panel a: annotation-box trace is gone, but so is the entire curve. The big red component
`[94,138,1324,319]` (94974 px) is now retained in QC as a partial path with
`path_qc.status = NEEDS_REVIEW`, `partial_path_review_required = True`, rejection reason
`NO_PATH_SPANS_REQUIRED_X_RANGE`; the blue main component `[201,111,411,167]` is treated the
same way. Both still yield **0 plotted points**. `PARTIAL_PATHS_NEEDS_REVIEW` was not counted
as success anywhere. The blue `without urea` path is still absent — only colour pixels exist
in QC metadata.

Panel b: red and blue fragments are now drawn as **pixel geometry only**, with no axis
calibration, `UNASSIGNED / UNRESOLVED`, and empty `y_value`; they are not physical curves.

Panel c: `color_detection = MULTIPLE_CHROMATIC_FAMILIES / NEEDS_REVIEW`, no trace specification
and no raster QC, hence 0 points. Panel d: pink/blue paths remain separated, left/right axis
evidence unchanged, blue is smoother than the baseline (no 13.1–13.5 V excursions).

Verdict: **FAIL for P8 panel a**, **partial/incomplete for P3**, **fail for blue recovery**.
No annotation-box curve is plotted, but that is because panel a has no output at all.

## 6. Still unresolved / needs human review

- P8 panel a red vertical charge/discharge segments: present only as flagged partial QC geometry, not as plotted paths.
- P8 panel a blue `without urea`: no ordered path coordinates at all.
- P8 panel c: no trace specification; 0 points.
- P3 purple curve: only `x≈68–146` recovered; the rest is missing.
- P3 dual Y axis: still `UNASSIGNED / AMBIGUOUS_DUAL_Y_AXIS`, `y_value` empty; candidate scales are not results.
- Every series carries `NEEDS_REVIEW`-class status; nothing here is accepted extraction.
- No independently annotated point benchmark exists, so **no scientific point-level accuracy claim is made**.

## 7. Artifacts

The six PNGs, this `validation_report.md` and `manifest.json` are committed into
`review/junction-local-ambiguity-recovery/` on this branch. No PDF/SI, no unrelated local
file and no source change is included.
