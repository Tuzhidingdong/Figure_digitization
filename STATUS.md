# STATUS — Figure_digitization

> Execution record for the frozen user-owned TASK_PLAN_v1.4.1.md. This file tracks implementation and evidence only. Do not edit the Task Plan.

## Baseline and release governance

- Task Plan: TASK_PLAN_v1.4.1.md, frozen; its objective, scope and acceptance criteria remain unchanged.
- User-selected repository: Tuzhidingdong/Figure_digitization. This follows the user's later explicit repo selection, although the plan originally named Tuzhidingdong/scientific-figure-data.
- Upstream chem-literature remains read-only; no upstream files or behavior are changed.
- Implementation branch: main. Release/publish: not authorized.
- Target: Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU.
- Default runtime: one spawned paper worker; lazy sequential page/panel processing; one SQLite writer.
- Default LLM use: zero. No hidden model-provider calls or paid fallback.
- OCR: optional, disabled by default, local CPU-only; ONNX intra/inter-op thread counts are one.

## Current milestone

**M1 — Core implementation and P0 capability development; not yet ready for local acceptance.**

The repository contains an executable Python package/Skill, CLI, read-only corpus adapter, cross-page text context index, page-at-a-time PDFium wrapper, PDF backend measurement probe, conservative vector-path selection, OCR/native-text axis tick parsing, low-ambiguity raster trace primitive, scientific series/entity/measurement model, domain profiles, one-writer SQLite catalog, panel CSV artifacts, streaming query/export, corpus scheduler and review patch workflow.

The vector and axis paths are deliberately conservative. They require explicit plot/crop geometry and adequate axis evidence, or preserve pixel geometry and route records for review. They are not a universal automatic chart digitizer. No extraction accuracy claim is made without annotated real-paper benchmarks.

## Implementation status by area

Status key:
- Implemented; CI tested: code path exists and is covered by a green Windows CI snapshot.
- Partial: a bounded subset exists; broader plan capability is not accepted.
- Blocked on user-approved evidence: needs representative real PDFs or annotations.
- Deferred: P1/P2 scope not started.

| Area | Status | Evidence / limitations |
|---|---|---|
| Frozen Task Plan | Complete; immutable | TASK_PLAN_v1.4.1.md has not been modified |
| Independent downstream Skill | Partial | Standalone package/Skill entry exists in user-selected repository; original planned repo name differs |
| Read-only adapter | Partial | Common PDF, figure-inventory, evidence-index, MAIN/SI text and table paths supported; real upstream layout/version matrix still needs fixtures |
| Corpus manifest/fingerprints | Implemented; CI tested | Incremental discovery, SHA256 snapshots, POSIX-relative internal paths and Windows-safe storage IDs |
| MAIN/SI context | Implemented; CI tested | Streaming text scan; compact in-memory index spills to paper-local SQLite above configured budget |
| Low-resource scheduler | Partial | Default one worker, spawn, lease/heartbeat, finite retries, cache checks and one SQLite writer; process-crash and hard memory/disk pressure injection tests remain |
| PDF backend wrapper | Partial | Page-at-a-time PDFium rendering/native object inventory; path/text evidence persisted |
| Backend comparison | Blocked on user-approved evidence | Probe supports PDFium, PDFMiner and pikepdf/QPDF; 3–5 real representative PDFs required before final selection |
| Figure/Panel inventory | Partial | Upstream Figure records, stable IDs and shared legend refs consumed; robust automatic segmentation/confidence calibration incomplete |
| Native PDF axes | Partial | Numeric tick labels extracted from native text bounds with explicit plot geometry; complex/rotated layouts remain review-bound |
| Native vector curves | Partial | Conservative stroked line-only path filter, style/geometry evidence, unique/explicit candidate routing and crop mapping; not tested on real scientific PDFs |
| Raster curves | Partial | Explicit-color monotonic trace and plot box; dense same-color/crossing/marker charts route to review; no general CV/EIS raster tracer |
| CV/EIS | Partial | Explicit ordered paths preserve traversal order; arbitrary raster loops are not automatically traced |
| Relative spectral axes | Partial | Explicit relative-signal mode and Plot Box; baseline styles need real-paper testing |
| Dual Y axes | Partial | LEFT/RIGHT/UNASSIGNED storage and unresolved-axis geometry retention; general automatic axis-to-series classification incomplete |
| Entities/conditions | Partial | Separate SubjectEntity/Condition/Measurement/Series model and evidence-backed SeriesSubjectLink; automatic cross-page linking stays conservative |
| Battery/AOP/PFAS profiles | Implemented; CI tested | Inherited YAML profiles, analyte registry and metric boundaries; full profile-driven semantic extraction incomplete |
| Units/reference electrodes | Partial | Deterministic dimensional factors and evidence-gated reference conversion helper; full unit vocabulary/standardization pipeline incomplete |
| Provenance/QC | Partial | Input/PDF/image hashes, page/panel, algorithm, axis anchors, OCR/native evidence, component QC flags; full overlay/coverage/separation metrics and benchmark calibration incomplete |
| Storage/index/cache | Implemented; CI tested | Panel CSV, paper JSON/bundle hashes, SQLite single writer, streamed rebuild, stage fingerprints, reviewed-result lock/backups |
| Query/export | Implemented; CI tested | Exact entity/analyte aliases, cursor query, streamed CSV/JSON point export, series metadata JSONL and warnings |
| Offline review helper | Partial | Folder selection, lazy current-panel loading, source crop/overlay, metadata, ordered point and axis-anchor editing, patch export; browser workflow not yet manually accepted |
| Review patch apply | Partial | Base SHA256, schema validation, stale conflict, idempotency, version backups, atomic CSV rewrite, bundle hash refresh; latest axis-recalibration SQLite sync awaits CI |
| Corpus reporting | Partial | Counts, retries, failure reasons, elapsed time, throughput, sampled RSS and token count; full eligible/skipped/temp-disk report incomplete |
| P1/P2 | Deferred | Tables/markers/error bars/complex tables and heatmap/advanced LC-MS remain deferred |
| Real-paper acceptance | Blocked on user evidence | No annotated Battery/AOP/PFAS benchmark has been run |
| Production release | Not authorized | AC-102 release evidence remains open |

