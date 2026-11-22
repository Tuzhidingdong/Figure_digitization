# Skill 真实预处理数据测试报告 — 10.1002_adfm.75805

- 执行日期：2026-11-22
- Active Project Root：`E:\Zinc_batters_datas\Figure_digitization_pr16_test`
- 项目版本（worktree HEAD）：`4ca762e40c04045685db15c75838ade145589031`（与预期一致）
- Python：worktree 隔离 `.venv`，3.13.9，依赖 pytest/ruff/Pillow/numpy/psutil/PyYAML/scientific-figure-data 0.1.0 均可用
- Skill：从原项目原样复制 25 个文件到 worktree `.agents\skills\scientific-figure-data\`，全部 SHA256 一致；harness 已从 worktree 根目录成功加载并报告 Base directory 为该目录
- 输入（只读）：`E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805`
- 运行策略：`sfd scan` + 一次 `sfd run --workers 1`，未启用 OCR，零 LLM token，无 GPU；未访问 PDF/SI/网络

本次是**真实数据处理测试**，不是 pytest，也不是手工模拟。自动流程与人工辅助流程严格分开记录。

---

## A. 测试范围

| 指标 | 数量 | 依据 |
|---|---|---|
| 输入目录文件总数 | 70 | `inventory.csv` |
| 图像文件 | 34（29 PNG、5 JPEG） | `inventory.csv` / `inventory_summary.md` |
| 被 pipeline 识别并处理的 figure | 6（全部 MAIN，`doc_type=MAIN`） | `run_auto/out/papers/root-paper/figure_inventory.json` |
| pipeline 面板 | 6（每张图 1 个整图回退面板） | `panel_layout.json` |
| 视觉可判为曲线/含曲线面板的图像 | 6 张 MAIN 中有 4 张含曲线面板；17 张 SI 图像含曲线但无唯一 figure_id 映射 | `classification_results.csv` |
| 非图表 / 显微 / 结构 / 示意 / 无效 | MAIN 2 张（P3_01 混合显微结构、P8_06 错误细条）；SI 13 张明确非曲线 | `classification_results.csv` |
| 无法判断 | 0（对 34 张均给出人工视觉类别，但其中 17 张 SI 仅为“有曲线但无映射”） | 同上 |
| 重复文件哈希组 | 8 组（均为 extracted_tables 与 supplementary/tables 的重复 CSV/MD） | `inventory_summary.md` |
| 自动提取数据点 | **0** | 6 条 series 全部 `points_count=0` |
| 人工辅助提取数据点 | **25**（1 个面板，Figure 5a） | `data/Figure5_panel_a_4th_cycle_manual.csv` |

---

## B. Skill 实际能力

### 1. 图表识别（PR #16 行为）
自动流程对 6 张 MAIN 图全部给出 `UNCLASSIFIED / NEEDS_REVIEW`，**没有任何一张被误判为 CV**。这是 PR #16 修复的直接证据：旧版本曾把 `MAIN_FIG_P5_03`（SEM）和 `MAIN_FIG_P8_06`（正文细条）误判为 CV（`potential` 泛词）；新版本已移除泛词规则与正文文本上下文。

- `MAIN_FIG_P3_01`：schematic + SEM/TEM/HRTEM + EDX → UNCLASSIFIED（正确）
- `MAIN_FIG_P4_02`：CE 循环曲线 + 光学照片 + 柱状对比 → UNCLASSIFIED（整图层面正确，但未识别子面板）
- `MAIN_FIG_P5_03`：SEM 为主，含 LSV/Tafel/Nyquist 子面板 → UNCLASSIFIED（正确，未误判 CV）
- `MAIN_FIG_P7_04`：LSV/Nyquist/DRT/PDOS 多面板 → UNCLASSIFIED（保守，未误判）
- `MAIN_FIG_P7_05`：CV/倍率/循环多面板 → UNCLASSIFIED（保守）
- `MAIN_FIG_P8_06`：1549×89 页眉正文细条 → UNCLASSIFIED（正确拒绝）

### 2. 面板定位
Skill 未做自动多面板分割：6 个面板全部是 `SINGLE_PANEL_FALLBACK` / `WHOLE_FIGURE_NOT_SEGMENTED`，`bbox=null`。Figure 2/4/5 内部明显有 a–f 子面板，均未拆分。人工辅助案例中由人工提供 `plot_box=[83,45,421,296]`，引擎接受并记录为人工几何，不冒充自动识别。

### 3. 绘图区定位（自动流程实际结果）
| figure | plot_detection | 原因/候选 |
|---|---|---|
| P3_01 | NEEDS_REVIEW | `NO_RECTANGULAR_FRAME_PASSED_SIDE_COVERAGE`（h=4,v=3） |
| P4_02 | NEEDS_REVIEW | `NO_UNAMBIGUOUS_RECTANGULAR_FRAME`（h=13,v=0） |
| P5_03 | NEEDS_REVIEW | `NO_RECTANGULAR_FRAME_PASSED_SIDE_COVERAGE`（h=2,v=2） |
| P7_04 | NEEDS_REVIEW | `MULTIPLE_SIMILAR_PLOT_FRAME_CANDIDATES`（两个近似框，得分 0.7174 / 0.7135） |
| P7_05 | PROVISIONAL_PLOT_BOX | [83,358,891,608]，score 0.6984，provisional |
| P8_06 | NEEDS_REVIEW | `NO_UNAMBIGUOUS_RECTANGULAR_FRAME`（h=0,v=0） |

未发现图注/页眉被自动误当绘图区；但除 P7_05 外均未得到可用框。

### 4. 坐标轴识别与数值校准
- 自动流程：6/6 为 `NUMERIC_AXIS_CALIBRATION_UNRESOLVED`，锚点 0；`color_detection=null`；`calibration_errors` 为“至少两个数值锚点”。原因：轴刻度文字栅格化在图内、无 OCR、原生 PDF 文本在图区域内无数值对象、关联上游裁图时 `crop_mapping=None`。
- 人工辅助案例（Figure 5a，PR16 代码）：X 锚点 83.5→0.0 V、420.5→1.8 V；Y 锚点 65.5→3.0 A/g、274.5→−2.0 A/g。结果 `BOTH_AXES_NUMERICALLY_CALIBRATED`，X RMSE≈1.57e−16，Y RMSE=0.0，`x_unit=V`、`y_unit=A g-1` 正确传递。
- 关键点：两轴数值校准成功仍为 `PROVISIONAL_UNCALIBRATED`、`NEEDS_REVIEW`、`scientific_acceptance=NOT_ASSESSED_WITHOUT_ANNOTATED_REAL_PAPER_BENCHMARK`——**未被错误提升为科学验收通过**。

### 5. 实际数据提取
- 自动流程：0 点；全部 `NO_SUPPORTED_TRACE_SPECIFICATION`。
- 人工辅助：Figure 5a 红色实线（4th cycle 阳极支路）25 点，`EXPLICIT_ORDERED_PIXEL_POLYLINE` / `EXTRACTED_PROVISIONAL`，点序保持（`pixel_x` 严格递增、Y 值有 4 次方向变化，未按 X 排序或平滑）。
- 输出文件：`data/Figure5_panel_a_4th_cycle_manual.csv`，每行含 `point_index`、`pixel_x/pixel_y`、`x_value/y_value`、`series_id`；叠加证据图 `images/Figure5_panel_a_manual_overlay.png`（图中文字已标注 MANUAL）。

### 6. 可追溯性
自动与人工结果均保留：原图上链路径与 SHA256、figure_id/page/doc_type、`source_asset_status=VERIFIED`、paper input fingerprint、`extraction_channel`、算法版本、校准锚点与 RMSE、QC 分量与警告、canonical bundle 内容哈希。人工辅助输入保存在 `manual_inputs/`，含依据说明 `MANUAL_ANNOTATION.json`。

---

## C. 代表性案例（自动 / 部分成功 / 失败）

| 案例 | 类别 | 证据文件 | plot_box / 锚点 | 数据文件 | QC |
|---|---|---|---|---|---|
| Figure 5a 人工辅助 | 成功（人工输入） | `images/contact_MAIN.png`、`images/Figure5_panel_a_manual_overlay.png` | 人工 [83,45,421,296]；X 83.5→0.0、420.5→1.8 V；Y 65.5→3.0、274.5→−2.0 A/g | `data/..._manual.csv`（25 点） | PROVISIONAL_UNCALIBRATED / NEEDS_REVIEW；BOTH_AXES_NUMERICALLY_CALIBRATED |
| Figure 5 整图（自动） | 部分成功 | `run_auto/out/papers/root-paper/evidence/MAIN_FIG_P7_05_1.png` | 自动找到 PROVISIONAL_PLOT_BOX，但无锚点 | 无 | NEEDS_REVIEW，0 点 |
| Figure 4 整图（自动） | 失败（多候选） | 同上目录 P7_04 PNG | 两个相似框，置信度接近，拒绝 | 无 | NEEDS_REVIEW，0 点 |
| Figure 2 整图（自动） | 失败（多面板+照片） | P4_02 PNG | 13 横线 0 竖线，无框 | 无 | NEEDS_REVIEW，0 点 |
| P8_06 | 失败（上游资产错误） | `images/contact_MAIN.png` 右下 | 0 横线 0 竖线 | 无 | NEEDS_REVIEW；1549×89 正文细条 |

人工 vs 自动的边界：除 Figure 5a 的 plot_box、4 个轴锚点和 25 个像素点由人工提供外，其余（分类、绘图区自动检测、校准计算、点映射、QC、CSV/JSON 生成、SQLite 索引）均由 Skill 引擎自动完成。人工输入绝不作为自动识别成功或科学精度证据。

---

## D. 失败原因分解

| 失败类型 | 具体原因 | 归属 |
|---|---|---|
| 自动 0 点 | 轴刻度栅格化在嵌入图像内；原生 PDF 文本在 figure 区域无数值对象；未启用 OCR；关联上游裁图时 `crop_mapping=None`，原生锚点/矢量通道不启用 | 输入资产特性 + P0 能力边界（非单纯图像质量差） |
| 多面板未拆分 | 上游未提供 panels；引擎只有整图回退，无自动面板分割 | Skill 能力缺失（规划中） |
| Figure 4 绘图区歧义 | 多子图导致两个近似分框，保守拒绝 | 识别算法能力不足（合理保守） |
| Figure 2 / P3_01 / P5_03 无框 | 堆叠子图、SEM 形貌、混合内容本就不存在单一矩形绘图区 | 图像内容 + 算法能力 |
| P8_06 无法处理 | 上游错误裁剪：32pt 高的页眉/正文细条，caption 为正文段落 | 上游资产问题（非 Skill） |
| SI 17 张曲线相关图像未进入流程 | 上游未提供与论文 Figure 编号的唯一映射；Skill 明确不猜测 SI 页组合成 figure identity | 输入缺少必要信息 + 设计约束 |
| 柱状图/散点/误差棒 | P1 未实现生产支持 | Skill 能力缺失 |

---

## E. 最终评价（附证据）

| 能力 | 评价 | 证据 |
|---|---|---|
| 图表识别 | PARTIAL | 6/6 MAIN 被识别为 figure 并给出分类；但全部为整图级 UNCLASSIFIED，未识别子面板类型；SI 28 张未被自动分类 |
| CV 误分类防护 | PASS | PR16 新代码在这批真实数据上把旧版误判的 SEM（P5_03）和正文细条（P8_06）全部改为 UNCLASSIFIED/NEEDS_REVIEW；6/6 无 CV 误报 |
| 面板定位 | FAIL | 6/6 为 `WHOLE_FIGURE_NOT_SEGMENTED`，多面板 figure 未拆分 |
| 绘图区定位 | PARTIAL | 5/6 NEEDS_REVIEW，1/6 PROVISIONAL_PLOT_BOX；人工 plot_box 可用且被正确记录 |
| 坐标轴识别 | PARTIAL | 人工指定时轴标签/单位正确传递；自动锚点 0/6 |
| 数值坐标校准 | PARTIAL | 自动 0/6；人工辅助 1/1 成功，两轴 RMSE 有限，calibration_state 正确 |
| 曲线数据提取 | PARTIAL | 自动 0 点；人工有序路径 1 条 25 点成功，点序与坐标映射正确 |
| 数据点可追溯性 | PASS | CSV 含点序/像素/数值；JSON 含图像 SHA、figure/panel、算法版本、锚点、QC、bundle 哈希 |
| QC 可靠性 | PASS | 全部自动结果保留 PROVISIONAL_UNCALIBRATED/NEEDS_REVIEW/未评估科学验收；人工成功案例同样未被提升；警告按维度记录 |
| 端到端可用性 | PARTIAL | 正式 scan/run/validate/export 全流程可执行且 `validate` OK；但真实曲线数字化目前依赖人工 plot_box + 锚点 + 有序点路径 |

**没有独立人工标注的真实数值基准，本报告不宣称任何 RMSE/MAE/准确率或科学精度通过。** 上述 RMSE 仅为线性锚点拟合的残差，不是曲线点误差。

---

## 需要进入下一轮开发的关键问题

1. 多面板自动分割（当前 0/6）。
2. 从栅格图读取轴刻度：OCR 可选通道未启用且未安装；关联上游裁图时 `crop_mapping=None` 使原生文本/矢量锚点通道关闭。
3. 多绘图区歧义的消解策略（Figure 4 两候选）。
4. SI 图像与 Figure 编号的关联信息缺失，导致 17 张曲线相关 SI 图无法进入正式流程。
5. 柱状/散点/误差棒等 P1 图表类型未实现生产支持。
6. 错误上游资产（P8_06）的上游侧检测/隔离反馈。

---

## 交付文件清单

- `REPORT.md`（本文件）
- `inventory.csv`、`inventory_summary.md`
- `classification_results.csv`（34 张图像，含 pipeline 分类 + 人工视觉类别与证据）
- `digitization_summary.csv`（6 自动 + 1 人工辅助）、`qc_summary.csv`（同）
- `summary.json`、`summary_auto.json`、`manual_inputs/manual_result.json`
- `logs/`：`commands.md`、`inventory.log`、`contact_sheets.log`、`auto_scan.log`、`auto_run.log`、`analyze_auto.log`、`auto_validate.log`、`auto_export.log`、`classification.log`、`manual_scan.log`、`manual_run.log`、`finalize.log` 及 5 个只读分析脚本
- `images/`：`contact_MAIN.png`、`contact_SI_1.png`、`contact_SI_2.png`、`Figure5_panel_a_manual_overlay.png`
- `data/`：`Figure5_panel_a_4th_cycle_manual.csv`、`auto_export/`（0 行点数据 + manifest）
- `manual_inputs/`：`input/`（人工标注 override 与最小输入包）、`MANUAL_ANNOTATION.json`

结论：本次**确实使用 Skill 在真实预处理数据上完成了端到端处理**（自动流程 + 一个人工辅助提取案例），不是 pytest，也不是手工模拟。自动流程当前能正确识别与保守拒绝，但还不能在无人工输入的情况下产出曲线数值。
