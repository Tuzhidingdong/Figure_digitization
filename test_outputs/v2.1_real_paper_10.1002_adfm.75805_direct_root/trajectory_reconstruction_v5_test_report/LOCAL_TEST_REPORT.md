# PR #26 V5 trajectory reconstruction — local test report

Test-only validation. No production source, tests, Skill, algorithm parameters, config, or
docs were modified. No multimodal vision, no OCR, no reading of prior extraction results as
recognition priors, no manual path annotation.

## 1. Version under test

| Item | Value |
|---|---|
| Repository | `Tuzhidingdong/Figure_digitization` |
| PR | #26 — https://github.com/Tuzhidingdong/Figure_digitization/pull/26 |
| Dev branch | `feat/trajectory-reconstruction-v5-20261127` |
| Exact SHA | `438cfefa94efdb5e0014b8ddbaf0489848b3d1e7` |
| `ls-remote` branch head | `438cfefa94efdb5e0014b8ddbaf0489848b3d1e7` — exact match |
| `ls-remote refs/pull/26/head` | `438cfefa94efdb5e0014b8ddbaf0489848b3d1e7` — exact match |
| Isolated worktree | `E:\Zinc_batters_datas\_worktrees\Figure_digitization_test_v5_438cfefa` (detached HEAD, clean) |
| Python | `D:\Software\Anacoda\python.exe`, 3.13.9 |

The editable install points at the older original checkout, so `PYTHONPATH` was set to the
test worktree's `src` before launching Python. Verified absolute imports:

```
pkg:  E:\Zinc_batters_datas\_worktrees\Figure_digitization_test_v5_438cfefa\src\scientific_figure_data\__init__.py
traj: E:\Zinc_batters_datas\_worktrees\Figure_digitization_test_v5_438cfefa\src\scientific_figure_data\trajectory.py
```

The trace run meta log also records both loaded module paths.

## 2. Synthetic regression test — 10/11 PASS, 1 FAIL

Command:
```
PYTHONPATH=<test-worktree>\src python -m pytest -q tests/test_trajectory_reconstruction.py \
    --junitxml synthetic_junit.xml -p no:cacheprovider
```
JUnit: **11 tests, 10 passed, 1 failed, 0 errors, 0 skipped, 3.349 s; exit code 1**.
The exact specified command (without extra flags) likewise reports 1 failure.

| Test | Result |
|---|---|
| `test_two_solid_traces_are_separated` | PASS |
| `test_solid_and_dashed_paths_keep_real_gaps` | PASS |
| `test_four_mixed_paths_are_independently_traced` | **FAIL** — `assert len(candidates) == 4`, got **5** |
| `test_crossing_paths_are_not_collapsed` | PASS |
| `test_short_legend_swatches_are_not_full_tracks` | PASS |
| `test_blank_plot_returns_no_candidates` | PASS |
| `test_artifact_writer_checks_source_pixels_and_refuses_overwrite` | PASS |
| `test_cli_accepts_trace_image_command` | PASS |
| `test_short_regular_dash_pattern_is_reviewable_below_solid_point_threshold` | PASS |
| `test_irregular_fragment_path_is_not_promoted_by_coverage_alone` | PASS |
| `test_global_path_selection_is_node_disjoint` | PASS |

Failure detail (`logs/synthetic_test_full.log`, `logs/repro_failure.txt`): the fixture has
four paths (2 solid + 2 periodic dashed). V5 produced five review candidates because the
second dashed path was split into two node-disjoint paths:

| Review candidate | Points | Segments | X range | Periodicity |
|---|---:|---:|---|---:|
| TR01 (solid) | 472 | 1 | 59–530 | 0.0 |
| TR02 (solid) | 472 | 1 | 59–530 | 0.0 |
| TR03 (dash, period 15) | 294 | 17 | 59–524 | 0.9355 |
| TR04 (dash fragment) | 117 | 7 | 60–247 | 0.7824 |
| TR05 (dash fragment) | 109 | 6 | 270–437 | 0.9470 |

The gap between x=247 and x=270 (~23 columns) exceeds `max_gap_columns=12`, so the global
path cover splits the single dashed path; both halves independently pass the new periodic-dash
review gate. This is a real defect in the new dash gate / path-cover interaction, not a test
harness problem. No source or test file was changed.

## 3. Ruff

Command:
```
python -m ruff check src/scientific_figure_data/trajectory.py tests/test_trajectory_reconstruction.py
```
Ruff 0.12.0 is installed. Result: **exit code 1**, one pre-existing lint error in the test file:

