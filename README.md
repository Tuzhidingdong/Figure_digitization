# Scientific Figure Data

An independent downstream tool for turning existing chem-literature outputs into traceable, queryable scientific figure data.

## Current implementation boundary

This repository is being implemented against the frozen v1.4.1 Task Plan. The default workflow is local, offline, single-worker, sequential, and zero-LLM-token.

The initial implementation provides corpus discovery, immutable input snapshots, compact paper context, a PDF backend abstraction, resumable paper jobs, canonical JSON/CSV artifacts, a rebuildable SQLite catalog, scientific queries, filtered exports, and hash-checked review patches.

Automated digitization is conservative. A chart is not assigned guessed axes, units, sample identity, or reference scale. If a plot does not contain sufficient machine-readable evidence or a supported extraction override, the result is routed to review. Real-paper accuracy and calibrated QC require user-approved PDFs and annotations and are not claimed by this repository's synthetic tests.

## Install

Python 3.10 or newer is required.

    python -m pip install -e .
    # Optional PDF rendering:
    python -m pip install -e ".[pdf]"
    # Optional image algorithms:
    python -m pip install -e ".[images]"
    # Development:
    python -m pip install -e ".[dev]"

No GPU or LLM is required. OCR is optional and is not installed by the default package.

## Quick start

    sfd scan --input-root PATH_TO_CHEM_LITERATURE_OUTPUTS --output-root PATH_TO_SFD_DATA
    sfd run --all --input-root PATH_TO_CHEM_LITERATURE_OUTPUTS --output-root PATH_TO_SFD_DATA
    sfd status --output-root PATH_TO_SFD_DATA
    sfd query --output-root PATH_TO_SFD_DATA --technique CV
    sfd export --output-root PATH_TO_SFD_DATA --format csv --out ml-export

Use --dry-run before a first corpus run. Existing upstream files are read-only. The output root should be a separate directory.

## Commands

- scan: discover papers and write immutable input snapshots.
- run: process eligible papers, with --resume, --failed-only, --paper-id, --dry-run and resource controls.
- status/report: inspect job state and run metrics.
- query: filter indexed papers, entities, techniques, and domains.
- export: produce CSV/JSON plus an export manifest with compatibility warnings.
- review list: find review-required series.
- review apply --patch PATCH_PATH: apply a hash-matched review patch as a new version.
- index rebuild: recreate SQLite from canonical paper artifacts.
- validate: validate canonical artifacts and source immutability snapshots.

## Streaming and resource behavior

The default worker count is one. Within a worker, pages and figures are pulled lazily; no internal image queue is created. PDF pages are rendered on demand and released immediately. If multiple workers are explicitly enabled, the scheduler dispatch queue is bounded. Workers write paper-level artifacts and the parent process serializes SQLite writes.

A compact cross-page context index is built from existing main/SI text and extracted tables. Visual resources remain page/figure scoped. If the text context exceeds the in-memory budget, a SQLite-backed lookup is used.

## Important limitations

- The PDF backend probe measures the capabilities available in the installed builds; raw PDFium path access is not presumed complete.
- No real benchmark PDFs are included. The probe reports NO_INPUT_PDFS when no files are supplied.
- The initial raster tracer requires explicit color/axis calibration evidence. It refuses ambiguous branching components.
- CV/EIS order is preserved when a trace is explicitly supplied; automatic extraction does not sort paths by X.
- QC defaults are provisional and every such result is labeled PROVISIONAL_UNCALIBRATED.
- P1/P2 are not claimed complete.

See docs/ for the input contract, storage model, backend spike protocol, and Windows usage. See STATUS.md for implementation and acceptance evidence.
