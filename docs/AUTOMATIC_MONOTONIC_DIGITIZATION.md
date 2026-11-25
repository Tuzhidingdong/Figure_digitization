# Automatic monotonic multi-series raster digitization

This release adds a conservative, evidence-driven automatic path for a limited class of raster plots. It does not make the system a general-purpose scientific chart digitizer.

## Supported automatic case

A panel can be routed to the raster tracer only when all of the following are available from the image and OCR evidence:

- One unambiguous rectangular plot-frame candidate.
- An OCR-recognized X-axis label that explicitly indicates an ordered variable (currently time, seconds/minutes/hours, cycle number, wavelength, wavenumber, frequency, 2θ, or scan number).
- At least two monotonic numeric tick anchors on each axis.
- One or more separable chromatic trace-colour families in the plot region; every candidate must independently pass continuity and monotonic-path checks.
- A chart family not classified as CV, EIS, or another explicitly non-monotonic family.

The generated TraceSpecification records the source-image hash, plot box, color-family descriptor, any available calibration parameters, axis semantics and provenance. Each accepted colour family becomes its own series and the raster tracer samples that colour independently per X column. Candidate colors alone are not accepted as curves: every candidate must pass path continuity and single-band checks. It rejects discontinuities and multiple vertically separated same-colour bands rather than silently reducing them to one median trace.

UNCLASSIFIED by itself no longer prevents visual colour-candidate detection. However, an unclassified image is digitized only when OCR provides a supported ordered X-axis label and all other evidence gates pass. Recognized CV/EIS plots are never sent to the monotonic tracer.

## Panel segmentation

When upstream panel boundaries are absent, the pipeline first attempts broad near-white gutter segmentation. If that cannot separate the figure, it scans for multiple spatially distinct plot-frame candidates using achromatic axis-line continuity and local chromatic-content evidence. Black/gray horizontal axis lines and continuous colored vertical Y-axis spines are both supported; the detector also recognizes open L-shaped axis corners rather than requiring a closed four-sided frame. This catches compact layouts whose panels touch or have no broad blank gutter. An individual large frame is not accepted as the only panel merely because it occupies a large fraction of the source image.

The candidate scan is bounded to a downsampled image of at most five million pixels, then maps every accepted frame candidate back into the original image coordinate system. Per-series color tracing remains on the original-resolution panel crop.

For frame-candidate segmentation, each frame is expanded into a panel crop with a small shared margin so the plot border and nearby axis labels remain available to the per-panel detector. Adjacent crops may overlap slightly; the underlying plot-frame candidates remain spatially distinct. Candidate score, side coverage, bounding boxes and segmentation provenance are retained.

This is provisional geometry only:
- It does not infer scientific content or panel letters.
- It does not guarantee that every detected frame is a true scientific panel.
- Colored traces are excluded from the primary achromatic axis-line score so long curves are less likely to be mistaken for plot borders.
- Ambiguous or unsplit figures remain reviewable; no panel or plot boundary is fabricated.

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


## Experimental achromatic multi-series candidate path (P1 development)

The isolated `feat/p1-achromatic-multiseries-raster` development branch adds a conservative neutral-pixel candidate pass for grayscale/black traces. It is not a production-accepted capability.

- Achromatic candidates are identified by a bounded luminance/chroma mask inside an already resolved plot box. The initial detector proposes a neutral pixel pool; it does **not** claim that the pool represents one curve.
- Connected 2-D path decomposition inventories spatially separate paths. A full-span solid path remains independent from other paths.
- Disconnected local fragments may be associated into one dashed-trace candidate only when their left-to-right endpoint position, local tangent, predicted vertical offset and reciprocal best match are unique. Source fragments remain separate CSV path segments. No pixels are inserted or interpolated across gaps.
- Unassigned fragments, multiple plausible continuations, crossings and unsupported junctions remain `NEEDS_REVIEW`.
- Long, nearly horizontal achromatic paths are flagged as gridline-like and remain review-required; the detector does not silently classify them as data or delete them.
- Plot-boundary exclusion is geometric and narrow. Interior grid lines, gray text, marker glyphs and other neutral annotations may still enter the candidate inventory and must be rejected or reviewed through path/QC evidence.

