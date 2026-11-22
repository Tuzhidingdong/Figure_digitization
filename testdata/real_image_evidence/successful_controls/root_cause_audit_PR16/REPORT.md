# Figure_digitization 自动数字化失败 — 只读源码根因审查报告

日期：2026-11-22
性质：**只读审查**。未修改源码、配置、测试、Skill、TASK_PLAN、STATUS、上游输入或历史测试产物；未运行完整真实流程、未重复 pytest、未安装依赖。

---

## A. 执行版本与完整性

| 项 | 值 |
|---|---|
| worktree | `E:\Zinc_batters_datas\Figure_digitization_pr16_test` |
| worktree HEAD | `4ca762e40c04045685db15c75838ade145589031`（与预期一致） |
| worktree `git status --short` | `?? .agents/`、`?? src/scientific_figure_data.egg-info/`、`?? src/scientific_figure_data/__pycache__/`、`?? test_outputs/`、`?? tests/__pycache__/`（均为既有 untracked） |
| 原项目状态 | `M STATUS.md`、`?? .agents/`、`?? src/scientific_figure_data/__pycache__/`、`?? test_outputs/`（保持原样） |
| Skill 文件数 / SKILL.md SHA256 | 25 / `4340502553aefdab5a59950183443c5f20a8597fe7ad05876d78ab23e935e4b8` |
| TASK_PLAN_v1.4.1.md SHA256 | `25bea25eea38731cbc73aee153e5b0c0eac1a9e09d72aa5161cb02743cc8798c`（已读取全文 1980 行） |
| 审查后复核 | HEAD 未变；`git diff --name-only` 为空；Skill / TASK_PLAN 哈希未变；新增内容仅本报告 |

---

## B. 三个关键状态的源码根因

### B1. `NO_SUPPORTED_TRACE_SPECIFICATION`

**唯一点**：`src/scientific_figure_data/pipeline.py:938-949`，`_extract_panel()`（函数定义于 543 行）末尾的 `else` 分支：

```python
938: else:
939:     record.metadata = {
940:         "reason": "NO_SUPPORTED_TRACE_SPECIFICATION",
941:         "note": "Provide ordered pixel_points for non-monotonic paths or explicit color and calibrations for monotonic raster traces.",
...
949:     }
```

全仓库只有这一处赋值；没有第二个定义或消费该状态的分支（tests / test_outputs 中的出现均为断言或产物）。

**产生该状态的完整条件链**（同一函数内）：

1. `_series_overrides()`（398-404）只读取 `digitization_overrides.json`。无 override 时，`_extract_panel` 在 554-559 行合成**唯一一条空定义**：只有 `series_id/label/technique/domain`，**没有** `plot_box`、`x_axis_anchors`、`y_axis_anchors`、`pixel_points`、`color_rgb`。
2. 785-786 行：`pixel_points = definition.get("pixel_points")` → `None`；`color_rgb = definition.get("color_rgb")` → `None`。
3. 664-673 行：`plot_box` 来自 override 或 `detect_plot_box()`；真实测试中确实找到了 PROVISIONAL_PLOT_BOX（见 B3），但 plot box 本身不是 trace specification。
4. 796-889 行：矢量通道需要 `plot_bbox_pdf`，而 `_plot_box_to_pdf()`（484-501）在 `crop_mapping=None` 时返回 `None`，故 `vector_requested=False`，整段跳过。
5. 788-789 行：栅格颜色检测有**排除集**：
   ```python
   family not in {"NON_MONOTONIC", "NON_MONOTONIC_CURVE", "CV", "EIS", "UNCLASSIFIED"}
   ```
   真实数据中 `family = UNCLASSIFIED`（chart_classifier 默认，111-117），因此 `detect_single_trace_color()` **根本没被调用**，`color_detection` 保持 `None`，`color_rgb` 仍为 `None`。
6. 890 行 `pixel_points` 不存在 → 跳过；914 行 `image_path and color_rgb and family not in {...}` 为假 → 跳过；最终落入 938 行 else。

