from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

from .hashing import sha256_file, sha256_json
from .models import InputArtifact, PaperSnapshot, utc_now

ADAPTER_VERSION = "0.2.0"


def storage_paper_id(paper_id: str) -> str:
    """Normalize a corpus-relative paper path into the stable Windows-safe storage ID."""
    storage_id = str(paper_id).replace("/", "__").replace("\\", "__")
    storage_id = re.sub(r'[<>:"|?*\x00-\x1f]', "_", storage_id).rstrip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if not storage_id or storage_id.upper() in reserved:
        storage_id = "_" + (storage_id or "paper")
    if len(storage_id) > 120:
        storage_id = storage_id[:100] + "_" + sha256_json(paper_id)[:12]
    return storage_id


def iter_files(root: Path) -> Iterable[Path]:
    """Yield files lazily in stable order without materializing the complete file list."""
    for directory, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            yield Path(directory) / filename


def detect_role(relative_posix: str) -> str:
    lowered = relative_posix.lower()
    name = lowered.rsplit("/", 1)[-1]
    if lowered.endswith(".pdf"):
        if any(token in lowered for token in ("/si/", "supplement", "supporting", "_si", "-si")):
            return "si_pdf"
        return "main_pdf"
    if name in {"main_analysis.md", "main_analysis.txt", "main_text.md"}:
        return "main_text"
    if name in {"si_analysis.md", "si_analysis.txt", "supplementary_analysis.md"}:
        return "si_text"
    if name in {"figure_inventory.json", "figures.json", "figure_index.json"}:
        return "figure_inventory"
    if name in {"evidence_index.json", "manifest.json", "paper_manifest.json"}:
        return "evidence_index"
    if "extracted_tables/" in lowered or lowered.startswith("tables/"):
        return "table_data"
    if lowered.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")):
        return "figure_image"
    return "other"


def _extract_version_marker(payload: object, depth: int = 0) -> str | None:
    if not isinstance(payload, dict) or depth > 3:
        return None
    explicit_keys = (
        "chem_literature_version", "upstream_version", "producer_version", "tool_version",
        "package_version",
    )
    for key in explicit_keys:
        value = payload.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
        if isinstance(value, dict):
            nested = value.get("version")
            if isinstance(nested, (str, int, float)) and str(nested).strip():
                name = value.get("name") or value.get("id")
                return f"{name} {nested}".strip() if name else str(nested).strip()
    for key in ("metadata", "meta", "provenance", "producer", "software", "source"):
        marker = _extract_version_marker(payload.get(key), depth + 1)
        if marker:
            return marker
    for key in ("version", "schema_version"):
        value = payload.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            marker = str(value).strip()
            name = payload.get("name") or payload.get("id")
            if isinstance(name, str) and name.strip():
                return f"{name.strip()} {marker}"
            return marker
    return None


def _detect_upstream_version(
    paper_dir: Path, artifacts: list[InputArtifact], source_dir: str,
) -> str | None:
    source_relative = Path(source_dir)
    for artifact in artifacts:
        if artifact.role != "evidence_index":
            continue
        artifact_relative = Path(artifact.path)
        try:
            paper_relative = artifact_relative.relative_to(source_relative)
        except ValueError:
            # Older snapshots may contain only a path relative to the paper directory.
            paper_relative = artifact_relative
        candidate = (paper_dir / paper_relative).resolve()
        try:
            candidate.relative_to(paper_dir.resolve())
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        try:
            with candidate.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            continue
        marker = _extract_version_marker(payload)
        if marker:
            return marker
    return None


def _evidence_payloads(
    paper_dir: Path, corpus_root: Path, artifacts: list[InputArtifact],
) -> Iterable[dict]:
    for artifact in artifacts:
        if artifact.role != "evidence_index":
            continue
        candidate = (corpus_root / artifact.path).resolve()
        try:
            candidate.relative_to(paper_dir.resolve())
        except ValueError:
            continue
        try:
            with candidate.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            yield payload


def _has_embedded_figure_inventory(
    paper_dir: Path, corpus_root: Path, artifacts: list[InputArtifact],
) -> bool:
    return any(isinstance(payload.get("figures"), list)
               for payload in _evidence_payloads(paper_dir, corpus_root, artifacts))


