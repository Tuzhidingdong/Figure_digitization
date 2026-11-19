# STATUS — Figure_digitization

> Execution record for the frozen user-owned TASK_PLAN_v1.4.1.md. This file tracks implementation and evidence only. Do not edit the Task Plan.

## Baseline and governance

- Task Plan: v1.4.1; FROZEN — DO NOT EDIT.
- Implementation repository: Tuzhidingdong/Figure_digitization, as explicitly selected by the user after the plan was frozen.
- Upstream chem-literature: READ-ONLY; never modify, move, rename or delete upstream files.
- Branch: main. Release/publish: NOT AUTHORIZED.
- Target: Windows 10/11, 8 GB RAM, 4 logical CPU cores, no GPU.
- Default execution: one spawned paper worker, page/panel lazy streaming, one parent SQLite writer.
- Default LLM tokens: zero. No hidden model calls and no paid fallback.
- OCR: optional, disabled by default, local CPU-only; ONNX intra/inter-op threads are pinned to one.

## Current milestone

**M1 — Core implementation and P0 capability development; not yet ready for local acceptance.**

The repository has an executable downstream Python package/Skill, CLI, corpus adapter and fingerprinting, cross-page text index, PDFium page-at-a-time rendering/native objects, PDF backend probe, deterministic chart-family preclassification, plot-frame and unique-color heuristics, OCR/native-text tick parsing, conservative vector/raster extraction, scientific entities/measurements/series, domain profiles, single-writer SQLite, panel CSV artifacts, streaming query/export, scheduler/leases, and offline review workflow.

Automation is intentionally limited to low-ambiguity cases with explicit/derived plot geometry and sufficient axis evidence. Ambiguous curves retain pixels and enter review. The software is not a universal chart digitizer; real-paper accuracy has not been measured.

## Implementation status

| Area | Status | Evidence / open limitation |
|---|---|---|
| Frozen Task Plan | Complete; immutable | Task Plan unchanged |
| Independent downstream Skill | Partial | Standalone package/Skill entry exists in the user-selected repo; repo name differs from original planned name |
| Read-only adapter | Partial | Common chem-literature manifests, figure inventory, evidence index, MAIN/SI/table layout; real upstream version/layout fixtures still needed |
| Corpus discovery | Implemented; CI pending latest | Lazy discovery avoids corpus-root PDF swallowing nested papers; root/nested regression tests added |
| Canonical paper IDs | Implemented; CI pending latest | Windows-safe IDs shared by worker path, Job Ledger, Catalog and resume selection |
| Input fingerprints | Implemented; CI tested historically | Per-file SHA256, size/mtime/role snapshots and corpus manifest stream |
| MAIN/SI context | Implemented; CI tested historically | Streaming text scan with SQLite spillover over configured memory threshold |
| Scheduler and recovery | Partial | One worker default, spawn, bounded dispatch, lease/heartbeat, retries, active lease protection; process crash/BrokenProcessPool and disk/RAM pressure injection remain |
| Resume/cache | Implemented; latest CI pending | Fingerprint includes input, implementation source hashes, profiles, QC, overrides and output-relevant options; Bundle content hashes checked; unchanged papers skipped before worker |
| Reviewed-result protection | Implemented; latest CI pending | REVIEWED_ACCEPTED protected; corrupted/mismatched bundle blocks recompute; explicit force creates version backup |
| PDF backend | Partial | PDFium page-scoped render, native text/image/path evidence; vector paths are bounded evidence, not presumed traces |
| Backend spike | Blocked on user-approved evidence | Probe compares PDFium, PDFMiner and pikepdf/QPDF; 3–5 representative PDFs still required |
| Chart-family preclassification | Partial | Deterministic technique/caption/axis/native-text rules; ambiguous family stays UNCLASSIFIED |
| Plot-region/color detection | Partial; CI pending latest | Rectangle/frame and single chromatic-family heuristics; ambiguous frames/multicolor routed to review |
| Vector extraction | Partial | Conservative line-only path selection and explicit/unique object mapping; real PDFs and transformed/rotated/complex cases unvalidated |
| Raster extraction | Partial | Monotonic single-valued color tracer; multiple separated same-color bands now rejected; general CV/EIS raster loops not implemented |
| Native/OCR axis calibration | Partial | Native PDF numeric ticks preferred, optional OCR fallback, monotonic checks, evidence preserved; complex axes review-bound |
| Relative spectra | Partial | Relative signal mode; numeric Y ticks take precedence where found; real baseline types need benchmarking |
| Dual Y axis | Partial | LEFT/RIGHT/UNASSIGNED fields and partial geometry retention; no general automatic side-to-series classifier |
| Scientific entity/condition model | Partial | SubjectEntity/Condition/Measurement/Series and exact evidence links; fully automatic alias/condition resolution remains conservative |
| Battery/AOP/PFAS profiles | Implemented; CI tested historically | Inherited YAML and PFAS analytes; full profile-driven semantic extraction incomplete |
| Units/reference electrodes | Partial | Deterministic conversion helpers and strict evidence-gated reference conversion; full vocabulary/standardized-value flow incomplete |
| Provenance/QC | Partial | SHA256, source/page/panel/channel, calibration, OCR/native evidence and component QC; full metric calibration/overlay coverage not complete |
| Storage/index/query/export | Implemented; CI tested historically | Panel CSV, paper bundle hash, SQLite single writer, streamed rebuild, cursor query, ML export + metadata/warning sidecars |
| Review helper/apply | Partial | Lazy panel load, crop/curve/axis overlay, point/axis edit, hash patch, CSV recalibration and SQLite reindex; manual browser acceptance/rollback injection still needed |
| Corpus reporting | Partial | job counts, failures, throughput, sampled RSS and token count; full eligible/skipped/temp-disk/resource reporting incomplete |
| P1/P2 | Deferred | Table/bar/error bars/complex tables and heatmap/advanced LC-MS not claimed |
| Real-paper scientific acceptance | Blocked on user-approved evidence | No annotated Battery/AOP/PFAS benchmarks yet |
| Production release | Not authorized | AC-102 remains open |

