# Partial branch QC preservation — local validation report

Date: 2026-11-24
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/partial-branch-qc-preservation`
Validated HEAD: `2c472688b1c5fb2d346d4c2df521ca8baa39a720`
Parent / validation baseline: `804c0931f0d9ed4e632680b61fcbdc214399eb5c`
Required code commit `aa3618cfa01cf31d512f8778c1dfbcb508d886fc` is an ancestor of HEAD (verified).
Algorithm version: `0.8.0`.

## 1. Protected state

Existing project only; no clone/worktree, no OCR rerun, no paper/PDF/SI access, no dependency install.
Before sync: branch `fix/partial-raster-fragment-preservation` @ `804c093`, clean tracked tree,
untracked `.agents/`, `__pycache__/`, `test_outputs/`. `stash@{0}`, the `STATUS.md` backup,
all prior `test_outputs/` and the previous review artifacts (9 files) are intact.
No `reset --hard`, `git clean`, stash pop/drop or `git add -A`. `main`, `review/real-image-reconstruction-20261124`,
`fix/junction-local-ambiguity-recovery`, `fix/partial-raster-fragment-preservation`, PR #22 and the
frozen `TASK_PLAN_v1.4.1.md` were not touched. No source or test file was edited.

Syntax/import checks passed: `compileall -q src/scientific_figure_data` exit 0; core module imports exit 0
on Python 3.13.9.

## 2. One-pass targeted pytest

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py `
  tests/test_real_image_regressions.py tests/test_upstream_compat.py `
  -o addopts="" -q --durations=0
```

| Metric | Value |
|---|---|
| Collected / executed | **158** |
| Passed | **157** |
| Failed | **1** |
| Skipped | **0** |
| Exit code | **1** |
| Duration | **204.88 s** (0:03:24) |
| Log | `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_branch_qc.log` |

Exact failing node:
`tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`
— `assert len(detected.get("excluded_partial_branches", [])) == 1`, actual `0`.

All previously failing nodes from the last round now pass: the panel-d branch-count and
dual-axis-series regressions are fixed, and the version assertion matches `0.8.0`.
The five-way junction and path-segment tests pass; no scientific assertion was weakened.
No focused rerun was performed (no code correction was authorized); a direct probe reproduced the
single failure deterministically: waveform branch 1 / 366 points / y 25–76, 0 callout pixels,
`excluded_partial_branches = []`, rejected component reason still
`UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` (not the required
`PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS`).

## 3. Exact paths and source hashes

- P3_02 source: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P3_02.png`
  SHA256 `9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e`
- P8_06 source: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P8_06.png`
  SHA256 `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549`
- Fresh output: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124`
- Scripts: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\extract_only.py`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\render_reconstructions.py`
- Records: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\extraction_run.json`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\reconstruction_manifest.json`
- Point tables (with `path_segment_index`):
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\extraction\P3_02\output\papers\paper-p3-real__01_preprocessing\series\MAIN_FIG_P3_02__auto-03\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-01\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-02\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-04\panel_series.csv`

