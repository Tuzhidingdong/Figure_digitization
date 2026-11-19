from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .hashing import sha256_file, sha256_json
from .models import InputArtifact, PaperSnapshot, utc_now

ADAPTER_VERSION = "0.1.0"

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


def create_snapshot(paper_dir: Path, corpus_root: Path, paper_id: str | None = None) -> PaperSnapshot:
    paper_dir = paper_dir.resolve()
    corpus_root = corpus_root.resolve()
    paper_id = paper_id or paper_dir.name
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
    present = {item.role for item in artifacts}
    missing = [role for role in ("main_pdf", "figure_inventory") if role not in present]
    payload = {
        "paper_id": paper_id,
        "source_dir": paper_dir.relative_to(corpus_root).as_posix(),
        "adapter_version": ADAPTER_VERSION,
        "artifacts": [{"path": a.path, "role": a.role, "size_bytes": a.size_bytes,
                       "mtime_ns": a.mtime_ns, "sha256": a.sha256} for a in artifacts],
    }
    return PaperSnapshot(
        paper_id=paper_id,
        source_dir=paper_dir.relative_to(corpus_root).as_posix(),
        detected_upstream_version=None,
        adapter_version=ADAPTER_VERSION,
        created_at=utc_now(),
        artifacts=artifacts,
        missing_roles=missing,
        warnings=["Upstream version marker not detected; adapter used artifact discovery."],
        input_fingerprint=sha256_json(payload),
    )