**trace specification 生命周期（scan → run → validate → export）**：

- `sfd scan`（cli.py:37 / 128）只做发现与 SHA256 快照，**不生成任何曲线描述**。
- `sfd run`（cli.py:40 / 158）→ `scheduler._process_paper_task()`（scheduler.py:39-46）→ `pipeline.process_paper()`（1011）→ 面板循环（1205）→ `_extract_panel()`（1293）。
- `validate` / `export` 只读取已落盘的 JSON/CSV（真实测试 `validate` 返回 OK、export 为 0 行点数据）。
- **结论**：整个正式链路中不存在“自动生成 trace specification”的阶段。能承载它的字段只有 override 里的 `pixel_points` / `color_rgb`，必须由人工提供。
- 已实现但**未被调用以生成 spec** 的模块：`detect_plot_box()`（只产出一个矩形）、`detect_single_trace_color()`（被 family 排除集挡住）、`choose_vector_paths()`（被 crop_mapping 挡住）、`trace_monotonic_color()`（需要人工 color_rgb）。

**根因分类**：**A（自动生成 trace specification 的功能未实现）为主**，叠加 **B**（颜色/矢量/栅格提取算法已存在但被门控条件挡住，无法自行产生 spec）与 **D**（现有提取器仅支持“单色、X 单调”曲线，不支持 CV/EIS 有序路径、多系列、交叉、遮挡）。**不是 C**：这里不存在“已生成但传丢”的 trace 数据——根本没有生成。

证据充分程度：**高**（单一赋值点 + 完整分支链 + 两轮真实数据 13 个对象全部命中该状态）。

---

### B2. `crop_mapping=None`

**数据结构与产生位置**：

- `crop_mapping` **不是持久化模型字段**：全仓库只出现在 `pipeline.py`（486, 488-500, 549, 687, 702-708, 800-814, 842, 1215, 1268-1277, 1297）与 `axis_text.py`（140, 151-153）。`models.py` / `manifest.py` / `storage.py` 中**没有**该字段。它是一个局部变量。
- 默认值：`pipeline.py:1215  crop_mapping = None`，每个面板循环开始即置 None。
- 唯一生成处：`pipeline.py:1268-1277`，位于 **从源 PDF 重新渲染并裁剪**的回退分支（1244-1279）。

**为何在本批数据上必然为 None**：

```
1244: if (saved_crop is None and pdf_path and figure["page"]
1246:     and is_main_pdf_figure
1249:     and _may_use_source_pdf_bbox_fallback(source_figure, panel) ...):
```

- 上游 `media_assets` 通过 `image_path` 关联已裁图（pipeline 183-235 读取 `relative_path`/`sha256`），`image_asset_status=VERIFIED`。
- `_may_use_source_pdf_bbox_fallback()`（306-308）：`return not source_figure.get("image_asset_status") or bool(panel.get("image_path"))`。对已验证关联资产且面板无自身 image_path 的情况返回 **False**，所以**禁止**从 PDF 再裁。于是 1268 行不执行，`crop_mapping` 保持 None。
- 单图独立输入（本轮 P7_05 测试）根本没有 PDF，`pdf_path=None`，同样 None。

**上游是否真的没有映射？——不，上游明确提供了**：
`E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805\evidence_index.json:2821-2835`：

```json
"asset_id": "ASSET_00005",
"relative_path": "extracted_figures/MAIN/MAIN_MAIN_FIG_P7_05.png",
"sha256": "3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de",
"extraction_method": "pymupdf_vector_image_layout_fallback",
"page_number": 7,
"bbox": [53.89, 368.83, 557.89, 612.31],
"figure_id": "MAIN_FIG_P7_05"
```

即存在 PDF 页号 + 页空间 bbox + 提取方法 + 原图 SHA256，足以构造映射。

**解析器是否读取？——没有**：pipeline 对 media_assets 只取 `relative_path`（183）、`sha256`（196-203）并在 234-235 写入 `figure["image_path"]`；全仓库 grep 无任何 `asset.get("bbox")` / `media_bbox` 读取。上游 bbox 被丢弃。

