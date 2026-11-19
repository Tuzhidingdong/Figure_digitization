from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Iterator

from .manifest import create_snapshot
from .models import PaperSnapshot


def discover_papers(input_root: Path) -> Iterator[Path]:
    """Yield paper candidates lazily and do not descend into a detected paper's assets."""
    root = input_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input root does not exist or is not a directory: {root}")
    for directory, dirnames, filenames in os.walk(root):
        dirnames.sort()
        names = {name.lower() for name in filenames}
        if any(name.endswith(".pdf") for name in names) or names.intersection({
            "paper_manifest.json", "manifest.json", "figure_inventory.json",
            "figures.json", "main_analysis.md", "si_analysis.md"
        }):
            yield Path(directory)
            dirnames[:] = []


def snapshot_paper(paper_dir: Path, input_root: Path) -> PaperSnapshot:
    return create_snapshot(paper_dir, input_root, paper_dir.name)


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


def locate_pdf(paper_dir: Path, snapshot: PaperSnapshot) -> Path | None:
    for artifact in snapshot.artifacts:
        if artifact.role == "main_pdf":
            candidate = (paper_dir.parent.parent / artifact.path).resolve()
            try:
                candidate.relative_to(paper_dir.resolve())
            except ValueError:
                # The relative path is corpus-root relative; use its basename only within this paper.
                candidate = paper_dir / Path(artifact.path).name
            if candidate.is_file():
                return candidate
    return None
