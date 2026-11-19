# PDF backend technical spike protocol

Run the probe on 3–5 user-approved representative PDFs:

    python -m pip install -e ".[pdf,pdf-spike]"
    sfd backend-probe paper1.pdf paper2.pdf paper3.pdf --out backend_probe_report.json

The probe processes one page at a time and writes a comparative JSON report for:

- **pypdfium2 / PDFium**: native text, object types, path-segment inventory, embedded image sizes, rendered page dimensions, per-page elapsed time, current RSS and observed peak working set
- **pdfminer.six**: per-page layout/text counts, curve-like layout objects, images, elapsed time and observed memory
- **pikepdf / QPDF**: per-page content-stream operators, path construction/painting operators, text operators, XObject invocations/resource types, elapsed time and observed memory

The probe accepts only 3–5 PDFs for a benchmark run. With no input PDFs it reports \`NO_INPUT_PDFS\` and does not select a backend.

## What the automated probe does not prove

- PDFMiner layout curves are not a complete PDF drawing-object model.
- pikepdf operator counts are not a reconstruction of the active graphics state, clipping path, CTM, or final visible geometry.
- Page content-stream operator counts do not automatically recurse through every nested Form XObject.
- PDFium path-object inventory does not establish whether a path is a plotted curve, axis, gridline, marker, glyph, or decorative shape.
- A backend's presence of a method or raw API symbol is not proof of complete support.
- Observed RSS samples are engineering measurements, not a guarantee against all pathological PDFs.

## Required manual inspection

For each selected PDF, visually inspect and record coverage of:

1. Native text and text coordinates, including text rendered as paths
2. Vector paths, path fragmentation, fills/strokes, markers and line styles
3. Embedded raster images and mixed vector/raster charts
4. Clipping paths and nested clipping
5. Page rotation and coordinate transforms
6. Nested Form XObjects and reused resources
7. Axis/tick/legend text placement versus curve geometry
8. Complex multi-panel figures and shared legends

Record the PDF SHA256, tool/library versions, page-by-page elapsed time and Peak RSS, object/path coverage, unsupported cases, and visual correctness. Preserve probe JSON and manual annotations as benchmark evidence.

No final vector backend is selected until the 3–5 user-approved PDFs have been measured and inspected. Keep the adapter boundary capable of combining backends, for example PDFium for rendering/object iteration and PDFMiner for text-layout evidence if measurements justify that combination.