**直接后果**：
- `_plot_box_to_pdf()`（488）返回 None；
- 原生文本轴锚点通道（702-708）与矢量路径通道（800-801）整体关闭；
- 即使图内有原生矢量曲线，也无法被坐标反算到裁图像素。

**根因分类**：**C（输入/数据契约不匹配：上游已有映射但解析器未读取）+ 映射生成逻辑未实现（针对关联资产路径）**。不能归咎于上游缺失。

**恢复映射的最小输入契约**：每个已裁图资产须携带并持久化
`source_pdf_sha256`、`page_number`、`crop_bbox_pdf`（或归一化 bbox）、`bbox_coordinate_space`、`crop_pixel_width/height`、`render_scale`、`page_rotation_degrees`、`extraction_method`，并在 `_inventory()` 写入 Figure/Panel 记录、`process_paper` 恢复为 `crop_mapping` 传入 `_extract_panel`。同时需要“裁图像素 → PDF 页空间 → 原图”的双向变换函数（现仅有 `_plot_box_to_pdf` / `pdf_points_to_crop_pixels` 单向片段）。

证据充分程度：**高**（上游文件逐行 + 解析器只读字段 + 门控条件）。

---

### B3. `color_detection=null`

**出现位置与默认值**：`pipeline.py:787  color_detection = None`；唯一赋值调用在 791 行 `detect_single_trace_color(image_path, plot_box_pixels)`；795 行在依赖缺失时写 `{"status":"UNAVAILABLE",...}`。输出字段写入 840/909/935/944。

**为什么本次是 null——不是“没检测到颜色”，而是“没调用”**：
788-789 行的门控：
```python
if (not color_rgb and image_path and plot_box_pixels
        and family not in {"NON_MONOTONIC", "NON_MONOTONIC_CURVE", "CV", "EIS", "UNCLASSIFIED"}):
```
真实 13 个对象 `family` 全为 `UNCLASSIFIED` → 条件为假 → 函数未执行 → `null`。即使找到了 plot box（P7_05 六子图中 6/7 有 PROVISIONAL_PLOT_BOX），也不会做颜色检测。

**算法实际能力（`plot_region.py:140-201`）**：
- 只找**一个主色族**：饱和像素 `saturation>=45`、`brightness>=55`、数量≥12；`purity>=0.86`、`distance<=52` 才算 `UNIQUE_CHROMATIC_FAMILY`。
- 输出仅 `color_rgb` + `color_tolerance`。
- 不能：分离多颜色系列、同色不同线型、图例关联、交点/遮挡判断、标记形状识别。多色直接返回 `MULTIPLE_CHROMATIC_FAMILIES` / `NEEDS_REVIEW`。

**提取器实际能力（`raster.py:10-107`）**：
- `trace_monotonic_color()`：对**单一指定颜色**逐列取 Y 中位数；要求 ≥8 匹配列、间隙≤3 列；检测同列多条带时直接拒绝 `MULTIPLE_SAME_COLOR_BANDS`；粗线拒绝；`path_constraint = X_MONOTONIC_ONLY`。
- 明确注释：不能用于 CV/EIS/回环/非 X 单值曲线。
- 因此即使颜色检测成功，也只能抽取“单条、单色、X 单调”的曲线；Figure 5a 这种 CV 双分支、多系列曲线必定无法自动处理。

**根因分类**：**B（算法存在但被 family 门控阻断）+ D（提取器能力仅覆盖单色单调曲线）**；多系列/线型/交叉/遮挡属于 **A（未实现）**。不是序列化丢失。

证据充分程度：**高**。

---

## C. 当前自动数字化调用链（真实实现状态）

