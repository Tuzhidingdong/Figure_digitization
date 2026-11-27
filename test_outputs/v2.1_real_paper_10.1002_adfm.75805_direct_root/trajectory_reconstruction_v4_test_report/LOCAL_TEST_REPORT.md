# PR #25 V2.1 trajectory reconstruction — local test report

Test-only validation. No production source, Skill, test logic, OCR, PDF/SI, or multimodal
vision was used or modified. No curve count/color/style was assumed as a recognition prior.

## 1. Version under test

| Item | Value |
|---|---|
| Repository | `Tuzhidingdong/Figure_digitization` |
| Dev branch | `feat/trajectory-reconstruction-v4-20261127` |
| PR | #25 (Draft) — https://github.com/Tuzhidingdong/Figure_digitization/pull/25 |
| Target commit | `9e540500aac99105caef85f46e4df9ba35b76e6a` |
| `git ls-remote` branch head | `9e540500aac99105caef85f46e4df9ba35b76e6a` — exact match |
| `git ls-remote refs/pull/25/head` | `9e540500aac99105caef85f46e4df9ba35b76e6a` — exact match |
| Isolated worktree | `E:\Zinc_batters_datas\_worktrees\Figure_digitization_test_v4_9e540500` (detached HEAD at target SHA, clean) |
| Python | `D:\Software\Anacoda\python.exe`, Python 3.13.9 |
| Module actually imported | `..._test_v4_9e540500\src\scientific_figure_data\trajectory.py` |

Import-path check: the environment has an editable install of `scientific_figure_data`
pointing at the ORIGINAL checkout, which does not contain `trajectory.py`. `PYTHONPATH` was
therefore set to the test worktree's `src` before launching Python. The import check and the
trace run meta log both confirm the loaded module is the test-worktree file.

## 2. Synthetic regression test

Command (from the isolated worktree, default options plus JUnit output):
```
PYTHONPATH=<test-worktree>\src python -m pytest -q tests/test_trajectory_reconstruction.py \
    --junitxml synthetic_junit.xml -p no:cacheprovider
```
Result: **8 passed, 0 failed, 0 errors, 0 skipped; exit code 0; 4.163 s** (JUnit XML).
The command exactly as specified, `python -m pytest -q tests/test_trajectory_reconstruction.py`,
also exited 0 with all tests passing.

| Test | Result |
|---|---|
| `test_two_solid_traces_are_separated` | PASS |
| `test_solid_and_dashed_paths_keep_real_gaps` | PASS |
| `test_four_mixed_paths_are_independently_traced` | PASS |
| `test_crossing_paths_are_not_collapsed` | PASS |
| `test_short_legend_swatches_are_not_full_tracks` | PASS |
| `test_blank_plot_returns_no_candidates` | PASS |
| `test_artifact_writer_checks_source_pixels_and_refuses_overwrite` | PASS |
| `test_cli_accepts_trace_image_command` | PASS |

CLI help check: `sfd trace-image --help`, dispatched through the declared console entry point
`scientific_figure_data.cli:main`, **exit code 0**. Full usage text is in
`logs/cli_help.log`. `sfd` itself is not on this machine's PATH, so the entry point was
invoked as `python <runner that calls cli.main()> trace-image --help`.

## 3. Plot-region box

Input image: `...curve_extraction_pilot_v1\panels\F04-P01\01_original.png`, 460 × 365 RGB.

The supplied reference box `[85, 51, 457, 327]` was checked against the image coordinate
system and **used unchanged**:

* programmatic line-density analysis finds the strong frame at rows 51/52 and 327/328 and
  columns 84/85 and 457/458 — the reference box matches the inner edges of that frame;
* image size and detector scale are both 1.0, so coordinates are in the same pixel system;
* `detect_plot_box()` in this commit returns `NEEDS_REVIEW / NO_UNAMBIGUOUS_RECTANGULAR_FRAME`;
  `detect_plot_box_candidates()` returns one **provisional** box `[85, 51, 268, 275]` with
  bottom coverage 0.055 and right coverage 0.091 — incomplete and inconsistent with the actual
  frame. It was therefore not adopted.

