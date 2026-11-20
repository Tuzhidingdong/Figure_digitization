from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any


def _license_file_names(distribution: metadata.Distribution) -> list[str]:
    try:
        files = distribution.files or []
    except Exception:
        files = []
    markers = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT", "PATENTS")
    names = []
    for entry in files:
        path = Path(str(entry))
        if path.name.upper().startswith(markers):
            names.append(path.as_posix())
    return sorted(set(names), key=str.casefold)


def _package_record(distribution: metadata.Distribution) -> dict[str, Any]:
    meta = distribution.metadata
    name = str(meta.get("Name") or "UNKNOWN")
    version = str(distribution.version or "UNKNOWN")
    license_expression = (meta.get("License-Expression") or "").strip() or None
    license_text = (meta.get("License") or "").strip() or None
    classifiers = [
        item for item in (meta.get_all("Classifier") or [])
        if item.startswith("License ::")
    ]
    license_files = _license_file_names(distribution)

    if license_expression:
        status = "SPDX_EXPRESSION_DECLARED"
    elif license_text:
        status = "RAW_LICENSE_FIELD_REQUIRES_REVIEW"
    elif classifiers:
        status = "LICENSE_CLASSIFIERS_ONLY_REQUIRES_REVIEW"
    elif license_files:
        status = "LICENSE_FILES_ONLY_REQUIRES_REVIEW"
    else:
        status = "LICENSE_METADATA_MISSING"

    return {
        "name": name,
        "version": version,
        "status": status,
        "license_expression": license_expression,
        "license_text": license_text,
        "license_classifiers": classifiers,
        "license_file_names": license_files,
        "requires_dist": sorted(distribution.requires or [], key=str.casefold),
        "project_urls": meta.get_all("Project-URL") or [],
    }


def _installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def build_inventory() -> dict[str, Any]:
    packages = [_package_record(item) for item in metadata.distributions()]
    packages.sort(key=lambda item: (item["name"].casefold(), item["version"]))
    counts = Counter(item["status"] for item in packages)
    return {
        "schema_version": "1.0",
        "inventory_kind": "INSTALLED_PYTHON_DISTRIBUTION_METADATA",
        "generated_for": {
            "python_version": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "sbom_generator": {
            "distribution": "cyclonedx-bom",
            "version": _installed_version("cyclonedx-bom"),
        },
        "summary": {
            "package_count": len(packages),
            "license_status_counts": dict(sorted(counts.items())),
            "manual_review_required_count": sum(
                count for status, count in counts.items()
                if status != "SPDX_EXPRESSION_DECLARED"
            ),
        },
        "interpretation": (
            "SPDX expressions are reported as declared by package metadata, not legally validated. "
            "Raw License fields, classifiers, license-file-only packages, and missing metadata "
            "require human review. This inventory does not inspect every native binary notice or "
            "external model/data file."
        ),
        "packages": packages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write an inventory of installed Python package license metadata."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
