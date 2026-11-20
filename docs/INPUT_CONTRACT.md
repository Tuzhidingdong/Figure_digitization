# Upstream input contract

The adapter treats the input root as immutable. All downstream files are written below a separate output root.

## Discovery

A directory is considered a paper candidate when it contains a PDF or a recognized upstream artifact such as paper_manifest.json, manifest.json, evidence_index.json, figure_inventory.json, figures.json, main_analysis.md, or si_analysis.md. For the current Chem-Literature layout, use runs/preprocessed as the input root: the adapter discovers each <paper_id>/01_preprocessing package independently.

Recognized roles include:

- main_pdf
- main_text
- si_text
- figure_inventory
- evidence_index
- table_data
- figure_image
- other

The adapter does not require every role. Missing or unreadable inputs are included in the snapshot and reported.

## Fingerprints

Each file is SHA256-hashed incrementally in 1 MiB chunks. A paper fingerprint covers the paper ID, paper-relative source directory, adapter version, and the ordered artifact paths, roles, sizes, mtimes, and hashes.

The hash, not mtime or size alone, is the source identity.

## Artifact conventions

Figure inventory JSON may be a list or an object containing figures, items, or figure_inventory. A figure may include figure_id/id, page/page_number, caption, shared_legends/legend, image_path, bbox/bounding_box, technique, domain, and panels.

Each panel may include panel_id/id/label, image_path, bbox/bounding_box, technique, and domain.

Paths supplied by an upstream artifact are resolved beneath the paper directory. Path traversal outside the paper directory is rejected.

## Optional deterministic digitization overrides

A paper may contain digitization_overrides.json. This file is a downstream configuration input and is never written by the tool.

Shape:

    {
      "schema_version": "1.0",
      "figures": {
        "Figure3": {
          "panels": {
            "c": {
              "series": [{
                "series_id": "Figure3c_sampleA",
                "label": "Sample A",
                "technique": "CV",
                "domain": "battery",
                "data_family": "NON_MONOTONIC",
                "x_axis_anchors": [{"pixel": 40, "value": -1.0}, {"pixel": 900, "value": 1.0}],
                "y_axis_anchors": [{"pixel": 420, "value": -2.0}, {"pixel": 30, "value": 2.0}],
                "x_unit": "V",
                "y_unit": "mA cm-2",
                "y_axis_side": "LEFT",
                "pixel_points": [[40, 210], [80, 180], [110, 130]]
              }]
            }
          }
        }
      }
    }

pixel_points are in the local panel image coordinate system and preserve their declared order. This is the supported explicit path for CV/EIS and other non-monotonic traces.

For a monotonic single-color raster trace, replace pixel_points with color_rgb [R,G,B] and optional color_tolerance. Automatic color tracing is conservative and refuses obvious discontinuity or multiple-band ambiguity.

An override is evidence/configuration, not a claim that values have been independently validated. The result remains provisional and is routed for review by default.

## Cross-page text context

The context index reads upstream main_analysis.md, si_analysis.md, and extracted_tables text/CSV files line-by-line. Each matched alias, reference-electrode mention, and statistics phrase stores its source path, line number, and snippet. It does not render PDF pages.


## Chem-Literature 1.1 source-package compatibility

The current upstream preprocessor writes each package to runs/preprocessed/<paper_id>/01_preprocessing/. The package contains evidence_index.json, main_analysis.md, si_analysis.md, extracted_tables/, extracted_figures/, and supporting evidence. The upstream evidence index stores the original MAIN PDF in inventory.main_pdf.path (normally an absolute path outside the preprocessing package) with its SHA256.

The downstream adapter resolves that explicit reference read-only. It opens the referenced PDF only when the file exists, has a PDF signature, and matches the upstream SHA256; a mismatch or missing file is reported and the PDF is not used. The local absolute path is runtime-only and is not serialized into the downstream manifest. When the referenced file is outside the selected input root, the manifest records only the JSON-pointer reference, integrity state, size, and content hash. The referenced file's content hash participates in the paper fingerprint.

MAIN figure crops are linked from evidence_index.json media_assets to figures by exact figure_id and doc_type, and the asset SHA256 is checked before use. A linked upstream crop is treated as an already-cropped figure image; its figure caption bbox is not applied as a second crop. SI page composites and embedded images are not guessed into individual figure identities when the upstream package does not provide a unique association; those figures remain for review. SI page numbers are never applied to the MAIN PDF.


When an upstream evidence index declares a figure asset but it is missing, ambiguous, unreadable, or fails SHA256 validation, the figure is marked with an asset status and routed to review. The pipeline does not use the evidence index figure bbox as a fallback crop because it may describe only the caption. The page-level PDF evidence remains available for manual review.


## Source-image and panel-geometry provenance

A figure image linked from an upstream evidence index is used only when its exact figure/document-type association is unique and its SHA256 matches. The downstream worker rechecks the hash when copying that image into its own `papers/<paper_id>/evidence/` folder. It records the original relative upstream path and image hash, but does not modify the upstream file. If the source changes between inventory and copy, the copy is rejected and the figure remains for review. The offline review helper reads the downstream evidence copy, not a path outside the selected paper-output folder.

An untyped Figure-level bbox in an evidence index is preserved as source metadata, but is not assumed to be a Panel boundary or plot-area crop. Panel records separately preserve the original source bbox, an explicit or safely recognized normalized bbox, coordinate-space label, bbox provenance, segmentation provenance/status, and segmentation-confidence status. When only a whole-figure fallback exists, the record states that panel segmentation was not performed rather than fabricating a boundary.

The MAIN PDF is hash-checked when the input snapshot is created and again immediately before worker use. If its content changes between those two points, the worker does not open it using the old snapshot identity; the paper is retained with a `CHANGED_AFTER_SNAPSHOT` provenance status and routed to `NEEDS_REVIEW`. The original snapshot fingerprint is retained so a subsequent scan can detect and reprocess the changed input.
