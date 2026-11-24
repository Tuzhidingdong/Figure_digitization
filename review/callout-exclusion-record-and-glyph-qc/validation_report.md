# Callout exclusion QC and P3 glyph diagnosis — local validation report

Date: 2026-11-24
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/callout-exclusion-record-and-glyph-qc`
Validated HEAD: `738fb27ee64090e5acd012efadb94a0c2982bc37`
Parent / baseline: `d12da5e47604b67cd54258c37e0a6b3fe3af7ae3`
Required code commit `b1fa8d24b60944eda27977a58f4e51c93f34fc40` is an ancestor of HEAD (verified).
Algorithm version: `0.8.1`.

## 1. Protected state

Existing project only; no clone/worktree, no OCR rerun, no paper/PDF/SI access, no new dependency.
Before sync: branch `fix/partial-branch-qc-preservation` @ `d12da5e`, clean tracked tree, untracked
`.agents/`, `__pycache__/`, `test_outputs/`. `stash@{0}`, the `STATUS.md` backup, all previous
`test_outputs/` and all prior review artifacts are intact. No `reset --hard`, `git clean`,
stash pop/drop or `git add -A`. `main`, all earlier review/fix branches, PR #22 and the frozen
`TASK_PLAN_v1.4.1.md` were not touched. No source or test file was edited in this validation.

Compile/import checks passed: `compileall -q src/scientific_figure_data` exit 0, core module imports exit 0
on Python 3.13.9.

## 2. One-pass targeted pytest

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py `
  tests/test_real_image_regressions.py tests/test_upstream_compat.py `
  -o addopts="" -q --durations=0
```

| Metric | Value |
|---|---|
| Collected / executed | **159** (as handoff predicted: 158 + 1 new helper test) |
| Passed | **158** |
| Failed | **1** |
| Skipped | **0** |
| Exit code | **1** |
| Duration | **157.66 s** (0:02:37) |
| Log | `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_callout_qc.log` |

Exact failing node:
`tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`
— `assert len(detected.get("excluded_partial_branches", [])) == 1`, actual `0`.
All other tests pass, including the new direct helper regression and the P8 panel-d branch-count,
five-way junction, segment-boundary and compact-glyph tests. No focused rerun was performed (no code
correction was authorized); the failure was reproduced by a direct probe. No scientific assertion was weakened.

### Callout QC evidence (requirement 1: FAIL)

Direct probe of the synthetic waveform+callout image:

| Item | Observed |
|---|---|
| `detect_monotonic_color_branches().status` | `SINGLE_MONOTONIC_COLOR_BAND` |
| `branch_count` | 1 |
| waveform branch | bbox `[11,25,179,77]`, 366 px ordered path, `PATHS_EXTRACTED` |
| `trace_monotonic_color()` points | 366, y range 25–76 |
| callout pixels in selected path | **0** |
| `excluded_partial_branches` | **[]** (expected exactly 1 record) |
| rejected component | bbox `[82,4,127,19]`, 288 px, top-level `rejection_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`, nested `path_qc.reason` same, cluster reason `UNSUPPORTED_JUNCTION_PORT_COUNT` |
| `source_qc_rejection_reason` / `source_path_qc_reason` | **absent** from every returned QC record |

Mechanism found by read-only source inspection of `raster.py::_compact_rejected_review_candidates`:
the candidate is spatially separate (callout y 4–19 vs waveform y 25–77) and passes both relative
bbox gates (45 ≤ 168×0.40=67.2; 15 ≤ 52×0.50=26), but the raw component pixel gate fails:
**288 > 366×0.30 = 109.8**. Therefore no exclusion record is emitted and the two required reason
fields never appear. The nested junction reason is preserved in the rejected component's
`ambiguous_junction_clusters[0].reason`, but not as `source_path_qc_reason`.

This is a missing QC record, not a curve-contamination problem: the callout is still never plotted.

## 3. Exact paths and source hashes

- P3_02 source: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P3_02.png`
  SHA256 `9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e`
- P8_06 source: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P8_06.png`
  SHA256 `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549`
- Fresh output: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124`
- Scripts: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\extract_only.py`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\render_reconstructions.py`
- Records: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\extraction_run.json`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\reconstruction_manifest.json`
- Point tables (with `path_segment_index`):
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\extraction\P3_02\output\papers\paper-p3-real__01_preprocessing\series\MAIN_FIG_P3_02__auto-03\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-01\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-02\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-04\panel_series.csv`
- Cached OCR: `tests/fixtures/real_figures/P3_02_ocr.json` (149 rows; 33 rows inside the auto-03 crop).
- Comparisons: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\real_image_reconstruction_20261124`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_partial_branch_qc_20261124`.

Both pipeline runs `COMPLETED_WITH_REVIEW`. Every plotted point comes from the fresh CSVs.

## 4. Per-series results

