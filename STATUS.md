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
- Implementation status: IN PROGRESS — NOT READY FOR LOCAL ACCEPTANCE
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
| Windows installation/CI | PARTIAL | Windows Actions workflow covers Python 3.11–3.13; no successful run result has been retrieved yet |
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
| Resume/idempotency/review lock | PARTIAL | Leases, retries, content/stage fingerprints, cache artifact hash checks, version backup, reviewed-result protection; crash-recovery tests remain pending |
| Query and ML export | PARTIAL | Cursor-based query, panel-streamed CSV/JSON export, subject/condition/provenance/QC fields and warnings; full scientific comparability rules need further integration |
| Offline review helper | PARTIAL | Folder selection, source crop/overlay, metadata correction and review-patch export; direct point editing, axis-anchor editing and full visual QC workflow remain incomplete |
| Review patch apply | CODE PRESENT — TEST PENDING | Schema allowlist, base SHA256, stale conflict, idempotent patch ID, version backup, bundle hash refresh and SQLite update |
| Corpus reporting | PARTIAL | Job counts, retries, elapsed time, throughput, sampled RSS, failure distribution, and zero LLM token field; complete eligible/skipped/disk metrics need more verification |
| Real-paper P0 acceptance | BLOCKED ON USER INPUT | Requires user-approved Battery/AOP/PFAS PDFs and annotated reference points/anchors |
| P1 | DEFERRED | Tables, bar/scatter/marker/error-bar automation and complex tables are not claimed |
| P2 | DEFERRED | Heatmap matrix reconstruction, advanced LC-MS/MS and specialized image reconstruction are not claimed |
| Production release | NOT AUTHORIZED | AC-102 requires all real-paper, Windows resource, licensing, and data-integrity evidence |

## Acceptance tracking by plan criteria

The canonical checklist remains AC-01–AC-102 in the frozen Task Plan. This summary does not replace or modify that checklist.

### Code is present; automated verification is pending

- Input/model foundation: AC-01, AC-02, AC-04 (partial input-schema coverage), AC-07–AC-13, AC-18–AC-23.
- Core figure/storage/query plumbing: AC-26, AC-28, AC-33–AC-35, AC-38, AC-40–AC-41, AC-46 (conservative fallback only), AC-47, AC-49–AC-50, AC-52–AC-54, AC-58–AC-59, AC-61–AC-65, AC-71–AC-80, AC-85–AC-91, AC-95–AC-98.
- Review patch behavior is implemented but still requires test execution: AC-82–AC-83 and AC-86–AC-88.

### Partial or not yet accepted

- Adapter/version compatibility and failure isolation: AC-03, AC-05.
- Upstream immutability proof: AC-06.
- Full resource controls, pressure handling, and Windows measurements: AC-14–AC-17.
- Worker crash recovery and valid stage-level reuse under failure: AC-24–AC-25.
- Normalized panel geometry, independent segmentation confidence, and revision of chart classification: AC-27, AC-29–AC-30.
- Real backend comparison and final backend selection: AC-31–AC-32.
- Dependency/license verification: AC-36.
- General P0 extraction coverage: AC-37, AC-39, AC-42–AC-45.
- Different series linked automatically to different subjects: AC-48.
- Full domain-specific comparability semantics: AC-55–AC-57.
- Original/standardized measurement values and comprehensive unit interpretation: AC-60.
- Multi-dimensional QC and benchmark-calibrated metrics: AC-66–AC-70.
- Review visualization and complete review editing: AC-81.
- Full ML comparability and provenance contract: AC-92–AC-93.
- Full corpus report fields: AC-94.

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

- Test source files have been committed.
- The Windows CI workflow has been committed.
- **No successful CI run is recorded in this STATUS update.**
- The assistant-side environment could not retrieve the repository archive for an independent local execution; GitHub file operations remain available.
- Synthetic tests, even when they pass, will not count as real-paper scientific acceptance.

## Engineering log

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
- Regression tests: 15 currently pass on each Python 3.11/3.12/3.13 runner for the CI run #39 source snapshot. Additional later commits are awaiting the refreshed CI run.

## Current blockers / next engineering actions

1. Resolve any static, import, package-build, or test failures reported by Windows CI; do not mark tests passed without the actual run result.
2. Finish end-to-end CLI smoke tests over a small synthetic upstream directory: scan → dry-run → run → status/report → query → export → index rebuild → validate.
3. Add regression tests for worker crash/lease recovery, reviewed-result locks, stale input changes, cache invalidation, source immutability, and low-memory/disk-pressure behavior.
4. Finish review helper editing for point paths and axis anchors, and verify patch provenance in the UI workflow.
5. Improve P0 chart family/axis evidence extraction and vector/raster hybrid routing without extending unsupported automation claims.
6. Run the PDF backend technical spike on 3–5 user-approved real PDFs and record per-page time, Peak RSS, object/path coverage, and licensing decisions.
7. Validate the P0 extraction path against user-approved annotated Battery, AOP, and PFAS papers; generate calibrated QC thresholds only from those annotations.
8. Keep P1/P2 deferred until the P0 evidence chain and benchmark results are acceptable.

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
