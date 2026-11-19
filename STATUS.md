# STATUS — Figure_digitization

> Execution record for the frozen, user-owned TASK_PLAN_v1.4.1.md. This file tracks implementation and evidence only; the Task Plan remains unchanged.

## Baseline and governance

- Task Plan: TASK_PLAN_v1.4.1.md, FROZEN — DO NOT EDIT.
- Implementation repository selected by the user: Tuzhidingdong/Figure_digitization. This follows the later explicit repo selection, although the plan originally named Tuzhidingdong/scientific-figure-data.
- Upstream chem-literature: READ-ONLY. No upstream file or behavior has been modified.
- Release: NOT AUTHORIZED. Current work is an implementation/verification draft only.
- Target: Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU.
- Default: one spawned paper worker, sequential lazy page/panel processing, one parent SQLite writer.
- LLM: zero tokens by default; no model provider or paid fallback is implemented.
- OCR: optional, local, disabled unless --ocr is explicitly passed; ONNX threads are constrained to one.

## Current milestone

**M1 — Corpus pipeline and P0 extraction capability development. NOT READY FOR LOCAL ACCEPTANCE.**

An executable Python package/Skill and CLI exist. They include read-only paper discovery and fingerprints, MAIN/SI context indexing, PDFium page rendering/native object evidence, conservative native vector trace extraction, native-text/OCR axis tick candidates, simple raster plot-frame and single-color detection, scientific profiles and data models, corpus scheduling/cache/indexing/export, and an offline hash-checked review workflow.

This is a bounded, conservative implementation—not a universal automatic figure digitizer. Synthetic tests prove code paths and safety behavior only. Real scientific extraction accuracy and QC thresholds have not yet been measured against annotated papers.

## Implementation status

Status meanings: Implemented/CI-tested = present and tested by a green Windows snapshot; Partial = only the bounded subset below exists; Blocked = needs user-approved real PDFs/annotations; Deferred = P1/P2.

| Area | Status | Notes |
|---|---|---|
| Frozen Task Plan | Complete; immutable | No change to TASK_PLAN_v1.4.1.md |
| Independent downstream Skill | Partial | Standalone Skill/package in Figure_digitization; original planned repo name differs |
| Read-only chem-literature adapter | Partial | Common figure inventory, evidence-index, PDF, MAIN/SI text and table paths; real upstream layout/version fixtures remain needed |
| Corpus discovery | Partial | Distinguishes strong paper markers from weak root-level manifests; root PDF must not swallow nested corpus; Windows path cases covered synthetically |
| Input snapshots | Implemented; CI-tested | SHA256, sizes, mtimes, relative paths, adapter version and fingerprint |
| Paper identity | Implemented; tests pending CI | Single Windows-safe paper_id normalizer now used by scheduler, output, resume and failed-only selection |
| MAIN/SI context | Implemented; CI-tested | Streamed text scan and bounded index with SQLite spillover |
| Scheduler | Partial | Spawn workers, default one, finite retries, lease/heartbeat, one SQLite writer; process-crash/BrokenProcessPool and pressure injection remain |
| Resume/cache | Partial | Fingerprints input, algorithm source, profiles, QC thresholds and extraction options; verifies every bundle-tracked artifact; skips intact unchanged papers before worker start; latest 54-test set awaits CI |
| Reviewed-data lock | Partial | Intact accepted result is protected; bundle integrity failure returns BLOCKED unless explicit force recompute; preserves version backup |
| PDFium backend | Partial | Page-at-a-time render, native text/images/paths, bounded segment data, transformations and paint style |
| Backend comparison | Blocked on user-approved PDFs | Probe supports PDFium, PDFMiner and pikepdf/QPDF; final choice needs 3–5 representative PDFs and licensing review |
| Figure/Panel inventory | Partial | Consumes upstream inventory and shared legends; robust automatic segmentation/confidence calibration incomplete |
| Native tick extraction | Partial | Numeric tick labels from PDF text object bounds; OCR optional fallback; complex/rotated layouts route to review |
| Vector curve extraction | Partial | Conservative line-only path preselector, style/geometry evidence, coordinate mapping, ordered points; Bezier/ambiguous candidates route to review |
| Raster plot-frame detection | Partial | Provisional unique rectangular frame from line projections; ambiguous/no frame routes to review |
| Raster curve extraction | Partial | Unique chromatic family + monotonic column trace for simple single-valued plots; multi-color/same-color separated bands route to review |
| Hybrid routing | Partial | Prefer native vector; raster fallback only when vector candidates are ambiguous and a unique raster color family exists; latest tests await CI |
| CV/EIS | Partial | Explicit ordered paths preserve loop/branch order; general automatic raster loop tracing is not implemented |
| Spectral axes | Partial | Relative-signal mode when no numeric Y scale; numeric Y tick evidence can take precedence; real baseline styles need benchmark |
| Dual Y axes | Partial | LEFT/RIGHT/UNASSIGNED and geometry retention; broad automatic curve-to-axis assignment incomplete |
| Entity/Condition/Measurement/Series model | Partial | Distinct concepts and series-level evidence links; automated cross-page semantic linking remains conservative |
| Battery/AOP/PFAS profiles | Implemented; CI-tested | Inherited YAML profiles and metric boundaries; complete profile-driven semantic interpretation incomplete |
| Units/reference electrodes | Partial | Deterministic dimension conversion and evidence-gated reference conversion; full standardized-value pipeline incomplete |
| Provenance/QC | Partial | PDF/input hashes, page/panel, pixel points, algorithm, axis evidence, component status; calibrated geometric QC needs annotation |
| Panel CSV/Bundle/SQLite | Implemented; CI-tested | Panel-level CSV, paper metadata JSON, bundle hashes, single-writer query index and streaming rebuild/export |
| Offline review helper | Partial | Folder selection, lazy Panel CSV loading, source crop/curve/axis overlays, anchor/point edits and Review Patch export; manual browser acceptance remains |
| Review apply | Partial | Base-hash and schema checks, stale conflict, atomic CSV, metadata/bundle hashes, SQLite resync, version backup; latest tests await CI |
| P1/P2 | Deferred | Tables/complex tables/markers/error bars, heatmap matrix and advanced LC-MS/MS |
| Real-paper acceptance | Blocked | No annotated Battery/AOP/PFAS figures have been benchmarked |
| Production release | Not authorized | Release acceptance evidence incomplete |

