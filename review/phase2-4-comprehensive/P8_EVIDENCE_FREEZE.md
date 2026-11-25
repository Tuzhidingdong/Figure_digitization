# Phase 2 — P8 existing evidence freeze

Date: 2026-11-25
Branch: `review/phase2-4-comprehensive` (created from Phase 1 report commit `4922071…`)
Production algorithm version: `0.8.2`; artifact generated at `2026-11-24T08:55:08+00:00`.

## Scope

No extraction, OCR, rendering or production-code change was performed. This freeze uses only the
already existing run `test_outputs/reconstruction_callout_qc_bbox_only_20261124` and the unchanged
fixture `tests/fixtures/real_figures/P8_06.png`. All files below were confirmed present and hashed
from disk; paths are repo-relative.

## 1. File inventory (path, size, SHA256)

| File (repo-relative) | Bytes | SHA256 |
|---|---:|---|
| `tests/fixtures/real_figures/P8_06.png` | 450356 | `581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549` |
| `tests/fixtures/real_figures/P8_06_ocr.json` | 20073 | `be04ad9adf0f46b80971143b2f0072906d7855e239216455829cb2cd7226b7e8` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extract_only.py` | 9120 | `942803ae90516b25b64de304ced132c636edb02e2f3e03f375d4e97b35bde6be` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/render_reconstructions.py` | 17899 | `e67a03ed95e52f8b10b3307210041bd3ad3495d01531af1c864327b555ccf241` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction_run.json` | 4110090 | `df2c33e3e5f3f422d38b91e08232850bb8c42c27c221f63e2ed12ff375d531d0` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/reconstruction_manifest.json` | 37403 | `1e82df2a8ebe34c4800cea1bd14ea495f9072120de0d3af2b8cc98fe41e4d474` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/P8_06_reconstructed.png` | 254176 | `e7c05fe9bf01d8909077e588f5c22866559ce9f17b48b1764db309317bb1fc28` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/P8_06_side_by_side.png` | 719259 | `8ec50ab36046b90f6cc96b9eb5f2cad944853f3c87829999de3a47dd75f26ebc` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/P8_06_overlay.png` | 467545 | `549256a018eb2db5a120db533a79579665b8fa1275cec826a4540cc92cbed399` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/digitization.json` | 1205772 | `8ad96f858ebe139552fc2da24cede16d8ae0a999100917681eaa06fe8b847dc3` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/panel_layout.json` | 7073 | `a9fc2606b4ddac87ef5bea469d588525de625000e4f4fe3bf439a9a2308bf79c` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/paper_manifest.json` | 976 | `d27da73ce201133f97fb18b429584dfa2ad96b8b5d4019bc159bb6a743c4d7d3` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/paper_bundle.json` | 2390 | `4c9d53e67257d36034da4c86964b60e32dfaac8c3b251a9eec0eafe825f5d8e1` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/figure_inventory.json` | 47090 | `07da929b0e173b0e668c675bc07a288de840d8b8824749fdeabd4d0ff5fd83af` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/series/P8_06__auto-frame-01/panel_series.csv` | 3944261 | `1b10f8549ed290fd37f922c3ab689ab8994c37ef427762376a6540a704bbf345` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/series/P8_06__auto-frame-02/panel_series.csv` | 144876 | `7ec23fbe59a555197424ace1c5b09f1076bc14d90e8747c0530f8a0b40c3f787` |
| `test_outputs/reconstruction_callout_qc_bbox_only_20261124/extraction/P8_06/output/papers/paper-p8-real/series/P8_06__auto-frame-04/panel_series.csv` | 178756 | `e8a4c3c35742433a9bb63b0a5e56dc4518ec1387742fe61f108cb4c5abbaed90` |

## 2. Panel status

| Panel | bbox | series records | with points | points | trace spec |
|---|---|---:|---:|---:|---|
| auto-frame-01 | [0, 141, 1407, 514] | 2 | 2 | 23981 | READY |
| auto-frame-02 | [27, 540, 481, 911] | 7 | 7 | 1226 | READY |
| auto-frame-03 | [491, 540, 937, 911] | 1 | 0 | 0 | NEEDS_REVIEW (X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER) |
| auto-frame-04 | [955, 544, 1391, 895] | 3 | 3 | 953 | READY |

## 3. Series status (authoritative CSV point tables)