def _resolve_main_pdf_reference(
    paper_dir: Path, corpus_root: Path, artifacts: list[InputArtifact],
    external_path_root: Path | None = None,
) -> tuple[Path | None, list[dict], list[InputArtifact], list[str]]:
    """Resolve the MAIN PDF referenced by Chem-Literature's evidence_index.

    The source preprocessor stores an absolute source path in inventory.main_pdf,
    while the immutable preprocessing package normally contains only crops and
    text. The absolute path is kept in memory only; snapshots store hashes and a
    stable JSON-pointer reference, never the local path.
    """
    if any(item.role == "main_pdf" for item in artifacts):
        return None, [], [], []

    for payload in _evidence_payloads(paper_dir, corpus_root, artifacts):
        inventory = payload.get("inventory")
        entry = inventory.get("main_pdf") if isinstance(inventory, dict) else None
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        expected_hash = str(entry.get("sha256") or "").strip().lower() or None
        reference = "evidence_index.json#/inventory/main_pdf"
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None, [{"reference": reference, "status": "MISSING_PATH",
                           "expected_sha256": expected_hash}], [], [
                "Upstream evidence_index has no inventory.main_pdf.path."
            ]

        declared = Path(raw_path).expanduser()
        candidates = [declared] if declared.is_absolute() else [
            paper_dir / declared,
            (external_path_root or corpus_root) / declared,
            corpus_root / declared,
        ]
        candidate = None
        for value in candidates:
            resolved = value.resolve()
            if not declared.is_absolute():
                try:
                    resolved.relative_to(paper_dir.resolve())
                except ValueError:
                    try:
                        resolved.relative_to(corpus_root.resolve())
                    except ValueError:
                        continue
            if resolved.is_file():
                candidate = resolved
                break

        if candidate is None:
            return None, [{"reference": reference, "status": "MISSING",
                           "expected_sha256": expected_hash}], [], [
                "The MAIN PDF referenced by evidence_index is missing; no source PDF was opened."
            ]

        try:
            stat = candidate.stat()
            with candidate.open("rb") as handle:
                magic = handle.read(5)
            actual_hash = sha256_file(candidate)
        except OSError as exc:
            return None, [{"reference": reference, "status": "UNREADABLE",
                           "expected_sha256": expected_hash}], [], [
                f"The referenced MAIN PDF could not be read ({type(exc).__name__})."
            ]

        if candidate.suffix.lower() != ".pdf" or magic != b"%PDF-":
            status = "INVALID_PDF"
        elif expected_hash and actual_hash != expected_hash:
            status = "HASH_MISMATCH"
        elif expected_hash:
            status = "HASH_VERIFIED"
        else:
            status = "HASH_COMPUTED_NO_EXPECTED_SHA256"

        try:
            relative = candidate.relative_to(corpus_root).as_posix()
            in_corpus = True
        except ValueError:
            relative = None
            in_corpus = False

        source_record = {
            "reference": reference,
            "status": status,
            "scope": "INPUT_ROOT" if in_corpus else "EXTERNAL",
            "sha256": actual_hash,
            "expected_sha256": expected_hash,
            "size_bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }
        if status not in {"HASH_VERIFIED", "HASH_COMPUTED_NO_EXPECTED_SHA256"}:
            return None, [source_record], [], [
                f"The referenced MAIN PDF failed integrity checks ({status}); it was not used."
            ]

        additions: list[InputArtifact] = []
        if in_corpus and relative and not any(item.path == relative for item in artifacts):
            additions.append(InputArtifact(
                path=relative, role="main_pdf", size_bytes=int(stat.st_size),
                mtime_ns=int(stat.st_mtime_ns), sha256=actual_hash,
            ))
        external_sources = [] if in_corpus else [source_record]
        return candidate, external_sources, additions, []

    return None, [], [], []


def create_snapshot(
    paper_dir: Path, corpus_root: Path, paper_id: str | None = None,
    external_path_root: Path | None = None,
) -> PaperSnapshot:
    paper_dir = paper_dir.resolve()
    corpus_root = corpus_root.resolve()
    paper_id = paper_id or paper_dir.relative_to(corpus_root).as_posix()
    artifacts: list[InputArtifact] = []
    for path in iter_files(paper_dir):
        try:
            stat = path.stat()
            relative = path.relative_to(corpus_root).as_posix()
            role = detect_role(path.relative_to(paper_dir).as_posix())
            artifacts.append(InputArtifact(path=relative, role=role, size_bytes=stat.st_size,
                                           mtime_ns=stat.st_mtime_ns, sha256=sha256_file(path)))
        except (OSError, ValueError) as exc:
            artifacts.append(InputArtifact(
                path=path.name, role="unreadable", size_bytes=-1, mtime_ns=-1,
                sha256=f"UNREADABLE:{type(exc).__name__}",
            ))
    source_pdf, external_sources, referenced_artifacts, source_warnings = _resolve_main_pdf_reference(
        paper_dir, corpus_root, artifacts, external_path_root=external_path_root,
    )
    artifacts.extend(referenced_artifacts)
    present = {item.role for item in artifacts}
    if source_pdf is not None:
        present.add("main_pdf")
    if _has_embedded_figure_inventory(paper_dir, corpus_root, artifacts):
        present.add("figure_inventory")
    missing = [role for role in ("main_pdf", "figure_inventory") if role not in present]
    warnings = list(source_warnings)
    for role in ("main_pdf", "figure_inventory", "evidence_index"):
        count = sum(1 for item in artifacts if item.role == role)
        if count > 1:
            warnings.append(f"Multiple {role} candidates detected ({count}); deterministic first-candidate routing applies.")
    if "figure_inventory" not in present and "evidence_index" in present:
        warnings.append("No standalone figure inventory; downstream adapter will inspect evidence-index manifests for embedded figures.")
    source_dir = paper_dir.relative_to(corpus_root).as_posix()
    upstream_version = _detect_upstream_version(paper_dir, artifacts, source_dir)
    payload = {
        "paper_id": paper_id, "source_dir": source_dir,
        "adapter_version": ADAPTER_VERSION,
        "artifacts": [{"path": a.path, "role": a.role, "size_bytes": a.size_bytes,
                       "mtime_ns": a.mtime_ns, "sha256": a.sha256} for a in artifacts],
        "external_sources": external_sources,
    }
    storage_id = storage_paper_id(paper_id)
    return PaperSnapshot(
        paper_id=storage_id,
        source_dir=source_dir,
        detected_upstream_version=upstream_version,
        adapter_version=ADAPTER_VERSION, created_at=utc_now(),
        artifacts=artifacts, missing_roles=missing,
        warnings=warnings + ([] if upstream_version else ["Upstream version marker not detected; artifact discovery adapter used."]),
        input_fingerprint=sha256_json(payload),
        external_sources=external_sources,
        resolved_main_pdf=source_pdf,
    )