```
CLI sfd scan  ──►  adapter.discover_papers / create_snapshot
   (cli.py:37,128)      ✅ 已实现并调用：发现、角色、SHA256、输入指纹
        │
CLI sfd run   ──►  scheduler._process_paper_task (scheduler.py:39)
   (cli.py:40,158)      ✅ 已实现并调用：隔离 worker、资源限制、重试
        │
        └──►  pipeline.process_paper (pipeline.py:1011)
                │
                ├─ _inventory (137)          ✅ 读取 evidence_index；⚠️ 丢弃 asset.bbox
                ├─ context_index             ✅ 文本上下文（不读图像文字）
                ├─ native PDF evidence       ✅ inventory（本批 raster 图内无数值文本）
                ├─ _figure_panels (353)      ⚠️ 仅“上游 panels”或“整图回退”；❌ 无自动子面板分割
                │
                └─ 每面板 _extract_panel (543)
                     ├─ _series_overrides(398) ⚠️ 只读人工 override；无 override → 空定义
                     ├─ classify_chart_family(652) ⚠️ 纯字符串规则；❌ 不从图像读轴标签
                     ├─ detect_plot_box(668)   ✅ 单矩形检测（真实数据 6/7 找到）
                     ├─ _plot_box_to_pdf(687)  ❌ crop_mapping=None → 返回 None
                     ├─ extract_native_numeric_axis_anchors(706) ❌ 被 crop_mapping 门控关闭
                     ├─ ocr.run_ocr(1283)      ⚠️ 代码存在；需 --ocr + rapidocr；本批未启用
                     ├─ fit_linear_axis(764/781) ✅ 算法存在；0 锚点 → 报错
                     ├─ detect_single_trace_color(791) ❌ 被 UNCLASSIFIED 排除集挡住
                     ├─ choose_vector_paths(805)  ❌ 被 crop_mapping 门控关闭
                     ├─ pixel_points 分支(890)    ⚠️ 仅接受人工有序点
                     ├─ trace_monotonic_color(915)⚠️ 仅单色 X 单调；需人工 color_rgb
                     └─ else(938)              ✅ 产出 NO_SUPPORTED_TRACE_SPECIFICATION
        │
validate / export                             ✅ 已实现；只序列化 0 点结果与 QC
        │
❌ 独立重绘（reconstructed PNG / 对比图）      —— 仓库中无此模块；本轮对比图由测试脚本生成
❌ 可提取性判断模块                            —— 无函数，只有 NEEDS_REVIEW 状态字段
❌ 图表类型→提取器路由/注册表                  —— 无
```

节点状态图例：✅ 已实现并接入；⚠️ 有代码/数据但条件不满足或只接受人工输入；❌ 未实现或未接入。

---

## D. 冻结 TASK_PLAN v1.4.1 符合度（只读对照）

