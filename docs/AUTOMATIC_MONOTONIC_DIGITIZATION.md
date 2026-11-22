# Automatic single-colour monotonic raster digitization

This release adds a conservative, evidence-driven automatic path for a limited class of raster plots. It does not make the system a general-purpose scientific chart digitizer.

## Supported automatic case

A panel can be routed to the raster tracer only when all of the following are available from the image and OCR evidence:

- One unambiguous rectangular plot-frame candidate.
- An OCR-recognized X-axis label that explicitly indicates an ordered variable (currently time, seconds/minutes/hours, cycle number, wavelength, wavenumber, frequency, 2θ, or scan number).
- At least two monotonic numeric tick anchors on each axis.
- One unique chromatic trace-colour family in the plot region.
- A chart family not classified as CV, EIS, or another explicitly non-monotonic family.

The generated TraceSpecification records the source-image hash, plot box, colour, calibration parameters, axis semantics and provenance. The existing raster tracer then samples one colour per X column. It rejects discontinuities and multiple vertically separated same-colour bands rather than silently reducing them to one median trace.

UNCLASSIFIED by itself no longer prevents visual colour-candidate detection. However, an unclassified image is digitized only when OCR provides a supported ordered X-axis label and all other evidence gates pass. Recognized CV/EIS plots are never sent to the monotonic tracer.

## Panel segmentation

When upstream panel boundaries are absent, the pipeline first checks whether the source image contains one dominant plot frame. If not, it may split the image at broad near-white horizontal/vertical gutters.

This is provisional geometry only:
- It does not infer scientific content or panel letters.
- It does not guarantee that every separated region is a true scientific panel.
- Ambiguous or unsplit figures remain reviewable; no boundaries are fabricated.

An upstream panel inventory remains preferred where available.

## OCR and coordinate provenance

Enable the optional local CPU OCR dependency when running the pipeline:

~~~powershell
python -m pip install -e ".[dev,images,ocr]"
sfd run --input-root <preprocessed-root> --output-root <output-root> --paper-id <paper-id> --ocr
~~~

OCR is local preprocessing; it does not call an LLM.

The pipeline records both PDF-page mappings and raster-image crop mappings with explicit coordinate-space identifiers. A SOURCE_IMAGE_PIXELS mapping is never interpreted as PDF points. Upstream media-asset bbox/page/extraction metadata is retained as provenance, but is not converted to PDF coordinates unless the source coordinate system is explicitly known and validated.

OCR label/tick candidates retain their source text, position and confidence. Numeric tick anchors are accepted only when they occur in the expected axis margins and are monotonic in pixel order.

## Outputs

For each series with at least two calibrated numeric points and pixel provenance, the pipeline writes:

- An independent reconstructed chart derived from exported numeric points (no interpolation or smoothing).
- An overlay showing the extracted pixel path on the original panel crop.
- comparisons/ALL_PANELS_COMPARISON.png, including panels without automatic extraction and their refusal/review reason.

The independent reconstruction is a diagnostic visualization, not an accuracy benchmark.

## Explicit limitations

This path does not digitize:
- CV/EIS loops or other non-monotonic X paths.
- Multi-colour or same-colour multi-branch curves when a unique trace cannot be established.
- Scatter plots, bar charts, error bars, or image/structure schematics.
- Axes without two defensible numeric anchors per axis.
- X axes whose labels do not establish an ordered variable.

The first-phase path therefore may correctly produce zero points for a multi-panel battery figure whose panels are cyclic voltammetry, dual-axis plots, scatter plots or schematics. Such refusal is preferable to fabricated data. Multi-panel segmentation, semantic panel recognition and broad chart-family extraction remain separate capability areas.

All automatically extracted records remain provisional and require review. Two-point axis calibration residuals are not evidence of digitization accuracy; accuracy requires an independent annotated reference benchmark.
