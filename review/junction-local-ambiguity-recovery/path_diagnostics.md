# Path-level diagnostics — P8_06 panel a, synthetic tracer tests and legacy gaps

Date: 2026-11-24
Branch: `fix/junction-local-ambiguity-recovery` @ `c2e99ba00485610061e44cf76cdab27850b07cf6`
Source of all numbers: `test_outputs/reconstruction_junction_local_20261124/extraction/`
(`digitization.json` → `metadata.raster_qc` → `branch_detection` / `path_qc`), plus
read-only inspection of `src/scientific_figure_data/raster.py`, `trace_spec.py` and `pipeline.py`.
No source, test or OCR output was modified; no paper/PDF/SI was consulted.

## 0. Global thresholds that explain most rejections

`_find_color_components()` uses `min_span_fraction = 0.08` and
`min_pixels = max(12, 0.01 × width)`; `_ordered_skeleton_paths()` applies the same x-span
threshold to **each ordered path**. For panel a (`plot_box = [93, 53, 1338, 320]`, width 1245):

| Threshold | Value | Consequence |
|---|---:|---|
| component min x-span | **100 px** | components narrower than 100 px never reach skeletonisation |
| component min pixels | **12 px** | tiny fragments dropped before path QC |
| path min x-span | **100 px** | every ordered path shorter than 100 px gets `PATH_X_SPAN_TOO_SHORT` |
| right edge columns removed | 1324–1337 | red chromatic Y-axis spine excised from the mask |

Both panel-a families end with `component_detection.status = NO_TRACE_COMPONENTS`,
`branch_detection.status = NO_CONTINUOUS_PATH_COMPONENTS`, `branch_count = 0`,
**0 plotted points**.

---

## 1. P8_06 panel a — RED (`[238,63,70]`)

Colour mask: 95,608 active pixels; 15 rejected components; no accepted component.

### 1.1 Main red component `[94,138,1324,319]`

| Item | Value |
|---|---|
| component pixels | 94,974 |
| skeleton pixels / used edges | 25,110 / 23,110 (9 thinning iterations, converged) |
| endpoints / junctions | 414 / 264 |
| junction clusters | 18 (11 pairable 4-port clusters; **7 ambiguous**) |
| `unpaired_ports` | `[]` (empty — ambiguity is captured by cluster port counts, not by unmatched ports) |
| ordered candidate paths | **199** |
| path class counts | vertical=166, diagonal / mixed (uncertain)=2, other short fragment=19, short vertical / dot=12 |
| max path x-span / y-span / points | 52 / 163 / 292 |
| `backward_x_steps` | **0 on all 199 paths** — no `PATH_BACKTRACKS_IN_X` rejection |
| per-path rejection | **199 × `PATH_X_SPAN_TOO_SHORT`** (all paths < 100 px vs required 100 px) |
| component-level reason | `NO_PATH_SPANS_REQUIRED_X_RANGE` |
| path QC status | `NEEDS_REVIEW`, `partial_path_review_required = True` |

**Mechanism:** the tracer did build 166 long vertical ordered paths (typical bbox
`[x,165,x+2,317]`, y-span ≈150 px) that correspond to the genuine charge/discharge verticals,
but at this figure scale one vertical occupies only ≈2 px in x. The 100 px x-span rule —
designed to reject noise — removes **every** one of them. Horizontal plateaus are mostly
absorbed into the 7 ambiguous junction clusters (e.g. cluster 0 spans x=100–742 at y≈160–168);
only short plateau fragments remain as paths. The component is then discarded for lack of any
path spanning 100 px, so nothing reaches `panel_series.csv`.

Full per-path table: Appendix A.1.

### 1.2 Ambiguous red junction clusters

| cluster | junction px | ports | port x range | port y range | reason | paired? |
|---|---:|---:|---|---|---|---|
| 0 | 666 | 91 | 100–742 | 158–168 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |
| 6 | 26 | 8 | 192–217 | 197–201 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |
| 7 | 187 | 26 | 225–323 | 197–311 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |
| 8 | 26 | 8 | 440–463 | 202–207 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |
| 15 | 266 | 46 | 488–669 | 203–314 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |
| 16 | 215 | 29 | 754–964 | 156–160 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |
| 17 | 349 | 50 | 976–1317 | 152–159 | UNSUPPORTED_JUNCTION_PORT_COUNT | NO |

Full port coordinate lists: Appendix B.1.

### 1.3 All 15 rejected red components

