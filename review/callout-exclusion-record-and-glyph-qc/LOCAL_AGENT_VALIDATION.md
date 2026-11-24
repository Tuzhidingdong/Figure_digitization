# Callout exclusion QC and P3 glyph diagnosis — local validation handoff

Repository: `Tuzhidingdong/Figure_digitization`
Target branch: `fix/callout-exclusion-record-and-glyph-qc`
Validation baseline / parent: `d12da5e47604b67cd54258c37e0a6b3fe3af7ae3`
Minimum required code commit (must be an ancestor of local HEAD): `b1fa8d24b60944eda27977a58f4e51c93f34fc40`
Algorithm version: `0.8.1`

This is a narrow corrective candidate. It has **not** been executed in the local Windows environment and is not accepted yet.

## 1. Protected state

Work only in:
`E:\\Zinc_batters_datas\\Figure_digitization`

Before sync, inspect branch and `git status`. Preserve local modifications and all untracked items, including `.agents/`, `__pycache__/`, every `test_outputs/` directory, the old `STATUS.md` backup, `stash@{0}`, and all previous review artifacts.

Do not use `git reset --hard`, `git clean`, stash pop/drop or `git add -A`. Do not overwrite conflicting local files. Use explicit paths only.

Do not modify:
- `main`;
- `review/real-image-reconstruction-20261124`;
- `fix/junction-local-ambiguity-recovery`;
- `fix/partial-raster-fragment-preservation`;
- `fix/partial-branch-qc-preservation`;
- PR #22;
- frozen `TASK_PLAN_v1.4.1.md`.

No PR merge or release is authorized.

## 2. Code correction in this branch

The only production change is in `src/scientific_figure_data/raster.py`:
- compact-component exclusion now checks both the component's top-level `rejection_reason` and nested `path_qc.reason`;
- a specific nested junction reason can no longer mask the public component-level reason `UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`;
- the QC record preserves both as `source_qc_rejection_reason` and `source_path_qc_reason`;
- the existing review-only classification remains `UNRESOLVED_COMPACT_COMPONENT_RETAINED_IN_REVIEW_QC`. Do not call it definitely an annotation.

The algorithm version is `0.8.1` and the stale report-version assertion was updated.

A new direct helper regression test covers a component whose top-level reason matches the component rejection contract while its nested path reason is `UNSUPPORTED_JUNCTION_PORT_COUNT`. The existing synthetic waveform+callout integration test still requires:
- waveform ordered coordinates retained;
- zero callout coordinates in the selected data path;
- exactly one `excluded_partial_branches` record;
- rejection QC reason `PARTIAL_BRANCH_EXCLUDED_WHEN_UNIQUE_COMPLETE_PATH_EXISTS`;
- both original rejection reasons retained.

No thresholds were relaxed and no annotation pixels are promoted to a curve.

## 3. Sync and one-pass tests

Safely sync/switch to `fix/callout-exclusion-record-and-glyph-qc` only after preserving the current local state. Confirm the local HEAD contains `b1fa8d24b60944eda27977a58f4e51c93f34fc40`.

Use existing Python 3.13.9. Run compile/import checks, then execute the four relevant files **once**:

```powershell
python -m pytest tests/test_core.py tests/test_automatic_digitization.py tests/test_real_image_regressions.py tests/test_upstream_compat.py -o addopts="" -q --durations=0
```

Expected collection is previous 158 tests plus one new direct helper regression test (159, unless unrelated collection configuration changes). Record actual collected/passed/failed/skipped, exit code, duration and exact failing node IDs.

Do not weaken:
- callout exclusion QC;
- P8 panel-d two-red/one-blue branch detection;
- long full-span partial-QC branch retention;
- five-way junction rejection;
- segment-boundary rendering/CSV;
- compact ring unit test.

Do not enter a repeated broad test loop. If one test fails, inspect it and perform at most one relevant focused rerun after an authorized correction.

## 4. Real-image validation — cached OCR only

Use unchanged fixtures:
- `tests/fixtures/real_figures/P3_02.png`
- `tests/fixtures/real_figures/P8_06.png`

Use cached OCR JSON only. Do not rerun OCR, open papers/PDF/SI or install dependencies.

Fresh output directory:
`test_outputs/reconstruction_callout_exclusion_qc_20261124/`

