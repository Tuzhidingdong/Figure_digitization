# Partial raster fragment preservation — local validation report

Date: 2026-11-24
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/partial-raster-fragment-preservation`
Validated HEAD: `3f23ff22649d5754dc997a6ce57c47810dbaf1e1`
Validation baseline: `43d1b6c5aca07b9ee22977f0eae360154912a7fe`
Required code commit `97bdba4ae0953c4e4d5edfe7b75313fe043fb487` is an ancestor of HEAD (verified).
Algorithm version reported by the pipeline: `0.7.0`.

## 1. State and method

Existing project only; no clone/worktree, no OCR rerun, no paper/PDF/SI access, no new dependency.
Before sync: branch `fix/junction-local-ambiguity-recovery` @ `43d1b6c`, clean tracked tree,
untracked `.agents/`, `__pycache__/`, `test_outputs/`. `stash@{0}`, the `STATUS.md` backup,
all old `test_outputs/` directories and the prior review artifacts are intact.
No `reset --hard`, `git clean`, stash pop/drop or `git add -A`. `main`, the previous review
branches, PR #22 and `TASK_PLAN_v1.4.1.md` were not touched. No source or test file was edited.

Syntax/import check: `python -m compileall -q src/scientific_figure_data` exit 0;
`import scientific_figure_data.{raster,pipeline,reconstruction,storage}` exit 0 on Python 3.13.9.

## 2. One-pass targeted pytest

Command:

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py `
  tests/test_real_image_regressions.py tests/test_upstream_compat.py `
  -o addopts="" -q --durations=0
```

| Metric | Value |
|---|---|
| Collected / executed | **156** |
| Passed | **152** |
| Failed | **4** |
| Skipped | **0** |
| Exit code | **1** |
| Duration | 169.12 s |
| Log | `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_partial_fragments.log` |

Failures (no test expectation was weakened; no focused rerun was performed because no code was
corrected and the failures were independently reproduced by direct probes / fresh extraction):

1. `tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`
   — **scientific requirement 5 fails**. The waveform is restored and the callout is not traced,
   but `detect_monotonic_color_branches()` returns `excluded_partial_branches: []`; the callout is
   only recorded as `rejected_components` with reason `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`.
   The required `PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS` record is absent.
   Direct probe: status `SINGLE_MONOTONIC_COLOR_BAND`, 1 branch, 366 waveform points (y 25–76),
   0 callout pixels.
2. `tests/test_core.py::test_run_report_distinguishes_selected_cached_and_filtered_papers`
   — stale non-scientific expectation `algorithm_version == "0.6.0"` vs intended `0.7.0`.
3. `tests/test_real_image_regressions.py::test_p8_real_figure_detects_two_red_branches_and_one_blue_band`
   — panel-d red branch detection returns `SINGLE_MONOTONIC_COLOR_BAND` (1 branch) instead of 2;
   the second red branch is in `excluded_partial_branches` QC only.
4. `tests/test_real_image_regressions.py::test_p8_real_figure_pipeline_uses_panel_local_ocr_and_dual_y_mapping`
   — panel-d series count 2 instead of ≥3; one red curve (319 pts) is no longer a plotted series.

The five-way junction test passed: still 0 points, `NEEDS_REVIEW`, no bridge.

## 3. Exact paths and source hashes

- Source P3_02: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P3_02.png`
  SHA256 `9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e`
- Source P8_06: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P8_06.png`
  SHA256 `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549`
