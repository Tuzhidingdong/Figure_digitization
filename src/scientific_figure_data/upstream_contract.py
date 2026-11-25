from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

UPSTREAM_REPOSITORY = "Tuzhidingdong/chem-literature"
UPSTREAM_COMMIT = "e099406adb689281c0337bcacc7868c3ccdbc438"
UPSTREAM_SCHEMA_PATH = "schemas/source_package.schema.json"
UPSTREAM_SCHEMA_SHA256 = "25994d361c9b87d8255bcadc4899e85dd84fa72f"
SUPPORTED_PACKAGE_VERSION = "1.1.0"
REQUIRED_CSV_COLUMNS = {"doi", "local_pdf_path", "local_si_info"}
PACKAGE_ROOT_KEYS = {
    "package_version", "paper_id", "metadata", "inventory", "pages", "tables",
    "figures", "si_references", "media_assets", "processing_summary",
}
PACKAGE_STATUSES = {
    "COMPLETE", "PARTIAL_NO_SI", "PARTIAL_SI_UNSUPPORTED", "WARNING_SCANNED_PAGES",
}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class CorpusPackage:
    paper_dir: Path
    paper_id: str
    doi: str
    row_number: int
    preprocessing_status: str


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_package_file(package_dir: Path, relative_path: str) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    candidate = (package_dir / relative_path).resolve()
    try:
        candidate.relative_to(package_dir.resolve())
    except ValueError:
        return None
    return candidate


def validate_evidence_index(package_dir: Path) -> tuple[dict | None, list[str], list[str]]:
    """Validate the pinned Chem-Literature 1.1.0 package contract without third-party deps."""
    errors: list[str] = []
    warnings: list[str] = []
    evidence_path = package_dir / "evidence_index.json"
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"evidence_index.json cannot be read: {type(exc).__name__}"], warnings
    if not _is_mapping(payload):
        return None, ["evidence_index root must be an object"], warnings

    missing = sorted(PACKAGE_ROOT_KEYS - set(payload))
    if missing:
        errors.append(f"missing root keys: {', '.join(missing)}")
    version = payload.get("package_version")
    if version != SUPPORTED_PACKAGE_VERSION:
        errors.append(
            f"unsupported package_version {version!r}; expected exact {SUPPORTED_PACKAGE_VERSION}"
        )
    paper_id = payload.get("paper_id")
    if not isinstance(paper_id, str) or not paper_id.strip():
        errors.append("paper_id must be a non-empty string")

    metadata = payload.get("metadata")
    if not _is_mapping(metadata):
        errors.append("metadata must be an object")
    else:
        for key in ("doi", "title", "has_si"):
            if key not in metadata:
                errors.append(f"metadata.{key} is required")

    inventory = payload.get("inventory")
    main_pdf = inventory.get("main_pdf") if _is_mapping(inventory) else None
    if not _is_mapping(main_pdf):
        errors.append("inventory.main_pdf must be an object")
    else:
        for key in ("path", "sha256", "size_bytes", "page_count"):
            if key not in main_pdf:
                errors.append(f"inventory.main_pdf.{key} is required")
        if not isinstance(main_pdf.get("path"), str) or not main_pdf.get("path", "").strip():
            errors.append("inventory.main_pdf.path must be a non-empty string")
        if not isinstance(main_pdf.get("sha256"), str) or not SHA256_RE.fullmatch(main_pdf.get("sha256", "")):
            errors.append("inventory.main_pdf.sha256 must be a lowercase SHA256")
        if not isinstance(main_pdf.get("size_bytes"), int) or main_pdf.get("size_bytes", -1) < 0:
            errors.append("inventory.main_pdf.size_bytes must be a non-negative integer")
        if not isinstance(main_pdf.get("page_count"), int) or main_pdf.get("page_count", 0) < 1:
            errors.append("inventory.main_pdf.page_count must be a positive integer")

    array_keys = ("pages", "tables", "figures", "si_references", "media_assets")
    for key in array_keys:
        if not isinstance(payload.get(key), list):
            errors.append(f"{key} must be an array")

    summary = payload.get("processing_summary")
    if not _is_mapping(summary):
        errors.append("processing_summary must be an object")
    elif summary.get("status") not in PACKAGE_STATUSES:
        errors.append(f"unsupported successful package status {summary.get('status')!r}")

    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    media_assets = payload.get("media_assets") if isinstance(payload.get("media_assets"), list) else []
    figure_ids = {
        item.get("figure_id") for item in figures
        if _is_mapping(item) and isinstance(item.get("figure_id"), str)
    }
    for index, asset in enumerate(media_assets):
        if not _is_mapping(asset):
            errors.append(f"media_assets[{index}] must be an object")
            continue
        rel = asset.get("relative_path")
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"media_assets[{index}].relative_path is required")
            continue
        asset_path = _safe_package_file(package_dir, rel)
        if asset_path is None:
            errors.append(f"media_assets[{index}].relative_path escapes package or is invalid")
            continue
        expected = asset.get("sha256")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            errors.append(f"media_assets[{index}].sha256 must be a lowercase SHA256")
        elif not asset_path.is_file():
            errors.append(f"media asset is missing: {rel}")
        elif _sha256(asset_path) != expected:
            errors.append(f"media asset SHA256 mismatch: {rel}")
        if asset.get("asset_type") == "figure":
            figure_id = asset.get("figure_id")
            if figure_id not in figure_ids:
                warnings.append(
                    f"figure media asset {asset.get('asset_id')!r} has no matching figure_id"
                )

    # A figure bbox in this upstream contract is not a crop. Only media_assets paths
    # with asset_type=figure and a matching figure_id may identify an image crop.
    return payload, errors, warnings


