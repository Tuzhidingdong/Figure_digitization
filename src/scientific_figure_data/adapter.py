from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from .manifest import create_snapshot, storage_paper_id
from .models import PaperSnapshot

PAPER_MARKERS = {
    "paper_manifest.json",
    "figure_inventory.json",
    "figures.json",
    "figure_index.json",
    "main_analysis.md",
    "main_analysis.txt",
    "si_analysis.md",
    "si_analysis.txt",
}
ROOT_WEAK_MARKERS = {"manifest.json", "evidence_index.json"}


def discover_papers(input_root: Path) -> Iterator[Path]:
    """Yield paper directories lazily without mistaking a corpus root for one paper.

    A directory with an upstream manifest, Figure inventory, or extracted MAIN/SI
    analysis is a strong paper boundary. A nested PDF-only directory is still treated
    as an incomplete paper so the caller can report the missing upstream artifacts.
    The corpus root is only treated as one paper when it has no child directories.
    """
    root = input_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input root does not exist or is not a directory: {root}")
    for directory, dirnames, filenames in os.walk(root):
        dirnames.sort()
        names = {name.casefold() for name in filenames}
        is_root = Path(directory).resolve() == root
        has_marker = bool(names.intersection(PAPER_MARKERS))
        has_weak_marker = bool(names.intersection(ROOT_WEAK_MARKERS))
        has_pdf = any(name.endswith(".pdf") for name in names)
        root_manifest_is_paper = is_root and has_weak_marker and not dirnames

        if (has_marker or (has_weak_marker and not is_root) or root_manifest_is_paper
                or (has_pdf and not is_root) or (has_pdf and is_root and not dirnames)):
            yield Path(directory)
            # Do not descend into an already identified paper's images/PDF/SI assets.
            dirnames[:] = []


def snapshot_paper(paper_dir: Path, input_root: Path) -> PaperSnapshot:
    relative_id = paper_dir.resolve().relative_to(input_root.resolve()).as_posix()
    if relative_id == ".":
        relative_id = "root-paper"
    return create_snapshot(paper_dir, input_root, relative_id)


def load_json_artifact(paper_dir: Path, relative_to_paper: str) -> dict | list | None:
    path = (paper_dir / relative_to_paper).resolve()
    try:
        path.relative_to(paper_dir.resolve())
    except ValueError as exc:
        raise ValueError("Artifact path escapes paper directory") from exc
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def locate_pdf(paper_dir: Path, input_root: Path, snapshot: PaperSnapshot) -> Path | None:
    for artifact in snapshot.artifacts:
        if artifact.role == "main_pdf":
            candidate = (input_root / artifact.path).resolve()
            try:
                candidate.relative_to(paper_dir.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
    return None



def ensure_unique_paper_ids(papers: Iterator[Path], input_root: Path) -> Iterator[Path]:
    """Fail before writes if two source paths normalize to the same output paper ID."""
    seen: dict[str, str] = {}
    root = input_root.resolve()
    for paper in papers:
        relative = paper.resolve().relative_to(root).as_posix()
        paper_id = storage_paper_id("root-paper" if relative == "." else relative)
        previous = seen.get(paper_id)
        if previous is not None and previous != relative:
            raise ValueError(
                f"Paper ID normalization collision: {previous!r} and {relative!r} "
                f"both map to {paper_id!r}; rename or separate one source directory."
            )
        seen[paper_id] = relative
        yield paper