| # | bbox | px | x_span | y_span | rejection | interpretation |
|---|---|---:|---:|---:|---|---|
| 0 | [438, 83, 449, 89] | 43 | 11 | 6 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash (y≈83–89, x≈438–449) |
| 1 | [456, 83, 468, 87] | 37 | 12 | 4 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 2 | [476, 83, 488, 87] | 36 | 12 | 4 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 3 | [495, 84, 499, 95] | 44 | 4 | 11 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 4 | [1158, 86, 1199, 89] | 121 | 41 | 3 | COMPONENT_X_SPAN_TOO_SHORT | legend 'with urea' swatch / leader line |
| 5 | [438, 96, 442, 108] | 43 | 4 | 12 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 6 | [495, 103, 499, 115] | 38 | 4 | 12 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 7 | [438, 115, 442, 127] | 36 | 4 | 12 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 8 | [495, 123, 499, 134] | 38 | 4 | 11 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 9 | [206, 127, 218, 131] | 45 | 12 | 4 | COMPONENT_X_SPAN_TOO_SHORT | likely annotation/curve connector fragment (uncertain) |
| 10 | [226, 127, 236, 133] | 43 | 10 | 6 | COMPONENT_X_SPAN_TOO_SHORT | likely annotation/curve connector fragment (uncertain) |
| 11 | [198, 130, 201, 142] | 34 | 3 | 12 | COMPONENT_X_SPAN_TOO_SHORT | likely annotation/curve connector fragment (uncertain) |
| 12 | [438, 135, 441, 147] | 33 | 3 | 12 | COMPONENT_X_SPAN_TOO_SHORT | red dashed annotation box dash |
| 13 | [94, 138, 1324, 319] | 94974 | 1230 | 181 | NO_PATH_SPANS_REQUIRED_X_RANGE | MAIN: waveform + possible touching annotation, all paths rejected |
| 14 | [232, 141, 236, 152] | 43 | 4 | 11 | COMPONENT_X_SPAN_TOO_SHORT | likely annotation/curve connector fragment (uncertain) |

Counts: 14 × `COMPONENT_X_SPAN_TOO_SHORT`, 1 × `NO_PATH_SPANS_REQUIRED_X_RANGE`.
Nine small components at x≈438–499 / y≈83–147 are the red **dashed annotation box**, one at
x≈1158–1199 / y≈86 is the legend swatch; four near x≈198–236 / y≈127–152 are likely annotation
connector fragments (uncertain without new tracing). These are filtered at component level and
**are not plotted** — the annotation exclusion itself works. The failure is that the real
waveform is filtered by the same geometric rule.

---

## 2. P8_06 panel a — BLUE (`[103,147,197]`), `without urea`

Colour mask: 7,130 active pixels (family itself detected, 6,566 pixels reported by the colour
family detector); 115 rejected components; no accepted component.

### 2.1 Main blue component `[201,111,411,167]`

| Item | Value |
|---|---|
| component pixels | 1,918 |
| skeleton pixels / used edges | 600 / 355 (3 thinning iterations, converged) |
| endpoints / junctions | 60 / 31 |
| junction clusters | 1 (cluster 0, **ambiguous**, 212 junction pixels, 33 ports) |
| `unpaired_ports` | `[]`; cluster 0 has **no pairings** |
| ordered candidate paths | **14** |
| path class counts | short vertical / dot=7, vertical=6, other short fragment=1 |
| max path x-span / y-span / points | **5** / 39 / 41 |
| `backward_x_steps` | 0 on all 14 |
| per-path rejection | **14 × `PATH_X_SPAN_TOO_SHORT`** |
| component-level reason | `NO_PATH_SPANS_REQUIRED_X_RANGE` (`NEEDS_REVIEW`, partial=True) |

**Answers to the specific questions:**
- A skeleton **was** generated (600 px) and **14 ordered candidate paths were built** — but only
  summary records (bbox, point count, spans, backward steps, rejection reason) are persisted.
  No ordered coordinate array exists in the outputs, so **zero recoverable path coordinates**;
  detecting 6,566 blue pixels is *not* path recovery.
- All 14 paths fail the 100 px minimum x-span (max 5 px). No path is rejected for backtracking.
- Branching/endpoints: 60 endpoints, 31 junctions, one 33-port ambiguous cluster; ports run
  from `[202,155]` to `[405,151]`. This is genuine colour-mask fragmentation at the dashed
  early-cycle blue segment, not an axis assignment problem.
- Status: `color_detection.status = UNIQUE_CHROMATIC_FAMILY` for this series (blue is selected
  as a family), `component_detection.status = NO_TRACE_COMPONENTS`,
  `branch_detection.status = NO_CONTINUOUS_PATH_COMPONENTS`, branch_count 0,
  `extraction_status = NEEDS_REVIEW`, **0 points**.

Full per-path table: Appendix A.2; ports: Appendix B.2.

### 2.2 Blue rejected-component portfolio