```
tests\test_trajectory_reconstruction.py:11:1: E402 Module level import not at top of file
  (import placed after pytest.importorskip("PIL.ImageDraw"))
Found 1 error.
```

No lint errors reported in `trajectory.py`. The test file was not modified.

## 4. Real F04-P01 run

`sfd` is not on PATH on this machine. As in PR #25, the run was made through the declared
console entry point `scientific_figure_data.cli:main` via a small runner; this is recorded in
`logs/trace_run_meta.json`.

```
trace-image <01_original.png> --plot-box 85 51 457 327 \
    --out ...\trajectory_reconstruction_v5_local_test
```
Single run, default parameters, fresh output directory. **Exit code 0, duration 2.239 s.**
Image 460 × 365; candidate mask 7,600 pixels / 1,107 column runs.

Effective defaults: `max_tracks=12`, `max_gap_columns=12`, `max_abs_slope=6.0`,
`slope_step=0.5`, `min_contrast=12.0`, `max_run_height=12`, `max_nodes_per_column=16`,
`min_x_coverage=0.25`, `min_active_columns=67`, `min_active_fraction=0.2`,
`start_penalty=6.0`, `max_slope_change=1.5`, `curvature_penalty=1.2`, `gap_penalty=0.35`,
`color_penalty=2.4`, `width_penalty=0.30`, `min_dashed_points=24`,
`min_dashed_x_coverage=0.1`, `min_dashed_active_fraction=0.3`,
`boundary_exclusion_fraction=0.012`.

### Global assignment

| Field | Value |
|---|---|
| `method` | `GLOBAL_NODE_DISJOINT_MIN_COST_FLOW_WITH_LOCAL_TANGENTS` |
| `flow_diagnostics.status` | **PASS** |
| `flow_count` / `path_count` | 12 / 12 |
| `selected_node_count` | 996 |
| `transition_edges` | 25,804 |
| `objective` | 1,125.92466 |
| `node_disjoint` | **true** |
| `max_tracks` | 12 |

### Path distribution

12 paths: **2 `CANDIDATE_REVIEW`, 7 `UNRESOLVED_FRAGMENT_PATH`, 3 `REJECTED_WEAK_PATH`**.
`selected_node_count=996` equals the CSV point rows exactly.

| ID | Status | Points | Segments | X range | Y range | Style | Periodicity | Review reason |
|---|---|---:|---:|---|---|---|---:|---|
| TR01 | CANDIDATE_REVIEW | 297 | 3 | 134–433 | 91–142 | SOLID_WITH_OCCLUSION | 0.0721 | COHERENT_SOLID_PATH |
| TR10 | CANDIDATE_REVIEW | 31 | 3 | 134–181 | 95–99 | DASHED_CANDIDATE | 0.7506 | PERIODIC_DASH_PATTERN |
| TR02 | UNRESOLVED_FRAGMENT_PATH | 141 | 26 | 217–431 | 253–308 | DISCONTINUOUS_UNRESOLVED | 0.0298 | GAP_PATTERN_NOT_SUFFICIENTLY_REGULAR |
| TR03 | UNRESOLVED_FRAGMENT_PATH | 140 | 24 | 217–443 | 220–258 | DISCONTINUOUS_UNRESOLVED | 0.0493 | same |
| TR04 | UNRESOLVED_FRAGMENT_PATH | 83 | 17 | 217–357 | 221–283 | DISCONTINUOUS_UNRESOLVED | 0.0211 | same |
| TR05 | UNRESOLVED_FRAGMENT_PATH | 76 | 17 | 217–356 | 254–308 | DISCONTINUOUS_UNRESOLVED | 0.0540 | same |
| TR06 | UNRESOLVED_FRAGMENT_PATH | 57 | 14 | 279–369 | 228–283 | DISCONTINUOUS_UNRESOLVED | 0.0695 | same |
| TR07 | UNRESOLVED_FRAGMENT_PATH | 56 | 10 | 277–357 | 246–308 | DISCONTINUOUS_UNRESOLVED | 0.0492 | same |
| TR09 | UNRESOLVED_FRAGMENT_PATH | 38 | 8 | 134–198 | 94–177 | DISCONTINUOUS_UNRESOLVED | 0.1010 | same |
| TR08 | REJECTED_WEAK_PATH | 52 | 3 | 158–211 | 99–182 | SOLID_WITH_OCCLUSION | 0.1054 | INSUFFICIENT_COVERAGE_OR_SUPPORT |
| TR11 | REJECTED_WEAK_PATH | 13 | 1 | 409–421 | 304–308 | SOLID_CANDIDATE | 0.0 | INSUFFICIENT_COVERAGE_OR_SUPPORT |
| TR12 | REJECTED_WEAK_PATH | 12 | 1 | 423–434 | 253–258 | SOLID_CANDIDATE | 0.0 | INSUFFICIENT_COVERAGE_OR_SUPPORT |

