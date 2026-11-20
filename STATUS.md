# STATUS — Figure_digitization

> Execution tracking for [TASK_PLAN_v1.4.1.md](./TASK_PLAN_v1.4.1.md). This file records implementation progress only; it does not modify the frozen objective, scope, constraints, or acceptance criteria.

## Baseline and governance

- Task Plan: [TASK_PLAN_v1.4.1.md](./TASK_PLAN_v1.4.1.md)
- Task Plan version: v1.4.1
- Baseline status: FROZEN — DO NOT EDIT
- Plan commit recorded in the baseline: \`6d6386e13da72d67d70bc0a93b83df2cce6594c3\`
- User-selected implementation repository: \`Tuzhidingdong/Figure_digitization\`
- Note: the frozen plan names \`Tuzhidingdong/scientific-figure-data\` as its target repository. The user subsequently explicitly selected \`Figure_digitization\` for implementation. This execution follows that later repository instruction; the frozen plan file remains unchanged.
- Implementation branch: \`main\`
- Implementation status: IN PROGRESS — P0 ENGINEERING BASELINE; REAL-PAPER AND TARGET-HARDWARE ACCEPTANCE PENDING
- Release status: NOT AUTHORIZED
- Default runtime: Windows 10/11; 8 GB RAM; 4 logical CPU cores; no GPU
- Default worker mode: one spawned paper worker; lazy sequential page/panel processing
- Default LLM usage: zero tokens
- OCR: optional, disabled by default, loaded lazily and reused within each worker

## Current milestone

**M1 — Core implementation and verification**

The initial executable framework and a substantial portion of the P0 data path have been committed. The repository now contains a Python package, CLI, read-only input adapter, paper context index, PDFium backend wrapper/probe, bounded scheduler, canonical paper artifacts, SQLite catalog, query/export, review patch application, domain profiles, offline review helper, regression tests, and Windows CI workflow.

This is an implementation milestone, not a production-readiness claim. The native PDF backend spike has not been completed with the required 3–5 user-approved PDFs. The current digitization algorithms are deliberately conservative and only automatically digitize explicitly specified/low-ambiguity traces. No general-purpose automatic vector-curve digitizer or broad automatic chart classifier is claimed.

## Progress summary

Status key:
- **CODE PRESENT — TEST PENDING**: implementation exists, but no successful automated test run has yet been recorded.
- **PARTIAL**: some required behavior exists; acceptance criterion is not fully met.
- **BLOCKED ON USER INPUT**: requires user-approved source PDFs/annotations or target-machine measurements.
- **DEFERRED**: P1/P2 or release-only work not started.

| Area | Status | Current evidence / remaining limitation |
|---|---|---|
| Frozen Task Plan | COMPLETE — IMMUTABLE | \`TASK_PLAN_v1.4.1.md\`; no implementation edits have been made to it |
| Repository/package/Skill entry | CODE PRESENT — TEST PENDING | \`pyproject.toml\`, \`SKILL.md\`, \`README.md\`, package under \`src/scientific_figure_data\` |
| Windows installation/CI | VERIFIED IN CI | Windows CI #152 passed package install, compileall, Ruff, and 58 pytest tests on Python 3.11, 3.12, and 3.13; hosted-runner CI is not the user's 8 GB target-machine measurement |
| Read-only upstream adapter | PARTIAL | Recognizes common chem-literature output files and hashes inputs; actual upstream layout/version compatibility needs representative corpus fixtures |
| Corpus manifest/fingerprints | CODE PRESENT — TEST PENDING | Lazy file iteration, SHA256 snapshots, JSONL corpus manifest, POSIX internal paths, Windows-safe paper IDs |
| MAIN/SI text context | CODE PRESENT — TEST PENDING | Line-streamed MAIN/SI/table index; spills to SQLite above configured in-memory budget; preserves source snippets/line numbers |
| PDF page handling | PARTIAL | PDFium page-at-a-time access/rendering and native object inventory; actual backend comparison and path coverage not yet validated |
| PDF backend technical spike | BLOCKED ON USER INPUT | Probe exists; 3–5 representative real PDFs are needed. No final vector backend selection is claimed |
| Figure/Panel inventory | PARTIAL | Consumes upstream Figure inventory; stores shared legend references and panel records; automatic panel segmentation/confidence calibration is incomplete |
| Hybrid evidence | PARTIAL | Stores page-level native text/object/path inventory alongside raster panel evidence; full native text-coordinate/axis extraction and vector curve reconstruction remain incomplete |
| P0 curve digitization | PARTIAL | Explicit ordered pixel polyline and conservative explicit-color monotonic raster tracing; relative-signal mode is supported with explicit plot box; automatic chart recognition and broad trace extraction remain incomplete |
| CV/EIS handling | PARTIAL | Explicit point order is preserved and not sorted; automatic extraction of arbitrary raster CV/EIS loops is not implemented |
| Entity/Measurement/Condition/Series model | PARTIAL | Separate model classes and series-level evidence links; links/conditions currently require explicit adapter/override evidence for reliable assignment |
| Battery/AOP/PFAS profiles | CODE PRESENT — TEST PENDING | Inherited YAML profiles plus PFAS analyte registry; profile semantics are not yet wired into a comprehensive automatic interpretation engine |
| Units/reference electrodes | PARTIAL | Separate dimensional conversion and conservative reference conversion helpers; broad unit vocabulary and profile-integrated validation remain incomplete |
| Dual Y axis | PARTIAL | LEFT/RIGHT/UNASSIGNED field supported; automatic evidence-based axis-side classifier not yet implemented |
| QC/evidence chain | PARTIAL | Source PDF/input hashes, extraction channel, algorithm version, calibration metadata, and component QC states are recorded; QC metrics/thresholds require benchmark calibration |
| Provisional/calibrated thresholds | PARTIAL | Provisional YAML is present and selected thresholds enter cache fingerprints; no calibrated threshold file is generated because no annotated benchmark exists |
| Streaming persistence | CODE PRESENT — TEST PENDING | Panel CSV point batches; paper JSON/bundle; batched SQLite point indexing and rebuild; scheduler single writer |
| Resume/idempotency/review lock | PARTIAL — FAULT-INJECTION COVERED | Leases, retries, content/stage fingerprints, bundle integrity checks and reviewed-result lock; CI injects BrokenProcessPool, verifies retry success and finite retry exhaustion. Actual OS-level worker termination on the target PC remains unmeasured |
| Query and ML export | PARTIAL | Cursor-based query, panel-streamed CSV/JSON export, subject/condition/provenance/QC fields and warnings; full scientific comparability rules need further integration |
| Offline review helper | PARTIAL — MANUAL ACCEPTANCE PENDING | Folder selection, lazy Panel CSV loading, source crop/curve overlay, X/Y anchor editing, ordered point correction and patch export are implemented; manual Windows browser acceptance/readback remains outstanding |
| Review patch apply | VERIFIED BY REGRESSION AND FAILURE INJECTION | Schema allowlist, base SHA256, stale conflict, idempotent patch ID, version backup, Bundle hash refresh, SQLite synchronization, and rollback of CSV/JSON/Bundle when the catalog transaction fails |
| Corpus reporting | PARTIAL | Job counts, retries, elapsed time, throughput, sampled RSS, failure distribution, zero-token declaration, and free-disk start/minimum/end plus pressure-pause reason are reported; full eligible/skipped classification and peak temporary-disk accounting still need completion |
| Real-paper P0 acceptance | BLOCKED ON USER INPUT | Requires user-approved Battery/AOP/PFAS PDFs and annotated reference points/anchors |
| P1 | DEFERRED | Tables, bar/scatter/marker/error-bar automation and complex tables are not claimed |
| P2 | DEFERRED | Heatmap matrix reconstruction, advanced LC-MS/MS and specialized image reconstruction are not claimed |
| Production release | NOT AUTHORIZED | AC-102 requires all real-paper, Windows resource, licensing, and data-integrity evidence |

## Acceptance tracking by plan criteria

The canonical checklist remains AC-01–AC-102 in the frozen Task Plan. This summary does not replace or modify that checklist.

### Regression-tested code paths

- Windows matrix: Python 3.11, 3.12 and 3.13 each pass package installation, compileall, Ruff and the 58-test suite in CI #152.
- Scheduler fault injection: AC-24 retry behavior and retry exhaustion are covered by injected `BrokenProcessPool` exceptions; Lease recovery and cache reuse are also covered by tests.
- Review transaction: AC-86–AC-88 schema/base-hash/idempotency behavior plus cross-artifact rollback on injected SQLite failure are covered by tests.
- A new synthetic source-immutability test is included in the next CI commit; passing it will still not replace target-corpus/release evidence for AC-06.
- The remaining AC checklist in the frozen plan is not implicitly accepted by passing this regression suite.

### Partial or not yet accepted

- Adapter/version compatibility and failure isolation: AC-03, AC-05.
- Upstream immutability proof: AC-06.
- Full resource controls and target-Windows measurements: AC-14–AC-16; AC-17 now includes a tested low-free-disk dispatch pause, while memory pressure and target-machine measurements remain partial.
- Stage-level reuse under all failure modes: AC-25; AC-24 has synthetic BrokenProcessPool retry/retry-exhaustion coverage, not a destructive real-process kill on the target PC.
- Normalized panel geometry, independent segmentation confidence, and revision of chart classification: AC-27, AC-29–AC-30.
- Real backend comparison and final backend selection: AC-31–AC-32.
- Dependency/license verification: AC-36.
- General P0 extraction coverage: AC-37, AC-39, AC-42–AC-45.
- Different series linked automatically to different subjects: AC-48.
- Full domain-specific comparability semantics: AC-55–AC-57.
- Original/standardized measurement values and comprehensive unit interpretation: AC-60.
- Multi-dimensional QC and benchmark-calibrated metrics: AC-66–AC-70.
- Review visualization and complete review editing: AC-81; local-browser manual acceptance remains pending.
- Full ML comparability and provenance contract: AC-92–AC-93.
- Full corpus report fields: AC-94; free-disk metrics are present, but the complete eligible/skipped and peak temporary-disk breakdown is not yet satisfied.

### Blocked or deferred

- Real annotated benchmark and calibrated thresholds: AC-16, AC-31–AC-32, AC-36, AC-68–AC-70, AC-102.
- P1: AC-51, AC-99–AC-100.
- P2: AC-101.
- Release boundary: AC-06, AC-16, AC-36, AC-68, AC-94, AC-102 remain release-gated.

## Tests and evidence

### Added test assets

- \`tests/test_core.py\`: input fingerprinting, paper discovery, role detection, cross-page context spill, calibration, ordered paths, reference-scale conservatism, unit/PFAS/Battery rules, evidence-backed entity linking, profile inheritance, measurement-condition isolation, streaming catalog rebuild, review patch apply/conflict/idempotency, and CLI parser coverage.
- \`.github/workflows/windows-ci.yml\`: Windows runner matrix for Python 3.11, 3.12, and 3.13; package install, compileall, Ruff undefined-name/import checks, and pytest.
- \`docs/PDF_BACKEND_SPIKE.md\`: required 3–5-PDF backend protocol.

### Verification state

- Test source files have been committed; the source-immutability test added in the 2026-11-20 update brings the suite to 59 tests and is awaiting the next Windows CI run.
- The Windows CI workflow has been committed.
- Windows CI run #39 passed package install, compileall, Ruff, and all 15 tests on Python 3.11, 3.12, and 3.13.
- Windows CI run #45 passed package install, compileall, Ruff, and all 17 tests on Python 3.11, 3.12, and 3.13. This run included the full CLI workflow and scheduler cache-reuse tests.
- Windows CI #152 passed the 58-test suite on Windows Python 3.11, 3.12 and 3.13; each job passed installation, compileall, Ruff and pytest.
- Windows CI #149 passed the injected Worker-pool crash/retry, retry-exhaustion, and review-rollback tests on all three Python versions.
- Windows CI #150–#152 passed the low-free-disk dispatch guard and CLI parameter tests; #152 is the latest completed full matrix before the source-immutability addition.
- Added an optional backend spike that performs per-page measurements with PDFium, PDFMiner, and pikepdf/QPDF. The extra libraries are not part of the default installation.
- The assistant-side environment could not retrieve the repository archive for an independent local execution; GitHub file operations remain available.
- Synthetic tests, even when they pass, do not count as real-paper scientific acceptance.

## Engineering log

### 2026-11-20 — Failure recovery and disk-pressure protection

- Added deterministic fault-injection coverage for a BrokenProcessPool worker crash followed by recovery, finite retry exhaustion, and review rollback after the SQLite transaction is forced to fail. The rollback test verifies byte-identical restoration of digitization.json, panel_series.csv and paper_bundle.json, and no catalog commit.
- Added `--min-free-disk-mb` (default 256 MiB). The scheduler checks available space before each new dispatch, stops scheduling below the threshold, allows active work to drain, and records start/minimum/end free-space values and pause reason in run_report.json. `0` disables the guard.
- Windows CI #149–#152 passed the 58-test source state on Python 3.11, 3.12 and 3.13; #152 also passed compileall and Ruff.
- Added a synthetic source immutability regression test; its CI verification is pending in this update.

### 2026-11-19 — M1 corpus/P0 verification increment

- Added conservative PDFium vector trace selection using path type, paint mode, stroke color/width, segment order, plot geometry and page-to-panel coordinate transforms.
- Added native PDF text numeric tick extraction first, optional OCR margin-based tick extraction second, with monotonic anchor validation.
- Added chart-family preclassification and a conservative raster path for simple charts: provisional rectangular plot-frame detection, unique chromatic-family detection and monotonic trace reconstruction.
- Added Hybrid routing: native vector is preferred; if multiple native candidates remain and one raster color family is independently unique, raster fallback is allowed and the ambiguity is retained in metadata. Multi-color or multiple same-color bands are not auto-selected.
- CV/EIS continue to preserve explicit ordered paths; they are not routed through the monotonic color tracer.
- Added source/paper identity consistency, root-vs-nested paper discovery, and resume based on input SHA256, algorithm source fingerprint, profile/QC configuration, extraction options and bundle integrity.
- A reviewed result with a broken/mismatched bundle is BLOCKED by default; explicit force recompute is required and creates a prior-version backup.
- Added review-helper X/Y anchor editing. Applying a patch recalibrates panel CSV values from pixel coordinates, refreshes Series metadata, synchronizes affected SQLite point rows in bounded batches and refreshes bundle hashes.
- Current test suite: 54 tests. Windows CI #146 passed the full suite on Python 3.11, 3.12 and 3.13, including compileall and Ruff.
- Real-paper accuracy, backend choice and calibrated QC remain unverified and are not claimed.

### 2026-11-19 — M0/M1 implementation

- Verified the frozen Task Plan and retained it unchanged.
- Followed the user's explicit selection of \`Tuzhidingdong/Figure_digitization\` as the implementation repository.
- Added package metadata, models, hashing, adapter, compact text context, PDFium adapter/probe, calibration and conservative raster trace primitives.
- Added one-writer SQLite schema/catalog, paper JSON artifacts, panel CSV persistence, corpus scheduler, leases, retries, and run report.
- Added inherited Battery/AOP/PFAS profiles and conservative units/reference-electrode/PFAS semantic helpers.
- Added query/export, offline review helper, review patch apply with stale-hash rejection, and Windows CI workflow.
- Changed catalog rebuild and ML export to stream point rows in bounded batches rather than accumulating a full paper or corpus point matrix in memory.
- Added cache artifact-hash validation and cleanup of incomplete panel CSV outputs left by interrupted workers.
- Updated the implementation to attach source PDF SHA256, input fingerprint, algorithm version, extraction channel, and component QC states to series evidence.
- CI run #39: 15 tests passed on each Windows Python 3.11/3.12/3.13 runner.
- CI run #45: 17 tests passed on each Windows Python 3.11/3.12/3.13 runner, including the end-to-end CLI and scheduler cache-reuse tests.
- Post-run-45: added a fake-PDFium test for TextPage lifetime; run #49 exposed a missing backend identifier on PdfPageView and the fix is committed, pending rerun.
- Extended the backend probe to measure PDFium native object evidence, PDFMiner layout/text objects, and pikepdf/QPDF content-stream operations page by page; real PDF measurements remain blocked on user-approved sample PDFs.

## Latest verification — 2026-11-20

- The current source is expected to contain 59 regression tests after the new source-immutability fixture is added; the latest completed CI #152 verified 58 tests before that final test addition.
- Windows CI run #152 passed on Windows Python 3.11, 3.12 and 3.13. Each runner passed package installation, compileall, Ruff (imports/undefined names), and the full pytest suite (58 tests).
- The four failures from runs #142/#143 were fixed:
  1. OCR tick extraction now accepts an explicit absolute pixel Plot Box even when the caller supplies OCR rows without a source image; normalized boxes still require image dimensions.
  2. Review-axis test expectations now match the source pixels and pixel-to-value slopes; untouched Series values are asserted unchanged.
  3. A generic "wavenumber" label alone no longer forces FTIR classification.
  4. Hybrid raster fallback provenance is retained in final Series metadata.
- Run #146 validates software behavior using synthetic fixtures. It does not validate numerical accuracy on real scientific figures.
- Frozen TASK_PLAN_v1.4.1.md remains unchanged. No release or publication has been authorized.

## Current blockers / next engineering actions

1. Run the PDF backend technical spike on 3–5 user-approved real PDFs. Compare PDFium, PDFMiner and pikepdf/QPDF for text, vector paths, embedded images, clipping, rotation, Form XObjects, path fragmentation and text-as-path; record per-page time, Peak RSS and licensing.
2. Validate P0 extraction against user-approved, human-annotated Battery, AOP and PFAS figures. Measure axis calibration residuals and curve point errors before setting QC thresholds or claiming scientific accuracy.
3. Measure memory, CPU, disk and recovery behavior on the user's Windows 10/11 target configuration (8 GB RAM, 4 logical cores); hosted CI and synthetic pressure tests are not substitutes.
4. Manually validate the offline review helper in a Windows browser, including local folder selection, source overlay, axis/point edits, patch export and CLI apply/readback.
5. Complete the remaining corpus report breakdown (eligible/skipped states and peak temporary disk usage), expand upstream layout compatibility checks, and collect source immutability evidence on representative corpus folders.
6. Keep P1/P2 deferred until P0 has real-paper accuracy and operational acceptance.

## Non-negotiable constraints

- Do not edit \`TASK_PLAN_v1.4.1.md\`.
- Do not modify the upstream \`chem-literature\` repository or any of its source artifacts.
- Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU is the baseline target.
- One worker by default; lazy synchronous streaming inside a paper worker.
- Bounded dispatch only at real asynchronous boundaries; no unnecessary internal queues.
- Heavy PDF/image buffers must be loaded on demand and released promptly.
- Workers never write to SQLite; one parent process owns catalog writes.
- Zero LLM tokens by default. No hidden model calls and no paid-model fallback.
- Review patches must be base-hash checked; accepted results must not be overwritten by default.
- Unsupported scientific values/relationships remain UNKNOWN, UNASSIGNED, or NEEDS_REVIEW.
- No production-ready claim or release without real-paper benchmark, Windows resource, licensing, and integrity evidence.