| 计划要求 | 对应文件/函数 | 实际实现情况 | 是否进入正式 pipeline | 差距 / 真实测试证据 |
|---|---|---|---|---|
| 3.1 上游 adapter / snapshot / 指纹 | `adapter.py`、`manifest.py:40-235` | 已实现 | 是 | 两轮真实测试均成功；上游哈希不变 |
| 3.3 Figure/Panel 层级、稳定 ID | `pipeline.py:137-240, 353-380, 1205+` | 部分实现 | 是 | 6 张图各 1 个 `SINGLE_PANEL_FALLBACK` 面板，**无自动分割**；真实测试 7/7 面板 `WHOLE_FIGURE_NOT_SEGMENTED` |
| 3.3 Panel segmentation（§5 范围 C、AC-29） | `pipeline.py:353-380` | **仅整图回退** | 是（但无算法） | 未实现自动分割；真实测试必须人工裁 6 个子图 |
| 3.4 Hybrid PDF evidence | `pdf_backend.py`、`backend_probe.py`、`pipeline.py:1160-1204` | 已实现 inventory | 是 | 本批图为栅格嵌入图，页内数值 TEXT=0；vector 通道因 crop_mapping 关闭 |
| 3.5 初步分类与**提取路由** | `chart_classifier.py:31-117` | 分类已实现；**路由未实现** | 分类是 / 路由否 | PR#16 修复误判；但分类结果只用于排除集，不产生提取任务 |
| 3.6 数值重建（像素→数值） | `calibration.py`、`raster.py`、`pipeline.py:890-937` | 人工输入下可用 | 是 | 真实自动 0 点；人工锚点+点路径可产 25 点（隔离诊断），非自动 |
| 3.9 P0 一维曲线/CV/EIS | `raster.py:10-107`（仅 X 单调单色） | **部分** | 是 | CV/EIS 无骨架图追踪；真实 Figure 5a 无法自动提取 |
| §5 CV/EIS（1092-1098）：禁止逐列扫描、需 skeleton/graph | 无对应模块 | **未实现** | 否 | 与计划明确冲突：现只有逐列中位数 |
| §5 面板分割与图例（1107-1113） | `entities.py`/`pipeline.py` 部分字段 | 部分 | 是 | 多面板、共享图例继承无图像侧实现 |
| 5 Axis calibration（1115-1121） | `calibration.py:9-31` | 已实现 | 是 | 0 锚点 → UNRESOLVED；PR#16 新增 `calibration_state` 正确 |
| 5 OCR（793, 910, 1443） | `ocr.py:29-67` | 代码存在 | **否**（默认 `--ocr` 关闭） | 环境未安装 rapidocr；栅格刻度无法读取 |
| 5 QC（1204-1249、AC-66~71） | `qc.py:build_series_qc_report` | 已实现且接入 | 是 | 真实全部 `PROVISIONAL_UNCALIBRATED`、`NOT_ASSESSED...`，正确 |
| 5 独立重绘 / 叠加对比（1337、1797） | 无 | **未实现** | 否 | 正式产物只有 CSV/JSON；对比图由测试脚本临时绘制 |
| AC-37 P0 workflow 可 inventory/calibrate/extract/QC/persist | 全链路 | 部分：流程可跑，extract 无数据 | 是 | 13 对象 0 点 |
| AC-38/39 CV/EIS 保序 | `pipeline.py:890-906`（仅人工 pixel_points） | 部分：人工可用 | 是 | 自动不可用 |
| AC-46 低歧义路由、歧义转 NEEDS_REVIEW | `qc.py` + `pipeline.py` 各 NEEDS_REVIEW | 已实现（保守拒绝） | 是 | 真实测试全部 NEEDS_REVIEW，无凭空数据 |
| AC-68/70 校准阈值需真实人工基准 | `configs/qc_thresholds_*` | 配置存在，基准未完成 | 是 | 报告明确 `NOT_ASSESSED` |
| AC-99 P1 bar/scatter/error bars | 无生产实现 | 未实现 | 否 | Figure 5f 散点对比无法处理 |
| AC-102 发布门槛 | — | 未满足 | 否 | 未发布，符合冻结计划 |

**PR #16 的作用边界**：只改了 `chart_classifier.py`（去掉 `potential/current density/scan rate` 泛词与 native_text 上下文，新增成对轴标签规则）和 `qc.py`（新增 `calibration_state` 维度）。它解决的是**分类误报**与**校准状态语义**，不解决面板分割、轴刻度读取、trace 自动生成、曲线追踪、多系列、重绘。并且在无 OCR 的真实数据上，因轴标签不可见，分类更保守地落到 UNCLASSIFIED，反而使 788-789 的颜色检测门控更难通过——即 PR#16 提升 precision，但不增加自动提取能力。后续开发必须保留该保守分类，同时补上“不依赖文本分类也能生成 trace spec”的路径。

---

## E. 实际能力矩阵（源码 + 两轮真实测试）

