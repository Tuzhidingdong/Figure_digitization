# Phase 4 — dual Y axis, Panel c semantics and numeric calibration

Date: 2026-11-25
Inputs only: existing cached-run `digitization.json`, `panel_series.csv`, QC objects and archived OCR
JSON. No new extraction, no OCR, no production change and no invented label or value.

## 1. P3 dual Y axis (`auto-03`)

| Item | Evidence |
|---|---|
| X calibration | `CALIBRATED_NUMERIC`, slope `0.238565`, intercept `-13.902`, unit `None` |
| Left/right Y calibrations | both `CALIBRATED_NUMERIC`, units null |

| Side | Status | Slope | Intercept | RMSE | Unit |
|---|---|---:|---:|---:|---|
| LEFT | CALIBRATED_NUMERIC | -15.987067 | 5303.732 | 3.3439 | None |
| RIGHT | CALIBRATED_NUMERIC | -2.538042 | 845.172 | 0.5675 | None |

Axis-assignment evidence: `AMBIGUOUS_DUAL_Y_AXIS` /
`SERIES_TO_Y_AXIS_MAPPING_REQUIRED`, match evidence
`NO_UNIQUE_MATCH`. Both sides report
`NO_CHROMATIC_TEXT_COLOR` for tick labels, no axis-title colour evidence and no continuous chromatic
spine; no curve-to-axis colour match is possible. Series-level `y_calibration` is absent and
`y_mapping_status = AMBIGUOUS_DUAL_Y_AXIS`, `y_axis_side = UNASSIGNED`, `y_value` empty.

**Decision:** keep `UNASSIGNED / AMBIGUOUS_DUAL_Y_AXIS`. No series is assigned to a Y axis and no
physical Y value is generated. The two numeric calibrations are retained as candidates only;
they are not results.

## 2. P8 Panel c X-axis semantics

`trace_specification.status = NEEDS_REVIEW`, reason
`X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER`, `x_axis_label = None`,
`automation_status = NOT_READY`.
The pipeline calls the raster tracer only when this status is `READY`, so panel c yields 0 points.

Cached OCR inside the panel-c crop contains 9 rows. Near the X axis: numeric ticks `39.0, 39.5, 40.0,
40.5, 41.0` (confidence ≈1.0) and a candidate `Time (h)` with confidence **0.54463** at bbox
`[679,872,753,903]`. `is_supported_monotonic_x_label()` would accept `Time (h)` as a monotonic
term, but the axis-label evidence gate requires higher-confidence selection; this candidate was not
promoted. Numeric tick anchors alone do **not** establish that X is a monotonic ordered variable.

**Decision:** keep the gate. Missing evidence: a grounded, sufficiently confident X-axis label (or
other explicit axis-semantics evidence) for panel c. No label was invented and the threshold was not
lowered.

## 3. Numeric calibration by series

| Panel / series family | X | Y | Numeric `y_value` in CSV | Caveat |
|---|---|---|---|---|
| P8 a red/blue | Time (h), `CALIBRATED_NUMERIC`, unit null | Voltage, LEFT `CALIBRATED_NUMERIC`, unit V | yes (22,146 + 1,835) | all still `NEEDS_REVIEW_PARTIAL_PATH`; segment geometry only |
| P8 d two red + blue | Cycle number, `CALIBRATED_NUMERIC`, unit null | LEFT/RIGHT `CALIBRATED_NUMERIC`; series `y_unit = Ah L-1` | yes (317+319+317) | second red has unpaired spur; series-level `y_label` is inherited and not proof of physical axis meaning |
| P8 b red/blue | no X/Y calibration (`UNRESOLVED`) | none | **no** (0 / 1226) | pixel geometry only |
| P8 c | no points | none | no | X-semantics gate |
| P3 all series | X `CALIBRATED_NUMERIC`, unit null | both Y candidates numeric but unassigned, units null | **no** (0 / 1377) | dual-Y ambiguity blocks physical Y |

Calibration anchors, slopes, intercepts and RMSE values are retained in `digitization.json`; they
are evidence for a pixel→data mapping, not proof of point-level accuracy. Geometric precision
(ordered pixel coordinates) and numerical-calibration precision are distinct and neither has an
independent annotated benchmark here.

## 4. Unresolved

- P3 series-to-Y-axis assignment and unit interpretation.
- P8 panel c X-axis semantics (missing confident label evidence).
- P8 panel d per-axis physical meaning of the `y_label` inherited from a single label.
- All review-state series remain `NEEDS_REVIEW`; no accuracy claim is made.
