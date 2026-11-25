# Phase 2–4 test report

Date: 2026-11-25
Branch: `review/phase2-4-comprehensive`, created from Phase 1 report commit
`4922071064803f47f6212c2f718452e2b522d60d`. Phase 1 baseline HEAD: `4495a4a5…`.

## Production change
None. `src/` diff against the Phase 1 report commit is 0 files. Algorithm version remains `0.8.2`.
No new tests were added in this branch.

## Compile / import checks
- `python -m compileall -q src/scientific_figure_data` → exit 0.
- Core module imports on Python 3.13.9 → exit 0.

## Four-file full suite
**Not rerun in Phase 2–4** because production code did not change. The applicable result is the
Phase 1 run on `4495a4a5d945ff7fcacc427e0f0dfd6a16c12f4c`:

```
python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0
```

**159 collected, 159 passed, 0 failed, 0 skipped, exit code 0, 197.12s.** It applies only to that
Phase 1 HEAD, not to a new production implementation. No focused test was run separately here.

## Requirement coverage in the existing suite
| Required invariant | Existing test |
|---|---|
| full evidence object vs compact review summary | `test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations` |
| partial segments not connected across breaks | `test_reconstruction_keeps_explicit_path_segment_breaks`, `test_panel_series_csv_preserves_path_segment_indices` |
| independent curves not wrongly merged | `test_full_span_partial_qc_branch_is_not_auto_excluded`, real-image P8 panel-d regression |
| annotation candidate isolated from curve | same callout test (366 waveform points, 0 callout points) |
| unsupported junction not bridged | `test_2d_path_tracer_rejects_unsupported_five_way_junction` |
| dual-Y ambiguity | `test_unresolved_dual_axis_keeps_vector_geometry_and_calibrated_x` |
| unresolved mapping gives no scientific values | `test_geometry_only_trace_specification_does_not_require_a_y_axis_mapping`, `test_qc_distinguishes_numeric_axis_calibration_from_uncalibrated_thresholds` |
| X-axis semantics gate blocks | `test_trace_specification_requires_ordered_x_axis_and_numeric_axes` |

There is **no dedicated test** asserting that OCR bbox overlap must not automatically delete a
candidate. Current production has no such deletion rule; the Phase 3 decision to keep all three
candidates as review-only is a diagnostic conclusion, not a new tested algorithm behaviour.

## New visual/OCR work
None in this branch. P8/P3 numbers quoted in Phase 2–4 reports are inherited from previously
validated cached runs, not freshly re-extracted or re-rendered here. No point-level accuracy claim
is made without an independent annotated benchmark.