Synthetic tests cover a gray solid path, gray dashed fragments, a neutral gridline and the no-achromatic-pixels case. These tests establish software behavior only. Real-image acceptance is still pending, including rerunning F04-P01 locally with the Skill and reviewing its overlay/diagnostics. The F04-P01 local result on 2026-11-25 found one complete red path (335 points/1 segment), one provisional red fragment collection (152 points/2 segments), and no achromatic extraction; this is the motivating failure evidence, not a passing benchmark.

## Explicit limitations

This path does not digitize:
- CV/EIS loops or other non-monotonic X paths.
- Same-colour multi-branch curves, or multi-colour candidates that fail the independent path checks, in the accepted P0 path. The achromatic fragment-tracking route described above remains experimental P1 development and is not yet accepted for real-paper extraction.
- Scatter plots, bar charts, error bars, or image/structure schematics.
- Axes without two defensible numeric anchors per axis. When both left and right Y axes are calibrated, a series is mapped only when a side is unambiguous or explicitly supplied; both calibrations are retained and the software refuses to guess a series-to-axis association.
- X axes whose labels do not establish an ordered variable.

The first-phase path therefore may correctly produce zero points for a multi-panel battery figure whose panels are cyclic voltammetry, dual-axis plots, scatter plots or schematics. Such refusal is preferable to fabricated data. Multi-panel segmentation, semantic panel recognition and broad chart-family extraction remain separate capability areas.

All automatically extracted records remain provisional and require review. Two-point axis calibration residuals are not evidence of digitization accuracy; accuracy requires an independent annotated reference benchmark.

## Worker lifecycle and interruption safety

Each spawned worker redirects stdout/stderr to a per-run worker log so an orphaned child cannot keep the invoking PowerShell output pipe open after the parent exits. Workers monitor the multiprocessing parent sentinel and exit when the parent disappears. Normal scheduler shutdown is bounded: it waits briefly for executor-owned workers, then terminates and, only if necessary, kills those exact worker processes. Shutdown actions and worker log locations are recorded in the corpus run report. This does not replace atomic artifact writes or the job-ledger lease/recovery path.


## Multiple colour families and dual Y axes

For semantically ordered X axes, the detector may propose up to eight distinct saturated colour families from the plot region. The families are grouped by circular HSV hue rather than strict RGB distance, so anti-aliased shades of one curve are not needlessly split. Persistent chromatic axis spines are identified separately and excluded from the curve-family pixel inventory; those colors remain available as axis-association evidence, not as standalone series. Hue-family candidates are recorded with pixel counts and color evidence; each is then independently passed through the X-monotonic tracer. Disconnected markers, scatter-like traces, thick bands and same-colour multi-branch paths remain review-required rather than being reduced to a median line. If more than eight separable families remain, candidate discovery is marked truncated and automatic expansion is withheld. Automatic family expansion is performed only for an unconfigured default series and does not replace explicit reviewer series definitions.

Numeric anchors on the left and right Y margins are retained and calibrated independently. Pixel-space path extraction is independent of numeric-axis assignment: an unresolved Y-axis mapping no longer blocks a valid X-monotonic pixel trace. In that case the points and source overlay are retained, numeric Y values remain null, and no numeric reconstruction is fabricated. A curve uses an axis calibration only when its requested side is available or only one side is defensibly calibrated. When both sides are calibrated and the series-to-axis relationship is not established by explicit series metadata, both calibrations are retained and the series remains `NEEDS_REVIEW`; the software does not infer the mapping from curve color alone.


### Color-coded dual Y-axis association

When both Y axes have valid numeric anchors, the system preserves and calibrates both independently. It may assign a curve to one side only when OCR-located numeric tick labels, the OCR-located Y-axis title, or a persistent colored Y-axis spine contain a consistent chromatic hue that uniquely matches the curve's detected hue family. Tick-label evidence requires at least two colored labels; a single axis-title box is accepted only when the spatially identified title has a clear chromatic ink color. Axis-spine evidence is sampled in a narrow strip along the left/right plot boundary and requires substantial vertical coverage, a long continuous run, and one dominant hue family; a colored curve endpoint or isolated tick is insufficient. Conflicting tick/title/spine colors and ambiguous matches do not resolve the association. The match, sampled colors, coverage, purity and distance are retained as evidence. Black/gray tick labels, conflicting labels, or a match to both sides do not resolve the association; the series stays `AMBIGUOUS_DUAL_Y_AXIS`.
