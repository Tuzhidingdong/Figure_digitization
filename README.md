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

    sfd scan --input-root PATH_TO_CHEM_LITERATURE_OUTPUTS --output-root PATH_TO_SFD_DATA
    sfd run --all --input-root PATH_TO_CHEM_LITERATURE_OUTPUTS --output-root PATH_TO_SFD_DATA --workers 1 --min-free-disk-mb 256
    sfd status --output-root PATH_TO_SFD_DATA
    sfd query --output-root PATH_TO_SFD_DATA --technique CV
    sfd export --output-root PATH_TO_SFD_DATA --format csv --out ml-export

Use --dry-run before a first corpus run. Existing upstream files are read-only. The output root should be a separate directory.

## Commands

- scan: discover papers and write immutable input snapshots.
- run: process eligible papers, with --resume, --failed-only, --paper-id, --dry-run and resource controls. Resume rechecks input, implementation, profile/QC and bundle fingerprints; intact unchanged papers are skipped before a worker starts.
- status/report: inspect job state and run metrics.
- query: filter indexed papers, entities, techniques, and domains.
- export: produce CSV/JSON plus an export manifest with compatibility warnings.
- review list: find review-required series.
- review apply --patch PATCH_PATH: apply a hash-matched review patch as a new version.
- index rebuild: recreate SQLite from canonical paper artifacts.
- validate: validate canonical artifacts and source immutability snapshots.

## Streaming and resource behavior

The default worker count is one. Within a worker, pages and figures are pulled lazily; no internal image queue is created. PDF pages are rendered on demand and released immediately. If multiple workers are explicitly enabled, the scheduler dispatch queue is bounded. Workers write paper-level artifacts and the parent process serializes SQLite writes.

A compact cross-page context index is built from existing main/SI text and extracted tables. Its cache is keyed by source content fingerprints: unchanged inputs reuse the prior JSON/SQLite index, while changed inputs invalidate and rebuild it. Visual resources remain page/figure scoped. If the text context exceeds the in-memory budget, a SQLite-backed lookup is used. Before each new paper is dispatched, the scheduler checks free space on the output filesystem. When free space falls below `--min-free-disk-mb` (default 256 MiB), it stops dispatching, lets active work finish, and records the pause reason in `run_report.json`. Use `--resume` after freeing space; set the threshold to `0` only to disable this guard.

## Important limitations

- The PDF backend probe measures the capabilities available in the installed builds; raw PDFium path access is not presumed complete.
- No real benchmark PDFs are included. The probe reports NO_INPUT_PDFS when no files are supplied.
- For simple charts, the raster path can provisionally detect a rectangular plot frame and a unique chromatic trace family, then use text/explicit axis anchors. Multiple color families, same-color separated bands, ambiguous frames and branching components route to review. This is a narrow heuristic, not general chart understanding.
- CV/EIS order is preserved when a trace is explicitly supplied; automatic extraction does not sort paths by X.
- QC defaults are provisional and every such result is labeled PROVISIONAL_UNCALIBRATED.
- P1/P2 are not claimed complete.

See docs/ for the input contract, storage model, backend spike protocol, and Windows usage. See STATUS.md for implementation and acceptance evidence.
