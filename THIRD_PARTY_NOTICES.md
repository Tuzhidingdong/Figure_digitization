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
| rapidocr | Optional OCR | Version 3.10.0; package metadata declares Apache-2.0 in the Windows/Python 3.12 snapshot | OCR model weights and preprocessing dependencies must be inventoried separately |
| opencv-python-headless | Transitive optional OCR dependency via RapidOCR | Version 5.1.0.95 in the Windows/Python 3.12 snapshot; raw License field says "Apache 2.0" and Apache classifiers/license files are present, but no SPDX License-Expression was declared | Manual review of the exact wheel and bundled third-party notices required before OCR distribution; not a base-package dependency |
| onnxruntime | Optional CPU OCR inference | MIT | CPU runtime only; configure one intra-op and one inter-op thread |
| pdfminer.six | Backend spike candidate; not a core dependency | MIT | Include notice if adopted/distributed |
| pikepdf / QPDF | Backend spike candidate; not a core dependency | MPL-2.0 for pikepdf; QPDF component notices also apply | Review the exact wheel's bundled dependencies |
| PyMuPDF | Not selected by default | AGPL-3.0 or commercial licensing | Do not add without a separate license decision |

OpenCV is not a direct dependency of the base package, but the dependency audit confirms that `opencv-python-headless` is installed transitively when the optional RapidOCR OCR extra is installed. The version shown above is a point-in-time Windows/Python 3.12 resolution, not a project-wide lock. Its raw license metadata is not treated as a validated SPDX expression. This table and the generated SBOM are engineering inventory evidence, not legal advice or a release approval; inspect the selected wheel's bundled notices, external OCR model/data terms, and every exact release dependency before distribution.

The **Dependency and License Inventory** GitHub Actions workflow builds an inventory from the actual Windows/Python 3.12 environment with all declared extras installed. It publishes three artifacts: a CycloneDX 1.6 JSON SBOM, an exact pip-freeze snapshot, and a package-metadata license report (raw License / License-Expression fields, license classifiers, and packaged license-file names). The report separates declared SPDX expressions from raw text, classifier-only declarations, license-file-only packages, and packages with no license metadata.

These generated files are evidence for review, not legal approval. The workflow does not validate whether a declared license is compatible with this project, does not inspect every license text bundled inside native wheels, and does not inventory OCR model weights downloaded separately from Python packages. Before distribution, resolve all missing/ambiguous metadata, inspect bundled notices and model terms, and preserve notices from the exact selected package set. No OCR weights are bundled by this repository.