def load_corpus_packages(
    corpus_csv: Path, corpus_root: Path, input_root: Path,
) -> tuple[list[CorpusPackage], list[dict[str, Any]]]:
    """Resolve CSV preprocessing_path values against the upstream workflow CWD."""
    corpus_root = corpus_root.resolve()
    input_root = input_root.resolve()
    csv_path = corpus_csv if corpus_csv.is_absolute() else corpus_root / corpus_csv
    csv_path = csv_path.resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"Corpus CSV not found: {csv_path}")
    try:
        csv_path.relative_to(corpus_root)
    except ValueError as exc:
        raise ValueError("Corpus CSV must be located inside --corpus-root") from exc

    packages: list[CorpusPackage] = []
    skipped: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_CSV_COLUMNS - fields)
        if missing:
            raise ValueError(f"Corpus CSV missing required columns: {', '.join(missing)}")
        if "preprocessing_path" not in fields:
            raise ValueError(
                "Corpus CSV has no preprocessing_path; run the Chem-Literature preprocessing stage first"
            )
        for row_number, row in enumerate(reader, start=2):
            doi = (row.get("doi") or "").strip()
            status = (row.get("preprocessing_status") or "").strip().upper()
            raw_path = (row.get("preprocessing_path") or "").strip()
            if status == "FAILED":
                skipped.append({"row": row_number, "doi": doi, "reason": "UPSTREAM_PREPROCESSING_FAILED"})
                continue
            if not raw_path:
                skipped.append({"row": row_number, "doi": doi, "reason": "NO_PREPROCESSING_PATH"})
                continue
            declared = Path(raw_path).expanduser()
            candidate = declared if declared.is_absolute() else corpus_root / declared
            package_dir = candidate.resolve()
            try:
                package_dir.relative_to(input_root)
            except ValueError as exc:
                raise ValueError(
                    f"CSV row {row_number}: preprocessing_path is outside --input-root"
                ) from exc
            if not package_dir.is_dir():
                skipped.append({"row": row_number, "doi": doi, "reason": "PACKAGE_DIRECTORY_MISSING"})
                continue
            payload, errors, warnings = validate_evidence_index(package_dir)
            if errors:
                skipped.append({
                    "row": row_number, "doi": doi, "reason": "INVALID_UPSTREAM_PACKAGE",
                    "errors": errors,
                })
                continue
            assert payload is not None
            package_id = str(payload["paper_id"])
            packages.append(CorpusPackage(
                paper_dir=package_dir, paper_id=package_id, doi=doi,
                row_number=row_number, preprocessing_status=status or "UNKNOWN",
            ))
            if warnings:
                skipped.append({
                    "row": row_number, "doi": doi, "reason": "PACKAGE_WARNINGS",
                    "warnings": warnings,
                })
    return packages, skipped