Note: the JSON field `rejected_candidate_track_ids` lists all 10 non-review IDs, i.e. it
includes the 7 `UNRESOLVED_FRAGMENT_PATH` entries as well as the 3 weak-path rejections.

### Gap/segment/periodicity statistics

* TR10 (the only newly-promoted dashed candidate): gaps `[8, 9]`, segments `[7, 12, 12]`,
  `gap_cv=0.0588`, `segment_length_cv=0.2281`, periodicity `0.7506`. The gap lengths are nearly
  equal and segment lengths regular, so the periodicity statistics are internally consistent.
  However the path is short (31 points, X coverage 0.129) and nearly horizontal (Y 95–99 over
  X 134–181). Without vision or priors it cannot be determined whether this is a genuine short
  dashed curve or a gridline/legend-like repeat. **It remains a review hypothesis only.**
* The seven unresolved paths have 8–26 segments, irregular gaps (`gap_cv` 0.56–0.91) and low
  periodicity (0.021–0.101); they were **not** promoted merely because of high X coverage
  (e.g. TR02 coverage 0.578, TR03 0.610). This is a genuine improvement over v4, where those
  fragments were review candidates.
* No "large irregular fragment promoted to review" case was found among the 12 paths.

## 5. Artifact, source-pixel and consistency audit

| Check | Result |
|---|---|
| CSV point rows | 996; all `source_pixel_verified=True` |
| Independent mask recomputation | all 996 CSV points inside the recomputed 92nd-percentile foreground mask |
| CSV RGB vs original image | 0 mismatches |
| Duplicate source-node assignment | **0** (flow `node_disjoint=true` independently confirmed per-coordinate) |
| One point per column per track | 12/12 tracks |
| Points on plot frame / strong axis lines | **0** |
| `source_pixel_integrity` | **PASS**; `generated_pixels=0`; `interpolated_pixels=0` |
| Overlay ↔ CSV | 996/996 points drawn in the matching per-track overlay; all overlays 460 × 365 |
| Combined vs all-series overlay | byte-identical |
| Inventory ↔ diagnostics | 12 inventory rows; IDs, counts, ranges, reasons consistent |
| `index.html` offline | 4,578 B; 0 external URLs; 0 scripts; 16 images and 3 CSV/JSON links all present |
| Path decomposition failure | none observed; 12 flows → 12 paths → 12 overlays |

Machine-readable evidence: `logs/validation_report.json`, `logs/validation_stdout.txt`,
`logs/summarize_out.txt`.

## 6. Defects and unresolved items

1. **Synthetic regression failure (v5 defect).** One four-path fixture yields 5 review
   candidates because a single periodic dashed path is split by a gap larger than
   `max_gap_columns` and both halves pass the new periodicity gate. Root cause evidence in
   `logs/repro_failure.txt`. Test remains failing; no fix applied.
2. **New dashed gate can promote near-horizontal short fragments.** TR10 in the real run has
   Y 95–99 over X 134–181 with 31 points. Its periodicity is genuine by the computed metrics,
   but the geometry is ambiguous (gridline/underline vs short dashed curve). Not claimed as a
   scientific curve.
3. **Ruff E402** in the test file (pre-existing style issue; not fixed).
4. **Environment:** editable install points to an old checkout; `PYTHONPATH` override required.
   `sfd` not on PATH; entry point invoked through `cli.main()`.
5. **`rejected_candidate_track_ids` semantics** mixes unresolved fragments with true weak-path
   rejections; the per-track `status` field is the reliable discriminator.
6. No OCR/calibration; outputs are pixel paths only. Point-level scientific accuracy is
   **NOT_EVALUATED**. The 2 review candidates are hypotheses, not confirmed scientific curves.

## 7. Scope statement

Only package installation/path resolution, the specified pytest run, the specified Ruff run,
one default-parameter real-image run, and offline audits were performed. No source or test
logic was edited; no parameter was tuned; no result was adjusted to match an expected curve
count.
