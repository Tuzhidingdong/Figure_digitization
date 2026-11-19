from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from .hashing import atomic_write_json, sha256_file, sha256_json

SAMPLE_RE = re.compile(r"\b(?:sample|specimen|electrode|catalyst|material)\s*[-_ ]?[A-Za-z0-9][A-Za-z0-9_.-]{0,40}\b", re.I)
REFERENCE_RE = re.compile(r"\b(?:vs\.?|versus)\s+(?:Ag/AgCl|SCE|SHE|RHE|Hg/HgO|Hg/Hg2SO4|Li/Li\+|Na/Na\+|Zn/Zn2+)\b", re.I)
ERROR_RE = re.compile(r"\b(?:mean\s*[±+/-]\s*(?:SD|SEM)|standard deviation|standard error|95%\s*(?:CI|confidence interval)|n\s*=\s*\d+)\b", re.I)


@dataclass
class ContextEntry:
    kind: str
    value: str
    source_path: str
    line_number: int
    snippet: str


class PaperContextIndex:
    """Compact cross-page text index; visual PDF pages are never rendered here."""

    def __init__(self, entries: list[ContextEntry], fingerprint: str, db_path: Path | None = None):
        self.entries = entries
        self.fingerprint = fingerprint
        self.db_path = db_path

    @classmethod
    def build(cls, paper_dir: Path, output_dir: Path, memory_budget_bytes: int = 500_000):
        output_dir.mkdir(parents=True, exist_ok=True)
        entries: list[ContextEntry] = []
        fingerprints = []
        estimated = 0
        db_path = output_dir / "paper_context.sqlite"
        if db_path.exists():
            db_path.unlink()
        con = None

        def persist(entry: ContextEntry):
            nonlocal con, entries, estimated
            size = len(json.dumps(asdict(entry), ensure_ascii=False).encode("utf-8"))
            if con is None and estimated + size <= memory_budget_bytes:
                entries.append(entry)
                estimated += size
                return
            if con is None:
                con = sqlite3.connect(db_path)
                con.execute("CREATE TABLE entries(kind TEXT, value TEXT, source_path TEXT, line_number INTEGER, snippet TEXT)")
                con.execute("CREATE INDEX idx_context_kind ON entries(kind)")
                if entries:
                    con.executemany("INSERT INTO entries VALUES(?,?,?,?,?)",
                                    [(e.kind, e.value, e.source_path, e.line_number, e.snippet) for e in entries])
                    entries = []
            con.execute("INSERT INTO entries VALUES(?,?,?,?,?)",
                        (entry.kind, entry.value, entry.source_path, entry.line_number, entry.snippet))

        for directory, _, names in os.walk(paper_dir):
            for name in sorted(names):
                path = Path(directory) / name
                rel = path.relative_to(paper_dir).as_posix().lower()
                if path.suffix.lower() not in {".md", ".txt", ".csv"}:
                    continue
                if not ("main_analysis" in rel or "si_analysis" in rel
                        or "extracted_tables" in rel or "tables/" in rel):
                    continue
                try:
                    fingerprints.append((path.relative_to(paper_dir).as_posix(), sha256_file(path)))
                    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                        for line_number, line in enumerate(stream, 1):
                            text = " ".join(line.strip().split())
                            if not text:
                                continue
                            found = []
                            found.extend(("sample_alias", m.group(0)) for m in SAMPLE_RE.finditer(text))
                            found.extend(("reference_electrode", m.group(0)) for m in REFERENCE_RE.finditer(text))
                            found.extend(("statistics", m.group(0)) for m in ERROR_RE.finditer(text))
                            for kind, value in found:
                                persist(ContextEntry(kind, value, path.relative_to(paper_dir).as_posix(),
                                                     line_number, text[:500]))
                except OSError:
                    continue

        fingerprint = sha256_json(fingerprints)
        if con is not None:
            con.commit()
            con.close()
            entries = []
        else:
            if db_path.exists():
                db_path.unlink()
            db_path = None
        atomic_write_json(output_dir / "paper_context_index.json", {
            "schema_version": "1.0", "fingerprint": fingerprint,
            "storage": "sqlite" if db_path else "json",
            "estimated_memory_bytes": estimated if db_path is None else memory_budget_bytes,
            "entries": [asdict(e) for e in entries],
        })
        return cls(entries, fingerprint, db_path)

    def search(self, kind: str, text: str = "") -> list[dict]:
        if self.db_path and self.db_path.exists():
            with sqlite3.connect(self.db_path) as con:
                rows = con.execute(
                    "SELECT kind,value,source_path,line_number,snippet FROM entries WHERE kind=? AND value LIKE ? LIMIT 100",
                    (kind, f"%{text}%"),
                ).fetchall()
            return [dict(zip(("kind", "value", "source_path", "line_number", "snippet"), row)) for row in rows]
        return [asdict(e) for e in self.entries if e.kind == kind and text.casefold() in e.value.casefold()]