### P3_02 — 17 series with data, 1377 points, 66 drawn segment views (unchanged from prior run)

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
The two ring-like short candidates are still emitted; see `p3_short_fragment_diagnostics.md`
and the diagnostic PNG. Purple coverage still stops at x≈280 panel-local (source x≈1194);
no coordinates were inferred for x≈355–390.

### P8_06 — 12 series with data, 26160 points (unchanged from prior run)

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

Panel a: red 22,146 points / 178 segments, blue `without urea` 1,835 points / 26 segments —
**no regression**; both `EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW`.
`path_segment_index` preserved; renderer draws segments independently, no connectors.
Red callout/arrow pixels are not plotted. Panel d: 317 + 319 red and 317 blue branches still
present; the 319-point branch keeps `PARTIAL_PATHS_NEEDS_REVIEW` with unpaired spur `[242,77]`.
Panel b: 1226 points, geometry only, `UNRESOLVED`, `y_value` empty.
Panel c: 0 points; still blocked by `trace_specification = NEEDS_REVIEW /
X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER`. No X label invented.

## 5. P3 short-fragment / OCR diagnosis (summary)

Crop transform came from saved `crop_mapping` (`SOURCE_IMAGE_PIXELS`, crop `[914,0,1399,404]`,
render scale 1.0); CSV coordinates are panel-local, so source = local + (914,0).

| Series | pts | source bbox | length/chord/ratio | direction changes | OCR association |
|---|---:|---|---|---|---|
| `_color_01_branch_03` | 41 | [1036,125,1076,126] | 42.07 / 40.01 / 0.951 | 4 | entire 40 px² bbox overlaps cached text `Bulk Te——Discharge —` (conf 0.89585), bbox [973,114,1185,139]; nearest distance 0 |
| `_color_03_branch_03` | 14 | [1181,125,1194,126] | 13.83 / 13.00 / 0.940 | 1 | 13/13 px² overlaps `Charge` (conf 0.98309, [1175,116,1251,140]); 4 px² overlaps `Bulk Te——Discharge —` |
| `_color_01_branch_04` | 28 | [1052,97,1060,105] | 35.07 / 8.25 / 0.235 | 4 | 64/64 px² overlaps `Te NSs —— Discharge` (conf 0.88995); compact closed stroke (ratio 0.235) |

Genuine-looking elongated neighbours were checked too: `_color_01_branch_05` (22 pt, ratio 0.917,
nearest OCR 5 px, no overlap) and `_color_01_branch_06` (19 pt, ratio 0.979, overlaps `0.2` label)
are short near-horizontal data-like fragments; `_color_03_branch_01/02` (35/44 pt) have no OCR overlap.

**Evidence-backed candidate rule (proposed, not implemented):** classify a retained short path as
`OCR_ASSOCIATED_GLYPH_NEEDS_REVIEW` (review-only, not plotted as data) only when its *entire* ordered
bbox is contained in a cached high-confidence OCR text box, it is spatially separate from the main
curve, and it is either near-closed (chord/length < ~0.35) or lies on a legend text baseline.
False-positive risks: data curves crossing label text inside the plot, coloured legend swatches that
legitimately resemble data, and OCR boxes that span a wide legend row covering real curve pixels.
Because this patch does not change the P3 filter and the rule has non-trivial false-positive risk,
**no generic threshold was raised and no production filter was justified here**; the two candidates
remain `NEEDS_REVIEW`. See `p3_short_fragment_diagnostics.md` for exact ordered coordinate sequences,
all OCR overlaps/nearest distances and the diagnostic image `P3_short_fragment_diagnostic.png`.

## 6. Requirement check

| # | Requirement | Result |
|---|---|---|
| 1 | callout exclusion QC with both reason fields | **FAIL** — callout 0 pts, waveform 366 pts, but `excluded_partial_branches` empty and no `source_*_reason` fields |
| 2 | P8 d two red (317+319) + one blue (317) | **PASS** |
| 3 | P8 a 22146/178 and 1835/26, no cross-segment connectors | **PASS** |
| 4 | P3 path geometry + OCR spatial association | **PASS** — diagnostic produced; no arbitrary filtering |
| 5 | no threshold relaxation; insufficient evidence stays NEEDS_REVIEW | **PASS** |
| six-way | five-way junction, panel c, y_value | unchanged / unresolved as before |

## 7. Remaining blockers

- 1 failing scientific test (callout exclusion QC) with concrete pixel-gate root cause.
- P3 ring-like short fragments remain in output as `NEEDS_REVIEW`; purple x≈355–390 unresolved.
- P3 dual Y `UNASSIGNED`; panel b `UNRESOLVED`; panel c X-semantics gate; all `review_state = NEEDS_REVIEW`.
- No independent annotated point benchmark: **no point-level accuracy claim**.

## 8. Artifacts

Six comparison PNGs, `p3_short_fragment_diagnostics.md`, `P3_short_fragment_diagnostic.png`,
this report and `manifest.json` are committed to `review/callout-exclusion-record-and-glyph-qc/`
on this branch only. No PDF/SI/raw OCR/unrelated file is included.