No curve paths were manually annotated.

## 4. Real image run

Single run with default parameters:
```
PYTHONPATH=<test-worktree>\src python <runner calling cli.main()> trace-image \
  <01_original.png> --plot-box 85 51 457 327 \
  --out ...\trajectory_reconstruction_v4_local_test
```
Exit code **0**, duration **3.668 s**. Output directory was fresh (did not exist), so the
writer's refuse-to-overwrite guard was not triggered. See `logs/trace_run_meta.json` and
`logs/trace_stdout.log`.

Effective defaults recorded in `trajectory_diagnostics.json`: `max_tracks=12`,
`max_gap_columns=12`, `max_abs_slope=6.0`, `slope_step=0.5`, `min_contrast=12.0`,
`max_run_height=12`, `max_nodes_per_column=16`, `min_x_coverage=0.25`,
`min_active_columns=67`, `min_active_fraction=0.20`, `start_penalty=4.0`,
`max_slope_change=1.5`, `curvature_penalty=0.32`, `gap_penalty=0.10`,
`color_penalty=2.4`, `width_penalty=0.30`, `boundary_exclusion_fraction=0.012`.

Candidate mask: **7,600** foreground pixels / **1,107** column runs.

### Candidates and segments

12 tracks were written: **5 `CANDIDATE_REVIEW`** and **7 `REJECTED_WEAK_PATH`**.
929 point rows in total.

| ID | Status | Points | Segments | X range | Y range | Style | Conf. | X coverage |
|---|---|---:|---:|---|---|---|---:|---:|
| TR01 | CANDIDATE_REVIEW | 298 | 3 | 134–434 | 91–142 | SOLID_WITH_OCCLUSION_CANDIDATE | 0.9695 | 0.8091 |
| TR02 | CANDIDATE_REVIEW | 116 | 22 | 217–430 | 279–308 | DISCONTINUOUS_UNRESOLVED | 0.8286 | 0.5753 |
| TR03 | CANDIDATE_REVIEW | 123 | 34 | 217–445 | 228–283 | DISCONTINUOUS_UNRESOLVED | 0.8036 | 0.6156 |
| TR04 | CANDIDATE_REVIEW | 92 | 31 | 217–444 | 220–258 | DISCONTINUOUS_UNRESOLVED | 0.6662 | 0.6129 |
| TR05 | REJECTED_WEAK_PATH | 51 | 4 | 158–211 | 99–182 | DASHED_CANDIDATE | 0.6179 | 0.1452 |
| TR06 | CANDIDATE_REVIEW | 73 | 27 | 252–431 | 246–308 | DISCONTINUOUS_UNRESOLVED | 0.5864 | 0.4839 |
| TR07 | REJECTED_WEAK_PATH | 37 | 4 | 133–194 | 94–99 | DASHED_CANDIDATE | 0.7515 | 0.1667 |
| TR08 | REJECTED_WEAK_PATH | 40 | 21 | 263–383 | 246–258 | DISCONTINUOUS_UNRESOLVED | 0.5404 | 0.3253 |
| TR09 | REJECTED_WEAK_PATH | 32 | 7 | 134–198 | 101–177 | DASHED_CANDIDATE | 0.6218 | 0.1747 |
| TR10 | REJECTED_WEAK_PATH | 24 | 2 | 217–249 | 304–304 | DISCONTINUOUS_UNRESOLVED | 0.7033 | 0.0887 |
| TR11 | REJECTED_WEAK_PATH | 25 | 15 | 265–351 | 224–258 | DISCONTINUOUS_UNRESOLVED | 0.4923 | 0.2339 |
| TR12 | REJECTED_WEAK_PATH | 18 | 10 | 273–317 | 300–308 | DISCONTINUOUS_UNRESOLVED | 0.5089 | 0.1210 |

