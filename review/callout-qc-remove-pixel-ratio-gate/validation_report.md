# Callout exclusion QC — remove pixel-count ratio gate (validation report)

Date: 2026-11-24
Repository: `Tuzhidingdong/Figure_digitization`
Branch: `fix/callout-qc-remove-pixel-ratio-gate`
Validated HEAD: `dfb5a48a9e3fa5c61d0504e8233afad82baab7f9`
Parent / baseline: `946bff14994243ed88ea3391fe0fd273c48b780f`
Required code commit `947141f82a18a6264872c91d7e26ae438144abc5` is an ancestor of HEAD (verified).
Algorithm version: `0.8.2`.

## 1. Protected state

Existing project only; no clone/worktree, no OCR rerun, no paper/PDF/SI access, no dependency install.
Before sync: branch `fix/callout-exclusion-record-and-glyph-qc` @ `946bff1`, clean tracked tree,
untracked `.agents/`, `__pycache__/`, `test_outputs/`. `stash@{0}`, the `STATUS.md` backup, all prior
`test_outputs/` and all earlier review artifacts are intact. No `reset --hard`, `git clean`, stash
pop/drop or `git add -A`. `main`, every earlier review/fix branch, PR #22 and the frozen
`TASK_PLAN_v1.4.1.md` were not touched. No source or test file was edited during validation.

Compile/import checks passed: `compileall -q src/scientific_figure_data` exit 0; core imports exit 0
on Python 3.13.9.

## 2. One-pass targeted pytest

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py `
  tests/test_real_image_regressions.py tests/test_upstream_compat.py `
  -o addopts="" -q --durations=0
```

| Metric | Value |
|---|---|
| Collected / executed | **159** |
| Passed | **158** |
| Failed | **1** |
| Skipped | **0** |
| Exit code | **1** |
| Duration | **192.50 s** (0:03:12) |
| Log | `C:\Users\Administrator\AppData\Local\Temp\opencode\pytest_callout_bbox_only.log` |

Exact failing node:
`tests/test_core.py::test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`
— failure is now on the *bbox equality* assertion, not the exclusion count:
`assert excluded["bbox"] == [82, 8, 126, 18]`, actual `[82, 4, 127, 19]`.
The emitted record covers the full connected component (rectangle plus the short dashed marks above
it, x through 127, y from 4), while the test expects only the drawn rectangle outline bbox.
All other assertions (exactly one exclusion record, rejection reason, both source reason fields,
waveform coordinates, zero callout coordinates) pass. No focused rerun was performed; no scientific
assertion was weakened.

## 3. The 288 / 366 pixel callout case — emitted exclusion QC

Direct probe on the synthetic waveform+callout image (same construction as the regression test):

| Item | Value |
|---|---|
| selected waveform | bbox `[11,25,179,77]`, **366** pixels, `PATHS_EXTRACTED` |
| rejected callout component | bbox `[82,4,127,19]`, **288** pixels |
| relative gates | x 45 ≤ 168×0.40 = 67.2; y 15 ≤ 52×0.50 = 26; spatially separate |
| `excluded_partial_branches` count | **exactly 1** in `detect_monotonic_color_branches()` and in `trace_monotonic_color()` QC |
| `rejection_reason` | `PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS` |
| `source_qc_rejection_reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` |
| `source_path_qc_reason` | `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW` (actual nested `path_qc.reason`; public component reason retained) |
| original junction detail | `path_qc.ambiguous_junction_clusters[0]`: 33 junction pixels, 7 ports, reason `UNSUPPORTED_JUNCTION_PORT_COUNT`, ports `[[84,8],[85,7],[93,7],[101,7],[109,7],[117,7],[118,8]]` |
| `classification` | `UNRESOLVED_COMPACT_COMPONENT_RETAINED_IN_REVIEW_QC` (review-only, not an annotation label) |
| `decision_basis` | unique full-span bbox `[11,25,179,77]`, `spatially_separate: True`, relative x/y maxima 0.40/0.50, `selected_path_pixel_count: 366`, `candidate_component_pixel_count: 288`, `pixel_count_ratio_used_for_selection: false` |
| trace result | **366 ordered waveform coordinates**; callout-region pixels in selected path: **0** |

Conclusion: requirements 1–3 are functionally met (record emitted with both reason fields and cluster
detail; callout contributes no plotted coordinate). The single test failure is the record's bbox
granularity (full component vs rectangle outline), not a curve/contamination regression.

## 4. Exact paths and source hashes

- P3_02: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P3_02.png`
  SHA256 `9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e`
