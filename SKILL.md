---
name: scientific-figure-data-skill
description: >
  Downstream, offline, evidence-first extraction of numerical scientific figure data
  from existing chem-literature paper outputs. Supports corpus-scale Windows processing,
  reviewable digitization artifacts, scientific series/entity/condition indexing, and ML export.
---

# Scientific Figure Data Skill

## Role

This is an independent downstream Skill. It consumes existing chem-literature outputs and source PDFs; it does not modify, rename, move, or delete upstream files.

The Skill converts Figure/Panel records and scientific plots into numerical Series with source evidence. It is not an autonomous research agent and must not invent measurements or scientific interpretations.

## Non-negotiable operating rules

1. Zero LLM tokens by default. Do not call an LLM or remote service. OCR is a local optional computer-vision/text-recognition feature, not an LLM. Only run OCR when the user explicitly enables --ocr.
2. Do not silently call paid models or fall back to paid models. The implementation does not require a model provider.
3. Preserve original values, source units, pixel coordinates, PDF page, figure/panel identity, source hashes, algorithm version, axis calibration evidence, and QC status.
4. Never infer a sample/entity link from a weak name match. Keep unresolved links UNASSIGNED / UNKNOWN and route them to review.
5. Do not treat a PDF vector path as a scientific trace merely because it is a path. It may be an axis, grid line, border, marker, glyph, or decorative graphic.
6. CV/EIS traces are ordered paths. Never sort their points by X. A non-monotonic trace requires an explicit ordered path or a validated dedicated extractor.
7. A numeric axis requires at least two explicit numeric anchors. An unnumbered spectral intensity axis must remain relative/arbitrary, not be presented as absolute signal.
8. Keep y_axis_side=UNASSIGNED when dual-axis association is uncertain.
9. Do not convert reference-electrode potentials from labels alone. If required electrolyte, filling solution/concentration, temperature, pH, conversion formula, and formula evidence are incomplete, retain the raw value and mark REFERENCE_CONVERSION_UNRESOLVED.
10. Do not collapse Battery gravimetric/areal/volumetric capacity or half-cell/full-cell scope. Do not equate PFAS parent removal, defluorination, fluoride release, and mineralization. Preserve <LOD / <LOQ as censored values, never zero.
11. All automatic QC thresholds are provisional until calibrated with user-approved, annotated real papers.
12. Do not overwrite REVIEWED_ACCEPTED results unless the user explicitly passes --force-recompute-reviewed; always retain the previous run.

## Hardware and streaming defaults

Target environment: Windows 10/11, 8 GB RAM, 4 logical CPU cores, no dedicated GPU.

- Default to --workers 1.
- Pull pages and panels sequentially with lazy processing.
- Render only the page/panel currently required; close the page and bitmap immediately after use.
- Save each panel's point batch to one panel_series.csv; keep paper metadata in JSON.
- SQLite is a rebuildable index and has one writer (the parent scheduler only).
- Keep the cross-page MAIN/SI text index compact; spill to a paper-local SQLite context index when the memory budget is exceeded.
- Avoid loading all papers or all image pixels into memory.
- If an optional dependency is unavailable, report the missing feature and continue with the remaining work where possible.

## Standard workflow

### 1. Discover and fingerprint upstream papers

    sfd scan --input-root INPUT_ROOT --output-root OUTPUT_ROOT

The output root must be separate from and outside the upstream input root. A corpus manifest stream stores per-paper input snapshots. Source artifacts are SHA256-hashed incrementally.

### 2. Preview and process

    sfd run --all --input-root INPUT_ROOT --output-root OUTPUT_ROOT --dry-run
    sfd run --all --input-root INPUT_ROOT --output-root OUTPUT_ROOT

Useful modes:

    sfd run --resume --input-root INPUT_ROOT --output-root OUTPUT_ROOT
    sfd run --failed-only --input-root INPUT_ROOT --output-root OUTPUT_ROOT
    sfd run --paper-id PAPER_ID --input-root INPUT_ROOT --output-root OUTPUT_ROOT

Keep --workers 1 on a normal office workstation. Increase workers only after measuring RAM and native-library stability on the target computer.

### 3. Inspect status and validate artifacts

    sfd status --output-root OUTPUT_ROOT
    sfd report --output-root OUTPUT_ROOT
    sfd validate --output-root OUTPUT_ROOT --input-root INPUT_ROOT

