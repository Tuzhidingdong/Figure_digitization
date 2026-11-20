# Scientific Figure Data

An independent downstream tool for turning existing chem-literature outputs into traceable, queryable scientific figure data.

## Current implementation boundary

This repository is being implemented against the frozen v1.4.1 Task Plan. The default workflow is local, offline, single-worker, sequential, and zero-LLM-token.

The initial implementation provides corpus discovery, immutable input snapshots, compact paper context, a PDF backend abstraction, resumable paper jobs, canonical JSON/CSV artifacts, a rebuildable SQLite catalog, scientific queries, filtered exports, and hash-checked review patches.

Automated digitization is conservative. A chart is not assigned guessed axes, units, sample identity, or reference scale. If a plot does not contain sufficient machine-readable evidence or a supported extraction override, the result is routed to review. Real-paper accuracy and calibrated QC require user-approved PDFs and annotations and are not claimed by this repository's synthetic tests.

## Install

Python 3.11 or newer is required.

    python -m pip install -e .
    # PDF rendering and native text/vector evidence:
    python -m pip install -e ".[pdf]"
    # PDF + raster figure extraction:
    python -m pip install -e ".[pdf,images]"
    # Optional PDF backend comparison spike:
    python -m pip install -e ".[pdf-spike]"
    # Development:
    python -m pip install -e ".[dev]"

No GPU or LLM is required. OCR is optional and is not installed by the default package. To enable local single-thread CPU OCR, install `.[ocr]` and pass `--ocr`.

## Quick start

    sfd scan --input-root PATH_TO_CHEM_LITERATURE_OUTPUTS/runs/preprocessed --output-root PATH_TO_SFD_DATA
    sfd run --all --input-root PATH_TO_CHEM_LITERATURE_OUTPUTS --output-root PATH_TO_SFD_DATA --workers 1 --temp-disk-limit 2048 --min-free-disk-mb 256 --min-free-memory-mb 512
    sfd status --output-root PATH_TO_SFD_DATA
    sfd query --output-root PATH_TO_SFD_DATA --technique CV
    sfd export --output-root PATH_TO_SFD_DATA --format csv --out ml-export

For the current Chem-Literature output layout, point --input-root at runs/preprocessed; each <paper_id>/01_preprocessing package is discovered separately. The adapter follows the package's hash-checked MAIN PDF reference in evidence_index.json when that source PDF is stored outside the preprocessing package. Use --dry-run before a first corpus run. Existing upstream files are read-only. Input and output roots must be disjoint: neither directory may contain the other. The CLI and direct scheduler API reject same-root, nested-output, and ancestor-output layouts before writing.

## Commands

- scan: discover papers and write immutable input snapshots.
- run: process eligible papers, with --resume, --failed-only, --paper-id, --dry-run and resource controls. Resume rechecks input, implementation, profile/QC and bundle fingerprints; intact unchanged papers are skipped before a worker starts.
- status/report: inspect job state and run metrics.
- query: filter indexed papers, entities, techniques, and domains.
- export: produce CSV/JSON plus an export manifest with compatibility warnings. Export schema 1.1 is one row per digitized point and carries paper/figure/panel/series IDs, point order, reconstructed axis values, explicit raw-value copies, units, pixel coordinates, error-bar fields, series-level sample/entity links, experimental conditions, evidence/QC/review provenance and comparability warnings. JSON retains numeric types; CSV follows text-cell semantics. Standardization is explicitly `NOT_PERFORMED` and compatibility is `NOT_HARMONIZED`—the exporter never silently converts or merges units, reference scales, capacity bases, cell scopes, or PFAS metrics.
- review list: find review-required series.
- review apply --patch PATCH_PATH: apply a hash-matched review patch as a new version.
- index rebuild: recreate SQLite from canonical paper artifacts.
- validate: validate canonical artifacts and source immutability snapshots.

## Streaming and resource behavior

The default worker count is one. Within a worker, pages and figures are pulled lazily; no internal image queue is created. PDF pages are rendered on demand and released immediately. If multiple workers are explicitly enabled, the scheduler dispatch queue is bounded. Workers write paper-level artifacts and the parent process serializes SQLite writes.