- P8_06: `E:\Zinc_batters_datas\Figure_digitization\tests\fixtures\real_figures\P8_06.png`
  SHA256 `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549`
- Fresh output: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124`
- Scripts/records: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\extract_only.py`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\render_reconstructions.py`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\extraction_run.json`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\reconstruction_manifest.json`
- Point tables with `path_segment_index`:
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\extraction\P3_02\output\papers\paper-p3-real__01_preprocessing\series\MAIN_FIG_P3_02__auto-03\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-01\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-02\panel_series.csv`,
  `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_qc_bbox_only_20261124\extraction\P8_06\output\papers\paper-p8-real\series\P8_06__auto-frame-04\panel_series.csv`
- Comparison baselines: `E:\Zinc_batters_datas\Figure_digitization\test_outputs\real_image_reconstruction_20261124`, `E:\Zinc_batters_datas\Figure_digitization\test_outputs\reconstruction_callout_exclusion_qc_20261124`.

Both pipeline runs `COMPLETED_WITH_REVIEW`. All plotted points come from these fresh CSVs.

## 5. Per-series results

### P3_02 — 17 series / 1377 points / 66 segment views (unchanged)

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
The OCR-associated short strokes from the previous diagnostic are **unchanged and still review-only**:
`_color_01_branch_03` 41 pt (source bbox `[1036,125,1076,126]`, chord/length 0.951, overlaps
`Bulk Te——Discharge —`), `_color_03_branch_03` 14 pt (`[1181,125,1194,126]`, 0.940, overlaps `Charge`),
and the loop-like `_color_01_branch_04` 28 pt (`[1052,97,1060,105]`, 0.235, overlaps `Te NSs——Discharge`).
No new P3 filter was added: broad OCR bbox overlap does not prove a stroke is a legend swatch or an
underline, and cannot justify deletion. Purple x≈355–390 remains unresolved; no coordinates were
inferred from mask pixels.

### P8_06 — 12 series / 26160 points (unchanged)

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

Panel a: red **22,146 pts / 178 segments**, blue `without urea` **1,835 pts / 26 segments** — no
regression. Both `EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW`;
segment boundaries preserved, no connectors drawn; callout/arrow pixels absent from curve coordinates.
Panel d: **317 + 319 red + 317 blue**, second red bbox `[58,75,375,83]` with unpaired spur `[242,77]`
still `EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH`.
Panel b: 1226 pts, geometry only, `UNRESOLVED`, `y_value` empty. Panel c: 0 pts, still blocked by the
X-semantics trace-spec gate; no X label invented.

## 6. Verdict and remaining blockers

| Requirement | Result |
|---|---|
| exactly one exclusion record for 288/366 case | **PASS** |
| both source reason fields + original junction cluster detail | **PASS** |
| callout coordinates 0 / waveform 366 | **PASS** |
| P8 a 22146/178 and 1835/26 unchanged | **PASS** |
| P8 d 317+319+317, second red partial-review | **PASS** |
| P3 short strokes kept NEEDS_REVIEW, no new filter | **PASS** |
| one-pass pytest clean | **FAIL** — 1 failure (exclusion bbox granularity) |

Remaining: the bbox-granularity test failure; P3 OCR-associated strokes still drawn as review-only
artefacts; purple x≈355–390 unresolved; panel c X gate; all `review_state = NEEDS_REVIEW`.
No independent annotated benchmark exists: **no point-level accuracy claim**.

## 7. Artifacts

Six comparison PNGs, `validation_report.md` and `manifest.json` are committed only to
`review/callout-qc-remove-pixel-ratio-gate/` on this branch. No PDF/SI, raw OCR or unrelated file included.
