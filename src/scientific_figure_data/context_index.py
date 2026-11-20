from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .hashing import atomic_write_json, sha256_file, sha256_json

SAMPLE_RE = re.compile(r"\b(?:sample|specimen|electrode|catalyst|material)\s*[-_ ]?[A-Za-z0-9][A-Za-z0-9_.-]{0,40}\b", re.I)
REFERENCE_RE = re.compile(r"\b(?:vs\.?|versus)\s+(?:Ag/AgCl|SCE|SHE|RHE|Hg/HgO|Hg/Hg2SO4|Li/Li\+|Na/Na\+|Zn/Zn2+)\b", re.I)
ERROR_RE = re.compile(r"\b(?:mean\s*[±+/-]\s*(?:SD|SEM)|standard deviation|standard error|95%\s*(?:CI|confidence interval)|n\s*=\s*\d+)\b", re.I)
TEXT_SUFFIXES = {".md", ".txt", ".csv"}


@dataclass
class ContextEntry:
    kind: str
    value: str
    source_path: str
    line_number: int
    snippet: str


def _iter_context_sources(paper_dir: Path):
    """Yield eligible MAIN/SI/table text artifacts in deterministic order."""
    for directory, dirnames, names in os.walk(paper_dir):
        dirnames.sort()
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(paper_dir).as_posix()
            lowered = relative.lower()
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if ("main_analysis" in lowered or "si_analysis" in lowered
                    or "extracted_tables" in lowered or "tables/" in lowered):
                yield path, relative


def _source_fingerprint(sources: list[tuple[str, str]]) -> str:
    return sha256_json(sources)


def _cached_index(index_path: Path, db_path: Path, fingerprint: str,
                  memory_budget_bytes: int) -> "PaperContextIndex | None":
    try:
        metadata = json.loads(index_path.read_text(encoding="utf-8"))
        if metadata.get("schema_version") != "1.0" or metadata.get("fingerprint") != fingerprint:
            return None
        storage = metadata.get("storage")
        if storage == "sqlite":
            if not db_path.is_file():
                return None
            with sqlite3.connect(db_path) as con:
                check = con.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                return None
            return PaperContextIndex([], fingerprint, db_path)
        if storage == "json":
            if int(metadata.get("estimated_memory_bytes", 0)) > memory_budget_bytes:
                return None
            entries = [ContextEntry(**item) for item in metadata.get("entries", [])]
            return PaperContextIndex(entries, fingerprint, None)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        return None
    return None


class PaperContextIndex:
    """Compact cross-page text index with fingerprinted, reusable JSON/SQLite storage."""

    def __init__(self, entries: list[ContextEntry], fingerprint: str, db_path: Path | None = None):
        self.entries = entries
        self.fingerprint = fingerprint
        self.db_path = db_path

    @classmethod
    def build(cls, paper_dir: Path, output_dir: Path, memory_budget_bytes: int = 500_000):
        output_dir.mkdir(parents=True, exist_ok=True)
        index_path = output_dir / "paper_context_index.json"
        db_path = output_dir / "paper_context.sqlite"
        sources = list(_iter_context_sources(paper_dir))
        source_fingerprints = []
        for path, relative in sources:
            try:
                source_fingerprints.append((relative, sha256_file(path)))
            except OSError as exc:
                source_fingerprints.append((relative, f"UNREADABLE:{type(exc).__name__}"))
        fingerprint = _source_fingerprint(source_fingerprints)

        cached = _cached_index(index_path, db_path, fingerprint, memory_budget_bytes)
        if cached is not None:
            return cached

        entries: list[ContextEntry] = []
        estimated = 0
        connection = None
        temporary_db = None

        def persist(entry: ContextEntry):
            nonlocal connection, temporary_db, entries, estimated
            size = len(json.dumps(asdict(entry), ensure_ascii=False).encode("utf-8"))
            if connection is None and estimated + size <= memory_budget_bytes:
                entries.append(entry)
                estimated += size
                return
            if connection is None:
                fd, name = tempfile.mkstemp(prefix=".paper_context.", suffix=".sqlite", dir=output_dir)
                os.close(fd)
                temporary_db = Path(name)
                connection = sqlite3.connect(temporary_db)
                connection.execute(
                    "CREATE TABLE entries(kind TEXT, value TEXT, source_path TEXT, line_number INTEGER, snippet TEXT)"
                )
                connection.execute("CREATE INDEX idx_context_kind ON entries(kind)")
                if entries:
                    connection.executemany(
                        "INSERT INTO entries VALUES(?,?,?,?,?)",
                        [(item.kind, item.value, item.source_path, item.line_number, item.snippet)
                         for item in entries],
                    )
                    entries = []
            connection.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?)",
                (entry.kind, entry.value, entry.source_path, entry.line_number, entry.snippet),
            )

        try:
            for path, relative in sources:
                try:
                    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                        for line_number, line in enumerate(stream, 1):
                            text = " ".join(line.strip().split())
                            if not text:
                                continue
                            found = []
                            found.extend(("sample_alias", match.group(0)) for match in SAMPLE_RE.finditer(text))
                            found.extend(("reference_electrode", match.group(0)) for match in REFERENCE_RE.finditer(text))
                            found.extend(("statistics", match.group(0)) for match in ERROR_RE.finditer(text))
                            for kind, value in found:
                                persist(ContextEntry(kind, value, relative, line_number, text[:500]))
                except OSError:
                    continue

            if connection is not None:
                connection.commit()
                connection.close()
                connection = None
                os.replace(temporary_db, db_path)
                temporary_db = None
                storage = "sqlite"
                stored_entries = []
                estimated_size = memory_budget_bytes
            else:
                storage = "json"
                stored_entries = [asdict(entry) for entry in entries]
                estimated_size = estimated

            atomic_write_json(index_path, {
                "schema_version": "1.0",
                "fingerprint": fingerprint,
                "storage": storage,
                "estimated_memory_bytes": estimated_size,
                "entries": stored_entries,
            })
            if storage == "json" and db_path.exists():
                db_path.unlink()
        except Exception:
            if connection is not None:
                connection.close()
            if temporary_db is not None:
                try:
                    temporary_db.unlink()
                except FileNotFoundError:
                    pass
            raise

        return cls(entries, fingerprint, db_path if storage == "sqlite" else None)

    def search(self, kind: str, text: str = "") -> list[dict]:
        if self.db_path and self.db_path.exists():
            with sqlite3.connect(self.db_path) as con:
                rows = con.execute(
                    "SELECT kind,value,source_path,line_number,snippet FROM entries WHERE kind=? AND value LIKE ? LIMIT 100",
                    (kind, f"%{text}%"),
                ).fetchall()
            return [dict(zip(("kind", "value", "source_path", "line_number", "snippet"), row))
                    for row in rows]
        return [asdict(entry) for entry in self.entries
                if entry.kind == kind and text.casefold() in entry.value.casefold()]
