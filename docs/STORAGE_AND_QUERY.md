# Canonical storage, SQLite index, query, and export

## Canonical paper artifacts

Each paper is stored under output_root/papers/PAPER_ID/:

- paper_manifest.json
- figure_inventory.json
- digitization.json
- paper_bundle.json
- context/paper_context_index.json
- context/paper_context.sqlite when the memory budget is exceeded
- series/FIGURE__PANEL/panel_series.csv
- evidence/ derived panel crops when a source PDF crop was required

The merged panel CSV uses series_id to distinguish curves. Source PDFs and upstream files are not copied or modified.

## SQLite

catalog.sqlite is a rebuildable query index. Only the parent/scheduler process writes to it. Paper workers return compact JSON-compatible results and artifact references.

The index stores paper, figure, panel, series, point, entity-link, condition, measurement, observation, job, event, review, and applied-patch tables. The initial reconstruction path rebuilds query-critical series metadata from canonical JSON; the panel CSV remains the point-data source of truth.

## Query

The query CLI supports filters for paper_id, technique, domain, entity_id, series_role, QC status, and review state. Filters are combined with AND semantics. Entity links are exact IDs; unresolved aliases are not silently promoted to canonical entities.

## Export

Exports contain a data file and export_manifest.json. The manifest describes filters, schema version, source artifact references, QC/review state, and comparability warnings. The export uses one row per digitized series point. Each row carries paper/figure/panel/series identity, point index, reconstructed axis values and units, explicit `*_raw` copies, pixel coordinates, available error-bar fields, QC/review/extraction states, source artifact references, series-level subject entity IDs and evidence links, and measurement conditions. Subject links and conditions are JSON columns so each point row remains self-describing; `series_metadata.jsonl` remains a companion audit record.

`x_value` and `y_value` are reconstructed on the plotted axes. `*_raw` means no subsequent unit/reference-scale normalization has been applied; it does not mean a raw pixel coordinate. `standardization_status` is `NOT_PERFORMED` by default and the four standardized value/unit columns remain empty. A future explicit dimensional conversion can populate those columns only with a supported conversion method and evidence identifier. Potential-reference conversions remain a separate operation and are never handled by the dimensional factor table. `compatibility_status` is `NOT_HARMONIZED`. Pixel coordinates remain separately available. Missing unit, entity, condition, or uncertainty data is not inferred.

No automatic harmonization occurs across unresolved reference scales, capacity bases, cell scopes, analyte metrics, or experimental conditions. The export manifest records this policy and warnings. Use filters or exclude unresolved records explicitly.
