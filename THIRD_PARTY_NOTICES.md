# Third-party dependency and license inventory

This project keeps the core runtime dependency-light. Optional packages are not imported until the corresponding feature is requested.

| Component | Use | Declared package/license status | Distribution note |
|---|---|---|---|
| Python standard library | Core runtime, SQLite, hashing, JSON, CSV, scheduler | Python PSF license | Provided by Python distribution |
| psutil | Process memory measurement and resource limits | BSD-3-Clause | Runtime dependency; include package notice |
| PyYAML | YAML domain-profile configuration | MIT | Runtime dependency; include package notice |
| pypdfium2 | Optional PDF rendering and text page access | Verify exact pinned release notices; pypdfium2 project uses Apache-2.0/BSD-3-Clause notices and bundles PDFium | Preserve included PDFium and dependency notices with any binary distribution |
| PDFium | Native PDF engine used by pypdfium2 | Upstream component license notices apply | Raw API availability varies by build; symbol presence is not proof of full path extraction |
| Pillow | Optional image loading/cropping | HPND | Include package notice if redistributed |
| NumPy | Optional raster array processing | BSD-3-Clause | Include package notice if redistributed |
| rapidocr | Optional OCR | Verify exact pinned RapidOCR distribution license | OCR model weights and preprocessing dependencies must be inventoried separately |
| onnxruntime | Optional CPU OCR inference | MIT | CPU runtime only; configure one intra-op and one inter-op thread |
| pdfminer.six | Backend spike candidate; not a core dependency | MIT | Include notice if adopted/distributed |
| pikepdf / QPDF | Backend spike candidate; not a core dependency | MPL-2.0 for pikepdf; QPDF component notices also apply | Review the exact wheel's bundled dependencies |
| PyMuPDF | Not selected by default | AGPL-3.0 or commercial licensing | Do not add without a separate license decision |

OpenCV is not currently an active dependency. This table is a preliminary engineering inventory, not legal advice or a substitute for scanning the exact resolved dependency tree and binary wheels used for a release.

Before distribution, generate a machine-readable SBOM and preserve all notices from the exact locked package versions. No OCR weights are bundled by this repository.