TR01 is the only review candidate with a genuinely continuous trajectory (3 segments, gaps
of 1 and 2 columns, X coverage 0.81, confidence 0.97). Four review candidates (TR02, TR03,
TR04, TR06) remain `DISCONTINUOUS_UNRESOLVED` with 22–34 segments. All 7 rejected tracks fall
below the 67-point minimum; TR07/TR08/TR10 are near-horizontal and were auto-rejected.

## 5. Artifact and audit checks

| Check | Result |
|---|---|
| `index.html` offline | 4,529 B; 0 external URLs; 0 `<script>` tags; 16 referenced images and 3 CSV/JSON links all present locally |
| Overlay dimensions | all 16 overlays and the combined/mask images are 460 × 365, matching the source |
| Overlay ↔ CSV consistency | every CSV point is drawn in its own `track_TR*_overlay.png`: 929/929 points match one-for-one across all 12 tracks |
| Combined vs all-series overlay | byte-identical (`03_reconstructed_trajectories.png` == `04_all_series_overlay.png`) |
| Duplicate source nodes | **0** (no `(x, y)` reused across tracks or within a track) |
| One point per column per track | yes (column counts equal point counts for all 12 tracks) |
| Points on plot frame / strong axis lines | **0** |
| CSV `source_pixel_verified` | **929 True / 0 False** |
| Independent mask recomputation | recomputed the 92nd-percentile-background mask from the original image; all 929 CSV points fall inside it |
| CSV RGB vs original image | 0 mismatches at the recorded coordinates |
| `source_pixel_integrity` | `PASS`; `generated_pixels=0`; `interpolated_pixels=0` |
| Inventory ↔ diagnostics | 12 inventory rows, IDs and statistics consistent |

Full machine-readable evidence: `logs/validation_report.json`, `logs/validation_stdout.txt`,
`logs/interference.json`, `logs/plotbox_detection.json`.

## 6. Defects and unresolved items

1. **Plot-region detector mismatch (code behaviour).** For this image `detect_plot_box()`
   declines (`NO_UNAMBIGUOUS_RECTANGULAR_FRAME`) and `detect_plot_box_candidates()` returns a
   provisional frame `[85, 51, 268, 275]` whose right/bottom edges are not supported by the
   pixels. The true frame (confirmed by line density) is `[85, 51, 457, 327]`. The command
   has no automatic way to obtain the correct box here; the supplied reference was used.
2. **Review status overstates fragmented tracks.** Four of five `CANDIDATE_REVIEW` tracks have
   22–34 segments and are labelled `DISCONTINUOUS_UNRESOLVED`. They pass numeric thresholds
   (coverage, active columns, point count) but have no gap-regularity/style gate, so they are
   review candidates rather than credible continuous curves.
3. **Sequential greedy extraction.** Tracks are found one at a time with used nodes removed;
   later tracks are progressively weaker (TR05–TR12 all rejected). There is no global
   multi-track competition or competing-solution margin output.
4. **No gap interpolation is a deliberate strength, but real dashed paths are only recovered
   when gaps are ≤ 12 columns and curvature stays low.** Several short dashed candidates were
   rejected solely for the 67-point minimum.
5. **Environment/packaging.** The editable install points at the older original checkout;
   `scientific_figure_data.trajectory` is only importable from this worktree via `PYTHONPATH`.
   `sfd` is not installed on PATH on this machine, so the console entry point was invoked
   through `cli.main()`.
6. **No OCR / calibration.** This command discovers pixel paths only. No scientific axis
   coordinates were produced. Point-level scientific accuracy is **NOT_EVALUATED**.

No fix was attempted for any of the above; none of these results were tuned by changing
parameters.

## 7. Scope statement

Software execution and data-structure validity were verified. The five review candidates are
hypotheses only; nothing here establishes that any of them is a true scientific curve or that
the count four/five is correct. No prior v1/v2 extraction results were read as priors, no
multimodal vision or OCR was used, and no source file was modified.