| # | bbox | px | x_span | y_span | rejection | interpretation |
|---|---|---:|---:|---:|---|---|
| 0 | [1158, 65, 1199, 69] | 159 | 41 | 4 | COMPONENT_X_SPAN_TOO_SHORT | legend 'without urea' swatch / leader line |
| 1 | [498, 101, 518, 166] | 545 | 20 | 65 | COMPONENT_X_SPAN_TOO_SHORT | annotation box edge fragment |
| 2 | [415, 103, 495, 167] | 1696 | 80 | 64 | COMPONENT_X_SPAN_TOO_SHORT | annotation box edge fragment |
| 3 | [201, 111, 411, 167] | 1918 | 210 | 56 | NO_PATH_SPANS_REQUIRED_X_RANGE | MAIN: blue early-cycle waveform fragment, all paths rejected |
| 4 | [117, 150, 198, 168] | 421 | 81 | 18 | COMPONENT_X_SPAN_TOO_SHORT | likely connector / plateau fragment (uncertain) |
| 5 | [94, 152, 100, 159] | 23 | 6 | 7 | COMPONENT_X_SPAN_TOO_SHORT | early blue vertical segment (x≈94–100, inside plot left edge) |
| 6 | [101, 152, 108, 162] | 30 | 7 | 10 | COMPONENT_X_SPAN_TOO_SHORT | early blue vertical segment (x≈101–108) |
| 7 | [109, 152, 116, 162] | 32 | 7 | 10 | COMPONENT_X_SPAN_TOO_SHORT | early blue vertical segment (x≈109–116) |
| 8 | [412, 152, 413, 167] | 15 | 1 | 15 | COMPONENT_X_SPAN_TOO_SHORT | small blue fragment near x≈412 |
| 9 | [408, 157, 409, 162] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 10 | [416, 157, 417, 161] | 4 | 1 | 4 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 11 | [449, 157, 450, 160] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 12 | [515, 157, 516, 163] | 6 | 1 | 6 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 13 | [400, 158, 401, 159] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 14 | [466, 158, 467, 159] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 15 | [474, 158, 475, 161] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 16 | [482, 158, 483, 163] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 17 | [490, 158, 491, 161] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 18 | [507, 158, 508, 162] | 4 | 1 | 4 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 19 | [334, 159, 335, 162] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 20 | [498, 159, 499, 160] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 21 | [433, 160, 434, 161] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 22 | [470, 161, 471, 166] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 23 | [494, 161, 495, 166] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 24 | [260, 162, 261, 163] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 25 | [371, 162, 372, 167] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 26 | [379, 162, 380, 167] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 27 | [387, 162, 388, 166] | 4 | 1 | 4 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 28 | [305, 163, 306, 167] | 4 | 1 | 4 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 29 | [313, 163, 314, 166] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 30 | [346, 163, 347, 167] | 4 | 1 | 4 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 31 | [354, 163, 355, 166] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 32 | [461, 163, 462, 166] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 33 | [502, 163, 503, 165] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 34 | [264, 164, 265, 167] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 35 | [321, 164, 322, 166] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 36 | [395, 164, 396, 166] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 37 | [428, 164, 429, 165] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 38 | [519, 164, 520, 165] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 39 | [223, 165, 224, 167] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 40 | [231, 165, 232, 167] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 41 | [272, 165, 273, 167] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 42 | [297, 165, 298, 167] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 43 | [94, 166, 96, 288] | 242 | 2 | 122 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 44 | [149, 166, 150, 168] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 45 | [157, 166, 158, 167] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 46 | [182, 166, 183, 168] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 47 | [190, 166, 191, 168] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 48 | [198, 166, 199, 167] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 49 | [239, 166, 240, 167] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 50 | [247, 166, 248, 167] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 51 | [289, 166, 290, 167] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 52 | [108, 167, 109, 168] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 53 | [116, 167, 117, 168] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 54 | [141, 167, 142, 168] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 55 | [510, 170, 511, 210] | 40 | 1 | 40 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 56 | [469, 171, 470, 215] | 44 | 1 | 44 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 57 | [477, 171, 478, 183] | 12 | 1 | 12 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 58 | [485, 171, 486, 172] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 59 | [502, 171, 503, 207] | 36 | 1 | 36 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 60 | [387, 172, 388, 180] | 8 | 1 | 8 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 61 | [428, 172, 429, 173] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 62 | [436, 172, 437, 178] | 6 | 1 | 6 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 63 | [444, 172, 445, 173] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 64 | [461, 172, 462, 202] | 30 | 1 | 30 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 65 | [354, 173, 355, 174] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 66 | [420, 175, 421, 178] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 67 | [494, 175, 495, 203] | 28 | 1 | 28 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 68 | [272, 176, 273, 177] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 69 | [428, 176, 429, 284] | 108 | 1 | 108 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 70 | [346, 177, 347, 181] | 4 | 1 | 4 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 71 | [412, 180, 413, 196] | 16 | 1 | 16 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 72 | [264, 182, 265, 185] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 73 | [354, 182, 355, 190] | 8 | 1 | 8 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 74 | [379, 182, 380, 205] | 23 | 1 | 23 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 75 | [453, 183, 454, 202] | 19 | 1 | 19 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 76 | [486, 184, 487, 303] | 119 | 1 | 119 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 77 | [420, 185, 421, 312] | 127 | 1 | 127 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 78 | [231, 187, 232, 190] | 3 | 1 | 3 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 79 | [436, 187, 437, 189] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 80 | [346, 194, 347, 269] | 75 | 1 | 75 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 81 | [305, 198, 306, 199] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 82 | [445, 203, 446, 205] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 83 | [182, 204, 183, 219] | 15 | 1 | 15 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 84 | [461, 206, 462, 243] | 37 | 1 | 37 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 85 | [478, 206, 479, 208] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 86 | [494, 206, 495, 313] | 107 | 1 | 107 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 87 | [453, 207, 454, 224] | 17 | 1 | 17 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 88 | [223, 210, 224, 237] | 27 | 1 | 27 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 89 | [412, 210, 413, 313] | 103 | 1 | 103 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 90 | [511, 211, 512, 213] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 91 | [502, 212, 503, 313] | 101 | 1 | 101 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 92 | [445, 215, 446, 313] | 98 | 1 | 98 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 93 | [256, 216, 257, 217] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 94 | [510, 217, 512, 313] | 115 | 2 | 96 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 95 | [182, 222, 183, 224] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 96 | [264, 226, 265, 231] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 97 | [371, 226, 372, 312] | 86 | 1 | 86 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 98 | [338, 231, 339, 314] | 83 | 1 | 83 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 99 | [453, 234, 454, 313] | 79 | 1 | 79 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 100 | [182, 237, 183, 247] | 10 | 1 | 10 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 101 | [437, 237, 438, 311] | 74 | 1 | 74 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 102 | [478, 237, 479, 283] | 46 | 1 | 46 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 103 | [264, 240, 265, 274] | 34 | 1 | 34 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 104 | [461, 253, 462, 280] | 27 | 1 | 27 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 105 | [174, 260, 175, 311] | 51 | 1 | 51 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 106 | [404, 268, 405, 311] | 43 | 1 | 43 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 107 | [461, 285, 462, 290] | 5 | 1 | 5 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 108 | [478, 293, 479, 313] | 20 | 1 | 20 | COMPONENT_X_SPAN_TOO_SHORT | unclassifiable fragment |
| 109 | [305, 295, 306, 296] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 110 | [461, 295, 462, 301] | 6 | 1 | 6 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 111 | [215, 300, 216, 311] | 11 | 1 | 11 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 112 | [305, 300, 306, 301] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 113 | [461, 311, 462, 313] | 2 | 1 | 2 | COMPONENT_TOO_SMALL | unclassifiable fragment |
| 114 | [486, 312, 487, 313] | 1 | 1 | 1 | COMPONENT_TOO_SMALL | unclassifiable fragment |

