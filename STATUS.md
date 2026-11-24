# STATUS — Figure_digitization

Updated: 2026-11-23 (Asia/Singapore)

## Baseline and governance

- Downstream repository: [Tuzhidingdong/Figure_digitization](https://github.com/Tuzhidingdong/Figure_digitization). It remains independent of the read-only upstream `Tuzhidingdong/chem-literature`.
- Frozen plan: `TASK_PLAN_v1.4.1.md`; SHA256/blob SHA recorded by GitHub fetch: `80b02880a1485e1d8f6ad6ccaeac723ea2597ef3`. The plan is unchanged.
- Current validation work is on `feat/real-image-regression-diagnostics` and open draft PR #22; this branch is not yet merged to `main`. No Release/tag or production-readiness claim has been made.
- Default execution remains one spawned CPU worker, zero LLM tokens, no GPU requirement, and no paid-model fallback.

## Current milestone

The P0 engineering implementation has been extended beyond the previous M1 baseline. The current code adds upstream package compatibility and integrity checks, safer Panel provenance, downstream review-image availability, bounded temporary-disk accounting, explicit semantic warnings, condition-value querying, and per-paper scheduler preflight isolation.

These are software-engineering results. They do not establish scientific point accuracy. Outputs remain provisional until real annotated-paper benchmarks and manual acceptance are completed.

## Progress summary

- Current Chem-Literature 1.1 packages are discovered at `runs/preprocessed/<paper_id>/01_preprocessing`. The adapter reads the evidence index, follows the MAIN PDF reference, associates exact figure media assets, and keeps absolute paths out of serialized manifests.
- MAIN PDF and image hashes are rechecked at the point of Worker use/copy; changes between scan and processing or during processing force `NEEDS_REVIEW`.
- Upstream Figure bboxes are not silently relabelled as Panel boundaries. Source bbox, normalized bbox, coordinate space, provenance, segmentation status, and confidence status are stored separately.
- Verified upstream images are copied byte-for-byte into downstream `papers/<paper_id>/evidence/`; the offline reviewer looks up the actual evidence filename. Upstream files remain unchanged.
- Corpus reporting now exposes explicit completion/review/failure/retry counts, run-scoped SFD temporary-disk peak and cleanup/isolation telemetry, plus algorithm/profile/QC fingerprints.
- Condition queries match both condition names and serialized values.
- Explicit Battery/AOP/PFAS measurement semantics can be supplied in per-series overrides; missing or incompatible metrics produce warnings without automatic conversion or harmonization.
- Scheduler preflight and retry-snapshot failures are recorded per paper; BrokenProcessPool submission failures receive finite retry handling.

## Acceptance tracking by plan criteria

### Regression-tested code paths

- **AC-03/04:** Chem-Literature 1.1 and legacy figure-inventory image paths are recognized; package version and input fingerprints are captured.
- **AC-05:** Snapshot/preflight failure isolation is tested with a bad paper followed by a valid paper; retry snapshot and submission errors are isolated. BrokenProcessPool submission retry is bounded.
- **AC-06:** Integration tests compare the upstream package path set and SHA256 values plus the external MAIN PDF size/hash before and after downstream processing. This is synthetic fixture evidence, not representative-corpus acceptance.
- **AC-17/24/25:** Resource-pressure guards, finite retry, recovery, and resume/cache paths have regression coverage. Target-PC destructive crash/recovery acceptance is still pending.
- **AC-27/29:** Panel source/normalized geometry and segmentation provenance/status/confidence are stored separately. An evidence-index Figure bbox with unresolved semantics is not reused as a Panel bbox.
- **AC-47–50/52:** Subject entity, condition, measurement, series, and series-subject link storage/query paths have synthetic integration coverage.
- **AC-55–57:** Explicit measurement-semantic warning paths cover Battery capacity bases, AOP metric non-interchangeability, and PFAS metric non-interchangeability. This is an evidence-backed guardrail, not automatic domain interpretation.
- **AC-66/67/69/71:** Per-series evidence, independent QC dimensions, panel-segmentation metadata, and conservative review routing are covered by regression tests.
- **AC-74–79/86–88:** Bundle hashes, cache/review versioning, stale-patch conflict, and idempotent review-apply paths remain regression-tested.
- **AC-89–93:** CLI, query, ML export, provenance and comparability warning paths are tested. Condition filtering now includes values as well as names.
- **AC-94/95–98:** Run reports expose named corpus counters, throughput, CPU/RSS, run-scoped temporary disk, algorithm/profile/QC fingerprints, and zero LLM token usage. P0/P1/P2 boundaries are documented.

### Partial or not yet accepted

- **AC-03/05:** Supported layouts are covered by current and legacy fixtures; exhaustive upstream version/layout compatibility remains partial.
- **AC-06:** Source immutability is proven on synthetic fixture trees; representative user corpus confirmation remains release-gated.
- **AC-16:** The local Windows sampler is implemented and parse-checked in CI, but has not been run on the target 8 GB / 4-core Windows machine.
- **AC-25:** Cache/resume behavior has synthetic coverage; full recovery under target-PC failure and disk-pressure conditions is pending.
- **AC-30:** Software-side classification revision is implemented and regression-tested: manual family selection requires reviewer evidence; technique/axis-label changes reclassify deterministically; panel summaries, SQLite, bundle hashes, revision history and rollback are covered. Human Windows browser acceptance remains local.
- **AC-31/32:** PDF backend comparison and final backend choice require 3–5 approved representative real PDFs.
- **AC-36:** Windows/Python 3.12 SBOM and package metadata inventory generation is automated for all declared extras. Manual review of raw/missing declarations, native-wheel notices, OCR model/data terms, and the project's own licensing decision remains release-gated.
- **AC-37–46:** P0 extraction routes and low-ambiguity guards are implemented; scientific accuracy for supported plot families is not established without annotated real figures.
- **AC-48:** Evidence-backed series-level subject links and cross-technique queries work; automatic subject assignment from real legends/text remains partial.
- **AC-55–60:** Battery/AOP/PFAS semantic guardrails remain explicit and conservative; LOD/LOQ retains comparator and limit metadata without converting censored results to numbers. Export schema 1.2 supports explicitly requested per-axis dimensional conversions with separate X/Y statuses, method/evidence IDs, unresolved warnings, and unchanged original values/units. This does not implement the separate P1 scalar-observation ingestion workflow.
- **AC-68–70:** Thresholds remain provisional; no calibrated real-paper benchmark or point-error report has been accepted.
- **AC-30/80–83/86–88:** Offline review exposes chart-family revision and axis-label corrections; patch application recomputes or explicitly overrides preliminary classification with revision history. Panel summaries, bundle hashes and SQLite index update transactionally with rollback coverage. Human browser acceptance remains pending.
- **AC-92/93:** ML export schema 1.2 preserves originals, units, identity, conditions, provenance and QC/review state; explicit whitelisted dimensional conversions are supported without overwriting originals. Cross-series comparability remains `NOT_HARMONIZED`; no automatic pooling or reference-electrode conversion occurs.
- **AC-94:** Scheduler-level SFD temporary scratch peak is reported, but target-PC and representative-corpus reconciliation is not complete.

### Blocked or deferred

- **AC-16:** Target Windows hardware resource run.
- **AC-31/32/68–70/102:** 3–5 approved real PDFs, manual point annotations, backend comparison, and scientific accuracy/QC calibration.
- **AC-36:** Manual legal review of package metadata declarations, native-wheel bundled notices, OCR model/language-data terms, transitive OCR dependencies, and the project's own license decision.
- **AC-81:** Manual browser workflow acceptance.
- **AC-51/99/100:** P1 table/scalar, bar/scatter, error-bar, marker and complex table support.
- **AC-101:** P2 heatmap, advanced LC-MS/MS and specialized image reconstruction.
- **Release boundary:** AC-06, AC-16, AC-36, AC-68, AC-70, AC-94 and AC-102 remain release-gated.


## 2026-11-22 — Figure-local classification and explicit calibration reporting

- Restricted automatic CV classification to explicit technique wording or a paired panel-local potential/voltage X-axis plus current Y-axis. Removed generic single-word triggers such as `potential` and `current density`; page-level native text is no longer used as chart-family routing evidence because it can contain unrelated body discussion and cross-references. Weak/ambiguous evidence remains `UNCLASSIFIED` / `NEEDS_REVIEW`.
- Added regression cases for SEM captions accompanied by unrelated page text, body sentences mentioning potential, and valid paired CV axis labels.
- Added an explicit `calibration_state` and matching QC component that distinguish both numeric axes calibrated, partial calibration, X numeric/Y relative signal, and unresolved numeric calibration. The overall `PROVISIONAL_UNCALIBRATED` status intentionally remains unchanged until QC thresholds are benchmark-calibrated against annotated real papers; axis calibration alone is not scientific acceptance.
- Documented the existing per-series `plot_box` override in `docs/INPUT_CONTRACT.md`, including coordinate system, normalized/pixel forms, bounds, and the distinction between reviewer-supplied geometry and scientific acceptance.
- Added QC regression coverage proving that two numerically calibrated axes can coexist with provisional scientific QC status.
- This branch has not yet been run through GitHub Actions or local Windows synchronization. Awaiting CI and local Agent verification; no Release/tag is authorized.

## Tests and evidence

- Test files: `tests/test_core.py`, `tests/test_upstream_compat.py`, `tests/test_temp_disk_monitor.py`, `tests/test_dependency_audit.py`.
- Current source count before this branch: **117 test functions / 121 pytest cases** (two parametrized functions contribute four additional cases).
- Latest source/test HEAD `f597d01f4e14c728d09394c04875ca70164d169a`: [Windows CI #44747871501](https://github.com/Tuzhidingdong/Figure_digitization/actions/runs/44747871501), all test jobs passed on Python 3.11, 3.12 and 3.13; compileall, Ruff and Windows harness parse check passed.
- CI validates Python 3.11, 3.12, 3.13 on hosted Windows; it is not a substitute for the target-PC measurement or scientific benchmark.

## Engineering log

### 2026-11-20 — Export, semantics, multi-paper identity and report hardening

- Namespaced generated Series IDs by paper identity, with stable hash suffixes where sanitization/truncation is required. Spawned two-paper integration proves same Figure1/a panel names no longer collide in the global SQLite primary key.
- Upgraded point export to schema 1.2: each row includes point index, values and explicit raw copies, units, per-axis optional standardized values/statuses, pixel/error fields, subject links/evidence, measurement conditions, source/QC/review/extraction state, and explicit NOT_PERFORMED/NOT_HARMONIZED statuses. JSON numeric types are preserved.
- Made scientific comparability conservative: missing battery capacity/cell/current-density/protocol dimensions remain UNRESOLVED; PFAS metrics are not conflated; reference conversion rejects non-finite inputs and outputs.
- Improved nested upstream version detection using exact paper-relative artifact paths and producer/version metadata rather than repeated basename searches.
- Expanded corpus reports with parent/worker CPU seconds, average core use and total/peak per-paper evidence/context-index storage. The context-index size is measured once per paper to avoid rescanning a large SQLite index for every panel.
- Enforced non-overlapping input/output directory trees at CLI and scheduler entry points; tests verify rejected paths leave upstream source hashes unchanged.
- Windows CI #187 passed 70 pytest cases, compileall and Ruff on Python 3.11, 3.12 and 3.13.

### 2026-11-20 — Job ledger, worker identity and corpus identity consistency

- Extended `jobs` with `worker_id`, `worker_pid`, `started_at` and `input_fingerprint`, using additive SQLite migrations for existing catalogs.
- Parent scheduler creates the input snapshot once and passes it to the spawned worker, avoiding duplicate full artifact hashing in the worker. The worker returns its PID; only the parent writes that PID to SQLite.
- Normalized single-paper-root runs to the same `root-paper` storage ID for Job Ledger, canonical output and resume. Added a collision detector that preserves established storage IDs but fails before scan/run when two source directories would map to the same output ID.
- Added root-paper Spawn integration coverage for actual worker PID, worker slot ID, start time, input fingerprint, job state and canonical output directory.
- CI #170 passed all 65 tests, compileall and Ruff on Python 3.11, 3.12 and 3.13.

### 2026-11-20 — Incremental context cache and cross-platform verification

- Added content-fingerprinted reuse of per-paper context indexes. Unchanged MAIN/SI/table text reuses the prior JSON/SQLite context index; changed inputs rebuild the index. Rebuilds write to a temporary SQLite database and atomically replace the active cache only after closing the DB handle.
- Added a regression test for unchanged cache reuse and changed-source invalidation, including the disk-backed SQLite path.
- Fixed Windows SQLite file replacement by explicitly closing validation/search connections. A first CI attempt exposed this Windows-specific handle behavior; the corrected source passed.
- Windows CI #157 passed all 60 regression tests, compileall and Ruff on Python 3.11, 3.12 and 3.13.

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

## Additional P0 follow-up — 2026-11-20

After the previous status sync, the following software-level gaps were addressed:

- Scheduler preflight snapshot errors and retry-snapshot errors are recorded as per-paper failures; BrokenProcessPool raised by submit receives a finite retry path. A regression test verifies that a bad paper does not stop a later valid paper.
- Condition queries now search both condition names and serialized values.
- Battery/AOP/PFAS export warnings consume only explicit per-series measurement_semantics; AOP/PFAS metric-role conflicts and missing Battery capacity bases remain warnings, never automatic conversions.
- Reference-electrode conversion now retains every required condition including pH and records the scale factor/offset. Dimensional conversion rejects NaN/Infinity and non-finite results.
- Normalized Panel bboxes are validated for finite, ordered 0–1 coordinates; invalid boundaries are retained as review-required rather than drawn as valid geometry.
- README and Windows benchmark examples consistently use the Chem-Literature runs/preprocessed input root.

These changes are code-complete in the current branch. Their final Windows CI result must be checked against the matching current HEAD before this follow-up is called regression-accepted. Real-paper scientific accuracy, target-PC resource measurement and manual browser review remain external acceptance items.

## 2026-11-23 follow-up — real upstream-package integration and bounded image scan

- The P3_02 end-to-end regression now enters through the Chem-Literature 1.1 package layout (`01_preprocessing/evidence_index.json`) rather than the simplified standalone `figure_inventory.json` path. It uses only the already committed real-image fixture and archived OCR JSON; it checks that the OCR fixture SHA256 matches the exact image bytes.
- The integration fixture verifies the external MAIN-PDF reference hash contract, upstream package-version detection, source-asset provenance, and that every file in the input package plus the referenced external PDF remains byte-identical after downstream processing. It also confirms that absolute external PDF paths are not serialized into the snapshot.
- Important boundary: the external PDF in this test is a minimal synthetic signature/hash fixture. This validates the upstream reference/integrity contract only; it is not a real-PDF backend test and does not replace the planned 3–5 user-approved PDF comparison.
- The P3_02 pipeline assertions retain the scientific safety boundary: dual-Y-axis curve geometry can be persisted while the side remains `UNASSIGNED`; no candidate y-value is written as a final numeric value without a supported assignment.
- Plot-frame candidate scanning now downsamples to at most 5,000,000 analysis pixels before RGB conversion, avoiding an additional full-resolution RGB conversion buffer for large grayscale/RGBA/CMYK inputs. A regression test checks that conversion is performed only on the bounded analysis image. This bounds the analysis image, not every decoder/native-library allocation.
- Matching Windows CI [#45173075740](https://github.com/Tuzhidingdong/Figure_digitization/actions/runs/45173075740) passed the upstream-package integration on Python 3.11, 3.12 and 3.13. Latest code/performance run [#45173235199](https://github.com/Tuzhidingdong/Figure_digitization/actions/runs/45173235199) passed the same matrix and RapidOCR 3.10.0 compatibility check.

## Latest verification

- AC-30 classification revision is implemented: manual family selection requires reviewer evidence; technique/axis-label edits trigger deterministic reclassification; history, panel summaries, SQLite, bundle hashes and rollback are covered. CI [#44744604564](https://github.com/Tuzhidingdong/Figure_digitization/actions/runs/44744604564) passed on Python 3.11, 3.12 and 3.13. Human browser acceptance remains local.
- AC-36 dependency inventory generation is automated. The Windows/Python 3.12 workflow installs all declared extras and uploads a CycloneDX 1.6 SBOM, resolved-package snapshot and package metadata report. Latest matching run: [#44747870960](https://github.com/Tuzhidingdong/Figure_digitization/actions/runs/44747870960); artifact ID `14634007008`.
- AC-60 export schema 1.2 supports explicitly requested per-axis dimensional conversions. Only exact pairs in the deterministic factor table are converted; originals are preserved; unresolved axes remain empty and produce warnings; reference-electrode conversions remain separate. P1 scalar-observation ingestion is not included.
- Latest source/test commit: `501fa2c924f1bfedbd12aefff21359db8d3758e7`. Matching Windows CI [#45173235199](https://github.com/Tuzhidingdong/Figure_digitization/actions/runs/45173235199) passed the Python 3.11, 3.12 and 3.13 test jobs and RapidOCR 3.10.0 compatibility check.
- Current test source count on this branch: **151 test functions across seven Python test modules**; parametrized functions expand the collected pytest case count.
- Frozen Task Plan blob SHA: `80b02880a1485e1d8f6ad6ccaeac723ea2597ef3`; unchanged. The upstream repository remains untouched. No Release/tag was created.

## Current blockers / next acceptance actions

1. Run the PowerShell resource harness on the actual target Windows 8 GB / 4-core machine with an approved small corpus; record machine specifications, peak memory, temporary disk use, timing and report output. Hosted Windows CI is not this acceptance.
2. Compare PDFium/high-level and raw APIs, pdfminer.six, and pikepdf/QPDF on 3–5 user-approved real PDFs; retain JSON probe reports and inspect clipping, rotation, Form XObjects, text-as-path and fragmented paths before selecting a backend.
3. Use manually annotated Battery, AOP and PFAS figures/axes to calculate anchor residuals and point errors before calibrating thresholds or claiming scientific accuracy.
4. Open the offline review helper in Windows and verify real image loading, overlays, panel/axis/point editing, patch export/apply and readback. Code tests do not replace human browser acceptance.
5. Review the generated dependency/license artifact (37 package metadata records were marked for manual review in the captured package set); inspect native-wheel notices, RapidOCR model/data terms, the transitive `opencv-python-headless` wheel, and the project's own license decision. SBOM generation is complete, but is not legal approval.
6. Keep P1 (scalar table/text observations, tables, bars/scatter, error bars, marker-dependent and complex curve separation) deferred. Keep P2 (heatmaps, advanced LC-MS/MS and specialized reconstruction) deferred.

GitHub regression success establishes software behavior for the tested fixtures and hosted Windows versions only. It does not establish representative-corpus integrity, scientific digitization accuracy, calibrated QC, target-PC resource acceptance, or production readiness.
 
## Non-negotiable constraints

- Do not modify, move, rename or delete anything in the upstream `chem-literature` repository or its input directories.
- Do not modify `TASK_PLAN_v1.4.1.md`; update this `STATUS.md` instead.
- No model/LLM call by default; zero LLM tokens remains the default. Never auto-fallback to paid models.
- Do not claim scientific accuracy, calibrated QC, production readiness or Release from synthetic CI alone.
- Preserve raw evidence and route ambiguity to `NEEDS_REVIEW`; never invent values, identities, units or comparison semantics.

## Phase 1 automatic monotonic digitization (development PR)

- Added a conservative raster panel-geometry splitter for figures without upstream panel boundaries.
- Added OCR-positioned axis-label parsing and a guarded TraceSpecification for single-colour, X-monotonic raster curves.
- Removed the UNCLASSIFIED semantic label as a blanket blocker for visual colour-candidate detection; recognized CV/EIS/non-monotonic families remain excluded from the monotonic tracer.
- Added explicit source-image pixel crop mappings, retaining upstream media-asset bbox/page/extraction metadata without guessing PDF coordinate transforms.
- Added independent reconstruction, source-pixel overlay and all-panel comparison-sheet output.
- Scope is intentionally limited. Actual paper-image performance and Windows CI are pending; this entry does not claim scientific accuracy, general multi-panel understanding, CV/EIS, scatter or bar extraction.

