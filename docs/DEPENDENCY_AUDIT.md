# Dependency and license inventory

The Dependency and License Inventory workflow runs on GitHub for Windows / Python 3.12. It installs the base project and every declared optional extra (pdf, images, ocr, pdf-spike, and dev), then captures the environment actually resolved by pip.

## Artifacts

Each workflow run publishes the artifact named windows-py312-dependency-license-inventory:

- sbom.cdx.json: CycloneDX 1.6 JSON generated from the installed environment, including package identities, dependency relationships, and license metadata where the installed distributions declare it.
- resolved-dependencies.txt: exact package versions reported by pip freeze --all.
- python-license-audit.json: raw distribution metadata, version, dependency declarations, license expression/text/classifiers, and names of packaged license/notice files.

## Interpreting the license report

SPDX_EXPRESSION_DECLARED means a package publishes a License-Expression metadata field. It is not an independent legal validation. RAW_LICENSE_FIELD_REQUIRES_REVIEW, LICENSE_CLASSIFIERS_ONLY_REQUIRES_REVIEW, LICENSE_FILES_ONLY_REQUIRES_REVIEW, and LICENSE_METADATA_MISSING are deliberately retained as human-review items. The script does not guess SPDX identifiers from free text.

## Boundaries

This is a resolved-environment inventory for the Windows/Python 3.12 runner, not a lock file or a legal opinion. It does not inspect all native libraries embedded in wheels, external OCR model weights/data downloaded outside Python package metadata, or all system components on the Windows runner. Final distribution still requires manual review of ambiguous/missing metadata, bundled notices, selected binary wheels, model/data terms, and project-level license policy.
