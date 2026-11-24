# P3_02 short-fragment geometry / OCR proximity diagnostic

Source: freshly generated `panel_series.csv` (ordered coordinates) and archived `tests/fixtures/real_figures/P3_02_ocr.json`. No OCR was re-run. No paper/PDF/SI was read.

Panel `auto-03` crop (SOURCE_IMAGE_PIXELS, from `crop_mapping`): `[914, 0, 1399, 404]`; CSV `pixel_x/pixel_y` are panel-local, so source coordinate = local + (914, 0). Cached OCR rows inside this crop: 33.

| Series | pts | segs | local bbox | source bbox | length px | chord px | chord/len | dir changes | back-X | repeats |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| _color_01_branch_03 | 41 | 1 | [122.0, 125.0, 162.0, 126.0] | [1036.0, 125.0, 1076.0, 126.0] | 42.07 | 40.01 | 0.951 | 4 | 0 | 0 |
| _color_03_branch_03 | 14 | 1 | [267.0, 125.0, 280.0, 126.0] | [1181.0, 125.0, 1194.0, 126.0] | 13.83 | 13.00 | 0.940 | 1 | 0 | 0 |
| _color_01_branch_04 | 28 | 2 | [138.0, 97.0, 146.0, 105.0] | [1052.0, 97.0, 1060.0, 105.0] | 35.07 | 8.25 | 0.235 | 4 | 1 | 0 |
| _color_01_branch_05 | 22 | 1 | [149.0, 190.0, 169.0, 191.0] | [1063.0, 190.0, 1083.0, 191.0] | 21.83 | 20.02 | 0.917 | 2 | 0 | 0 |
| _color_01_branch_06 | 19 | 1 | [163.0, 182.0, 181.0, 183.0] | [1077.0, 182.0, 1095.0, 183.0] | 18.41 | 18.03 | 0.979 | 0 | 0 | 0 |
| _color_03_branch_01 | 35 | 1 | [68.0, 217.0, 101.0, 224.0] | [982.0, 217.0, 1015.0, 224.0] | 36.90 | 33.54 | 0.909 | 1 | 0 | 0 |
| _color_03_branch_02 | 44 | 1 | [105.0, 233.0, 146.0, 246.0] | [1019.0, 233.0, 1060.0, 246.0] | 47.56 | 43.01 | 0.904 | 0 | 0 | 0 |

## OCR spatial association

### _color_01_branch_03

Overlapping cached OCR boxes (intersection area px², text, confidence, OCR bbox in source px):

- 40 px² — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]

Nearest OCR boxes (distance px from path bbox to polygon):

- 0.0 px — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]
- 9.0 px — `Te NSs —— Discharge` (conf=0.88995) bbox=[973, 88, 1155, 116]
- 24.0 px — `0.1` (conf=0.99994) bbox=[1018, 150, 1053, 174]
- 26.1 px — `0.05` (conf=0.99999) bbox=[974, 140, 1014, 163]
- 34.0 px — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]

Exact ordered coordinates (panel-local px, from CSV):

`[122,126], [123,125], [124,125], [125,125], [126,125], [127,125], [128,125], [129,125], [130,125], [131,125], [132,126], [133,126], [134,125], [135,125], [136,125], [137,125], [138,125], [139,125], [140,125], [141,125], [142,126], [143,125], [144,125], [145,125], [146,125], [147,125], [148,125], [149,125], [150,125], [151,125], [152,125], [153,125], [154,125], [155,125], [156,125], [157,125], [158,125], [159,125], [160,125], [161,125], [162,125]`

### _color_03_branch_03

Overlapping cached OCR boxes (intersection area px², text, confidence, OCR bbox in source px):

- 13 px² — `Charge` (conf=0.98309) bbox=[1175, 116, 1251, 140]
- 4 px² — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]

Nearest OCR boxes (distance px from path bbox to polygon):

- 0.0 px — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]
- 0.0 px — `Charge` (conf=0.98309) bbox=[1175, 116, 1251, 140]
- 9.0 px — `Charge` (conf=0.99975) bbox=[1181, 92, 1251, 116]
- 27.5 px — `Te NSs —— Discharge` (conf=0.88995) bbox=[973, 88, 1155, 116]
- 60.8 px — `0.5` (conf=0.99983) bbox=[1099, 168, 1137, 196]

Exact ordered coordinates (panel-local px, from CSV):

`[267,126], [268,126], [269,126], [270,125], [271,125], [272,125], [273,125], [274,125], [275,125], [276,126], [277,126], [278,126], [279,126], [280,126]`

### _color_01_branch_04

Overlapping cached OCR boxes (intersection area px², text, confidence, OCR bbox in source px):

- 64 px² — `Te NSs —— Discharge` (conf=0.88995) bbox=[973, 88, 1155, 116]

Nearest OCR boxes (distance px from path bbox to polygon):

- 0.0 px — `Te NSs —— Discharge` (conf=0.88995) bbox=[973, 88, 1155, 116]
- 9.0 px — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]
- 45.0 px — `0.1` (conf=0.99994) bbox=[1018, 150, 1053, 174]
- 51.7 px — `0.05` (conf=0.99999) bbox=[974, 140, 1014, 163]
- 55.0 px — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]

