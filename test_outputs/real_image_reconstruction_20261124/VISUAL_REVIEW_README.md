# Real-image reconstruction visual review — P3_02 / P8_06

- Date: 2026-11-24
- Baseline commit: `7167107e6a0df829436489321d5fc51b8ea7d22b`
  (`feat/real-image-regression-diagnostics`)
- Review branch: `review/real-image-reconstruction-20261124`
- Purpose: allow direct visual inspection of what the current pipeline actually
  extracts from the two real published figures. This is **not** a numerical
  accuracy validation and does not replace an annotated benchmark.

No source code, configuration, test, Skill, frozen plan or original image was
modified. No OCR model was re-run and no paper, PDF or SI was re-opened.

---

## 1. The six images

| File | What it shows |
|---|---|
| `P3_02_reconstructed.png` | Three views of the only panel that produced data (`auto-03`): LEFT candidate scale, RIGHT candidate scale, and raw pixel geometry. The Y axis is `UNASSIGNED`, so both candidate scales are drawn separately and neither is presented as a result. |
| `P3_02_side_by_side.png` | Left: the unmodified original figure. Right: the reconstruction above, scaled to the same height. |
| `P3_02_overlay.png` | Extracted pixel positions drawn on the unmodified original (small colour-coded markers), plus detected panel boxes and plot boxes. |
| `P8_06_reconstructed.png` | Numeric reconstruction of `auto-frame-01` (single LEFT axis) and `auto-frame-04` (LEFT + RIGHT axes). Panels with zero traced points are not drawn. |
| `P8_06_side_by_side.png` | Left: the unmodified original figure. Right: the reconstruction above. |
| `P8_06_overlay.png` | Extracted pixel positions drawn on the unmodified original, plus detected panel boxes and plot boxes. |

All PNGs are the full-resolution files produced during this review; they were
not resized or recompressed for upload.

---

## 2. Original images (already in this repository)

| Figure | Repository path | SHA256 |
|---|---|---|
| P3_02 | `tests/fixtures/real_figures/P3_02.png` | `9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e` |
| P8_06 | `tests/fixtures/real_figures/P8_06.png` | `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549` |

The extraction run created byte-identical temporary copies of these files inside
its input tree. Those copies are intentionally **not** uploaded again.

---

## 3. Where the plotted numbers come from

1. `extract_only.py` replays the production pipeline
   (`scientific_figure_data.pipeline.process_paper`) using the cached OCR rows in
   `tests/fixtures/real_figures/P3_02_ocr.json` and `P8_06_ocr.json`.
   `ocr.run_ocr` is monkey-patched, so no OCR engine is executed.
2. The pipeline writes per-panel point tables. Every plotted coordinate is read
   from these files, unmodified:

   - `extraction/P3_02/output/papers/paper-p3-real__01_preprocessing/series/MAIN_FIG_P3_02__auto-03/panel_series.csv`
   - `extraction/P8_06/output/papers/paper-p8-real/series/P8_06__auto-frame-01/panel_series.csv`
   - `extraction/P8_06/output/papers/paper-p8-real/series/P8_06__auto-frame-04/panel_series.csv`

   Columns used: `point_index`, `x_value`, `y_value`, `pixel_x`, `pixel_y`,
   `y_axis_side`, `y_left_candidate`, `y_right_candidate`, `y_mapping_status`.

3. Series grouping, colours, calibrations and axis assignments are read from:

   - `extraction/P3_02/output/papers/paper-p3-real__01_preprocessing/digitization.json`
   - `extraction/P3_02/output/papers/paper-p3-real__01_preprocessing/panel_layout.json`
   - `extraction/P8_06/output/papers/paper-p8-real/digitization.json`
   - `extraction/P8_06/output/papers/paper-p8-real/panel_layout.json`

4. `render_reconstructions.py` only reads the CSVs and the two JSON files above.
   Nothing is interpolated, smoothed, mirrored or invented. Empty `y_value`
   stays empty.