## Windows CI and regression evidence

Workflow .github/workflows/windows-ci.yml runs Windows Python 3.11, 3.12 and 3.13: install, compileall, Ruff undefined-name/import checks, and pytest.

- Run #39: 15 tests passed on all three versions.
- Run #45: 17 tests passed on all three versions.
- Run #58: 19 tests passed on all three versions.
- Run #64: 22 tests passed on all three versions.
- Run #69: 23 tests passed on all three versions.
- Run #79: three new tests failed; fake PDF page interface, float assertion tolerance, and OCR X/Y margin overlap were corrected.
- Run #86: 30 tests passed on all three versions.
- Run #96: Ruff failed before pytest on an undefined test import; the import was corrected.
- Run #106: Ruff failed before pytest on a test import of connect_catalog; corrected.
- Current suite: **54 tests**, including plot-frame detection, single/multi-color classification, automatic simple GCD curve extraction, full PDF crop/vector integration, resume/cache validation, review integrity locks and Hybrid vector/raster routing. This exact snapshot has not yet completed CI.
- Tests use synthetic fixtures; they are not a substitute for real-paper accuracy measurement.

## Latest engineering work

### Automatic P0 extraction
- Added deterministic caption/axis technique preclassification for CV/EIS, XRD/Raman/FTIR/XPS, GCD/GITT and simple degradation time series.
- Added conservative rectangular plot-frame detection from horizontal/vertical line projections.
- Added dominant chromatic-family detection. Multiple color families and multiple separated same-color bands per column are rejected.
- Native PDF vector extraction now has priority over raster when the panel can be mapped into PDF coordinates.
- If vector candidates are ambiguous, an independently unique raster color family may be used; otherwise review is required.
- Pixel geometry is retained when physical axis mapping is unresolved.
- CV/EIS are excluded from the monotonic color tracer.

### Corpus and cache safety
- Fixed corpus root discovery so a root-level PDF does not incorrectly terminate traversal through nested paper folders.
- Nested evidence-index/manifest-only paper folders can be discovered even if their source PDF is missing.
- Centralized Windows-safe canonical paper IDs across worker paths, scheduler ledger, Catalog and selection CLI.
- Resume compares input fingerprint, algorithm source fingerprint, profile/QC fingerprint, relevant processing options and Bundle content hashes; intact unchanged papers are skipped before worker dispatch.
- Failed/incomplete job states are not mistaken for successful cache hits.
- Accepted results with broken bundle integrity are BLOCKED by default; force recompute is explicit and creates a version backup.

### Review and indexing
- Review helper supports editing X/Y axis anchors as well as ordered point paths.
- Review apply recalculates CSV values from source pixel coordinates, updates Series calibration metadata, streams corrected point rows into SQLite and refreshes paper bundle hashes.
- Rollback backups are kept for the digitization JSON, affected Panel CSVs and Bundle.

## Current blockers / next actions

1. Run the current 54-test snapshot on Windows Python 3.11/3.12/3.13 and fix any failures; do not infer a pass from earlier runs.
2. Add rollback/failure-injection tests for review CSV/SQLite multi-artifact updates.
3. Add ProcessPool crash/BrokenProcessPool and 8 GB RAM/disk-pressure tests.
4. Manually validate file:// offline review folder selection and patch apply in a Windows browser.
5. Run the PDF backend spike on 3–5 user-approved representative PDFs; record page time, Peak RSS, text/path/image coverage, clipping, rotation, Form XObjects, text-as-path and licenses.
6. Validate P0 curves and coordinate errors against user-annotated Battery, AOP and PFAS figures. Only then calibrate QC thresholds and state scientific accuracy.
7. Keep P1/P2 deferred until P0 is validated.

## Non-negotiable rules

- Never edit TASK_PLAN_v1.4.1.md.
- Never modify, move, rename or delete chem-literature source artifacts.
- Windows 10/11, 8 GB RAM, 4 cores, no GPU.
- One worker by default; lazy sequential work within each paper.
- Workers never write SQLite; parent process owns one writer.
- Zero LLM tokens by default; no hidden model calls or paid fallback.
- Preserve source values, units, pixel geometry and evidence; do not invent precision.
- Unknown semantics remain UNKNOWN/UNASSIGNED/NEEDS_REVIEW.
- Never overwrite REVIEWED_ACCEPTED silently.
- No production-ready or release claim without real-paper benchmarks, Windows resource evidence, dependency-license review and data-integrity verification.
