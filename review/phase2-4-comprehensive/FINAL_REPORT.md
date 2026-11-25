# Final report — Phase 2 / 3 / 4 comprehensive validation

Date: 2026-11-25
Branch: `review/phase2-4-comprehensive`
Created from: `4922071064803f47f6212c2f718452e2b522d60d` (Phase 1 report commit)
Phase 1 production HEAD: `4495a4a5d945ff7fcacc427e0f0dfd6a16c12f4c`
Production algorithm version: `0.8.2` (unchanged)

## Phase outcomes

| Phase | Completed work | Result |
|---|---|---|
| 2 | Froze existing P8 inputs, CSVs, QC JSON, reconstruction images and reports with exact paths/sizes/SHA256; panel-by-panel status and confirmation checks | Complete: `P8_EVIDENCE_FREEZE.md`, `P8_EVIDENCE_MANIFEST.json` |
| 3 | Re-analysed three OCR-associated review candidates with ordered coordinates, geometry, OCR overlap and neighbour distances; diagnosed purple x≈355–390 blocking stage | Diagnosis complete; no production fix justified |
| 4 | Audited P3 dual-Y evidence, P8 panel-c X-semantics gate and numeric calibration chain; decided what stays unassigned/unresolved | Complete: `PHASE4_AXIS_AND_CALIBRATION.md` |

## Answers to the required questions

1. **Phase 2/3/4:** evidence freeze (P8), OCR/fragment diagnosis (P3), axis/calibration audit (Phase 4). No new extraction or image generation.
2. **Solved vs diagnosed:** solved at evidence level — P8 provenance freeze, segment-boundary confirmation, P3 candidate geometry/OCR association, purple blocking-stage identification, P3 dual-Y evidence insufficiency, panel-c missing label evidence. Diagnosed but unresolved — physical identity of the three P3 strokes, whether purple tiny fragments form one curve, panel-d axis-label meaning, panel-c X semantics.
3. **Production algorithm modified?** No. `src/` diff is 0 files; no version, threshold, junction rule or filter changed. No new tests were added.
4. **P8 final panel states:** a = red 22,146 pts/178 segments + blue 1,835 pts/26 segments, all partial-review; b = 1,226 geometry-only points, uncalibrated, `y_value` empty; c = 0 points, X-semantics gate; d = 317+319 red + 317 blue, second red partial-review with unpaired spur `[242,77]`.
5. **P3 candidates:** orange `_color_01_branch_03` (41 pt) and purple `_color_03_branch_03` (14 pt) = high-probability legend/text strokes, human confirmation required; `_color_01_branch_04` (28 pt, near-closed) = high-probability legend glyph stroke, human confirmation required. Broad OCR overlap alone was not treated as deletion evidence.
6. **Purple x≈355–390 root cause:** component-admission stage — eight purple-family fragments (1–9 px, x-span 1–9) are rejected as `COMPONENT_TOO_SMALL` before skeletonisation; physical continuity of those fragments remains undetermined; no coordinates inferred.
7. **P3 dual-Y assignment:** not completed reliably — `AMBIGUOUS_DUAL_Y_AXIS`, no chromatic axis-text/spine evidence; all `y_value` empty.
8. **Panel c X semantics:** not proven — candidate `Time (h)` OCR confidence 0.54463 is below the accepted label threshold; `x_axis_label = None`, gate retained.
9. **Credibly calibrated series:** P8 panel a (Time/V) and panel d (Cycle/ numeric axes) have numeric mappings, but all remain review-only; axis-label physical meaning for panel d is provisional.
10. **Pixel-only series:** P8 panel b (1,226 pts) and P3 (1,377 pts) have no scientific `y_value`; panel c has 0 points.
11. **Tests:** Phase 1 four-file result on `4495a4a5…` = 159/159 passed, exit 0, 197.12s. Not rerun here because no production change. Phase 2–4 introduced no new test run.
12. **Inherited vs new:** all P8/P3 point counts, images and QC states are inherited from cached runs; this round newly computed hashes, geometry metrics, OCR associations and blocking-stage diagnoses from those existing files. No new visual validation is claimed.
13. **Human judgement still needed:** identity of the three P3 short strokes, physical continuity of purple far fragments, panel-c X-axis label evidence, panel-d axis-label meaning, and acceptance of every `NEEDS_REVIEW` series.

## Evidence discipline

No fabricated coordinates, no bridging between segments, no guessed axis semantics, no fabricated
calibration values, no promotion of `NEEDS_REVIEW` to success, and no point-level accuracy claim
without an annotated benchmark. No PR merge, release, protected-branch change or production edit.

## Files

- `FINAL_REPORT.md` — this summary
- `P8_EVIDENCE_FREEZE.md` / `P8_EVIDENCE_MANIFEST.json` — Phase 2
- `P3_OCR_AND_FRAGMENT_DIAGNOSIS.md` — Phase 3
- `PHASE4_AXIS_AND_CALIBRATION.md` — Phase 4
- `TEST_REPORT.md` — test scope and inherited result
