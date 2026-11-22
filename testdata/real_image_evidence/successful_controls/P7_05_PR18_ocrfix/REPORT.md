# PR #18 本地真实图片复测报告 — P7_05

日期：2026-11-22
性质：修复后第一次正式真实图片复测；只测试，不修改任何生产代码。

## 1. 版本与环境

| 项 | 结果 |
|---|---|
| Git 分支 / HEAD | `fix/p1-rapidocr-310-compatibility` / `33f0454b1d4a9a7bc9781fafaace58a0bdbf3706`（与指定一致） |
| 隔离 worktree | `E:\Zinc_batters_datas\Figure_digitization_p1_ocrfix_test_20261122` |
| Python | 3.13.9（独立 `.venv`） |
| RapidOCR | **3.10.0**（`importlib.metadata.version('rapidocr')` 确认） |
| ONNX Runtime | 1.32.0；numpy 2.5.5；Pillow 13.0.0 |
| 安装命令 | `pip install -e ".[dev,images,ocr]" "rapidocr==3.10.0"` 成功 |
| Skill | 从原项目原样复制 25 文件，SHA256 全部一致；SKILL.md `43405025…35e4b8`；已在新 worktree 根目录正式加载 |

## 2. 输入与输出目录

- 输入夹具：`E:\Zinc_batters_datas\Figure_digitization_p1_ocrfix_test_20261122\test_inputs\single_figure_P7_05\`
  - 只含 `MAIN_MAIN_FIG_P7_05.png` 与最小 `figure_inventory.json`（仅 `figure_id`、`image_path`），**零人工标注**。
- 原图 SHA256：`3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de`
- 夹具副本 SHA256：同上，**与上一轮 REPORT.md 记录完全一致**。
- 输出目录（独立于上一轮）：`E:\Zinc_batters_datas\Figure_digitization_p1_ocrfix_test_outputs_20261122`

实际执行命令（均在新 worktree 根目录，`<WT>`=worktree，`<OUT>`=输出目录）：
```
<WT>\.venv\Scripts\sfd.exe scan --input-root <WT>\test_inputs\single_figure_P7_05 --output-root <OUT>
<WT>\.venv\Scripts\sfd.exe run --input-root <WT>\test_inputs\single_figure_P7_05 --output-root <OUT> --paper-id root-paper --workers 1 --max-attempts 1 --ocr
<WT>\.venv\Scripts\sfd.exe validate --output-root <OUT> --input-root <WT>\test_inputs\single_figure_P7_05
<WT>\.venv\Scripts\sfd.exe export --output-root <OUT> --out <OUT>\exports\digitized_points --paper-id root-paper --format csv
```
`--out` 按要求传**目录**，因此本次正确生成 `exports\digitized_points\dataset.csv`，没有上一轮 `.csv` 被当目录名的问题。

## 3. 执行总览

| 步骤 | 结果 |
|---|---|
| scan | discovered = 1 |
| run | job state = **NEEDS_REVIEW**（`failed=0`, `permanently_failed_papers=0`），`last_error = null` |
| validate | **OK**（5 个 JSON，0 错误） |
| export | 6 个 series 元数据；**0 行点数据** |
| 运行资源 | 17.755 s，峰值 RSS 236,482,560 B，LLM token 0 |

---

## 4. 各阶段 PASS / PARTIAL / FAIL / NOT EVALUATED

| 阶段 | 结论 | 证据 |
|---|---|---|
| 输入与 Skill 加载 | **PASS** | HEAD/SHA 一致，Skill 正式加载 |
| RapidOCR 初始化 | **PASS** | 日志显示 3 个 ONNX 模型成功加载（det/cls/rec），无 `Det.engine_type` Enum 错误 |
| OCR 实际推理 | **PASS** | 6 个面板 `ocr_status=SUCCEEDED`，共 **137** 条 OCR 记录 |
| 自动面板分割 | **PARTIAL** | 6 个 `AUTO_RASTER_WHITESPACE_SEGMENTATION` 区域；但存在相邻面板标签渗入 |
| 轴标签 OCR | **PARTIAL** | 4/6 面板找到轴标签；部分仅识别到碎片（如 `g`、`efficiency`） |
| 数值 tick / 锚点 | **PARTIAL** | X 锚点合计 22，Y 锚点合计 5（仅 auto-01 有 Y 锚点） |
| 数值坐标校准 | **PARTIAL** | 仅 auto-01 完成两轴 CALIBRATED_NUMERIC；其余仅 X 或完全未校准 |
| TraceSpecification | **FAIL** | 0 个 READY；1 个 NOT_SUPPORTED、5 个 NEEDS_REVIEW；全部 `automation_status = NOT_READY` |
| 颜色检测 | **PARTIAL** | 3 个面板实际运行，均返回 `MULTIPLE_CHROMATIC_FAMILIES` |
| 自动数据提取 | **FAIL** | 0 series 有数据，**0 数据点** |
| CSV 导出 | **FAIL** | `dataset.csv` 仅表头，0 数据行 |
| 独立重绘 / overlay | **FAIL** | 0 个 reconstructed PNG、0 个 overlay PNG（无点可绘） |
| comparison sheet | **PASS** | pipeline 正式生成 `comparisons/ALL_PANELS_COMPARISON.png`，6 行，中列明确写 `NO AUTOMATIC DATA / NO PLOT` |
| CV/EIS 安全拒绝 | **PASS** | auto-01 被正确识别为 `NON_MONOTONIC_CURVE`，trace spec 为 `NOT_SUPPORTED / NON_MONOTONIC_PATH_REQUIRES_ORDERED_TRACE_ALGORITHM`，未误入单色 X 单调追踪器 |
| OCR 失败降级行为 | **NOT EVALUATED** | 本次 6/6 OCR 均成功，未触发失败路径；源码 `pipeline.py:1485-1501` 有 `ocr_status=FAILED` 处置，但本轮无实证 |

---

## 5. OCR 初始化与推理证据

- 日志中 RapidOCR 输出：
  - `Using engine_name: onnxruntime`
  - `File exists and is valid: …\PP-OCRv6_det_small.onnx`
  - `File exists and is valid: …\ch_ppocr_mobile_v2.0_cls_mobile.onnx`
  - `File exists and is valid: …\PP-OCRv6_rec_small.onnx`
- **没有**出现上一轮的 `TypeError: The value of Det.engine_type must be Enum Type.`
- 各面板 OCR 记录数：auto-01=22、auto-02=38、auto-03=7、auto-04=25、auto-05=23、auto-06=22（合计 137）。
- 典型轴标签证据：
  - auto-01：`Voltage (V)`（置信度 0.99976）、`Current (A`（0.98453）
  - auto-02：`Cycle number`（0.99994）、右轴 `efficiency`（0.97029）、左轴候选 `Capacity`/`(mAh`
  - auto-04：`Cycle number`、`Capacity`、`Coulombic efficiency`
  - auto-05：`Cycle number`、`Capacity (mAh)`、`Coulombic efficiency (%)`

## 6. 面板分割、校准与 TraceSpecification

| panel | bbox（源图像素） | 自动证据 | X/Y 锚点 | 校准 | trace_spec |
|---|---|---|---|---|---|
| auto-01 | [0,0,434,351] | AUTO_RASTER_WHITESPACE_SEGMENTATION, conf 0.7128 | 7 / 5 | X,Y 均 CALIBRATED_NUMERIC（rmse 0.00425 / 0.00223） | NOT_SUPPORTED — NON_MONOTONIC_PATH_REQUIRES_ORDERED_TRACE_ALGORITHM |
| auto-02 | [471,0,982,351] | 同上, conf 0.7129 | 4 / 0 | X CALIBRATED；Y UNRESOLVED | NEEDS_REVIEW — UNIQUE_SINGLE_TRACE_COLOR_NOT_ESTABLISHED |
| auto-03 | [1000,0,1401,351] | 同上, conf 0.7129 | 0 / 0 | 均未校准 | NEEDS_REVIEW — PLOT_REGION_UNRESOLVED |
| auto-04 | [0,356,484,677] | 同上, conf 0.7174 | 6 / 0 | X CALIBRATED；Y UNRESOLVED | NEEDS_REVIEW — UNIQUE_SINGLE_TRACE_COLOR_NOT_ESTABLISHED |
| auto-05 | [501,356,950,677] | 同上, conf 0.7174 | 5 / 0 | X CALIBRATED；Y UNRESOLVED | NEEDS_REVIEW — UNIQUE_SINGLE_TRACE_COLOR_NOT_ESTABLISHED |
| auto-06 | [974,356,1401,677] | 同上, conf 0.6815 | 0 / 0 | 均未校准 | NEEDS_REVIEW — PLOT_REGION_UNRESOLVED |

**分割局限（Agent 视觉观察，非 Skill 语义输出）**：auto-01 裁剪含子图 a 并带入子图 d 的标签；auto-02 含子图 b 并带入右侧 c/f 标签。几何分割不等于科学内容识别；6 个区域与 a–f 并非严格一一对应。所有面板 `automation_status = NOT_READY`，无 `FULLY_AUTOMATIC`。

颜色检测实际运行的面板：auto-02（纯度 0.356）、auto-04（0.386）、auto-05（0.568），均因 `MULTIPLE_CHROMATIC_FAMILIES` 被拒绝；auto-01 因 `NON_MONOTONIC_CURVE` 未运行颜色检测（这是正确的安全拒绝）；auto-03/06 无绘图区故为 null。

## 7. 实际数据、CSV 与图形产物

- series：6 条（每面板 1 条占位），**points_count 全部为 0**。
- `exports\digitized_points\dataset.csv`：**0 数据行**（仅表头）。
- `exports\digitized_points\series_metadata.jsonl`：41,041 bytes（6 条元数据，含 OCR/锚点/trace spec/QC）；`warnings.jsonl`：3,276 bytes。
- 导出警告计数：`QC_PROVISIONAL_UNCALIBRATED` 6、`NOT_REVIEWED_ACCEPTED` 6、`SUBJECT_LINK_UNASSIGNED` 6、`CONDITIONS_NOT_LINKED` 6、`CANONICAL_POINTS_FILE_MISSING` 6、`DUAL_AXIS_UNASSIGNED` 5。
- **无** `*_reconstructed.png`、**无** `*_overlay.png`（`reconstruction.py` 已实现且被 pipeline 调用，但只对有点的 series 生成；本轮无点）。
- **有** pipeline 正式比较图：`E:\Zinc_batters_datas\Figure_digitization_p1_ocrfix_test_outputs_20261122\papers\root-paper\comparisons\ALL_PANELS_COMPARISON.png`（6 行，中列明确为 `NO AUTOMATIC DATA / NO PLOT`，右列给出各面板 trace spec 原因）。

## 8. 与上一轮（PR #17）失败报告逐项比较

| 项目 | PR #17（727cb82） | PR #18（33f0454） |
|---|---|---|
| OCR 引擎 | 初始化 TypeError，整篇 FAILED_PERMANENT | 成功初始化并推理，137 条记录 |
| job state | FAILED_PERMANENT | NEEDS_REVIEW（failed=0） |
| validate | INVALID（5 个 canonical JSON 缺失） | OK |
| 自动面板 | 仅 1 个裁剪证据，无 panel_layout.json | 6 个面板 + panel_layout.json + 6 张裁剪 |
| OCR 记录 | 0 | 137 |
| 轴标签 / 锚点 | 无 | 4/6 面板有标签；X 锚点 22、Y 锚点 5 |
| 两轴校准 | 无 | 1 个面板（auto-01）完成 |
| TraceSpecification | 未产生 | 6 个均已产生状态（1 NOT_SUPPORTED、5 NEEDS_REVIEW），但无 READY |
| 数据点 / CSV 行 | 0 / 0 | 0 / 0（未改善） |
| 重绘 / overlay | 无 | 无（未改善） |
| 比较图 | Agent 诊断图 | **pipeline 正式输出** |

结论：PR #18 **修复了 OCR 兼容性阻塞**，使真实流程首次完整运行到分类、轴识别、校准与 trace spec 阶段；但**没有使自动数据提取从 0 变为正数**。

## 9. 尚存问题与科学能力边界

1. **无面板达到 Phase 1 提取条件**：auto-01 是 CV（非单调，正确拒绝）；auto-02/04/05 是双 Y 轴、多色系列且 Y 轴未校准；auto-03/06 无可靠绘图区。因此 0 点不是 OCR 阻塞，而是“没有适用子图 + trace spec 未 READY”。
2. **Y 轴刻度 OCR 不足**：仅 auto-01 得到 Y 锚点；双 Y 轴面板只识别到碎片标签（`g`、`efficiency`），未建立 5 个以上数值 tick。
3. **多色系列阻断**：颜色检测在 3 个面板返回 `MULTIPLE_CHROMATIC_FAMILIES`；当前不支持多色/同色多分支分离，保守拒绝正确。
4. **几何分割有渗出入**：auto-01 含 d 标签、auto-02 含 c/f 标签；分割未被评价为科学内容识别。
5. **所有 automation_status = NOT_READY**：没有 `FULLY_AUTOMATIC` 的 trace spec，因此无自动提取、无重绘、无 overlay。
6. **科学精度未验证**：没有独立人工数值基准，不宣称 RMSE/MAE/准确率通过。校准 RMSE 只是锚点线性拟合残差，不是曲线点误差。

**核心验收条件（零人工标注 + 双轴校准 + 点>0 + CSV 非空 + 独立重绘 + overlay）整体未满足：Phase 1 在真实图片上仍不能判定通过。** 但本次与上一轮有实质区别：阻塞已从“引擎崩溃”前移到“算法能力边界（TraceSpecification 未 READY）”。

---

## 10. 交付文件

- `REPORT.md`、`summary.json`、`panel_inventory.csv`、`digitization_summary.csv`、`qc_summary.csv`
- `logs/{scan,run,validate,export,analyze_results,summaries}.log` 及分析脚本
- `exports/digitized_points/{dataset.csv,export_manifest.json,series_metadata.jsonl,warnings.jsonl}`
- `papers/root-paper/{panel_layout.json,digitization.json,paper_bundle.json,paper_manifest.json,figure_inventory.json}`
- `papers/root-paper/evidence/P7_05_auto-01..06.png`
- `papers/root-paper/comparisons/ALL_PANELS_COMPARISON.png`（pipeline 正式输出）
- 输入夹具：`test_inputs/single_figure_P7_05/`（新 worktree 内）

最终完整性：新 worktree HEAD 未变、tracked diff 为空；原项目、PR16 worktree、PR17 worktree 状态未变；原始图片 SHA256 前后相同；Skill 与 TASK_PLAN 哈希未变；未修改任何源码/配置/测试/Skill/STATUS/TASK_PLAN/上游数据；未提交、推送、合并或发布。
