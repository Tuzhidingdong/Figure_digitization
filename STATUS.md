# STATUS — Figure_digitization

> Execution record for the frozen user-owned TASK_PLAN_v1.4.1.md. This file tracks implementation and evidence only. Do not edit the Task Plan.

## Baseline and release governance

- Task Plan: TASK_PLAN_v1.4.1.md, frozen; objective, scope and acceptance criteria remain unchanged.
- User-selected repository: Tuzhidingdong/Figure_digitization. This follows the user's later explicit repo choice, although the plan originally named Tuzhidingdong/scientific-figure-data.
- Upstream chem-literature remains read-only; no upstream files or behavior are changed.
- Release/publish: not authorized.
- Target: Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU.
- Default runtime: one spawned paper worker, lazy sequential page/panel processing, one SQLite writer.
- Default LLM use: zero. No hidden model calls or paid fallback.
- OCR: optional and disabled by default; local CPU-only with ONNX intra/inter-op thread counts set to one.

## Current milestone

**M1 — Core implementation and P0 capability development; not yet ready for local acceptance.**

The repository contains an executable Python package/Skill, CLI, read-only corpus adapter, cross-page text context index, page-at-a-time PDFium wrapper, PDF backend probe, conservative vector-path selection, OCR/native-text axis tick parsing, low-ambiguity raster trace primitive, scientific data model, domain profiles, single-writer SQLite catalog, panel CSV artifacts, streaming query/export, corpus scheduler, and offline review patch workflow.

Automatic extraction is deliberately constrained to cases with explicit plot/crop geometry and adequate axis evidence. Ambiguous curves retain pixel geometry and route to review. This is not a universal automatic chart digitizer; no real-paper accuracy claim has been made.

## Implementation status by area

Status key: Implemented; CI tested / Partial / Blocked on user-approved evidence / Deferred.

| Area | Status | Evidence / limitations |
|---|---|---|
| Frozen Task Plan | Complete; immutable | TASK_PLAN_v1.4.1.md unchanged |
| Independent downstream Skill | Partial | Standalone package/Skill exists in the user-selected repository; original planned repository name differs |
| Read-only adapter | Partial | Common PDF, figure inventory, evidence index, MAIN/SI text and table layouts supported; real chem-literature version matrix still needs fixtures |
| Corpus discovery and fingerprints | Implemented; CI tested | Lazy discovery, SHA256 snapshots, POSIX paths, Windows-safe IDs; latest root/nested directory changes await CI |
| MAIN/SI context | Implemented; CI tested | Streaming text scan; compact in-memory index spills to paper-local SQLite |
| Scheduler and recovery | Partial | One worker by default, spawn, finite retries, lease/heartbeat, cache checks and single writer; injected process crash/BrokenProcessPool and hard memory/disk pressure still needed |
| Canonical paper IDs | Implemented; test pending | Central Windows-safe ID normalizer now used by scheduler ledger, worker output and resume selection; nested-paper regression added |
| PDF backend wrapper | Partial | Page-at-a-time PDFium rendering/native object inventory, text, images and bounded path style/geometry evidence |
| Backend comparison | Blocked on user-approved evidence | Probe supports PDFium, PDFMiner and pikepdf/QPDF; 3–5 real representative PDFs required before selection |
| Figure/Panel inventory | Partial | Upstream Figure records, stable IDs and shared legend refs; robust automatic segmentation/confidence calibration incomplete |
| Native PDF axes | Partial | Numeric ticks parsed from native text object bounds with explicit plot geometry; complex/rotated layouts remain review-bound |
| Native vector curves | Partial | Conservative stroked line-only filtering, style/geometry evidence, unique/explicit candidate routing and crop mapping; real scientific PDFs not tested |
| Raster curves | Partial | Explicit-color monotonic trace and Plot Box; ambiguous crossings/marker-based charts route to review; no general CV/EIS raster tracer |
| CV/EIS | Partial | Explicit ordered paths preserve traversal order; arbitrary raster loops not automatically traced |
| Relative spectral axes | Partial | Explicit relative-signal mode and Plot Box; baseline styles need real-paper testing |
| Dual Y axes | Partial | LEFT/RIGHT/UNASSIGNED storage and unresolved-axis geometry retention; general automatic association classifier incomplete |
| Entity/condition links | Partial | SubjectEntity/Condition/Measurement/Series separation and evidence-backed SeriesSubjectLink; automatic cross-page entity linking remains conservative |
| Battery/AOP/PFAS profiles | Implemented; CI tested | Inherited YAML profiles, analyte registry and metric distinctions; full profile-driven semantic extraction incomplete |
| Units/reference electrodes | Partial | Deterministic dimensional factors and evidence-gated reference conversion helper; full standardized-value pipeline incomplete |
| Provenance/QC | Partial | Input/PDF/image hashes, page/panel, algorithm, axis anchors, OCR/native evidence and component QC flags; full overlay/coverage/separation metrics and benchmark calibration incomplete |
| Storage/index/cache | Implemented; CI tested | Panel CSV, paper JSON/bundle hashes, SQLite single writer, streamed rebuild, stage fingerprints, reviewed-result lock and version backups |
| Query/export | Implemented; CI tested | Exact entity/analyte aliases, cursor query, streamed CSV/JSON point export, metadata sidecar and compatibility warnings |
| Offline review helper | Partial | Folder selection, lazy Panel CSV loading, source crop/curve/axis overlay, metadata/point/axis-anchor editing and patch export; browser workflow not manually accepted |
| Review patch apply | Partial | Base SHA256, schema validation, stale conflict, idempotency, version backups, atomic CSV rewrite and bundle hashes; axis recalibration now synchronizes SQLite, latest test pending |
| Corpus reporting | Partial | Job counts, retries, failures, elapsed time, throughput, sampled RSS and token count; complete eligible/skipped/temp-disk report incomplete |
| P1/P2 | Deferred | Tables/markers/error bars/complex tables and heatmap/advanced LC-MS remain deferred |
| Real-paper acceptance | Blocked on user evidence | No annotated Battery/AOP/PFAS benchmark has been run |
| Production release | Not authorized | AC-102 remains open |