A compact cross-page context index is built from existing main/SI text and extracted tables. Its cache is keyed by source content fingerprints: unchanged inputs reuse the prior JSON/SQLite index, while changed inputs invalidate and rebuild it. Visual resources remain page/figure scoped. If the text context exceeds the in-memory budget, a SQLite-backed lookup is used. The `--temp-disk-limit` (default 2048 MiB) is applied separately to each paper's evidence/native-evidence plus context-index footprint and to the run-scoped SFD scratch directory; these are separate limits, not an accumulated shared budget. The scheduler redirects spawned workers' `TEMP`, `TMP` and `TMPDIR` to a unique subdirectory under `OUTPUT_ROOT/.sfd-runtime-tmp`, samples its peak regular-file bytes, reports Worker isolation and cleanup status, and removes the run folder after workers stop. Series CSVs and version backups remain in the paper-output footprint and are protected by the free-disk guard. This is scoped SFD temporary-file accounting, not a scan of other applications' global Windows temp folders. Before each new paper is dispatched, the scheduler checks free space on the output filesystem. When free space falls below `--min-free-disk-mb` (default 256 MiB) or available system memory falls below `--min-free-memory-mb` (default 512 MiB), it stops dispatching, lets active work finish, and records the pause reason and observed resource values in `run_report.json`. Use `--resume` after freeing resources; set a threshold to `0` only to disable that guard.

## Important limitations

- The PDF backend probe measures the capabilities available in the installed builds; raw PDFium path access is not presumed complete.
- No real benchmark PDFs are included. The probe reports NO_INPUT_PDFS when no files are supplied.
- For simple charts, the raster path can provisionally detect a rectangular plot frame and a unique chromatic trace family, then use text/explicit axis anchors. Multiple color families, same-color separated bands, ambiguous frames and branching components route to review. This is a narrow heuristic, not general chart understanding.
- CV/EIS order is preserved when a trace is explicitly supplied; automatic extraction does not sort paths by X.
- Series identifiers are namespaced by paper ID, so repeated Figure1/a panel names in different papers do not collide in the global SQLite index.
- QC defaults are provisional and every such result is labeled PROVISIONAL_UNCALIBRATED.
- P1/P2 are not claimed complete.

The corpus report records parent/worker CPU time, mean core use, sampled parent-plus-worker peak RSS, free disk and available memory, per-paper evidence/context-index storage, algorithm/profile/QC fingerprints and zero default LLM tokens. Its disk footprint fields are scoped estimates, not full OS temporary-directory accounting or a substitute for target-PC profiling.

See docs/ for the input contract, storage model, backend spike protocol, and Windows usage. See STATUS.md for implementation and acceptance evidence.

## P0/P1/P2 acceptance boundary

The repository implements the conservative P0 workflow and its evidence, persistence, review, query, and export paths. **Implementation is not the same as scientific validation:** automatic outputs remain `PROVISIONAL_UNCALIBRATED` until axis/point accuracy, QC thresholds, and domain semantics are benchmarked against user-approved real PDFs with human annotations. No real-paper accuracy claim is made by the current synthetic CI suite.

P0 automation is restricted to low-ambiguity one-dimensional traces with explicit figure/axis evidence. Non-monotonic CV/EIS raster traces, marker-dependent curve identity, ambiguous same-colour branches, overlapping curves, uncertain axes, and unresolved scientific identities must remain `NEEDS_REVIEW` unless a separately validated extractor is available.

P1 is planned expansion for tables, bar/scatter charts, error bars, marker classification, difficult curve separation, and schema-mapped scalar observations. P2 remains experimental/deferred for heatmaps, advanced LC-MS/MS, and specialized image reconstruction. Neither P1 nor P2 is claimed complete. Release/production readiness remains blocked on the frozen Task Plan's real-paper benchmark, target-Windows resource, licensing/SBOM, source-integrity, and manual review acceptance gates.


`run_report.json` publishes explicit counts for `completed_papers`, `review_required_papers`, `permanently_failed_papers`, `blocked_review_locked_papers` and `retried_papers` in addition to the underlying job-state counts. It also records discovered/eligible/skipped totals, failure-reason distribution, throughput, RSS, run-scoped SFD temporary disk peak, and algorithm/profile/QC fingerprints.