| Panel | Series | Points | Segments | Y side | Map status | y_value filled | Extraction / QC / Review |
|---|---|---:|---:|---|---|---:|---|
| auto-frame-01 | _color_01 | 22146 | 178 | LEFT | None | 22146 | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW |
| auto-frame-01 | _color_02 | 1835 | 26 | LEFT | None | 1835 | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW |
| auto-frame-02 | _color_01 | 839 | 6 | UNASSIGNED | None | 0 | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW |
| auto-frame-02 | _color_02_branch_01 | 42 | 1 | UNASSIGNED | None | 0 | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-02 | _color_02_branch_02 | 50 | 1 | UNASSIGNED | None | 0 | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-02 | _color_02_branch_03 | 112 | 1 | UNASSIGNED | None | 0 | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-02 | _color_02_branch_04 | 48 | 1 | UNASSIGNED | None | 0 | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-02 | _color_02_branch_05 | 110 | 1 | UNASSIGNED | None | 0 | GEOMETRY_ONLY_NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-02 | _color_02_branch_06 | 25 | 1 | UNASSIGNED | None | 0 | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW |
| auto-frame-03 | -frame-03_unassigned | 0 | 0 | LEFT | None | 0 | NEEDS_REVIEW / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-04 | _color_01_branch_01 | 317 | 1 | LEFT | None | 317 | EXTRACTED_PROVISIONAL / PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW |
| auto-frame-04 | _color_01_branch_02 | 319 | 1 | LEFT | None | 319 | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW |
| auto-frame-04 | _color_02 | 317 | 1 | RIGHT | None | 317 | EXTRACTED_PROVISIONAL_NEEDS_REVIEW / NEEDS_REVIEW_PARTIAL_PATH / NEEDS_REVIEW |

## 4. Segment-boundary evidence

| Panel | Series | Segments | Inter-segment pixel-x differences (first 12) | Backward-x steps |
|---|---|---:|---|---:|
| auto-frame-01 | _color_01 | 178 | [7, 7, 8, 7, 16, 16, -1, -1, 7, 1, 7, -1] | 40 |
| auto-frame-01 | _color_02 | 26 | [79, 164, 8, 13, 7, 3, 5, 7, 7, 7, 3, 1] | 1 |
| auto-frame-02 | _color_01 | 6 | [1, -1, 1, 1, -2] | 2 |
| auto-frame-02 | _color_02_branch_01 | 1 | [] | 0 |
| auto-frame-02 | _color_02_branch_02 | 1 | [] | 0 |
| auto-frame-02 | _color_02_branch_03 | 1 | [] | 1 |
| auto-frame-02 | _color_02_branch_04 | 1 | [] | 0 |
| auto-frame-02 | _color_02_branch_05 | 1 | [] | 2 |
| auto-frame-02 | _color_02_branch_06 | 1 | [] | 0 |
| auto-frame-04 | _color_01_branch_01 | 1 | [] | 0 |
| auto-frame-04 | _color_01_branch_02 | 1 | [] | 0 |
| auto-frame-04 | _color_02 | 1 | [] | 0 |

The renderer iterates `path_segment_index` groups and calls `plot()` once per group, so no line is
drawn between two segments. The inter-segment X differences above include real gaps and overlaps;
they are **not** interpolated and a single continuous polyline is not asserted. Series remain
separate `series_id` records; none was merged into another.

## 5. Confirmations and limits

| Check | Result |
|---|---|
| segment boundaries preserved | yes — `path_segment_index` in CSV and segment-wise rendering |
| independent series not merged | yes — distinct series ids per branch/family |
| review states not promoted | yes — every plotted series has `review_state = NEEDS_REVIEW`; partial series keep `EXTRACTED_PROVISIONAL_NEEDS_REVIEW` / `NEEDS_REVIEW_PARTIAL_PATH` |
| uncalibrated data not given scientific values | yes — panel b has `y_value_nonempty = 0` for all 1226 points and `UNASSIGNED / UNRESOLVED` |
| panel c gate preserved | yes — 0 points, `X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER` |
| panel a red/blue | 22,146 pts/178 segments and 1,835 pts/26 segments, both partial-review |
| panel d | 317 + 319 red and 317 blue; second red has unpaired spur `[242,77]` and partial-review QC |

**Not concluded here:** point-level accuracy, physical correctness of panel-d axis labels (series
`y_label` is inherited and not itself proof of per-series physical meaning), and any value not
already present in the frozen CSV/QC files. Pixel counts and reconstruction appearance are not
scientific accuracy evidence.

Machine-readable detail: `P8_EVIDENCE_MANIFEST.json`.