## Windows CI and regression evidence

- Workflow: .github/workflows/windows-ci.yml; Windows Python 3.11, 3.12 and 3.13; package install, compileall, Ruff import/undefined-name check and pytest.
- Run #39: 15 tests passed on all three versions.
- Run #45: 17 tests passed on all three versions, including CLI end-to-end and cache reuse.
- Run #58: 19 tests passed on all three versions, including PDFium TextPage lifetime and backend-probe no-input tests.
- Run #64: 22 tests passed on all three versions, including alias migration, lease recovery and reviewed-result locking.
- Run #69: 23 tests passed on all three versions, including RapidOCR CPU-thread configuration and process-local reuse.
- Run #79: three new checks failed (fake PDF page contract, floating comparison tolerance, OCR Y-tick/X-tick boundary); fixes were committed.
- Run #86: 30 tests passed on all three versions after those fixes; included vector selection, OCR tick parsing and partial-geometry retention.
- Run #96: all tests except the new review-axis recalibration fixture passed. The fixture supplied axis anchors at pixel coordinates 0/1 while its source points were at pixel coordinates 10/20 and 20/10. The implementation correctly mapped the source pixels to 20/40; the test fixture has been corrected to use the source pixel coordinates.
- Current test source contains 37 tests. New tests cover axis-patch CSV/SQLite/bundle consistency, strict axis-anchor validation, corpus-root paper discovery and canonical nested paper IDs. This 37-test snapshot is awaiting a fresh Windows CI run.

## Recent engineering work

### Corpus, scheduler and storage
- Added lazy corpus discovery and per-paper SHA256 input snapshots.
- Added compact MAIN/SI/table context extraction with SQLite spillover.
- Added merged per-panel CSV; workers return compact metadata only.
- Catalog rebuild and ML export stream points in bounded batches.
- Added cache artifact-hash verification, incomplete-output cleanup, one-writer SQLite and finite lease/retry recovery.
- Fixed corpus root detection so a root-level PDF cannot suppress discovery of nested paper directories.
- Added one canonical Windows-safe paper ID normalizer and wired it into job ledger keys, CLI resume selection and output paper IDs; the worker still receives the original source-relative directory path.

### PDF and curve extraction
- Added PDFium native object inventory with TextPage lifetime handling, image metadata, bounded path segments, transformations, path paint style and page rotation.
- Added optional per-page PDFium/PDFMiner/pikepdf backend probe; final backend selection waits for real PDF measurements.
- Added conservative vector-path candidate selection and PDF-to-panel crop transform.
- Added native PDF numeric tick extraction; OCR is fallback only when explicitly enabled.
- Unresolved-axis curves retain pixel geometry and route to review.

### Scientific semantics and review
- Added separate SubjectEntity, Condition, Measurement, Series and DataObservation model concepts and evidence-backed series links.
- Added Battery/AOP/PFAS profiles, censored-value preservation and conservative reference conversion helper.
- Added exact alias query, streaming ML export with provenance sidecar and comparability warnings.
- Added review patch base-hash/schema validation, stale conflict, idempotency, version backup and offline helper.
- Review helper can edit X/Y axis anchors. Applying an axis patch recalibrates Panel CSV rows from pixel coordinates, updates Series metadata and streams the updated point rows into SQLite, then refreshes the bundle content hashes. Latest end-to-end regression is pending CI.

## Current blockers and next actions

1. Run the latest 37-test source on Windows Python 3.11/3.12/3.13; fix any failures.
2. Complete review transaction tests for rollback after failed CSV/SQLite update, and multiple affected Series in one Panel.
3. Add process-crash/BrokenProcessPool injection and memory/disk pressure tests.
4. Manually verify the offline browser folder-selection and patch-export/apply workflow.
5. Improve P0 chart-family/Hybrid routing without overstating automatic support.
6. Run the backend probe on 3–5 user-approved PDFs; record per-page time, Peak RSS, object/path coverage, clipping, rotation, Form XObjects, text-as-path and licensing.
7. Validate P0 extraction on annotated Battery, AOP and PFAS figures; only then create calibrated thresholds and quantify scientific accuracy.
8. Keep P1/P2 deferred until P0 evidence is validated.

## Non-negotiable constraints

- Never edit TASK_PLAN_v1.4.1.md.
- Never modify, move, rename or delete upstream chem-literature artifacts.
- Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU remains the baseline.
- One worker by default; synchronous lazy iteration inside a paper worker.
- No unnecessary internal queues.
- PDF pages, crops, OCR engines and point batches are loaded/persisted incrementally.
- Workers never write to SQLite; one parent process owns catalog writes.
- Zero LLM tokens by default; no hidden model calls or paid fallback.
- Uncertain scientific values and links remain UNKNOWN/UNASSIGNED/NEEDS_REVIEW.
- REVIEWED_ACCEPTED results are protected unless explicit force recompute creates a version backup.
- No production-ready or release claim without real-paper benchmark, Windows resource measurements, licensing review and data-integrity evidence.
