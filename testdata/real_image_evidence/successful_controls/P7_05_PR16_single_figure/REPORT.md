# 单张真实多面板图片数字化能力测试报告
## MAIN_MAIN_FIG_P7_05.png

- 日期：2026-11-22
- Active Project Root：`E:\Zinc_batters_datas\Figure_digitization_pr16_test`
- worktree HEAD：`4ca762e40c04045685db15c75838ade145589031`（未变）
- Skill：25 文件，SHA256 与原项目一致，已从 worktree 根目录正式加载
- 目标图片：`E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805\extracted_figures\MAIN\MAIN_MAIN_FIG_P7_05.png`
- 图片：PNG / RGB / 1401×677 / 510,721 bytes；SHA256 测试前后均为 `3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de`，可正常打开
- 本轮只提交这张图（整图 + 由其派生的 6 个子图裁剪），未扫描整个论文目录，未重跑 pytest
- 自动运行：`sfd scan` + 一次 `sfd run --workers 1`，无 `digitization_overrides.json`，无 OCR，零 LLM token

**重要边界**：Skill 当前没有“自动子面板分割”功能。为回答“每个子图”的问题，Agent 仅做了**视觉裁剪准备**（6 个 crop box，记录在 `panel_inventory.csv` 与 `original/source_image_info.json`），**没有**向 Skill 提供任何 plot_box、轴锚点、曲线点、轴标签或技术名称。所有分类结果均来自 worktree 中的 Skill 代码/API；图片内容描述是 Agent 视觉参考，明确标注为 **AGENT_VISUAL_REFERENCE**，不是 Skill 识别结果。

---

## 1. 子图识别

图片共 **6 个子图（a–f）**。Skill 对所有 7 个输入对象（整图 + 6 子图）均给出 `UNCLASSIFIED / NEEDS_REVIEW`，**没有任何一个被识别出具体图表类型或科学内容**；也没有把 SEM/示意图误判为曲线。

| 子图 | 裁剪尺寸 | Agent 视觉内容参考（非 Skill 输出） | Skill 分类 | Skill 置信度 | 绘图区自动检测 | Skill 是否识别具体内容 |
|---|---|---|---|---|---|---|
| a | 424×310 | 循环伏安（CV）曲线；两条样品曲线，虚线 1st / 实线 4th；轴 Voltage (V) / Current (A g-1) | UNCLASSIFIED / NEEDS_REVIEW | null | PROVISIONAL_PLOT_BOX [65,33,402,284] | 否 |
| b | 480×310 | 倍率性能：容量 vs 循环数，右轴库仑效率；两个散点系列 | UNCLASSIFIED / NEEDS_REVIEW | null | PROVISIONAL_PLOT_BOX [112,36,450,286] | 否 |
| c | 470×306 | 电池结构示意图，无数值坐标轴 | UNCLASSIFIED / NEEDS_REVIEW | null | NEEDS_REVIEW / NO_UNAMBIGUOUS_RECTANGULAR_FRAME | 否 |
| d | 427×352 | 循环容量 vs 循环数，右轴 CE；两条系列 | UNCLASSIFIED / NEEDS_REVIEW | null | PROVISIONAL_PLOT_BOX [68,36,406,286] | 否 |
| e | 480×352 | 循环容量 vs 循环数，右轴 CE，含照片插图 | UNCLASSIFIED / NEEDS_REVIEW | null | PROVISIONAL_PLOT_BOX [112,36,448,286] | 否 |
| f | 470×352 | 能量密度 vs 面容量散点对比，带 Ref 标签 | UNCLASSIFIED / NEEDS_REVIEW | null | PROVISIONAL_PLOT_BOX [107,36,444,286] | 否 |
| WHOLE_IMAGE | 1401×677 | 六子图合成整图 | UNCLASSIFIED / NEEDS_REVIEW | null | PROVISIONAL_PLOT_BOX [83,358,891,608]（只覆盖局部） | 否 |

结论：Skill 能识别“这是一个 figure 输入”并保守拒绝分类，但**不能识别子图数量、子图内容、图表类型或轴含义**。子图枚举依赖 Agent 视觉裁剪。

---

## 2. 可提取性判断

`extractability_assessment.csv` 给出逐项判断与理由：

