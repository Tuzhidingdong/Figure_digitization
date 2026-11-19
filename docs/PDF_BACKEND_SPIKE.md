# PDF backend technical spike protocol

Run the probe on 3–5 user-approved representative PDFs:

    python -m scientific_figure_data.backend_probe paper1.pdf paper2.pdf paper3.pdf --out backend_probe_report.json

The probe processes one page at a time, recording per-page rendering/text timing, dimensions, process RSS, and available PDFium raw API symbols. It closes each page and document promptly.

Candidate comparison must include pypdfium2 high-level APIs, pypdfium2.raw, pdfminer.six, and pikepdf/QPDF where installed. The initial automated probe does not claim full vector-path coverage: raw symbol presence is only a capability hint.

Manually inspect representative files for native text, vector objects, embedded images, clipping, rotation, Form XObjects, path fragmentation, and text-as-path. Record per-page Peak RSS and time, object/path coverage, correctness, and unsupported cases.

No input PDFs means the report status is NO_INPUT_PDFS. Do not select a final vector backend or claim the technical spike is complete until the user-approved sample set is measured.
