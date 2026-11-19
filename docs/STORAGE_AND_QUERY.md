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

Exports contain a data file and export_manifest.json. The manifest describes filters, schema version, source artifact references, QC/review state, and comparability warnings. The MVP exports one row per series point and includes series metadata columns.

No automatic harmonization occurs across unresolved reference scales, capacity bases, or scientific metrics. Use filters or exclude unresolved records explicitly.
