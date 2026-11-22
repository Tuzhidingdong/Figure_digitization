# PR #19 正式真实图片验收报告 — P7_05

日期：2026-11-22
性质：一次正式真实图片复测；只测试，不修改任何生产代码、Skill、计划或上游数据。

## 1. Git HEAD 与环境版本

| 项 | 结果 |
|---|---|
| 分支 / HEAD | `feat/p1-multicolor-dual-y-axis` / `3c49ba37779274abd2c8b249ed4c746d64af5a1d`（与指定一致） |
| 新隔离 worktree | `E:\Zinc_batters_datas\Figure_digitization_p1_multicolor_test_20261122` |
| 新输出目录 | `E:\Zinc_batters_datas\Figure_digitization_p1_multicolor_test_outputs_20261122` |
| 算法版本 | **0.3.0**（run_report） |
| Python | 3.13.9（独立 `.venv`） |
| RapidOCR | **3.10.0**；ONNX Runtime **1.32.0**；numpy 2.5.5 |
| Skill | 25 文件与原项目逐文件 SHA256 一致；SKILL.md `43405025…35e4b8`；已从新 worktree 正式加载 |

## 2. 原图 SHA256 与夹具复用

- 原图：`…\chem-literacy\runs\preprocessed\10.1002_adfm.75805\extracted_figures\MAIN\MAIN_MAIN_FIG_P7_05.png`
- SHA256：`3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de`
- 与 PR18 报告中记录、PR18 工作区夹具副本、本轮副本三者**完全相同**；`figure_inventory.json` 与上一轮逐字节一致（只含 figure_id 与 image_path）。
- 本轮输入夹具：`E:\Zinc_batters_datas\Figure_digitization_p1_multicolor_test_20261122\test_inputs\single_figure_P7_05\`
- **零人工标注**：未切 panel、未给 bbox/plot_box、未指定颜色/series/左右 Y 轴、未补锚点或点。

## 3. 执行命令与结果总览

```
<WT>\.venv\Scripts\sfd.exe scan --input-root <WT>\test_inputs\single_figure_P7_05 --output-root <OUT>
<WT>\.venv\Scripts\sfd.exe run --input-root <WT>\test_inputs\single_figure_P7_05 --output-root <OUT> --paper-id root-paper --workers 1 --max-attempts 1 --ocr
<WT>\.venv\Scripts\sfd.exe validate --output-root <OUT> --input-root <WT>\test_inputs\single_figure_P7_05
<WT>\.venv\Scripts\sfd.exe export --output-root <OUT> --out <OUT>\exports\digitized_points --paper-id root-paper --format csv
```
`--out` 按要求传目录，生成 `exports\digitized_points\dataset.csv`（非错误目录结构）。

| 步骤 | 结果 |
|---|---|
| scan | discovered = 1 |
| run | job state = **NEEDS_REVIEW**，`failed=0`，`last_error=null` |
| validate | **OK**（5 个 JSON，0 错误） |
| export | 9 series 元数据；**0 行点数据** |
| 资源 | 22.947 s，峰值 RSS 215,375,872 B，LLM token 0 |

---

## 4. 六个面板的分割、分类与处理状态

| panel | bbox（源图像素） | 分割来源 / 置信度 | OCR 记录 | 图表族 | 处理状态 |
|---|---|---|---|---|---|
| auto-01 | [0,0,434,351] | AUTO_RASTER_WHITESPACE_SEGMENTATION / 0.7128 | 22 | NON_MONOTONIC_CURVE（CV） | 两轴数值校准成功；trace spec `NOT_SUPPORTED`（CV 需有序路径算法），安全拒绝 |
| auto-02 | [471,0,982,351] | 同上 / 0.7129 | 38 | UNCLASSIFIED | 双 Y 轴数值校准成功；颜色多族；trace `NEEDS_REVIEW / UNIQUE_SINGLE_TRACE_COLOR_NOT_ESTABLISHED` |
| auto-03 | [1000,0,1401,351] | 同上 / 0.7129 | 7 | UNCLASSIFIED | 无绘图区；trace `NEEDS_REVIEW / PLOT_REGION_UNRESOLVED` |
| auto-04 | [0,356,484,677] | 同上 / 0.7174 | 25 | UNCLASSIFIED | 检出 4 个自动颜色候选，各生成 1 条 series；双 Y 轴校准成功；轴归属歧义；trace `NEEDS_REVIEW / BOTH_NUMERIC_AXIS_CALIBRATIONS_REQUIRED` |
| auto-05 | [501,356,950,677] | 同上 / 0.7174 | 23 | UNCLASSIFIED | 双 Y 轴数值校准成功；颜色多族；trace `NEEDS_REVIEW / UNIQUE_SINGLE_TRACE_COLOR_NOT_ESTABLISHED` |
| auto-06 | [974,356,1401,677] | 同上 / 0.6815 | 22 | UNCLASSIFIED | 无绘图区；trace `NEEDS_REVIEW / PLOT_REGION_UNRESOLVED` |

分割局限（Agent 视觉观察，非 Skill 语义输出）：auto-01 含子图 a 并带入 d 标签；auto-02 含子图 b 并带入 c/f 标签。几何分割不是内容识别。

## 5. 每条颜色候选的独立追踪结果

PR #19 新增多颜色候选生成：auto-04 的 `family_detection` 状态为 `MULTIPLE_CHROMATIC_FAMILIES`，reason `COLOR_FAMILIES_ARE_CANDIDATES_NOT_CONFIRMED_SERIES`，`saturated_pixel_count=6737`，`family_count=4`。四个候选各自生成一条 series，`color_detection.status=UNIQUE_CHROMATIC_FAMILY`、`source=AUTOMATIC_MULTI_COLOR_FAMILY_CANDIDATE`：

| series 后缀 | color_rgb | tolerance | pixel_count | pixel_fraction | seed_rgb | trace_spec | 数据点 |
|---|---|---|---|---|---|---|---|
| auto_color_01 | [253,120,120] | 26 | 2868 | 0.4257 | [255,120,120] | NEEDS_REVIEW / BOTH_NUMERIC_AXIS_CALIBRATIONS_REQUIRED | 0 |
| auto_color_02 | [251,11,12] | 26 | 1845 | 0.2739 | [255,0,0] | 同上 | 0 |
| auto_color_03 | [252,69,69] | 26 | 1211 | 0.1798 | [255,72,72] | 同上 | 0 |
| auto_color_04 | [253,185,184] | 26 | 799 | 0.1186 | [255,192,192] | 同上 | 0 |

其它面板：auto-02 颜色检测 `NEEDS_REVIEW / MULTIPLE_CHROMATIC_FAMILIES`（dominant [251,21,24]，purity 0.356）；auto-05 同状态（dominant [255,234,0]，purity 0.568）；auto-01 因 `NON_MONOTONIC_CURVE` 未运行颜色检测；auto-03/06 无绘图区故颜色检测为空。

**颜色检测成功 ≠ 曲线提取成功**：4 条候选 series 都有 `UNIQUE_CHROMATIC_FAMILY` 状态，但没有任何一条进入 X-monotonic tracer，数据点均为 0。

## 6. LEFT/RIGHT 校准与系列轴关联证据

| panel | LEFT 校准 | RIGHT 校准 | series_axis_assignment | y_axis_text_color_association |
|---|---|---|---|---|
| auto-01 | slope −0.0238789, intercept 4.55254, rmse 0.002230, 5 anchors | 无（单轴） | **ASSIGNED / LEFT** | NOT_EVALUATED |
| auto-02 | slope −1.98976, intercept 592.902, rmse 0.340971, 6 anchors (500→0) | slope −0.438592, intercept 130.613, rmse 0.107433, 5 anchors (100→0) | **AMBIGUOUS_DUAL_Y_AXIS**（reason `SERIES_TO_Y_AXIS_MAPPING_REQUIRED`） | NOT_EVALUATED |
| auto-04 | slope −1.79210, intercept 451.073, rmse 0.438975, 5 anchors (400→0) | slope −0.437772, intercept 110.048, rmse 0.057846, 6 anchors (100→0) | **AMBIGUOUS_DUAL_Y_AXIS**（4 条 series 均如此） | **NO_UNIQUE_MATCH**：curve_color_rgb 与两侧均无唯一匹配；LEFT/RIGHT 均 `NO_CHROMATIC_TEXT_COLOR`、`colored_label_count=0`、`required_label_count=2`、`label_pixel_counts=[]`、`side_match_distances={}`；matching_rule=`UNIQUE_CURVE_TO_CHROMATIC_Y_TICK_TEXT_COLOR` |
| auto-05 | slope −0.218679, intercept 55.0866, rmse 0.057792, 6 anchors (50→0) | slope −0.418795, intercept 105.313, rmse 0.078219, 5 anchors (100,80,60,20,0) | **AMBIGUOUS_DUAL_Y_AXIS** | NOT_EVALUATED |
| auto-03 / auto-06 | 无 | 无 | UNRESOLVED | NOT_EVALUATED |

- **路径 1（左右刻度颜色与曲线颜色唯一匹配 → 自动关联轴）**：**NOT EVALUATED**。本图所有相关面板的刻度文字均为黑/灰色，未出现两侧彩色数值刻度，因此没有触发该路径。
- **路径 2（刻度黑/灰或匹配不唯一 → 必须保留 AMBIGUOUS，不得猜测）**：**PASS**。auto-04 的四条颜色候选均给出 `NO_UNIQUE_MATCH` + `AMBIGUOUS_DUAL_Y_AXIS`，没有强行选边；auto-02/05 同样保留 `AMBIGUOUS_DUAL_Y_AXIS`。
- 重要细节：auto-04 的 `y_axis_calibrations` 中 LEFT/RIGHT **都已 CALIBRATED_NUMERIC**，但单一 `y_calibration` 为 null，因为轴归属未解决；trace spec 因此返回 `BOTH_NUMERIC_AXIS_CALIBRATIONS_REQUIRED`（语义上要求“选定轴的校准”，不是“两侧校准都不存在”）。这说明双轴数值校准成功**不等于**系列轴归属成功。

## 7. Series / 数据点 / CSV

- series：**9** 条（6 个面板各 1 条基础 series + auto-04 的 3 条额外颜色候选 series，auto-04 共 4 条）。
- 数据点：**0**（所有 series `points_count=0`，`extraction_method=UNRESOLVED`，`extraction_status=NEEDS_REVIEW`）。
- `exports\digitized_points\dataset.csv`：**0 数据行**（仅表头）；`series_metadata.jsonl` 83,986 bytes；`warnings.jsonl` 5,295 bytes。
- 导出警告：`QC_PROVISIONAL_UNCALIBRATED` 9、`NOT_REVIEWED_ACCEPTED` 9、`SUBJECT_LINK_UNASSIGNED` 9、`CONDITIONS_NOT_LINKED` 9、`CANONICAL_POINTS_FILE_MISSING` 9、`DUAL_AXIS_UNASSIGNED` 8。
- 所有 9 条 series 的 `automation_status = NOT_READY`，**无 FULLY_AUTOMATIC**。

## 8. 重绘 / overlay / comparison sheet

- 独立重绘 PNG：**无**（0 个 `*_reconstructed.png`，因无点可绘）。
- source-image overlay：**无**（0 个 `*_overlay.png`）。
- comparison sheet（pipeline 正式输出）：`E:\Zinc_batters_datas\Figure_digitization_p1_multicolor_test_outputs_20261122\papers\root-paper\comparisons\ALL_PANELS_COMPARISON.png` — 6 行，中列统一 `NO AUTOMATIC DATA / NO PLOT`，右列显示各面板 trace spec 状态。
- 其它正式产物：`digitization.json`、`paper_bundle.json`、`panel_layout.json`、`paper_manifest.json`、`figure_inventory.json`、`evidence/P7_05_auto-01..06.png`。

## 9. 最终 job state / validate / 错误

- job state：`NEEDS_REVIEW`（1），`failed=0`，`last_error=null`；`job_events` 仅 JOB_STARTED 与 NEEDS_REVIEW。
- validate：`OK`（5 个 JSON，0 错误）。
- 无运行期错误；所有未成功项以明确 `NEEDS_REVIEW` + reason 表达。

## 10. 与 PR18 逐项对比

| 项目 | PR18（33f0454） | PR19（3c49ba3） |
|---|---|---|
| 算法版本 | 0.2.0 | 0.3.0 |
| 面板 / OCR 记录 | 6 / 137 | 6 / 137（一致） |
| series 数 | 6 | **9**（多 3 条颜色候选） |
| 颜色候选 series | 0 | **4**（auto-04） |
| 双 Y 轴数值校准 | 部分字段（无 y_axis_calibrations） | **auto-02/04/05 两侧均 CALIBRATED_NUMERIC** |
| series_axis_assignment | 无 | ASSIGNED / AMBIGUOUS_DUAL_Y_AXIS / UNRESOLVED |
| y_axis_text_color_association | 无 | NO_UNIQUE_MATCH / NOT_EVALUATED |
| trace_spec 状态 | 1 NOT_SUPPORTED + 5 NEEDS_REVIEW | 1 NOT_SUPPORTED + 8 NEEDS_REVIEW |
| 数据点 / CSV 行 | 0 / 0 | **0 / 0（未改善）** |
| 重绘 / overlay | 无 | 无 |
| comparison sheet | 有（pipeline） | 有（pipeline） |
| validate / job | OK / NEEDS_REVIEW | OK / NEEDS_REVIEW |

结论：PR19 新增了**多颜色候选生成**和**双 Y 轴数值校准 + 轴归属证据/歧义判定**，并正确地在刻度文字非彩色时保留 `AMBIGUOUS_DUAL_Y_AXIS`。但它**没有把任何候选推进到有效 TraceSpecification / 数据点**，因此核心提取能力仍为 0。

## 11. 未解决问题与科学能力边界

1. **TraceSpecification 未 READY**：9 条 series 全部 `NOT_READY`；auto-04 的颜色候选因“选定轴校准未建立”（轴归属歧义）被阻断，auto-02/05 因“唯一颜色未确立”被阻断，auto-01 因 CV 非单调被正确拒绝，auto-03/06 无绘图区。
2. **双轴颜色匹配路径未覆盖**：刻度文字为黑/灰色，`NO_UNIQUE_MATCH`；唯一匹配路径 1 在本图无法验证（NOT EVALUATED）；保守保留 AMBIGUOUS 是正确的。
3. **颜色候选不等于系列确认**：4 个 RGB 族被检出，但 `COLOR_FAMILIES_ARE_CANDIDATES_NOT_CONFIRMED_SERIES`，没有图例/颜色→系列科学语义绑定。
4. **几何分割有渗入**：auto-01/02 带相邻面板标签；不是科学内容识别。
5. **不支持类型安全**：CV 未进入单调追踪器（PASS）；scatter/schematic 因无绘图区未进入追踪（PASS）；未扩大支持范围。
6. **科学精度未验证**：无独立人工数值基准；不宣称 RMSE/MAE/准确率通过；校准 RMSE 仅为锚点拟合残差。

**核心目标（至少一个受支持的多颜色单调曲线面板完全自动提取两条 series）未达成：本轮判定 FAIL。** 本图没有满足 Phase 1 条件的面板；0 点是真实结果，不是人为设置的通过门槛。PR#19 保持 Draft，未合并。

---

## 12. 交付文件与完整性

- 报告与汇总：`REPORT.md`、`summary.json`、`panel_inventory.csv`、`digitization_summary.csv`、`qc_summary.csv`
- 日志：`logs/{scan,run,validate,export,analyze_results,summaries}.log` 与分析脚本
- 导出：`exports/digitized_points/{dataset.csv,export_manifest.json,series_metadata.jsonl,warnings.jsonl}`
- 正式产物：`papers/root-paper/{digitization,paper_bundle,panel_layout,paper_manifest,figure_inventory}.json`、`evidence/P7_05_auto-01..06.png`、`comparisons/ALL_PANELS_COMPARISON.png`

完整性核对：新 worktree HEAD 仍为 `3c49ba3…5a1d`，`git diff --name-only` 为空；原项目、PR17/PR18 worktree 状态未变；原始图片 SHA256 前后相同；Skill 25 文件与 TASK_PLAN 哈希未变；未修改源码/配置/测试/Skill/STATUS/TASK_PLAN/上游数据；未 commit/push/merge/发版。