Both pipeline runs `COMPLETED_WITH_REVIEW` (P3 22 series records, P8 13 series records).
Comparison baselines: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\real_image_reconstruction_20261124`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_junction_local_20261124`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124` (all preserved).

## 4. Per-series results

### P3_02 — 17 series with data, 1377 points, 66 drawn segment views

| Panel | Series | Pts | Segs | RGB | Y side | Map status | Extraction / QC / Review | y_value |
|---|---|---:|---:|---|---|---|---|---|
| auto-03 | _color_01_branch_01 | 424 | 3 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_02 | 67 | 1 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_03 | 41 | 1 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_04 | 28 | 2 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_05 | 22 | 1 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_06 | 19 | 1 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_07 | 46 | 1 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_01_branch_08 | 31 | 1 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_01 | 238 | 2 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_02 | 28 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_03 | 49 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_04 | 198 | 2 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_05 | 53 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_03_branch_01 | 35 | 1 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_03_branch_02 | 44 | 1 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_03_branch_03 | 14 | 1 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_04 | 40 | 1 | [172, 71, 103] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |

All P3 series remain `UNASSIGNED / AMBIGUOUS_DUAL_Y_AXIS`, `y_value` empty, `NEEDS_REVIEW`.
Ring-like artefacts **persist**: orange `_color_01_branch_03` (41 pts, bbox `[122,125,163,127]`,
`PATHS_EXTRACTED`) and purple `_color_03_branch_03` (14 pts, bbox `[267,125,281,127]`,
`LOCAL_SHORT_2D_FRAGMENT_NEEDS_REVIEW`) still appear as small loops in the reconstruction, exactly
as in the previous candidate. The narrower 2-D fragment rule kept genuinely line-like fragments
(`_color_01_branch_05` 22 pt bbox `[149,190,170,192]`, ratio ≈10.5; `_color_01_branch_06` 19 pt
bbox `[163,182,182,184]`, ratio ≈9.5) but did not remove the loops. Two short red fragments
from the previous run (`_color_02_branch_02` 23 pt and `_color_02_branch_03` 17 pt, 40 pt total)
are no longer emitted; no purple fragment beyond x≈280 was recovered.

### P8_06 — 12 series with data, 26225 points

| Panel | Series | Pts | Segs | RGB | Y side | Map status | Extraction / QC / Review | y_value |
|---|---|---:|---:|---|---|---|---|---|
| auto-frame-01 | _color_01 | 22146 | 178 | [238, 63, 70] | LEFT | ASSIGNED | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 22146 |
| auto-frame-01 | _color_02 | 1835 | 26 | [103, 147, 197] | LEFT | ASSIGNED | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 1835 |
| auto-frame-02 | _color_01 | 839 | 6 | [237, 74, 79] | UNASSIGNED | UNRESOLVED | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-frame-02 | _color_02_branch_01 | 42 | 1 | [69, 133, 192] | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-frame-02 | _color_02_branch_02 | 50 | 1 | [69, 133, 192] | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-frame-02 | _color_02_branch_03 | 112 | 1 | [69, 133, 192] | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-frame-02 | _color_02_branch_04 | 48 | 1 | [69, 133, 192] | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-frame-02 | _color_02_branch_05 | 110 | 1 | [69, 133, 192] | UNASSIGNED | UNRESOLVED | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-frame-02 | _color_02_branch_06 | 25 | 1 | [69, 133, 192] | UNASSIGNED | UNRESOLVED | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-frame-04 | _color_01_branch_01 | 317 | 1 | [245, 167, 172] | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | EXTRACTED_PROVISIONAL / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 317 |
| auto-frame-04 | _color_01_branch_02 | 319 | 1 | [245, 167, 172] | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 319 |
| auto-frame-04 | _color_02 | 317 | 1 | [17, 100, 172] | RIGHT | COLOR_MATCHED_TO_Y_AXIS_TEXT | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 317 |

Panel a: red 22,146 points / 178 segments and blue `without urea` 1,835 points / 26 segments —
unchanged from the previous candidate; all remain `EXTRACTED_PROVISIONAL_NEEDS_REVIEW /
NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW`. Segment boundaries are preserved by
`path_segment_index` and the renderer plots each segment independently; overlay/reconstruction
show gaps and no connector across a break. Red dashed box / arrow pixels are not plotted; their
exclusion QC for panel a remains empty (component-level filter), so no compact-callout QC record
is claimed for the real image.

Panel d: **restored to three independent plotted branches** — red `_color_01_branch_01` 317 pts
(`EXTRACTED_PROVISIONAL`, `PATHS_EXTRACTED`, LEFT by dual-axis exclusion) and red
`_color_01_branch_02` 319 pts with bbox `[58,75,375,83]`, unpaired spur `[242,77]`,
`path_qc.status = PARTIAL_PATHS_NEEDS_REVIEW`, kept as a separate series with
`EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW`; blue `_color_02`
317 pts RIGHT by colour-to-axis-text match. This is a separate plotted series, not a QC-only entry.
Panel b: 7 series / 1226 pts, geometry only (`UNRESOLVED`, `y_value` empty).
Panel c: still 0 points; `trace_specification = NEEDS_REVIEW /
X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER`, no monotonic X label was invented.

## 5. Old/new comparison

| Item | Original baseline | Prior diagnostic | Prior candidate (0.7.0) | This run (0.8.0) |
|---|---|---|---|---|
| P8 a red | 1237 pts (annotation spikes) | 0 pts | 22146 / 178 seg | 22146 / 178 seg (unchanged) |
| P8 a blue | 0 pts | 0 pts | 1835 / 26 seg | 1835 / 26 seg (unchanged) |
| P8 b | 0 pts | 839 pts | 1226 pts | 1226 pts |
| P8 c | 0 pts | 0 pts | 0 pts | 0 pts (same gate) |
| P8 d | 3 series / 986 pts | 3 / 953 | **2 / 634** | **3 / 953** (restored) |
| P3 | 6 / 1100 | 16 / 1248 | 19 / 1417 | 17 / 1377 (rings remain) |

## 6. Requirement check

| # | Requirement | Result |
|---|---|---|
| 1 | P8 d two red + one blue independent branches | **PASS** — 317 + 319 red, 317 blue; second red partial QC retained |
| 2 | synthetic callout exclusion in `excluded_partial_branches` + rejection QC | **FAIL** — waveform 366 pts and 0 callout pts, but exclusion QC empty; test fails |
| 3 | P3 orange/purple rings filtered without losing real fragments | **FAIL** — rings persist; two short red fragments removed; elongated fragments retained |
| 4 | P8 a red/blue segments kept, no invented connectors | **PASS** |
| 5 | five-way junction 0 pts / NEEDS_REVIEW / no bridge | **PASS** |
| 6 | partial states propagated through pipeline | **PASS** — panel a and panel d second red keep `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` / `NEEDS_REVIEW_PARTIAL_PATH` |

## 7. Remaining limitations

- 1 failing scientific test (callout exclusion QC).
- P3 ring-like short fragments still drawn; purple coverage still stops at x≈280.
- P3 dual Y axis `UNASSIGNED`; panel b `UNRESOLVED`; panel c unresolved; all `review_state = NEEDS_REVIEW`.
- No independently annotated point benchmark: **no point-level scientific accuracy claim**.

## 8. Artifacts

Six PNGs, this report and `manifest.json` are committed only to
`review/partial-branch-qc-preservation/` on this branch. No PDF/SI or unrelated local file included.
