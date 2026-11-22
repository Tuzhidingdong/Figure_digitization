# PR #17 Phase 1 — P7_05 单图自动数字化验收报告

- 日期：2026-11-22
- 测试 worktree：`E:\Zinc_batters_datas\Figure_digitization_p1_test_20261122`
- HEAD：`727cb82f9ce12c3c31d8e872d71aaceb620798e3`（与指定一致）
- Skill：从原项目原样复制 25 文件，全部 SHA256 一致；SKILL.md SHA256 `4340502553aefdab5a59950183443c5f20a8597fe7ad05876d78ab23e935e4b8`
- Active Project Root：已切换到新 worktree，Skill 工具从该目录正式加载成功（返回 Base directory = 新 worktree `.agents\skills\scientific-figure-data`）
- 环境：独立 `.venv`，Python 3.13.9；`pip install -e ".[dev,images,ocr]"` 成功（rapidocr 3.10.0、onnxruntime 1.32.0、opencv-python-headless 5.1.0.95 等）
- 输入：仅 `MAIN_MAIN_FIG_P7_05.png` + 最小 `figure_inventory.json`（只有 figure_id 与 image_path），**零人工标注**
- 命令：`sfd scan` → `sfd run --paper-id root-paper --workers 1 --max-attempts 1 --ocr` → `sfd validate` → `sfd export`，均在独立输入/输出目录，日志在 `logs/`

## 执行结果总览

| 步骤 | 结果 |
|---|---|
| scan | discovered = 1 |
| run | **FAILED_PERMANENT**，attempt_count = 1，`failure_reason_distribution = {"TypeError": 1}` |
| validate | `INVALID`，5 个 canonical JSON 缺失 |
| export | 只生成 `dataset.csv` 表头（0 行）、空 `series_metadata.jsonl` / `warnings.jsonl` |

**核心事实：本次真实图片自动提取数据点 = 0。** pipeline 在进入曲线提取之前即崩溃，因此不存在可评估的自动数字化结果。

---

## 对 15 个问题的逐项回答

1. **图片是否成功加载？** 是。原图与测试夹具 SHA256 完全一致 `3b860297…10de`，510,721 bytes，PNG/RGB/1401×677。
2. **Skill 是否成功加载？** 是。25 文件哈希一致，`skill` 工具正式加载并报告新 worktree 为 Base directory。
3. **自动识别出多少个 panel？** **无法确定完整数量**。`run` 崩溃导致 `panel_layout.json` 未写出；但 pipeline 在崩溃前已落盘 **1 个**自动裁剪证据 `evidence/P7_05_auto-01.png`（434×351），命名来自 `panel_segmentation.py:175` 的 `auto-{index:02d}`，分割来源常量为 `AUTO_RASTER_WHITESPACE_SEGMENTATION`（`panel_segmentation.py:179`）。该裁剪在视觉上对应子图 a，并带有子图 d 标签的少量下缘渗入（此为 Agent 观察，非 Skill 输出）。
4. **每个 panel 的 bbox 与分割证据？** 仅能从裁剪文件反推尺寸 434×351；**bbox 未持久化**（panel_layout.json 缺失），无置信度字段可读。证据文件：`papers/root-paper/evidence/P7_05_auto-01.png`。
5. **OCR 是否成功？读到了什么？** **失败，0 条 OCR 记录**。引擎初始化即抛异常，未执行任何文字识别。
6. **哪些 panel 形成有效 TraceSpecification？** **0 个**。pipeline 在 `_extract_panel` 之前崩溃，未产生任何 trace specification。
7. **哪些 panel 进入颜色检测？** **0 个**。同上，未进入。
8. **哪些 panel 完成自动坐标校准？** **0 个**。无锚点、无校准结果。
9. **哪些 panel 真正生成自动数据点？** **0 个**。
10. **每个成功系列多少点？** 无成功系列，不适用。
11. **CSV 是否实际包含数据？** **否**。`exports/digitized_points.csv/dataset.csv` 仅 1 行表头、0 行数据；`series_metadata.jsonl`、`warnings.jsonl` 均为 0 字节。注意：`--out .../digitized_points.csv` 被 exporter 当作目录名，实际文件在 `digitized_points.csv/dataset.csv`。
12. **独立重绘图是否存在？** **否**。pipeline 未生成任何 reconstructed PNG。`comparisons/ALL_PANELS_COMPARISON.png` 是 **Agent 依据真实 pipeline 证据整理的诊断图**，不是 Skill 重绘产物，图内已明确标注。
13. **原图叠加图是否存在？** **否**。无提取点，故无 overlay；未伪造。
14. **哪些面板无法提取，为什么？** 全部。直接原因不是图表本身，而是 **OCR 引擎初始化缺陷**；`--ocr` 是本次强制条件，且 pipeline 在 1479-1481 行对每个自动面板无条件调用 `run_ocr()`，因此任何面板都无法通过。
15. **当前最大实际技术阻塞？** PR #17 的 `src/scientific_figure_data/ocr.py:11-19` 把 `Det.engine_type` / `Cls.engine_type` / `Rec.engine_type` 设为字符串 `"onnxruntime"`，而安装的 rapidocr 3.10.0 要求 **Enum 类型**；`ocr.py:43` 构造 `RapidOCR(params=dict(_RAPIDOCR_PARAMS))` 时抛出：
    ```
    TypeError: The value of Det.engine_type must be Enum Type.
    ```
    完整栈（来自 `catalog.sqlite.jobs.last_error` / `job_events`）：
    ```
    scheduler.py:43 _process_paper_task -> pipeline.py:1481 process_paper -> ocr.py:43 run_ocr
    -> rapidocr/main.py:44 __init__ -> main.py:59 _load_config
    -> utils/parse_parameters.py:60 update_batch -> TypeError
    ```
    这是生产代码与依赖版本的接口不匹配，属**引擎实现缺陷**，不是输入问题、不是图像质量问题、不是 agent 操作问题。