5. `extraction_run.json` records the pipeline status and counts for both cases.
   `reconstruction_manifest.json` records, per plotted series, the point count,
   RGB colour, `y_axis_side`, `y_mapping_status` and how many physical /
   LEFT-candidate / RIGHT-candidate values exist.

---

## 4. Panel and series summary

### P3_02 (`10.1002/adma.202001469`)

6 panels detected, 12 series entries, 6 series with data, **1100 points total**.

| Panel | bbox (source px) | series entries | series with points | points |
|---|---|---|---|---|
| auto-01 | [0, 0, 547, 404] | 1 | 0 | 0 |
| auto-02 | [480, 0, 981, 404] | 1 | 0 | 0 |
| auto-03 | [914, 0, 1399, 404] | 7 | 6 | 1100 |
| auto-04 | [0, 404, 935, 508] | 1 | 0 | 0 |
| auto-05 | [938, 404, 1399, 807] | 1 | 0 | 0 |
| auto-06 | [0, 508, 1005, 807] | 1 | 0 | 0 |

Series with data (all in `auto-03`, which is panel (c) of the published figure):

| Panel | Series suffix | Points | RGB | Y side | Y mapping status | X calibration | Y calibrations available |
|---|---|---|---|---|---|---|---|
| auto-03 | `_color_01_branch_01` | 333 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-03 | `_color_01_branch_02` | 133 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-03 | `_color_01_branch_03` | 62 | [242, 132, 64] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-03 | `_color_02_branch_01` | 332 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-03 | `_color_02_branch_02` | 60 | [231, 46, 47] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-03 | `_color_03` | 180 | [130, 56, 131] | UNASSIGNED | AMBIGUOUS_DUAL_Y_AXIS | CALIBRATED_NUMERIC | LEFT, RIGHT |

Zero-point entries in `auto-03`: `_color_04` (323 detected family pixels, no
traced path). Panels `auto-01/02/04/05/06` have a single unresolved placeholder
series each and no points.

### P8_06 (`10.1002/adma.202404834`)

4 panels detected, 9 series entries, 4 series with data, **2223 points total**.

| Panel | bbox (source px) | plot box (panel px) | series entries | series with points | points |
|---|---|---|---|---|---|
| auto-frame-01 | [0, 141, 1407, 514] | [93, 53, 1338, 320] | 3 | 1 | 1237 |
| auto-frame-02 | [27, 540, 481, 911] | [55, 53, 399, 318] | 2 | 0 | 0 |
| auto-frame-03 | [491, 540, 937, 911] | [54, 53, 392, 318] | 1 | 0 | 0 |
| auto-frame-04 | [955, 544, 1391, 895] | [53, 50, 383, 301] | 3 | 3 | 986 |

Series with data:

| Panel | Series suffix | Points | RGB | Y side | Y mapping status | X calibration | Y calibrations available |
|---|---|---|---|---|---|---|---|
| auto-frame-01 | `_color_01_branch_01` | 1237 | [238, 63, 70] | LEFT | ASSIGNED | CALIBRATED_NUMERIC | LEFT |
| auto-frame-04 | `_color_01_branch_01` | 329 | [245, 167, 172] | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-frame-04 | `_color_01_branch_02` | 328 | [245, 167, 172] | LEFT | ASSIGNED_BY_DUAL_AXIS_EXCLUSION | CALIBRATED_NUMERIC | LEFT, RIGHT |
| auto-frame-04 | `_color_02` | 329 | [17, 100, 172] | RIGHT | COLOR_MATCHED_TO_Y_AXIS_TEXT | CALIBRATED_NUMERIC | LEFT, RIGHT |

Zero-point entries: `auto-frame-01` `_color_01_branch_02` and `_color_02`
(the blue family is detected but not traced), `auto-frame-02` `_color_01` and
`_color_02` (inset b), `auto-frame-03` unresolved placeholder (inset c).