Compare with the latest prior output:
`test_outputs/reconstruction_partial_branch_qc_20261124/`
and earlier baselines retained under the previous review directories.

### P8_06 checks

1. Panel a red 22,146 points / 178 segments and blue `without urea` 1,835 points / 26 segments must remain unchanged unless a source-backed reason explains any change.
2. Segment boundaries stay explicit; do not draw connectors.
3. Callout / arrow pixels remain excluded from curve coordinates.
4. The synthetic callout exclusion record must now expose both:
   - `source_qc_rejection_reason = UNSUPPORTED_JUNCTION_REQUIRES_COMPONENT_REVIEW`
   - `source_path_qc_reason = UNSUPPORTED_JUNCTION_PORT_COUNT`
5. Panel d must still contain two red branches (317 + 319 points) and one blue branch (317 points); the second red branch retains partial-review status.

### P3_02: diagnose, do not guess-filter, the two remaining short candidates

The previous run reports two ring-like visual artefacts:
- orange `_color_01_branch_03`: 41 points, bbox `[122,125,163,127]`, `PATHS_EXTRACTED`;
- purple `_color_03_branch_03`: 14 points, bbox `[267,125,281,127]`, `LOCAL_SHORT_2D_FRAGMENT_NEEDS_REVIEW`.

The current production patch does **not** change the P3 fragment filter. Do not add a new generic threshold merely to make the circles disappear.

Using the already-generated series CSVs and cached `P3_02_ocr.json`, produce a focused path-shape/annotation proximity diagnostic for these two series and the neighboring retained fragments:
- dump the exact ordered pixel-coordinate sequence (or a compact sampled sequence plus full CSV reference);
- compute bbox, point count, cumulative polyline length, endpoint chord length, chord/length ratio, number of direction changes and repeated/backward-X steps;
- map the path bboxes into the cached OCR crop coordinate system using the existing saved panel crop/layout metadata; do not guess offsets;
- compute overlap and nearest distance to each cached OCR polygon, identifying the matched OCR text/confidence/polygon;
- inspect whether the component is a legend swatch/text stroke, marker glyph, annotation, or a genuine curve segment; keep classification `UNRESOLVED` where the evidence does not distinguish these cases.

Create a diagnostic image only if the exact ordered coordinates and crop transform are available. Show original crop, candidate path, OCR polygons and candidate bbox. Do not draw estimated paths.

Required outcome is a report-backed diagnosis, not an arbitrary removal. If the two candidates are OCR/legend-associated, propose a general geometric+OCR evidence rule and give false-positive risks. If the evidence is insufficient, leave them in the output as `NEEDS_REVIEW` and state that no production filter was justified.

Also check:
- P3 purple x≈355–390 remains unresolved; do not infer curve coordinates from mask pixels;
- all P3 Y axes remain `UNASSIGNED`, `y_value` empty;
- P8 panel c remains blocked by its existing X-axis semantics gate unless existing evidence grounds a monotonic X label. Do not invent labels.

For every panel report series/point/segment counts, status, QC status, Y-axis assignment and unresolved numeric fields. No point-level accuracy claim without an independent point benchmark.

## 5. Upload

Upload only these files to:
`review/callout-exclusion-record-and-glyph-qc/`

Required:
- `P3_02_reconstructed.png`
- `P3_02_side_by_side.png`
- `P3_02_overlay.png`
- `P8_06_reconstructed.png`
- `P8_06_side_by_side.png`
- `P8_06_overlay.png`
- `p3_short_fragment_diagnostics.md`
- `validation_report.md`
- `manifest.json`

Add one diagnostic PNG only if the exact path coordinates and cached OCR crop transform are available. Manifest must include every uploaded file's byte size and SHA256.

Use explicit `git add <exact-path>`, commit and push only to `fix/callout-exclusion-record-and-glyph-qc`. Do not upload PDFs/SI, raw OCR, unrelated outputs or temporary files.

Return:
- final commit SHA and links;
- exact four-file test results;
- explicit callout QC record with both reason fields;
- P3 short-fragment coordinate/OCR diagnosis and whether any justified filtering rule exists;
- P8 panel a/d unchanged or changed point/segment counts;
- remaining blockers.

Stop after validation. Do not merge, publish or touch protected branches.
