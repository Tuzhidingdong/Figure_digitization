# Manual single-panel validation — verification report

Date: 2026-11-22. Scope: controlled validation of the existing explicit-anchor + ordered-pixel-path
digitization path only. NOT automatic recognition, NOT a scientific data product.

## 1. Selected panel and rationale
- Figure: `MAIN_FIG_P7_05` (Figure 5), panel `a` — CV curves of PVO//modified Cu and PVO//normal Cu.
- Rationale: both axes carry readable numeric ticks; the solid red 4th-cycle anodic branch is a
  continuous, visually distinguishable curve; the trace is non-monotonic in Y, which is the supported
  ordered-path case. Excluded: Figure 2 (four stacked CE sub-panels, dense scatter), Figure 4 (multiple
  overlapping LSV/EIS traces), SEM/optical panels, and the known-bad `MAIN_FIG_P8_06` strip.

## 2. Source image
- Existing downstream artifact: `test_outputs/real_paper_10.1002_adfm.75805/out/papers/root-paper/evidence/MAIN_FIG_P7_05_1.png`
- Validation copy: `input/extracted_figures/MAIN/MAIN_MAIN_FIG_P7_05.png`
- SHA256: `3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de` (upstream asset, validation copy and downstream copy all identical)
- Size: 1401 x 677 px; coordinate system: local image pixels, origin top-left, x right, y down.

## 3. Panel geometry
- `plot_box = [83, 45, 421, 296]` px; measured frame: left 83-84, right 420-421, top 45-46, bottom 296.
- Passed via supported override field `plot_box` (used by `pipeline.py:664`). Note: this field is
  implemented in the engine but not shown in the INPUT_CONTRACT example.

## 4. Axis anchors (manual, from visible ticks)
- X "Voltage (V)", unit `V`: pixel 83.5 -> 0.0 V; pixel 420.5 -> 1.8 V.
  Intermediate ticks observed at 139.5/195.5/252/308/364 px for 0.3/0.6/0.9/1.2/1.5 V.
- Y "Current (A g-1)", unit `A g-1`: pixel 65.5 -> 3.0; pixel 274.5 -> -2.0.
  Intermediate ticks observed at 107.5/149.5/191.5/233 px for 2/1/0/-1.
- Intermediates were used only as a consistency check, not as extra anchors.

## 5. Ordered pixel path
- 25 points, visual sweep order of the solid red 4th-cycle anodic branch, ~0.30 V to ~1.64 V.
- Not sorted by X by the annotator; no discontinuities crossed; dashed 1st-cycle and grey curves avoided.
- Full list: `input/digitization_overrides.json`; rationale: `annotation/MANUAL_ANNOTATION.json`.

## 6. API actually called
- `python -m scientific_figure_data scan --input-root <new>/input --output-root <new>/out`
- `python -m scientific_figure_data run --paper-id root-paper --input-root <new>/input --output-root <new>/out --workers 1`
- No OCR, no PDF/SI access, one worker, zero LLM tokens, no production code changes.
- Note: an initial invocation discovered 0 papers because the minimal package lacked an adapter
  strong marker; a `main_analysis.md` marker was added (new file), then the single processing run above
  was executed. No engine processing occurred in the zero-discovery invocation.

## 7. Calibration results
- X: status `CALIBRATED_NUMERIC`, slope 0.005341246290801187, intercept -0.4459940652818991,
  rmse 1.5700924586837752e-16, 2 anchors, unit V.
- Y: status `CALIBRATED_NUMERIC`, slope -0.023923444976076555, intercept 4.5669856459330145,
  rmse 0.0, 2 anchors, unit A g-1.
- `calibration_errors = {}` (empty). QC components: `axis_calibration_x/y = CALIBRATION_EVIDENCE_PRESENT`.

## 8. Extracted points
- 25 data points; `extraction_method = EXPLICIT_ORDERED_PIXEL_POLYLINE`;
  `extraction_status = EXTRACTED_PROVISIONAL`; points_count 25; `path_order = PRESERVED`.

## 9. First/last points (pixel -> value)
- p0 (140,190) -> (0.301780415 V, 0.0215311 A/g)
- p1 (165,190) -> (0.435311573 V, 0.0215311 A/g)
- p2 (185,188) -> (0.542136499 V, 0.06937799 A/g)
- p3 (195,178) -> (0.595548961 V, 0.308612440 A/g)
- p4 (202,155) -> (0.632937685 V, 0.858851675 A/g)
- p20 (340,162) -> (1.370029674 V, 0.691387560 A/g)
- p21 (350,172) -> (1.423442136 V, 0.452153110 A/g)
- p22 (365,177) -> (1.503560831 V, 0.332535885 A/g)
- p23 (380,176) -> (1.583679525 V, 0.356459330 A/g)
- p24 (390,175) -> (1.637091988 V, 0.380382775 A/g)

## 10. Order and mapping checks
- CSV point_index 0..24; pixel_x sequence strictly increasing; no re-sorting occurred.
- Independent linear-formula check: X(83.5)=0.0, X(139.5)=0.29911 (0.3 within tick-mark reading
  tolerance), X(420.5)=1.8; Y(65.5)=3.0, Y(191.5)=-0.01435 (0 within reading tolerance), Y(274.5)=-2.0.
- Point-level check: p14 pixel (292,76) -> X 1.113649852 V, Y 2.748803828 A/g, matching
  slope*pixel+intercept. Y values show 4 direction changes, confirming order was not x-sorted
  into a monotonic-value series.

## 11. QC
- `qc_status = PROVISIONAL_UNCALIBRATED`, `review_state = NEEDS_REVIEW`, paper status `COMPLETED_WITH_REVIEW`.
- Warnings: `SUBJECT_LINK_UNASSIGNED`, `CONDITIONS_NOT_LINKED`. No point-count or calibration warnings.
- `panel_segmentation = UNKNOWN` (whole-figure fallback), `legend_association = UNKNOWN`,
  `scientific_acceptance = NOT_ASSESSED_WITHOUT_ANNOTATED_REAL_PAPER_BENCHMARK`.

## 12. New files
- `input/{evidence_index.json,main_analysis.md,digitization_overrides.json}`
- `input/extracted_figures/MAIN/MAIN_MAIN_FIG_P7_05.png`
- `annotation/MANUAL_ANNOTATION.json`
- `annotation_aids/panel_a_zoom_grid.png`, `panel_a_anodic_zoom.png`, `panel_a_mainpeak_zoom.png`
- `out/` (corpus manifest, run_report, catalog.sqlite, paper artifacts, evidence copy, `series/MAIN_FIG_P7_05__1/panel_series.csv`)
- `scan.log`, `run.log`, `VALIDATION_REPORT.md`

## 13. Conclusion
**PASS — core manually-annotated digitization engine is effective** for the controlled path:
explicit anchors produce numeric linear calibration with evidence and finite RMSE; an ordered pixel
path is mapped point-by-point to scientific values with pixel coordinates retained, order preserved,
units propagated, and full provenance. This does NOT establish automatic figure/panel/curve recognition
or scientific accuracy, and does not mean the project is complete.