| 分类 | 数量 | 对象 | 理由摘要 |
|---|---|---|---|
| EXTRACTABLE | **0** | — | 自动流程没有任何面板满足“已识别类型 + 有轴锚点 + 有可追踪曲线”的条件 |
| CONDITIONALLY_EXTRACTABLE | 4 | a、b、d、e | Agent 视觉上是有数值轴的曲线/散点图，Skill 也找到了绘图框；但锚点 0、颜色族 null、无自动曲线路径，受限于无 OCR / 原生锚点通道关闭 / 无多系列自动分离 |
| NOT_SUPPORTED | 3 | c、f、WHOLE_IMAGE | c 为无坐标示意图；f 为散点对比（P1 未生产支持）；整图为合成图，单框只覆盖局部 |
| NEEDS_REVIEW | 0（分类层面） | — | 但所有 7 条 series 的 `review_state = NEEDS_REVIEW`，QC 状态均为 `PROVISIONAL_UNCALIBRATED` |

判断合理性：把“未成功提取”正确区分为**能力/输入缺失**（锚点、OCR、多系列分割、P1 散点支持）与**图像本身不适合**（示意图、合成整图），没有一概归咎于图片质量。

---

## 3. 数字化实际结果（自动）

| 指标 | 结果 |
|---|---|
| 提交 figure 数 | 7（整图 + 6 子图） |
| Skill 面板数 | 7，全部 `WHOLE_FIGURE_NOT_SEGMENTED` |
| 自动找到绘图框 | 6 / 7（子图 a,b,b,d,e,f；c 未找到） |
| 轴锚点 | **0**（全部 7 个对象） |
| 校准状态 | 全部 `NUMERIC_AXIS_CALIBRATION_UNRESOLVED` |
| 含数据点的 series | **0 / 7** |
| 数据点总数 | **0** |
| 提取失败原因 | 全部 `NO_SUPPORTED_TRACE_SPECIFICATION` |
| `sfd validate` | `OK`（5 个 JSON，0 错误） |
| 资源 | 0.749 s 引擎耗时，峰值 RSS 70,590,464 B，LLM token 0 |

失败位置：**坐标轴锚点阶段**。Skill 能找到图框，但无法从栅格化刻度读数（未启用 OCR，关联上游裁图时 `crop_mapping=None` 使原生文本锚点通道关闭），因此既不能校准也不能追踪曲线；`color_detection=null`。这是算法/输入通道缺位，不是图像完全不可数字化。

`data/auto_export/` 中导出 manifest 与 0 行点数据；**没有生成任何虚构数据文件**。`data/` 目录本身存在但无自动 series CSV，原因已记录于此。

---

## 4. 重绘效果与总览图

由于自动提取点数为 0，**无法用自动提取数据重绘任何子图**，也没有生成任何伪造的“重绘图”。

- **总览图（最重要交付）**：`comparisons/ALL_PANELS_COMPARISON.png`
  - 7 行（整图 + a–f），左列为原始子图，中列明确写 `NO AUTOMATIC DATA POINTS / NO PLOT DRAWN (no fabricated data)` 并给出原因，右列为状态与 QC。
  - 所有子图均出现，包括无法提取的 c、f。
- 每子图对比图：`comparisons/panel_a_comparison.png` … `panel_f_comparison.png`、`whole_image_comparison.png`（左原图，中“无数据可重绘”）。
- 自动绘图框证据：`evidence/plot_regions/<figure>_auto_plotbox.png`（蓝框为自动检测框）。
- 无校准证据：`evidence/calibration/no_anchor_evidence.json`（明确说明为何没有校准文件）。

**可选人工辅助诊断（与自动结果严格隔离）**：`manual_assisted_diagnostic/`
- 使用上一轮已记录的**人工** plot_box、X/Y 锚点与 25 点有序路径（来自同一张图），在 worktree 代码中重新生成 25 点 CSV。
- 生成 `reconstructed/panel_a_reconstructed.png`（由 `x_value/y_value` 真实绘制，非原图背景）、`comparisons/panel_a_comparison_manual_assisted.png`（原图 / 数据重绘 / 像素叠加）。
- 视觉上重绘曲线保留了原图红色 4th-cycle 阳极支路的双峰位置、谷值与末端走势；但这**只是人工输入下的流程可视化**，不是自动提取成功，不计入任何自动统计，也不构成精度验证。

---

## 5. 自动化程度

| 环节 | 执行者 |
|---|---|
| 图片读取、SHA256、尺寸、格式检查 | 脚本（只读） |
| 子图枚举/裁剪 | **Agent 视觉准备**（仅生成 crop，不提供任何标注参数） |
| 图表分类、绘图区检测、校准尝试、点提取、QC、CSV/JSON/SQLite 生成 | **Skill 自动**（worktree 正式代码） |
| 人工介入（首轮自动测试） | **无**：没有 plot_box、锚点、曲线点、轴标签或参数调整 |
| 未能完成 | 子图内容识别、多面板分割、轴锚点读取、数值校准、曲线/多系列提取、自动重绘 |
| 可选人工辅助诊断 | 独立子目录，明确不计入自动成功数 |