Exact ordered coordinates (panel-local px, from CSV):

`[138,100], [138,99], [138,98], [139,98], [139,97], [140,97], [141,97], [142,97], [143,97], [144,97], [144,98], [145,98], [145,99], [146,100], [138,102], [138,103], [138,104], [139,104], [139,105], [140,105], [141,105], [142,105], [143,105], [144,105], [144,104], [145,104], [145,103], [146,102]`

### _color_01_branch_05

No cached OCR polygon bbox overlaps the path bbox.

Nearest OCR boxes (distance px from path bbox to polygon):

- 5.0 px — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]
- 16.0 px — `0.5` (conf=0.99983) bbox=[1099, 168, 1137, 196]
- 18.9 px — `0.1` (conf=0.99994) bbox=[1018, 150, 1053, 174]
- 51.0 px — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]
- 55.9 px — `0.05` (conf=0.99999) bbox=[974, 140, 1014, 163]

Exact ordered coordinates (panel-local px, from CSV):

`[149,191], [150,191], [151,191], [151,190], [152,190], [153,190], [154,190], [155,190], [156,190], [157,190], [158,190], [159,190], [160,190], [161,190], [162,190], [163,190], [164,190], [165,191], [166,191], [167,191], [168,191], [169,190]`

### _color_01_branch_06

Overlapping cached OCR boxes (intersection area px², text, confidence, OCR bbox in source px):

- 18 px² — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]

Nearest OCR boxes (distance px from path bbox to polygon):

- 0.0 px — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]
- 4.0 px — `0.5` (conf=0.99983) bbox=[1099, 168, 1137, 196]
- 25.3 px — `0.1` (conf=0.99994) bbox=[1018, 150, 1053, 174]
- 43.0 px — `Bulk Te——Discharge —` (conf=0.89585) bbox=[973, 114, 1185, 139]
- 48.2 px — `1.0` (conf=0.99993) bbox=[1143, 187, 1176, 211]

Exact ordered coordinates (panel-local px, from CSV):

`[163,183], [164,183], [165,183], [166,183], [167,183], [168,183], [169,183], [170,183], [171,182], [172,182], [173,182], [174,182], [175,182], [176,182], [177,182], [178,182], [179,182], [180,182], [181,182]`

### _color_03_branch_01

No cached OCR polygon bbox overlaps the path bbox.

Nearest OCR boxes (distance px from path bbox to polygon):

- 12.0 px — `2000` (conf=0.99999) bbox=[915, 194, 970, 220]
- 32.6 px — `1000` (conf=0.99996) bbox=[914, 253, 967, 285]
- 43.1 px — `0.1` (conf=0.99994) bbox=[1018, 150, 1053, 174]
- 54.0 px — `0.05` (conf=0.99999) bbox=[974, 140, 1014, 163]
- 55.2 px — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]

Exact ordered coordinates (panel-local px, from CSV):

`[68,217], [69,217], [70,217], [71,218], [72,218], [73,218], [74,219], [75,219], [76,220], [77,220], [78,220], [79,220], [80,220], [81,220], [82,221], [83,221], [84,221], [85,222], [86,222], [87,222], [88,223], [89,223], [89,224], [90,224], [91,224], [92,224], [93,224], [94,223], [95,223], [96,223], [97,223], [98,223], [99,223], [100,223], [101,223]`

### _color_03_branch_02

No cached OCR polygon bbox overlaps the path bbox.

Nearest OCR boxes (distance px from path bbox to polygon):

- 48.0 px — `0.2` (conf=0.99994) bbox=[1060, 160, 1096, 185]
- 50.7 px — `2000` (conf=0.99999) bbox=[915, 194, 970, 220]
- 52.5 px — `1000` (conf=0.99996) bbox=[914, 253, 967, 285]
- 53.8 px — `0.5` (conf=0.99983) bbox=[1099, 168, 1137, 196]
- 59.0 px — `0.1` (conf=0.99994) bbox=[1018, 150, 1053, 174]

Exact ordered coordinates (panel-local px, from CSV):

`[105,233], [106,233], [107,233], [108,234], [109,234], [110,234], [111,235], [112,235], [113,235], [114,236], [114,237], [115,237], [116,237], [117,237], [118,238], [119,238], [120,238], [121,238], [122,239], [123,239], [124,239], [125,240], [126,240], [127,240], [128,240], [129,240], [130,240], [131,240], [132,241], [133,241], [134,241], [135,241], [135,242], [136,242], [137,242], [138,242], [139,242], [140,242], [141,243], [142,243], [143,244], [144,244], [145,245], [146,246]`

## Interpretation rule (evidence-based, no generic threshold change)

A path is classified as glyph/annotation-associated only when its ordered coordinates are spatially coincident with a cached OCR text box or a legend marker and its geometry is a short closed/near-closed stroke (high direction-change count, low chord/length). Otherwise it stays `UNRESOLVED / NEEDS_REVIEW`. No production length/pixel/aspect threshold was changed in this validation.