---

## 5. Anomalies visible in these images

1. **P3_02 — same-colour branch interleaving.** The "branches" of one colour
   family are not separated into single curves. Consecutive `point_index`
   values alternate between two same-colour curves, e.g. at
   `pixel_x = 60, 61, 62` the extracted `pixel_y` is `163.5, 226.5, 170.5`.
   The pixel positions sit on real ink (see the overlay), but each drawn line
   is the raw extraction order, not a validated single curve. This produces the
   box-like zigzag in `P3_02_reconstructed.png` and
   `P3_02_side_by_side.png`.
2. **P3_02 — dual-Y ambiguity.** All 6 series are `UNASSIGNED` with
   `AMBIGUOUS_DUAL_Y_AXIS`; `y_value` is empty for every point. The figure shows
   both candidate scales separately and explicitly labelled as candidates.
   No axis was chosen and no physical value was generated.
3. **P8_06 — annotation boxes traced as data.** In `auto-frame-01` the
   reconstruction contains two isolated excursions to about 2.2 V and 2.6 V.
   They coincide with the red dashed annotation rectangles in panel (a) of the
   source image, i.e. annotation pixels were followed as if they were curve
   pixels.
4. **P8_06 — blue "without urea" curve missed.** The blue family is detected
   (6566 family pixels in `auto-frame-01`) but yields 0 points; only the red
   "with urea" curve is traced.
5. **P8_06 — insets b/c not extracted.** `auto-frame-02` and `auto-frame-03`
   (the two magnified insets) produce 0 traced points.
6. **P8_06 — weaker LEFT evidence.** The two red branches in `auto-frame-04`
   are assigned to the LEFT axis by `ASSIGNED_BY_DUAL_AXIS_EXCLUSION`, not by
   direct axis-text/colour matching. The blue series is
   `COLOR_MATCHED_TO_Y_AXIS_TEXT`.

Units remain unresolved (`unit: null`) for both cases, so all axis labels in the
reconstructions say "unit unresolved".

---

## 6. Interpretation limits

- Visual agreement between a reconstruction and the source figure is **not**
  evidence of point-level accuracy.
- There is no independent manual annotation for these two figures in this
  review, so no error metric, tolerance or accuracy claim is made.
- The P3_02 reconstruction intentionally does not contain a single physical
  Y curve, because the pipeline cannot resolve the dual Y axis.
- The P8_06 reconstruction covers only the panels that produced points.

---

## 7. File inventory

| Path | Role |
|---|---|
| `P3_02_reconstructed.png` | reconstruction (candidate scales + pixel geometry) |
| `P3_02_side_by_side.png` | original vs reconstruction |
| `P3_02_overlay.png` | extracted pixels on the original |
| `P8_06_reconstructed.png` | reconstruction (LEFT and dual-axis panels) |
| `P8_06_side_by_side.png` | original vs reconstruction |
| `P8_06_overlay.png` | extracted pixels on the original |
| `reconstruction_manifest.json` | per-series plot manifest (counts, colours, axis status) |
| `extraction_run.json` | pipeline run record for both cases |
| `extract_only.py` | replay script used for extraction (cached OCR) |
| `render_reconstructions.py` | rendering script (reads only the CSVs/JSON above) |
| `extraction/P3_02/output/.../panel_series.csv` | P3_02 point table |
| `extraction/P3_02/output/.../digitization.json` | P3_02 series metadata and calibrations |
| `extraction/P3_02/output/.../panel_layout.json` | P3_02 panel boxes |
| `extraction/P8_06/output/.../panel_series.csv` (2 files) | P8_06 point tables |
| `extraction/P8_06/output/.../digitization.json` | P8_06 series metadata and calibrations |
| `extraction/P8_06/output/.../panel_layout.json` | P8_06 panel boxes |