- Extraction/render output: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124`
- Scripts: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\extract_only.py`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\render_reconstructions.py`
- Run record / manifest: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\extraction_run.json`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\reconstruction_manifest.json`
- P3 CSV: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\extraction\P3_02\output\papers\paper-p3-real__01_preprocessing\series\MAIN_FIG_P3_02__auto-03\panel_series.csv`
- P8 CSV a: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-01\panel_series.csv`
- P8 CSV b: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-02\panel_series.csv`
- P8 CSV d: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_raster_fragments_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-04\panel_series.csv`
- digitization.json / panel_layout.json live beside those CSVs in each paper output directory.

Both pipeline runs: `COMPLETED_WITH_REVIEW` (P3 24 series records, P8 12 series records).
The CSV schema now includes `path_segment_index`; every plotted point is read from these CSVs.
No interpolation or connector is generated: the renderer splits each series by segment index and
calls `plot()` separately for each segment.

## 4. Per-series results

### P3_02 (19 series with data, 1417 points, 72 drawn segment views)

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
| auto-03 | _color_02_branch_02 | 23 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_03 | 17 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_04 | 28 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_05 | 49 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_06 | 198 | 2 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_02_branch_07 | 53 | 1 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_03_branch_01 | 35 | 1 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_03_branch_02 | 44 | 1 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |
| auto-03 | _color_03_branch_03 | 14 | 1 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 0 |
| auto-03 | _color_04 | 40 | 1 | [172, 71, 103] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 0 |

All P3 series: Y `UNASSIGNED / AMBIGUOUS_DUAL_Y_AXIS`, `y_value` empty, `review_state = NEEDS_REVIEW`.
Purple: previous two fragments (35 pt bbox `[68,217,102,225]`; 44 pt bbox `[105,233,147,247]`) plus
**one new 14-point ordered fragment** at bbox `[267,125,281,127]`
(`LOCAL_SHORT_2D_FRAGMENT_NEEDS_REVIEW`). No purple fragment beyond x≈280 was recovered.
Two small ring/loop-like short-fragment artefacts are visible in the reconstruction (an orange
one near panel x≈8 / pixel x≈100 and the purple `[267,125,281,127]` fragment); they are flagged
partial-review geometry but visually resemble annotation glyphs rather than data curves.

### P8_06 (11 series with data, 25841 points)

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
| auto-frame-04 | _color_01 | 317 | 1 | [245, 167, 172] | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | EXTRACTED_PROVISIONAL / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW | 317 |
| auto-frame-04 | _color_02 | 317 | 1 | [17, 100, 172] | RIGHT | COLOR_MATCHED_TO_Y_AXIS_TEXT | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW | 317 |

Panel a detail:
- red `_color_01`: **22,146 ordered coordinates in 178 independent segments**, all
  `LOCAL_VERTICAL_FRAGMENT_NEEDS_REVIEW`; `path_qc.status = PARTIAL_PATHS_NEEDS_REVIEW`,
  reason `AMBIGUOUS_JUNCTIONS_RETAINED_AS_LOCAL_BREAKPOINTS`, `local_fragment_count = 178`;
  `extraction_status = EXTRACTED_PROVISIONAL_NEEDS_REVIEW`,
  `qc_status = NEEDS_REVIEW_PARTIAL_PATH`, `review_state = NEEDS_REVIEW`.
- blue `_color_02`: **1,835 ordered coordinates in 26 independent segments**, reason
  `LOCAL_GEOMETRY_FRAGMENTS_RETAINED_WITHOUT_FULL_X_COVERAGE`, same partial-review status chain.
- No segment bbox falls in the red dashed-box region (x≈438–499, y≈83–147) or the arrow start
  region (x≈198–236, y≈127–152); `excluded_partial_branches` for panel a is empty. Annotation pixels
  were filtered at component level, not promoted. Their exclusion is not explicitly recorded in
  branch QC.
- Segments are plotted independently: overlay/reconstruction show gaps, and no straight connector
  between a segment end and the next segment start.

Panel d: only 2 plotted series (317 LEFT red, 317 RIGHT blue). The second red branch (319 pts,
bbox `[58,75,375,83]`) is retained only in `excluded_partial_branches` QC with
`PARTIAL_PATHS_NEEDS_REVIEW` / unpaired spur at `[242,77]`. It is **not** a plotted series.
Panel c remains 0 points: `trace_specification = NEEDS_REVIEW /
X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER`, `raster_qc = None`; the pipeline gate
(`pipeline.py:1555`) still requires `READY`. No X label was invented.

## 5. Old / new visual comparison

| Item | Original baseline | Prior diagnostic run (junction) | This run |
|---|---|---|---|
| P8 panel a red | 1237 pts with ~2.2/2.6 V annotation spikes | 0 pts | **22,146 pts / 178 segments** |
| P8 panel a blue | 0 pts | 0 pts | **1,835 pts / 26 segments** |
| P8 panel b | 0 pts | 839 pts total | 1226 pts / 12 segments (red 839, blue 387) |
| P8 panel c | 0 pts | 0 pts | 0 pts (same trace-spec gate) |
| P8 panel d | 3 series / 986 pts | 3 series / 953 pts | **2 series / 634 pts** (one red branch QC-only) |
| P3 series / points | 6 / 1100 | 16 / 1248 | 19 / 1417 (+14 purple) |

verdict: panel a vertical charge/discharge geometry is now present as real ordered coordinates,
and the blue `without urea` curve now has real ordered coordinates. The red annotation box is
not plotted. Segment breaks are preserved. However panel d lost a plotted red series and P3
gained small ring-like false fragments; these prevent an unconditional pass.

## 6. Requirement check

| # | Requirement | Result |
|---|---|---|
| 1 | P8 a red ordered vertical coordinates | PASS — 178 segments / 22,146 pts |
| 2 | P8 a blue `without urea` ordered coordinates | PASS — 26 segments / 1,835 pts |
| 3 | independent segments, no invented connectors | PASS — `path_segment_index` in CSV, segment-wise plotting |
| 4 | red callout not promoted | PASS in real image (no annotation-region segments); QC record absent |
| 5 | synthetic waveform restored + callout exclusion in QC | **PARTIAL FAIL** — waveform restored, callout not traced, but exclusion QC key/reason missing; test fails |
| 6 | partial paths stay `NEEDS_REVIEW` | PASS — panel a `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` / `NEEDS_REVIEW_PARTIAL_PATH` |
| 7 | five-way junction no bridge | PASS — test passed, 0 pts, NEEDS_REVIEW |
| 8 | P3 purple more ordered fragments | PARTIAL — one 14-pt fragment x=267–280; no x≈355–390; ring artefacts |

## 7. Unresolved / needs human review

- 4 pytest failures listed above, including one scientific assertion about callout-exclusion QC.
- Panel d second red branch is QC-only, not a plotted series.
- P3 dual Y axis remains `UNASSIGNED`; all `y_value` empty; candidate scales are not results.
- P3 purple coverage still incomplete; short-fragment ring artefacts need review.
- Panel b has no axis calibration (`UNRESOLVED`, `y_value` empty); panel c unresolved.
- No independent point benchmark exists: **no scientific point-level accuracy claim is made**.

## 8. Artifacts

The six PNGs, this report and `manifest.json` are committed to
`review/partial-raster-fragment-preservation/` on this branch only. No PDF/SI or unrelated file
is included.