## Windows CI evidence

- Workflow: .github/workflows/windows-ci.yml; Windows Python 3.11/3.12/3.13; install, compileall, Ruff, pytest.
- Historical green: run #39 (15 tests), #45 (17), #58 (19), #64 (22), #69 (23), #86 (30), all across the three Python versions.
- Run #79 exposed three implementation/test issues (fake PDF page interface, floating comparison, OCR X/Y tick boundary); fixes were made and later run #86 passed.
- Run #96: review-axis calibration test failed because its fixture used anchor pixel positions inconsistent with the source curve. The test fixture was corrected; this was not a production mapping bug.
- Run #106: Ruff found a missing test import; fixed.
- Latest main snapshot contains 51 tests: resume first-run/unchanged skip/changed input/corrupted bundle, active lease protection, algorithm/profile/option stage fingerprint invalidation, reviewed bundle integrity lock, same-color curve ambiguity, plot-frame and single/multiple color routing. **Fresh Windows CI result is pending.**
- Synthetic tests only validate code behavior. They are not real-paper scientific accuracy evidence.

## Recent engineering work

### Auto extraction
- Added deterministic chart-family preclassification for explicit/upstream technique, caption, axes and native text.
- Added conservative image plot-frame detection and unique chromatic-family selection for simple single-valued curves.
- Same-color separated pixel bands are rejected rather than median-merged.
- Native PDF tick text is preferred; OCR is only used when explicitly enabled and native text is insufficient.
- PDFium path style, typed segments, crop transform and unique/explicit vector path selection are recorded.
- Extracted provisional data is explicitly marked EXTRACTED_NEEDS_REVIEW / COMPLETED_WITH_REVIEW until human accepted.

### Streaming, cache and safety
- Catalog rebuild and ML export process point data in bounded batches.
- Panel points are persisted to merged Panel CSV and released before the next panel.
- Resume stage fingerprint includes input SHA256, algorithm implementation source hashes, profile hashes, QC config, overrides and output-relevant options.
- Valid unchanged papers are skipped before a worker starts; changed or tampered artifacts are reprocessed.
- Active RUNNING leases remain protected; expired jobs are recovered by the Job Ledger.
- Bundle content hashes are checked before cache use. REVIEWED_ACCEPTED data with a corrupt Bundle blocks rather than overwrites; explicit force recompute retains a version backup.

### Review
- Review helper supports lazy current-panel load, crop/curve/axis overlay, ordered point and X/Y axis anchor editing.
- Applying axis anchors recalibrates CSV values, synchronizes Series metadata and SQLite point rows, then refreshes Bundle hashes using a streamed rewrite.

## Current next actions

1. Inspect current Windows CI run for the 51-test snapshot; fix failures before adding more features.
2. Add/complete rollback injection for review apply and process crash/BrokenProcessPool recovery.
3. Add low-memory/disk pressure tests and measure actual RSS/throughput on a representative office PC.
4. Manually test file:// browser folder selection and Review Patch export/apply.
5. Improve P0 chart-family/Hybrid routing conservatively; keep unresolved cases in review.
6. Run the PDF backend spike on 3–5 user-approved PDFs and record page time, Peak RSS, native text/path/image coverage, clip/rotation/Form XObject/text-as-path behavior and license evidence.
7. Validate extraction against annotated Battery/AOP/PFAS figures; only then generate calibrated thresholds and report real error metrics.
8. Keep P1/P2 deferred until P0 evidence is accepted.

## Non-negotiable constraints

- Never edit TASK_PLAN_v1.4.1.md.
- Never modify upstream chem-literature artifacts.
- Windows 10/11, 8 GB RAM, 4 cores, no GPU baseline.
- One worker by default; synchronous lazy page/panel work.
- No unnecessary in-process image queues.
- Workers never write SQLite.
- Zero LLM tokens by default; no hidden model calls or paid fallback.
- Uncertain scientific semantics remain UNKNOWN/UNASSIGNED/NEEDS_REVIEW.
- REVIEWED_ACCEPTED results are protected except explicit force recompute with version backup.
- No production-ready/release claim without real-paper accuracy, Windows resource, licensing and integrity evidence.