Counts: 73 × `COMPONENT_TOO_SMALL`, 41 × `COMPONENT_X_SPAN_TOO_SHORT`,
1 × `NO_PATH_SPANS_REQUIRED_X_RANGE`. The blue curve exists as pixels and as short ordered
fragments; it never becomes a plotted path.

---

## 3. Synthetic regression tests (no expectation changed)

### 3.1 `test_2d_path_tracer_preserves_vertical_time_series_segments_and_rejects_annotations`

`detect_monotonic_color_branches()` now inventories **connected 2-D components**, not row bands.
Plot box `(4,2,186,84)` gives component min x-span ≈15 px and min pixels 12. The callout box
(bbox `[82,8,126,18]`, 71 px, x-span 44, y-span 10) clears both thresholds **because it is
geometrically a wide-enough disconnected component**; there is no semantic annotation
classifier. It is therefore listed as a branch with
`path_qc.status = PARTIAL_PATHS_NEEDS_REVIEW`, reason
`AMBIGUOUS_JUNCTIONS_RETAINED_AS_LOCAL_BREAKPOINTS` (one 33-junction-pixel, 7-port ambiguous
cluster, reason `UNSUPPORTED_JUNCTION_PORT_COUNT`), path 71 points, x-span 44, y-span 10.

The real waveform (bbox `[11,25,179,77]`, 366 px, x-span 168, y-span 52) **is** retained as one
clean ordered path (`path_qc.status = PATHS_EXTRACTED`, 1 path, 366 points, zero junctions,
vertical portions present). So the science intent "keep the vertical waveform, do not trace the
callout" is satisfied *inside the branch records*.

It fails at the tracer API: `trace_monotonic_color()` returns
`NEEDS_REVIEW / MULTIPLE_DISCONNECTED_PATHS_REQUIRE_SEPARATE_SERIES` with **0 points** whenever
`branch_index is None` and more than one component exists (raster.py:917–932). There is no safe
automatic rule that picks the data branch over the annotation branch; the caller must supply
`branch_index`. Selecting `branch_index=0` yields 366 points / `EXTRACTED_PROVISIONAL` with no
annotation pixels. Therefore an extra same-colour annotation branch currently zeroes the whole
real waveform — a genuine downstream selection defect to fix, not a test-expectation problem.
No test was edited in this round.

### 3.2 `test_2d_path_tracer_rejects_unsupported_five_way_junction`

Still **0 points, `NEEDS_REVIEW`**. Because four disconnected components survive component
filtering, the returned QC uses the newer multi-component structure
(`branches` + `component_count` + `reason = MULTIPLE_DISCONNECTED_PATHS_REQUIRE_SEPARATE_SERIES`)
instead of the old `component_detection.rejected_components` key. Branch bboxes:
`[15,52,69,71]`, `[37,72,70,117]`, `[71,52,126,71]`, `[71,72,104,117]`; all have `path_qc=None`.
No junction cluster was paired, no bridge was invented, no "complete" path was returned. This is
QC-schema evolution only; the scientific invariant is intact.

---

## 4. Other legacy gaps (recorded, not fixed)

### 4.1 P8 panel c (`auto-frame-03`) — blocked before any raster tracing

`color_detection.status = NEEDS_REVIEW`, reason `MULTIPLE_CHROMATIC_FAMILIES`;
`trace_specification.status = NEEDS_REVIEW`, reason
`X_AXIS_SEMANTICS_DO_NOT_ESTABLISH_MONOTONIC_ORDER`, `x_axis_label = None`,
`automation_status = NOT_READY`, `y_signal_mode = None`, `raster_qc = None`.
`trace_spec.py:59–65` refuses to build a monotonic-order specification without an ordered X label
and without a `TIME_SERIES`/`SPECTRUM` family. `pipeline.py:1555` calls `trace_monotonic_color()`
**only** when `trace_specification.status == "READY"`, so panel c never enters colour-component
detection: no candidate series, no path QC, 0 points. The blocking stage is the
**trace-specification gate**, not the raster tracer and not the x-span filter.