| 能力 | 当前代码情况 | 真实数据表现 | 主要阻塞点 |
|---|---|---|---|
| 整图识别 | adapter + `_inventory` 已实现 | 6 张 MAIN 全部识别，哈希/页/资产状态正确 | 无 |
| 子面板自动分割 | **无算法**；`_figure_panels` 整图回退 | 6 张图均 1 个 whole-figure 面板；P7_05 需人工裁 6 图 | A |
| 子图内容识别 | **无图像内容识别**；分类靠字符串 | 7/7 UNCLASSIFIED，Agent 视觉描述非 Skill 输出 | A / 无 OCR |
| 图表类型分类 | `chart_classifier.py` 规则匹配 | 7/7 UNCLASSIFIED；PR#16 无误报 | 缺轴标签输入 |
| 可提取性判断 | **无模块**；只有 NEEDS_REVIEW 状态 | 测试中的分类由 Agent 依据 Skill 证据补全 | A |
| 绘图区定位 | `detect_plot_box` 单矩形 | 6/7 PROVISIONAL_PLOT_BOX | 多图框歧义；无子面板对应 |
| OCR/刻度读取 | `ocr.py` 有实现 | 未启用、依赖未装 → 0 | 默认关闭 + 未安装 |
| 坐标锚点检测 | `axis_text.py` 有 OCR/native 两个函数 | 0 锚点（全部） | crop_mapping=None + OCR 关闭 + 栅格图无原生文本 |
| 坐标校准 | `calibration.py` 已实现 | 人工 4 锚点时两轴 CALIBRATED_NUMERIC；自动 0 | 无锚点 |
| trace specification 自动生成 | **不存在** | 13 对象全部 `NO_SUPPORTED_TRACE_SPECIFICATION` | A |
| 多系列识别 | 无颜色多族/线型/图例→系列算法 | 0 系列被分离 | A |
| 曲线像素追踪 | 仅 `trace_monotonic_color`（单色 X 单调） | 需人工 color_rgb；CV 明确不支持 | D |
| 散点图提取 | 无 | Figure 5f 未处理 | P1 未实现 |
| 柱状图提取 | 无 | Figure 2c 等未处理 | P1 未实现 |
| 数据点导出 | exporter/storage 已实现 | 自动 0 行；人工辅助 25 行可导出 | 依赖上游有点 |
| 独立重绘 | **无模块** | 正式产物无重绘图 | A |
| 提取质量评估 | QC 多维已实现 | 状态正确、警告完整；但无叠合/重投影误差 | 部分 A |
| 数据证据追溯 | evidence + bundle + CSV 已实现 | 图像 SHA、figure/panel、锚点、QC 全保留 | 无 |

**总判定：当前版本不能完成用户要求的自动科研图片数字化。** 软件流程可运行且 QC 诚实，但 0 数据点是算法能力缺位的结果。

---

## F. 最小可行修复路径（建议，不实施）

原则：**先完成“一张单面板、单曲线图”的全自动闭环，再扩多面板/多系列**。不得把人工 plot_box/锚点/点包装成自动能力。

### 阶段 1（最小可交付）：单面板单曲线全自动闭环
1. **恢复坐标映射**：扩展 `_inventory()` 读取 `media_assets[].bbox/page_number/extraction_method/sha256`，写入可持久化 `SourceImageMapping`；`process_paper` 重建 `crop_mapping`。复用现有 `_plot_box_to_pdf` / `pdf_points_to_crop_pixels`，新增反向变换。**验证**：单图 run 后 crop_mapping 非 None，`native_axis_evidence` 字段出现。
2. **轴刻度文字获取**：把 `ocr.py` 接入正式流程作为可配置阶段（默认可关闭；对栅格图必须开启），直接复用 `extract_numeric_axis_anchors()`；若原生 PDF 文本可用则走 B2 的 native 通道。**验证**：单面板图得到 ≥2 X 锚点与 ≥2 Y 锚点，`fit_linear_axis` 产出有限 RMSE。
3. **新增 `trace_spec.py`（核心缺口）**：输入 = 图像 + plot_box + 锚点 + 校准 + 颜色候选；输出 = `TraceSpecification{series_id, path_kind: X_MONOTONIC, color_rgb, tolerance, plot_box, calibration_ref}`。当前代码只有**消费** trace 的分支，没有**生产**者。**验证**：自动 run 的 metadata 中出现 `trace_specification` 而不是 `NO_SUPPORTED_TRACE_SPECIFICATION`。
4. **去掉颜色门控的文本依赖**：把 788-789 的 `family not in {...}` 改为“有有效校准 + 唯一色族即可尝试”，由 trace spec 明确 path_kind；UNCLASSIFIED 不应等于禁止提取。保留 PR#16 的保守分类作为证据字段，而不是路由开关。
5. **复用 `trace_monotonic_color()`** 完成提取；输出 panel_series.csv。
6. **新增 `reconstruction.py`**：用 `SeriesRecord.points` 独立绘制 X/Y 轴、单位、数据系列 PNG，并生成点叠加图。**验证**：单曲线原图 / 重绘图 / 叠加图三件套。
7. **QC 增补**：用重投影一致性、像素覆盖率、点数、连续性作为独立维度；`scientific_acceptance` 保持 NOT_ASSESSED。

