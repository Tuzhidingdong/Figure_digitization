# Upstream input contract

The adapter treats the input root as immutable. All downstream files are written below a separate output root.

## Discovery

A directory is considered a paper candidate when it contains a PDF or a recognized upstream artifact such as paper_manifest.json, manifest.json, figure_inventory.json, figures.json, main_analysis.md, or si_analysis.md.

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