### 4.2 P3 purple (`color_03`) — component filter, not colour mask or junction

Panel `auto-03` plot box width 335 px → component min x-span **27 px**, min pixels **12**.
Purple family: 618 mask pixels in the component detector (570 in candidate evidence).
Only two components survive: `[68,217,102,225]` (35 px, x-span 34) and
`[105,233,147,247]` (44 px, x-span 42), both `PATHS_EXTRACTED` → x≈68–146.
The other 45 components are rejected **at component level**: 42 × `COMPONENT_TOO_SMALL`
(<12 px), 3 × `COMPONENT_X_SPAN_TOO_SHORT` (e.g. `[256,122,264,131]` 51 px / x-span 8;
`[267,125,282,127]` 25 px / x-span 15; fragments at x≈355–375). So purple pixels **do exist**
beyond x≈146, but they are thin, broken into <27 px components, and never skeletonised.
Not a junction rejection, not a path-backtrack, not a missing colour mask; the dominant cause is
component fragmentation plus the 27 px component x-span / 12 px pixel thresholds.

---

## 5. Diagnostic image

**Not generated.** `path_qc.path_summaries` persist only `path_index`, `path_points`, `bbox`,
`x_span`, `y_span`, `backward_x_steps` and `rejection_reason`; `ambiguous_junction_clusters`
persist port coordinates, but **no ordered path coordinate array** is present anywhere in the
existing outputs. Drawing a "waveform candidate / annotation candidate" overlay would require
inventing geometry, so none was produced.

---

## Appendix A — every rejected path summary

### A.1 Red main component `[94,138,1324,319]` (199 paths)

