# Experimental raster trajectory reconstruction

This is an isolated experimental path-discovery command. It does not replace
or change the regular `sfd scan` / `sfd run` processing pipeline.

## Usage

    sfd trace-image panel.png --plot-box X0 Y0 X1 Y1 --out trajectory_review

The plot box uses original-image pixel coordinates in x0, y0, x1, y1 order.
Normalized fractions from 0 to 1 are also accepted. The output directory must
be empty or absent. It contains an offline HTML review page, source and mask
images, combined and per-track overlays, point CSV, inventory CSV and JSON
diagnostics.

## Current experimental method

The detector extracts vertical foreground runs independently in each image
column. It estimates a local undirected tangent from the contrast structure
tensor, then builds a directed acyclic transition graph between runs in
successive columns. A successive-shortest-path min-cost-flow solver selects
node-disjoint paths jointly. Each source run has unit capacity, and residual
edges allow later augmentations to reroute earlier choices instead of consuming
nodes by sequential greedy peeling.

Transition costs account for horizontal gaps, local tangent disagreement,
source-colour differences and run-width differences. The solver is bounded by
node and edge budgets and returns `NEEDS_REVIEW` instead of attempting an
unbounded graph.

Each path is described separately from its review classification. Solid paths
use a continuous-path gate. Discontinuous paths are only promoted to review
candidates when segment lengths and gaps show a sufficiently regular dash
pattern; irregular fragment collections remain
`UNRESOLVED_FRAGMENT_PATH`. Short periodic candidates can therefore be
reviewed without lowering the solid-line minimum point threshold.

## Data integrity and limits

No morphology, interpolation, smoothing or gap filling is applied. Every
exported coordinate is an original source-image pixel. Dash and occlusion gaps
remain explicit independent segments. Node-disjoint selection prevents one
source run from being assigned to two reconstructed paths, but does not prove
that a path is a true scientific series.

All tracks remain review hypotheses, not accepted scientific measurements.
The command exports pixel coordinates only and performs no OCR or scientific
axis calibration. Plot-box selection is supplied by the caller and is not
automatically resolved by this command. It is intentionally not connected to
the default paper-processing pipeline while local real-image testing is
pending.

The synthetic test suite covers separate solid paths, dashed paths, crossings,
legend swatches, blank plots, source-pixel integrity, short periodic dashes,
irregular fragments, and node-disjoint global selection. Synthetic success is
not evidence of successful extraction from an unseen real figure.