---

## 6. 能力评价

| 能力 | 评价 | 证据 |
|---|---|---|
| 子图数量识别 | **FAIL** | Skill 未分割；6 个子图由 Agent 视觉裁剪得到（`panel_inventory.csv`） |
| 子图内容识别 | **FAIL** | 7/7 分类为 UNCLASSIFIED，confidence=null（`classification_results.csv`） |
| 图表类型分类 | **PARTIAL** | 保守拒绝误判（无 CV 误报），但未给出任何具体类型；证据同上 |
| 可提取性判断 | **PARTIAL** | `extractability_assessment.csv` 给出 4 条件可提取 / 3 不支持及具体原因，但内容依据部分来自 Agent 视觉参考 |
| 绘图区定位 | **PARTIAL** | 6/7 得到 PROVISIONAL_PLOT_BOX（Evidence overlay），但框未与真实子图边界做数值比对；c 失败 |
| 坐标轴识别 | **FAIL** | 轴锚点 0/7；轴名称/单位未被自动输出 |
| 自动坐标校准 | **FAIL** | 全部 `NUMERIC_AXIS_CALIBRATION_UNRESOLVED` |
| 自动数据提取 | **FAIL** | 0 series 有数据、0 点；`NO_SUPPORTED_TRACE_SPECIFICATION` |
| 多系列区分 | **FAIL** | 无自动系列/曲线分离；`color_detection=null` |
| 提取数据重绘 | **FAIL**（自动） | 0 点，无法重绘；可选人工辅助重绘在隔离目录，不计入 |
| 原图与重绘一致性 | **FAIL**（自动） | 无自动重绘图可比对；总览图已如实标注 |
| 端到端可用性 | **PARTIAL** | scan/run/validate/export 全流程可执行且 validate OK；但真实曲线数字化仍需人工输入 |

---

## 7. 对九个问题的直接回答

1. **子图识别**：6 个子图；Skill 均未识别具体内容，Agent 视觉参考见第 1 节表格。
2. **可提取性**：EXTRACTABLE 0、CONDITIONALLY_EXTRACTABLE 4、NOT_SUPPORTED 3、NEEDS_REVIEW（分类层面）0；判断见第 2 节，区分了能力缺失与图像不适合。
3. **数字化**：自动成功 0 个子图、0 条系列、0 个点；失败在轴锚点/校准阶段（第 3 节）。
4. **重绘效果**：自动无数据可重绘；总览图 `ALL_PANELS_COMPARISON.png` 已给出每个子图的原图 + “无数据”状态。可选人工辅助诊断显示 25 点重绘与红色阳极支路视觉一致，但不是自动结果。
5. **自动化程度**：Skill 自动完成分类/图框/QC/导出；Agent 仅调用 Skill 并做视觉裁剪；首轮自动无任何人工标注；未完成的见上表。
6. **能力评价**：见第 6 节表。
7. **成功/失败文件**：无成功系列 CSV；失败证据在 `qc_summary.csv`、`digitization_summary.csv`、`evidence/`、`logs/`。
8. **关键差距**：无自动子面板分割、无 OCR/轴刻度读取、无自动多系列与有序路径提取、散点/柱状（P1）未生产支持、SI 映射缺失（本图不涉及）。
9. **是否真正使用 Skill**：是——`sfd scan` / `run` / `validate` / `export` 在 worktree 3.13.9 环境对真实图片执行一次；不是 pytest，不是手工模拟；人工辅助仅存在于隔离诊断目录。

**没有独立人工标注的真实数值基准，本报告不宣称科学精度、RMSE/MAE 或准确率通过。** 唯一的人工辅助诊断也不作为精度证据。

---

## 8. 交付文件

- `REPORT.md`、`summary.json`
- `panel_inventory.csv`、`extractability_assessment.csv`、`classification_results.csv`、`digitization_summary.csv`、`qc_summary.csv`
- `original/source_image.png`、`original/source_image_info.json`
- `panels/panel_a…panel_f/source_crop.png`、`panels/panel_crops_check.png`
- `comparisons/ALL_PANELS_COMPARISON.png`（**核心交付**）、`comparisons/panel_*_comparison.png`
- `evidence/plot_regions/*.png`、`evidence/calibration/no_anchor_evidence.json`
- `logs/`：scan.log、run.log、validate.log、export.log、analyze_auto.log、comparison.log、manual_diagnostic.log 及分析脚本
- `manual_assisted_diagnostic/`（隔离）：data、reconstructed、comparisons、构建脚本

`data/auto_export/` 含导出 manifest 与 0 行点数据；`data/` 无自动 series CSV，原因见第 3 节。