### 4. Query and export

    sfd query --output-root OUTPUT_ROOT --paper-id PAPER_ID
    sfd query --output-root OUTPUT_ROOT --technique CV --domain battery
    sfd query --output-root OUTPUT_ROOT --entity "Sample A"
    sfd query --output-root OUTPUT_ROOT --analyte PFOA
    sfd export --output-root OUTPUT_ROOT --out EXPORT_DIR --format csv
    sfd export --output-root OUTPUT_ROOT --out EXPORT_DIR --reviewed-only

The export manifest must keep review/QC flags and warn about incompatible or unresolved units, reference scales, metric bases, or conditions. Never merge scientifically incomparable series automatically.

### 5. Review and apply corrections

Open review_helper.html in a local browser, select the paper output folder, inspect the source crop and traced overlay, and export a Review Patch JSON. Then:

    sfd review apply --output-root OUTPUT_ROOT --patch PATCH_PATH --dry-run
    sfd review apply --output-root OUTPUT_ROOT --patch PATCH_PATH

A patch must match the current digitization.json SHA256. A stale patch is rejected as PATCH_CONFLICT_STALE_BASE; never silently overwrite a changed base.

### 6. Rebuild the catalog

    sfd index rebuild --output-root OUTPUT_ROOT

The SQLite catalog can be rebuilt from canonical per-paper artifacts; do not treat a bundle snapshot as the only source of truth.

## PDF and extraction limits

Use sfd backend-probe on 3–5 user-approved representative PDFs before selecting a production vector backend. Record per-page time, Peak RSS, native text, object types, vector path segments, embedded images, clipping, rotation, nested Form XObjects, path fragmentation, and text-as-path behavior.

The current native-object inventory is evidence, not a validated universal vector digitizer. The initial raster tracer is limited to explicit color/axis evidence for monotonic single-valued curves. Dense same-color crossings, complex markers, ambiguous axes, and non-monotonic raster traces must remain NEEDS_REVIEW until a dedicated extractor is validated.

## Domain profiles

Profiles are inherited YAML configurations. Initial profile families:

- battery: XRD, Raman, FTIR, XPS, CV, GCD, EIS, GITT.
- AOP: pollutant degradation kinetics, C/C0, TOC, COD, radical/quenching semantics.
- PFAS: parent compound, fluoride release, fluorine balance; advanced LC-MS/MS remains experimental/P2.

The profile schema is extensible. Do not embed one paper's sample names, values, or reference conditions as production rules.


### Explicit measurement semantics in series overrides

A series override may include a measurement_semantics object alongside its label, technique, and domain. This object is evidence supplied by the user, not an invitation to infer missing fields.

For battery capacity series, provide metric, capacity_basis, cell_scope, current_density_basis, and cycling_protocol when known. Missing required fields produce BATTERY_BASIS_UNRESOLVED warnings; XRD/Raman/FTIR/XPS series are not treated as capacity measurements just because their domain is battery.

For AOP/PFAS series, provide metric. An optional comparison_target_metric enables an explicit non-interchangeability check. Missing metrics remain unresolved; different metric roles produce comparability warnings. These warnings never authorize conversion, pooling, or harmonization. ML exports remain NOT_HARMONIZED.

## Execution tracking and governance

- The frozen user-owned requirements baseline is TASK_PLAN_v1.4.1.md. Do not edit it.
- Record implementation and acceptance evidence in STATUS.md.
- Do not claim completion of a criterion based only on a synthetic test. Real-paper acceptance requires user-approved PDFs and human-annotated reference points/anchors.
- Do not publish a release without explicit user approval.

## Extraction acceptance boundary

P0 code paths are implemented conservatively, but their scientific accuracy is not yet validated against annotated real papers. Treat automatic results as `PROVISIONAL_UNCALIBRATED`; unsupported or ambiguous traces must remain `NEEDS_REVIEW`. Synthetic CI verifies software behavior, not point-level scientific accuracy.

P1 planned scope: tables, bar/scatter plots, error bars, marker classification and more difficult curve separation. P2 experimental/deferred scope: heatmaps, advanced LC-MS/MS and specialized image reconstruction. Do not describe P1/P2 as supported production features or claim production readiness until the frozen Task Plan's real-paper, target-Windows, licensing, integrity and manual-review gates are accepted.
