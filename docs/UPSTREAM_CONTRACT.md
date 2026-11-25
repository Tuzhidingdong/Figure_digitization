# Chem-Literature upstream contract

This adapter is pinned to the audited upstream implementation and package contract:

- Repository: `Tuzhidingdong/chem-literature`
- Audited commit: `e099406adb689281c0337bcacc7868c3ccdbc438`
- Schema: `schemas/source_package.schema.json`
- Schema blob SHA: `25994d361c9b87d8255bcadc4899e85dd84fa72f`
- Supported `evidence_index.json` package version: exactly `1.1.0` (Draft 7 schema).

## Entry point

The authoritative corpus handoff is `research_corpus_paired.csv`. The upstream workflow does not emit `research_corpus_paired_manifest.json`; this adapter does not require one.

Run from the Chem-Literature workflow working directory (or pass that directory explicitly):

```powershell
sfd scan \
  --corpus-csv "research_corpus_paired.csv" \
  --corpus-root "E:\\Chem-Literature" \
  --input-root "E:\\Chem-Literature\\runs\\preprocessed" \
  --output-root "E:\\SFD_Output"

sfd run --all \
  --corpus-csv "research_corpus_paired.csv" \
  --corpus-root "E:\\Chem-Literature" \
  --input-root "E:\\Chem-Literature\\runs\\preprocessed" \
  --output-root "E:\\SFD_Output"
```

`preprocessing_path` is resolved relative to `--corpus-root`, matching the upstream `run_workflow.py` working-directory contract. The package directory must remain inside `--input-root`. The CSV must contain `doi`, `local_pdf_path`, `local_si_info`, and `preprocessing_path`. Rows marked `FAILED` and rows without a preprocessing package are reported as skipped; a malformed or unsupported package is not silently accepted.

## Package identity and integrity

- The canonical paper identity is `evidence_index.json.paper_id`; it is not reconstructed from a downstream folder name.
- The adapter accepts only the audited package version `1.1.0`. Unknown versions or missing required root structures are rejected.
- The MAIN PDF reference is resolved against the explicit upstream working directory and SHA256-checked before it can be used.
- Every referenced media asset is resolved within its package directory and SHA256-checked.
- A figure crop is identified only through a `media_assets[]` entry with `asset_type="figure"`, matching `figure_id`, and a verified `relative_path`/SHA256. `figures[].bbox` is not assumed to be a crop or panel boundary.
- Absolute source paths are runtime-only and must not be serialized into portable downstream artifacts.
- `FAILED` is a CSV row processing failure, not a successful package status. Accepted package statuses are `COMPLETE`, `PARTIAL_NO_SI`, `PARTIAL_SI_UNSUPPORTED`, and `WARNING_SCANNED_PAGES`.

## Evidence limitations

The upstream package supplies deterministic extracted text, raw table cells, figure/caption inventory, page geometry, and media assets. It does not supply normalized sample identities, synthesis routes, experiment semantics, OCR text, or semantic condition objects. A scanned-page warning does not mean OCR was performed. Table row/header order must be preserved; headers are not guaranteed to be normalized.

This document records the downstream adapter contract. It does not modify or write to the upstream repository.
