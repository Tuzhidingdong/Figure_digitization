# Phase 3 — P3 OCR association and purple-fragment diagnosis

Date: 2026-11-25
Inputs: fresh cached run `test_outputs/reconstruction_callout_qc_bbox_only_20261124`
(`panel_series.csv`, `digitization.json`, QC objects) and archived
`tests/fixtures/real_figures/P3_02_ocr.json`. No OCR rerun, no paper/PDF/SI lookup,
no new extraction and no production change.

## Coordinate mapping

Panel `auto-03` crop from saved `crop_mapping`: `[914, 0, 1399, 404]` in SOURCE_IMAGE_PIXELS,
render scale 1.0. CSV pixel coordinates are panel-local; source = local + (914, 0).
OCR rows inside this crop: **33**.

## 1. Three review-only short candidates

| Candidate | Pts | Source bbox | RGB | Aspect (x/y) | Chord/length | Direction changes | Back-X | OCR overlap (area, text, conf) | Nearest retained series (px) |
|---|---:|---|---|---:|---:|---:|---:|---|---|
| `_color_01_branch_03` | 41 | [1036.0, 125.0, 1076.0, 126.0] | [242, 132, 64] | 40.0 | 0.951 | 4 | 0 | 40px² `Bulk Te——Discharge —` conf=0.89585 | _color_01_branch_04 25.6, _color_02_branch_01 41.0 |
| `_color_03_branch_03` | 14 | [1181.0, 125.0, 1194.0, 126.0] | [130, 56, 131] | 13.0 | 0.94 | 1 | 0 | 13px² `Charge` conf=0.98309; 4px² `Bulk Te——Discharge —` conf=0.89585 | _color_02_branch_01 41.0, _color_02_branch_04 81.0 |
| `_color_01_branch_04` | 28 | [1052.0, 97.0, 1060.0, 105.0] | [242, 132, 64] | 1.0 | 0.235 | 4 | 1 | 64px² `Te NSs —— Discharge` conf=0.88995 | _color_01_branch_03 20.0, _color_02_branch_01 62.0 |

Classification (conservative; OCR overlap alone is not sufficient for deletion):

| Candidate | Classification | Evidence and caveat |
|---|---|---|
| `_color_01_branch_03` | High-probability annotation/legend stroke, human confirmation required | 41 ordered points form a long near-straight stroke (chord/length 0.951) whose entire 40 px² bbox lies inside the `Bulk Te—Discharge` OCR box (conf 0.89585) at the legend text baseline; colour matches the orange family. Could be a legend line swatch or a text underline; OCR box is wide enough that a coincident data stroke cannot be excluded. |
| `_color_03_branch_03` | High-probability annotation/legend stroke, human confirmation required | 14 points, chord/length 0.940, bbox fully overlaps `Charge` (conf 0.98309) and partly `Bulk Te—Discharge`; colour matches purple family. Same caveat: legend row overlap is strong association but not proof. |
| `_color_01_branch_04` | High-probability legend glyph stroke, human confirmation required | 28 points, near-closed (chord/length 0.235), aspect ≈1, fully overlaps `Te NSs—Discharge` (conf 0.88995); compact loop-like glyph consistent with a legend marker/text stroke, but a genuine short curve crossing text cannot be ruled out from these files alone. |

All three keep `GEOMETRY_ONLY_NEEDS_REVIEW` / `EXTRACTED_PROVISIONAL_NEEDS_REVIEW`,
`NEEDS_REVIEW_PARTIAL_PATH` where applicable, `y_value` empty, and `UNASSIGNED` Y axis.
**No production filter was added**; broad OCR bbox overlap is not an automatic deletion criterion.

## 2. Purple x≈355–390 (panel-local) missing coverage

Mask/colour evidence does exist in this range, but it never becomes ordered path geometry:

| bbox (panel-local) | pixels | x_span | y_span | rejection |
|---|---:|---:|---:|---|
| [366, 169, 375, 170] | 9 | 9 | 1 | COMPONENT_TOO_SMALL |
| [363, 170, 364, 171] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |
| [357, 172, 358, 173] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |
| [355, 174, 356, 175] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |
| [353, 175, 354, 176] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |
| [390, 179, 391, 180] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |
| [369, 257, 370, 258] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |
| [382, 258, 383, 259] | 1 | 1 | 1 | COMPONENT_TOO_SMALL |

Blocking stage: **component admission** (`min_component_pixels = 12`,
`min_component_x_span = 27`). All eight purple-family
components in local x≈353–391 contain 1–9 pixels and have x-span 1–9; each is rejected as
`COMPONENT_TOO_SMALL`, so skeletonisation and path ordering are never attempted for them. The largest
emitted purple path ends at source x≈1195 (local x≈280).

Not the cause: junction pairing rejection (no path QC was built for these components), path
backtracking, trace-spec gate (spec is READY for auto-03) or OCR/annotation exclusion (no exclusion
record applies here). **Unresolved:** whether these tiny fragments belong to one continuous physical
curve; no coordinates were extrapolated from mask pixels, and no gap was bridged.

## 3. Decision

No production algorithm change is justified by the available evidence. A future OCR-assisted review
flag would need to distinguish legend line swatches/text glyphs from genuine curves crossing wide
OCR text boxes; that requires independent visual/human confirmation and is outside this round.