---

## 重点功能核查（第 10 节）

| 核查项 | 结果 | 证据 |
|---|---|---|
| A 自动面板分割 | **部分可见但未验收**：崩溃前写出 1 个 `auto-01` 裁剪；无 panel_layout.json，无法核对完整数量/bbox/置信度/误检 | `evidence/P7_05_auto-01.png`；`panel_segmentation.py:175-181` |
| B OCR 与轴识别 | **FAIL**：0 行 OCR，无标签、无刻度、无锚点；无人工输入计入 | `jobs.last_error`；`logs/run.log` |
| C TraceSpecification | **FAIL**：`trace_specifications = 0`，无 `status/reason/input_provenance/automation_status` 可读 | `summary.json` |
| D 曲线提取 | **FAIL**：无 `extraction_method/status/points_count/raster_qc/校准` | 无 digitization.json |
| E 独立重绘 | **FAIL**：无 Skill 重绘 PNG；诊断总览为 Agent 整理 | `comparisons/` 下仅 Agent 诊断图 |
| F 可提取性结果 | 无法由 pipeline 判定；本报告将 Agent 视觉参考与 pipeline 状态严格分开（见下） | 本报告 |

**Agent 独立视觉参考（不是本次 Skill 输出，不计入自动结果）**：a = CV 双系列；b = 倍率双 Y 轴散点；c = 结构示意；d/e = 循环容量双 Y 轴（e 含照片）；f = 能量密度-面容量散点。本次 Phase 1 按任务说明不支持 CV/EIS、散点、柱状、多系列、双分支，因此这些参考仅用于解释为何即使 OCR 修复，也不应强行把非支持类型送入 X 单调追踪器。

---

## PASS / PARTIAL / FAIL 验收表

| 能力 | 结论 | 判断依据 |
|---|---|---|
| 输入与 Skill 加载 | **PASS** | SHA 一致、Skill 25 文件一致并正式加载 |
| 子图几何分割 | **PARTIAL** | 有 1 个真实 auto 裁剪证据，但无 panel_layout.json，无法确认完整分割结果 |
| OCR 轴识别 | **FAIL** | 0 条 OCR，引擎初始化异常 |
| 数值锚点 | **FAIL** | 0 |
| 自动 TraceSpecification | **FAIL** | 0，无 FULLY_AUTOMATIC |
| 自动数据提取 | **FAIL** | 0 点 |
| CSV 导出 | **FAIL** | 0 数据行 |
| 独立重绘 | **FAIL** | 无 Skill 重绘产物 |
| 原图叠加 | **FAIL** | 无 overlay |
| CV/EIS 安全拒绝 | **PASS** | 没有任何曲线被误送入单调追踪器（因未进入提取阶段） |

**核心验收条件（零人工标注 + 双轴校准 + 点>0 + CSV 非空 + 独立重绘 + overlay）全部未满足。Phase 1 在真实图片上判定为 FAIL。**

---

## 未生成的文件与原因

`panel_layout.json`、`digitization.json`、`paper_bundle.json`、`paper_manifest.json`、`figure_inventory.json`（下游）、`series/*.csv`、任何 reconstructed/overlay PNG —— 均因 `run` 在 OCR 初始化处崩溃而未产生。**未生成任何占位或伪造数据。**

实际存在的结果文件：
- `REPORT.md`、`summary.json`、`panel_inventory.csv`、`digitization_summary.csv`、`qc_summary.csv`
- `exports/digitized_points.csv/{dataset.csv(表头),export_manifest.json,series_metadata.jsonl(空),warnings.jsonl(空)}`
- `papers/root-paper/evidence/P7_05_auto-01.png`（真实自动裁剪证据）
- `comparisons/ALL_PANELS_COMPARISON.png`（Agent 诊断图，非 Skill 重绘）
- `logs/{scan,run,validate,export,comparison}.log`、`logs/build_comparison.py`

---

## 建议（仅记录，不实施）

先修复 `ocr.py` 接口：把三个 `engine_type` 值改为 rapidocr 3.10.0 要求的 Enum（或按该版本的 params schema 传入），并在 `run_ocr` 中对引擎初始化失败做明确、可诊断的错误处理而非让整篇 paper 崩溃。修复后**用同一零人工标注夹具、同一命令重跑一次**，再依据真实points/CSV/重绘/overlay 重新验收。在此之前不能宣称 Phase 1 在真实图片上通过，也不能宣称任何科学数字化精度通过——本次没有独立人工数值基准。

---

## 完整性声明

测试结束后已核对：新 worktree HEAD 仍为 `727cb82…798e3`、tracked diff 为空；原项目与 PR16 worktree 状态未变；原始图片 SHA256 前后相同；Skill 与 TASK_PLAN 哈希未变；所有新增内容均位于新 worktree 的 `test_outputs/single_figure_P7_05_phase1_20261122/` 与 `test_inputs/single_figure_P7_05/`；未修改源码、配置、测试、Skill、TASK_PLAN、STATUS、PR 分支或上游数据；未提交/推送/合并/发版。
