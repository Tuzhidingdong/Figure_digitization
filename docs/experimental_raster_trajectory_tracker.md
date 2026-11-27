# Experimental raster trajectory reconstruction

This is an isolated experimental path-discovery command. It does not replace
or change the regular sfd scan / sfd run processing pipeline.

## Usage

    sfd trace-image panel.png --plot-box X0 Y0 X1 Y1 --out trajectory_review

The plot box uses original-image pixel coordinates in x0, y0, x1, y1 order.
Normalized fractions from 0 to 1 are also accepted. The output directory must
be empty or absent. It contains an offline HTML review page, source and mask
images, combined and per-track overlays, point CSV, inventory CSV and JSON
diagnostics.

## Method and limits

The detector extracts vertical foreground runs independently in each image
column and links them with second-order dynamic programming. It does not equate
a connected component with a curve. Disconnected dash runs can be linked as
one candidate trajectory; separate paths touching at isolated columns may be
recovered when their local geometry remains distinguishable.

No morphology, interpolation, smoothing or gap filling is applied. Every
exported coordinate is an original source-image pixel. All tracks are review
hypotheses, not accepted scientific series. The command exports pixel
coordinates only and performs no OCR or scientific axis calibration. It is
intentionally not connected to the default paper-processing pipeline while
local real-image testing is pending.