| idx | points | bbox (panel px) | x_span | y_span | back-x | reason | class |
|---|---:|---|---:|---:|---:|---|---|
| 0 | 151 | [101, 166, 103, 317] | 2 | 151 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 1 | 150 | [109, 167, 111, 317] | 2 | 150 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 2 | 150 | [117, 167, 119, 317] | 2 | 150 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 3 | 151 | [126, 167, 128, 317] | 2 | 150 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 4 | 151 | [134, 166, 136, 317] | 2 | 151 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 5 | 292 | [142, 166, 193, 316] | 51 | 150 | 0 | PATH_X_SPAN_TOO_SHORT | diagonal / mixed (uncertain) |
| 6 | 154 | [150, 166, 160, 317] | 10 | 151 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 7 | 157 | [158, 165, 169, 317] | 11 | 152 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 8 | 155 | [166, 165, 177, 317] | 11 | 152 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 9 | 154 | [175, 165, 185, 317] | 10 | 152 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 10 | 155 | [183, 165, 193, 317] | 10 | 152 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 11 | 35 | [191, 165, 193, 200] | 2 | 35 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 12 | 14 | [199, 150, 201, 164] | 2 | 14 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 13 | 33 | [199, 165, 201, 198] | 2 | 33 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 14 | 118 | [200, 199, 202, 317] | 2 | 118 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 15 | 33 | [208, 165, 210, 198] | 2 | 33 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 16 | 118 | [208, 199, 210, 317] | 2 | 118 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 17 | 33 | [216, 165, 218, 198] | 2 | 33 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 18 | 118 | [217, 199, 218, 317] | 1 | 118 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 19 | 34 | [224, 164, 226, 198] | 2 | 34 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 20 | 118 | [225, 199, 226, 317] | 1 | 118 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 21 | 34 | [232, 164, 235, 198] | 3 | 34 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 22 | 116 | [233, 201, 234, 317] | 1 | 116 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 23 | 36 | [240, 164, 242, 200] | 2 | 36 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 24 | 106 | [241, 211, 243, 317] | 2 | 106 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 25 | 47 | [249, 164, 251, 211] | 2 | 47 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 26 | 94 | [249, 223, 251, 317] | 2 | 94 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 27 | 58 | [257, 164, 259, 222] | 2 | 58 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 28 | 85 | [258, 233, 260, 317] | 2 | 84 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 29 | 68 | [265, 164, 267, 232] | 2 | 68 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 30 | 73 | [266, 244, 267, 317] | 1 | 73 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 31 | 81 | [273, 164, 275, 244] | 2 | 80 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 32 | 62 | [274, 255, 276, 317] | 2 | 62 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 33 | 92 | [282, 163, 284, 255] | 2 | 92 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 34 | 51 | [282, 267, 285, 317] | 3 | 50 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 35 | 103 | [290, 163, 292, 266] | 2 | 103 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 36 | 40 | [290, 278, 293, 317] | 3 | 39 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 37 | 114 | [298, 163, 300, 277] | 2 | 114 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 38 | 29 | [299, 288, 300, 317] | 1 | 29 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 39 | 126 | [306, 163, 308, 289] | 2 | 126 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 40 | 18 | [307, 299, 309, 317] | 2 | 18 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 41 | 137 | [314, 163, 316, 299] | 2 | 136 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 42 | 8 | [315, 309, 316, 317] | 1 | 8 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 43 | 147 | [323, 163, 325, 310] | 2 | 147 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 44 | 168 | [323, 163, 333, 318] | 10 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 45 | 154 | [339, 163, 341, 317] | 2 | 154 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 46 | 155 | [347, 162, 349, 317] | 2 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 47 | 154 | [356, 163, 358, 317] | 2 | 154 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 48 | 154 | [364, 163, 366, 317] | 2 | 154 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 49 | 154 | [372, 163, 374, 317] | 2 | 154 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 50 | 155 | [380, 162, 382, 317] | 2 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 51 | 155 | [389, 162, 390, 317] | 1 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 52 | 155 | [397, 162, 399, 317] | 2 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 53 | 22 | [402, 157, 421, 161] | 19 | 4 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 54 | 151 | [405, 166, 407, 317] | 2 | 151 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 55 | 149 | [413, 168, 415, 317] | 2 | 149 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 56 | 154 | [421, 163, 423, 317] | 2 | 154 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 57 | 155 | [430, 162, 432, 317] | 2 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 58 | 44 | [438, 162, 441, 206] | 3 | 44 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 59 | 111 | [439, 207, 441, 317] | 2 | 110 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 60 | 41 | [446, 162, 448, 203] | 2 | 41 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 61 | 248 | [446, 207, 498, 318] | 52 | 111 | 0 | PATH_X_SPAN_TOO_SHORT | diagonal / mixed (uncertain) |
| 62 | 120 | [447, 205, 456, 317] | 9 | 112 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 63 | 43 | [454, 161, 456, 204] | 2 | 43 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 64 | 119 | [455, 205, 464, 317] | 9 | 112 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 65 | 43 | [462, 161, 464, 204] | 2 | 43 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 66 | 170 | [463, 162, 481, 317] | 18 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 67 | 170 | [471, 162, 481, 317] | 10 | 155 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 68 | 120 | [480, 205, 489, 317] | 9 | 112 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 69 | 43 | [487, 161, 489, 204] | 2 | 43 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 70 | 17 | [496, 143, 497, 160] | 1 | 17 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 71 | 43 | [496, 161, 498, 204] | 2 | 43 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 72 | 47 | [504, 161, 506, 208] | 2 | 47 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 73 | 103 | [505, 214, 506, 317] | 1 | 103 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 74 | 52 | [512, 161, 514, 213] | 2 | 52 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 75 | 98 | [513, 219, 514, 317] | 1 | 98 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 76 | 57 | [520, 161, 522, 218] | 2 | 57 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 77 | 93 | [521, 224, 522, 317] | 1 | 93 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 78 | 62 | [528, 161, 530, 223] | 2 | 62 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 79 | 87 | [529, 230, 530, 317] | 1 | 87 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 80 | 68 | [537, 161, 538, 229] | 1 | 68 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 81 | 82 | [537, 235, 538, 317] | 1 | 82 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 82 | 73 | [545, 161, 547, 234] | 2 | 73 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 83 | 78 | [545, 240, 547, 318] | 2 | 78 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 84 | 79 | [553, 160, 555, 239] | 2 | 79 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 85 | 72 | [554, 245, 555, 317] | 1 | 72 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 86 | 85 | [561, 160, 563, 245] | 2 | 85 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 87 | 67 | [562, 250, 563, 317] | 1 | 67 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 88 | 89 | [570, 161, 571, 250] | 1 | 89 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 89 | 60 | [570, 256, 572, 316] | 2 | 60 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 90 | 94 | [578, 161, 579, 255] | 1 | 94 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 91 | 55 | [578, 262, 579, 317] | 1 | 55 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 92 | 101 | [586, 160, 588, 261] | 2 | 101 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 93 | 50 | [587, 267, 588, 317] | 1 | 50 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 94 | 106 | [594, 160, 596, 266] | 2 | 106 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 95 | 45 | [595, 272, 596, 317] | 1 | 45 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 96 | 110 | [603, 161, 604, 271] | 1 | 110 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 97 | 40 | [603, 277, 604, 317] | 1 | 40 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 98 | 116 | [611, 161, 612, 277] | 1 | 116 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 99 | 34 | [611, 283, 612, 317] | 1 | 34 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 100 | 122 | [619, 160, 621, 282] | 2 | 122 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 101 | 30 | [619, 288, 621, 318] | 2 | 30 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 102 | 127 | [627, 160, 629, 287] | 2 | 127 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 103 | 24 | [628, 293, 629, 317] | 1 | 24 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 104 | 132 | [635, 160, 637, 292] | 2 | 132 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 105 | 19 | [636, 298, 637, 317] | 1 | 19 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 106 | 137 | [643, 160, 645, 297] | 2 | 137 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 107 | 16 | [644, 303, 646, 319] | 2 | 16 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 108 | 143 | [652, 160, 653, 303] | 1 | 143 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 109 | 8 | [652, 309, 653, 317] | 1 | 8 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 110 | 148 | [660, 160, 662, 308] | 2 | 148 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 111 | 153 | [668, 160, 670, 313] | 2 | 153 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 112 | 169 | [668, 160, 678, 318] | 10 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 113 | 157 | [685, 160, 687, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 114 | 157 | [693, 160, 695, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 115 | 157 | [701, 160, 703, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 116 | 157 | [710, 160, 711, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 117 | 157 | [718, 160, 719, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 118 | 157 | [726, 160, 728, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 119 | 157 | [734, 160, 736, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 120 | 13 | [742, 158, 755, 159] | 13 | 1 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 121 | 157 | [742, 160, 744, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 122 | 161 | [751, 160, 756, 317] | 5 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 123 | 157 | [759, 160, 761, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 124 | 157 | [767, 160, 769, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 125 | 157 | [775, 160, 777, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 126 | 157 | [784, 160, 785, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 127 | 157 | [792, 160, 793, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 128 | 158 | [800, 159, 802, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 129 | 157 | [808, 160, 810, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 130 | 157 | [817, 160, 818, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 131 | 157 | [825, 160, 826, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 132 | 157 | [833, 160, 835, 317] | 2 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 133 | 158 | [841, 159, 843, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 134 | 160 | [849, 159, 852, 319] | 3 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 135 | 157 | [858, 160, 859, 317] | 1 | 157 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 136 | 158 | [866, 159, 867, 317] | 1 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 137 | 158 | [874, 159, 876, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 138 | 158 | [882, 159, 884, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 139 | 158 | [891, 159, 892, 317] | 1 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 140 | 158 | [899, 159, 900, 317] | 1 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 141 | 158 | [907, 159, 909, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 142 | 158 | [915, 159, 917, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 143 | 159 | [923, 158, 925, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 144 | 159 | [932, 158, 933, 317] | 1 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 145 | 159 | [940, 158, 942, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 146 | 159 | [948, 158, 950, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 147 | 159 | [956, 158, 958, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 148 | 13 | [964, 156, 977, 157] | 13 | 1 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 149 | 159 | [964, 158, 966, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 150 | 163 | [973, 158, 978, 317] | 5 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 151 | 159 | [981, 158, 983, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 152 | 158 | [990, 159, 992, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 153 | 158 | [998, 159, 1000, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 154 | 158 | [1006, 159, 1008, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 155 | 158 | [1015, 159, 1016, 317] | 1 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 156 | 158 | [1023, 159, 1024, 317] | 1 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 157 | 158 | [1031, 159, 1033, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 158 | 158 | [1039, 159, 1041, 317] | 2 | 158 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 159 | 159 | [1047, 158, 1049, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 160 | 159 | [1056, 158, 1057, 317] | 1 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 161 | 159 | [1064, 158, 1066, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 162 | 159 | [1072, 158, 1074, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 163 | 159 | [1080, 158, 1082, 317] | 2 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 164 | 159 | [1089, 158, 1090, 317] | 1 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 165 | 159 | [1097, 158, 1098, 317] | 1 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 166 | 159 | [1105, 158, 1106, 317] | 1 | 159 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 167 | 160 | [1113, 157, 1115, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 168 | 160 | [1121, 157, 1123, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 169 | 160 | [1130, 157, 1131, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 170 | 160 | [1138, 157, 1140, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 171 | 160 | [1146, 157, 1148, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 172 | 162 | [1154, 157, 1157, 319] | 3 | 162 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 173 | 160 | [1163, 157, 1164, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 174 | 160 | [1171, 157, 1172, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 175 | 160 | [1179, 157, 1181, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 176 | 160 | [1187, 157, 1189, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 177 | 160 | [1196, 157, 1197, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 178 | 160 | [1204, 157, 1206, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 179 | 160 | [1212, 157, 1214, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 180 | 160 | [1221, 157, 1222, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 181 | 160 | [1229, 157, 1230, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 182 | 160 | [1237, 157, 1239, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 183 | 160 | [1245, 157, 1247, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 184 | 160 | [1254, 157, 1255, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 185 | 160 | [1262, 157, 1263, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 186 | 161 | [1270, 156, 1272, 317] | 2 | 161 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 187 | 9 | [1275, 146, 1276, 155] | 1 | 9 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 188 | 161 | [1278, 156, 1280, 317] | 2 | 161 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 189 | 9 | [1283, 146, 1284, 155] | 1 | 9 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 190 | 162 | [1286, 157, 1289, 319] | 3 | 162 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 191 | 160 | [1295, 157, 1296, 317] | 1 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 192 | 10 | [1299, 145, 1301, 155] | 2 | 10 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 193 | 161 | [1303, 156, 1305, 317] | 2 | 161 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 194 | 11 | [1307, 144, 1309, 155] | 2 | 11 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 195 | 160 | [1311, 157, 1313, 317] | 2 | 160 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 196 | 163 | [1315, 156, 1322, 319] | 7 | 163 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |
| 197 | 11 | [1316, 142, 1317, 153] | 1 | 11 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 198 | 22 | [1317, 138, 1324, 154] | 7 | 16 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |

### A.2 Blue main component `[201,111,411,167]` (14 paths)

| idx | points | bbox (panel px) | x_span | y_span | back-x | reason | class |
|---|---:|---|---:|---:|---:|---|---|
| 0 | 12 | [215, 156, 217, 167] | 2 | 11 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 1 | 12 | [256, 155, 257, 167] | 1 | 12 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 2 | 14 | [330, 153, 331, 167] | 1 | 14 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 3 | 14 | [338, 153, 339, 167] | 1 | 14 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 4 | 9 | [351, 142, 353, 151] | 2 | 9 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 5 | 20 | [359, 131, 361, 151] | 2 | 20 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 6 | 14 | [363, 153, 364, 167] | 1 | 14 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 7 | 33 | [367, 118, 369, 151] | 2 | 33 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 8 | 34 | [376, 117, 378, 151] | 2 | 34 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 9 | 35 | [384, 115, 386, 150] | 2 | 35 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 10 | 36 | [392, 114, 394, 150] | 2 | 36 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 11 | 37 | [400, 113, 402, 150] | 2 | 37 | 0 | PATH_X_SPAN_TOO_SHORT | vertical |
| 12 | 15 | [404, 152, 405, 167] | 1 | 15 | 0 | PATH_X_SPAN_TOO_SHORT | short vertical / dot |
| 13 | 41 | [405, 113, 410, 152] | 5 | 39 | 0 | PATH_X_SPAN_TOO_SHORT | other short fragment |

## Appendix B — ambiguous cluster port coordinates

### B.1 Red

- cluster 0 (91 ports): [100,164], [101,166], [105,164], [109,167], [113,165], [117,167], [121,164], [127,167], [131,164], [134,166], [142,166], [146,164], [150,166], [154,163], [158,165], [166,165], [175,165], [183,165], [191,165], [199,165], [200,163], [208,165], [216,165], [224,164], [232,164], [240,164], [249,164], [257,164], [265,164], [273,164], [282,163], [290,163], [298,163], [306,163], [314,163], [323,163], [331,163], [339,163], [347,162], [356,163], [364,163], [372,163], [380,162], [389,162], [397,162], [402,160], [405,166], [413,168], [420,160], [421,163], [430,162], [438,162], [446,162], [454,161], [462,161], [471,162], [479,162], [487,161], [496,159], [496,161], [504,161], [512,161], [520,161], [528,161], [537,161], [545,161], [553,160], [561,160], [570,161], [578,161], [586,160], [594,160], [603,161], [611,161], [619,160], [627,160], [635,160], [643,160], [652,160], [660,160], [668,160], [677,160], [685,160], [693,160], [701,160], [710,160], [718,160], [726,160], [734,160], [742,158], [742,160]
- cluster 6 (8 ports): [192,199], [192,201], [199,197], [201,199], [208,199], [209,197], [217,197], [217,199]
- cluster 7 (26 ports): [225,197], [225,199], [233,197], [233,201], [240,199], [242,211], [249,210], [250,223], [257,221], [259,233], [265,231], [266,244], [273,243], [275,255], [282,254], [284,267], [290,265], [292,278], [298,276], [299,288], [307,288], [308,299], [314,298], [315,309], [323,309], [323,311]
- cluster 8 (8 ports): [440,205], [440,207], [446,207], [447,202], [455,203], [455,205], [463,203], [463,205]
- cluster 15 (46 ports): [488,203], [488,205], [497,203], [497,208], [504,207], [505,214], [513,212], [513,219], [521,217], [521,224], [529,222], [529,230], [537,228], [537,235], [545,233], [546,240], [554,238], [554,245], [562,244], [562,250], [570,249], [571,256], [578,254], [578,262], [586,260], [587,267], [594,265], [595,272], [603,270], [603,277], [611,276], [611,283], [619,281], [620,288], [628,286], [628,293], [636,291], [636,298], [644,296], [644,303], [652,302], [652,309], [661,307], [661,314], [668,314], [669,312]
- cluster 16 (29 ports): [754,158], [755,160], [759,160], [767,160], [775,160], [784,160], [792,160], [800,159], [808,160], [817,160], [825,160], [833,160], [841,159], [849,159], [858,160], [866,159], [874,159], [882,159], [891,159], [899,159], [907,159], [915,159], [923,158], [932,158], [940,158], [948,158], [956,158], [964,156], [964,158]
- cluster 17 (50 ports): [976,156], [977,158], [981,158], [990,159], [998,159], [1006,159], [1015,159], [1023,159], [1031,159], [1039,159], [1047,158], [1056,158], [1064,158], [1072,158], [1080,158], [1089,158], [1097,158], [1105,158], [1113,157], [1121,157], [1130,157], [1138,157], [1146,157], [1154,157], [1163,157], [1171,157], [1179,157], [1187,157], [1196,157], [1204,157], [1212,157], [1221,157], [1229,157], [1237,157], [1245,157], [1254,157], [1262,157], [1270,156], [1275,154], [1278,156], [1283,154], [1287,157], [1295,157], [1299,154], [1303,156], [1307,154], [1311,157], [1315,156], [1316,152], [1317,153]

### B.2 Blue

- cluster 0 (33 ports): [202,155], [204,153], [212,153], [216,156], [220,152], [228,152], [237,153], [245,152], [253,152], [256,155], [261,151], [269,151], [277,151], [285,152], [294,151], [302,151], [310,151], [318,151], [326,151], [330,153], [335,150], [338,153], [343,150], [351,150], [359,150], [363,153], [367,150], [376,150], [384,149], [392,149], [400,149], [404,152], [405,151]