## Windows CI and regression evidence

- Workflow: .github/workflows/windows-ci.yml; Windows Python 3.11, 3.12 and 3.13; install, compileall, Ruff import/undefined-name check, pytest.
- Run #39: 15 tests passed on all three versions.
- Run #45: 17 tests passed on all three versions, including CLI end-to-end and cache reuse.
- Run #58: 19 tests passed on all three versions, including PDFium TextPage lifetime and backend-probe no-input tests.
- Run #64: 22 tests passed on all three versions, including alias migration, lease recovery and reviewed-result locking.
- Run #69: 23 tests passed on all three versions, including RapidOCR CPU-thread configuration and process-local reuse.
- Run #79 failed three new checks: fake PDF page contract, floating comparison tolerance, and a Y-axis tick duplicated as an X tick. The failures were fixed.
- Run #86: 30 tests passed on all three versions after those fixes; includes conservative PDF vector selection, OCR tick parsing and partial-geometry retention.
- Current test source contains 34 tests. Four additional tests cover native PDF text-axis mapping and review-patch axis recalibration/SQLite consistency. This 34-test snapshot has not yet completed Windows CI.
- Synthetic fixtures validate software behavior only; they do not constitute scientific accuracy validation.

## Recent engineering work

### Corpus and storage
- Added lazy corpus discovery and per-paper SHA256 snapshots.
- Added compact MAIN/SI/table context extraction with SQLite spillover.
- Added panel-level merged point CSV; workers return compact metadata only.
- Changed catalog point rebuild and ML export to bounded streaming.
- Added cache artifact-hash verification and cleanup of incomplete panel output following worker interruption.
- Added a single-writer SQLite architecture and task leases/finite retries.

### PDF and curve extraction
- Added PDFium page-level object inventory with TextPage lifetime handling, image metadata, bounded path segments, transformations, path paint style and page rotation.
- Added optional PDFium/PDFMiner/pikepdf backend benchmark probe; no backend is selected without real PDF measurements.
- Added conservative vector-path candidate selection and page-PDF-to-panel-pixel transform.
- Added native PDF numeric tick detection; OCR tick detection is fallback only when OCR is explicitly enabled.
- Curves with unresolved physical axes retain pixel geometry and are routed to review.

### Scientific semantics and review
- Added SubjectEntity, Condition, Measurement, Series and DataObservation models; evidence-backed series-level subject links.
- Added Battery/AOP/PFAS profile inheritance, censored-value preservation and conservative reference-electrode conversion helper.
- Added query/export provenance and comparability warnings.
- Added review patch hash/schema validation, stale conflict records, idempotency, version backup and offline helper.
- Added editable X/Y axis anchors; patch application recalibrates CSV values from stored pixels, persists calibration metadata, and streams updated points into SQLite. Latest regression tests are pending.

## Current blockers and next actions

1. Run the current 34-test source on Windows Python 3.11/3.12/3.13; inspect and fix failures.
2. Complete end-to-end review tests, including rollback after failed CSV/SQLite update, multiple series in one panel, and axis-only recalibration without stale SQLite values.
3. Test process-crash/BrokenProcessPool isolation and resource-pressure behavior under bounded memory/disk.
4. Finish review overlay for vector candidates and native/OCR tick evidence; manually check browser folder-selection workflow.
5. Improve P0 chart-family/Hybrid routing without overstating supported automation.
6. Run the backend spike on 3–5 user-approved PDFs and record timing, Peak RSS, object/path coverage, clipping, rotation, Form XObjects, text-as-path and licensing.
7. Validate P0 extraction against annotated Battery, AOP and PFAS figures; only then generate calibrated QC thresholds and assess scientific accuracy.
8. Keep P1/P2 deferred until P0 is validated.

## Non-negotiable constraints

- Never edit TASK_PLAN_v1.4.1.md.
- Never modify, move, rename or delete upstream chem-literature artifacts.
- Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU is the baseline.
- One worker by default; synchronous lazy iteration within a paper worker.
- No unnecessary internal queues.
- PDF pages, crops, OCR engines and point batches are loaded/persisted incrementally.
- Workers never write to SQLite; one parent process owns catalog writes.
- Zero LLM tokens by default; no hidden model calls or paid fallback.
- Uncertain scientific values and links remain UNKNOWN/UNASSIGNED/NEEDS_REVIEW.
- REVIEWED_ACCEPTED results are protected unless explicit force recompute creates a version backup.
- No production-ready or release claim without real-paper benchmark, Windows resource measurements, licensing review and data-integrity evidence.