验收条件：对**一张单面板、单色、X 单调**真实图，全自动 run 产出 >0 点、两轴 CALIBRATED_NUMERIC、独立重绘图与叠加图、QC 明确；人工输入为 0。未达此条件不算阶段 1 完成。

### 阶段 2：单面板多系列 / CV
- 颜色族分离（多色）与图例→系列绑定；`plot_region.detect_single_trace_color` 扩展为多族检测。
- CV/EIS 需要**骨架化 / 图搜索路径追踪**（计划 §5 第 1092-1098 行明确要求），替代逐列中位数；保留点序、回环、交点歧义转 NEEDS_REVIEW。
- 同色/虚线/标记区分属 P1，不放在阶段 1。

### 阶段 3：多面板与扩展图表
- 基于版式空白分割 + 面板标签（a/b/c）识别做自动分割；共享图例继承；散点/柱状（P1）与误差棒；独立重绘支持双 Y 轴、对数坐标。

### 可直接复用
adapter/snapshot/fingerprint、`detect_plot_box` 几何检测、`axis_text` 两个锚点提取器、`calibration.py`、`trace_monotonic_color`、`choose_vector_paths`、`qc.py`、storage/export/SQLite、review 机制。

### 必须新增
面板分割、图像文字获取集成、`TraceSpecification` 生成器、家族→提取器注册表、骨架/图追踪 CV 算法、多系列分离、独立重绘模块、crop_mapping 持久化契约。

---

## G. 最终判断

1. **当前版本能否完成用户需要的自动科研图片数字化？** **不能。** 两轮真实测试 13 个对象、0 自动数据点；源码证明缺少 trace specification 生成器、面板分割、有效轴文字获取和重绘模块。
2. **最关键三个阻塞点**：
   - (1) 无自动生成 trace specification（pipeline.py:938 的 else 是唯一出口）；
   - (2) `crop_mapping=None` 关闭原生锚点/矢量通道，且上游已有 bbox 被解析器丢弃；
   - (3) `color_detection=null` 是门控导致的“未调用”，且现有提取器仅支持单色 X 单调曲线，CV/EIS/多系列无算法。
3. **可复用模块**：adapter、snapshot/指纹、context index、figure inventory 骨架、`detect_plot_box`、`axis_text` 锚点提取、`calibration`、`trace_monotonic_color`、vector preselector、`qc`、storage/export/SQLite、review。
4. **实际尚未实现**：面板分割、图像轴标签/刻度读取的正式接入、trace spec 生成、分类→提取器路由、CV/EIS 路径追踪、多系列/图例分离、散点/柱状提取、独立重绘、叠合质量评估。
5. **最小下一阶段任务**：按 F 阶段 1 做“单面板单曲线全自动闭环”，以“0 人工输入 + >0 点 + 两轴校准 + 重绘图 + 叠加图 + QC”为硬验收。
6. **PR #16 如何保留**：保留其分类保守性与 `calibration_state`/QC 维度，作为防误报与状态语义的护栏；但**不得把分类结果当作提取路由的唯一开关**。新增 trace spec 生成器应在有像素/轴证据时独立工作，UNCLASSIFIED 仍可进入基于颜色的低歧义提取尝试；所有自动结果继续保持 `PROVISIONAL_UNCALIBRATED` 与 `NOT_ASSESSED`，直到有用户批准的人工标注基准。

**本报告不宣称任何科学精度通过，也不把流程可执行、QC 可运行或接口存在等同于自动数据提取能力。**
