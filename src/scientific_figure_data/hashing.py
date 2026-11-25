from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import errno
from pathlib import Path
from typing import Any, BinaryIO


def sha256_stream(stream: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    with path.open("rb") as handle:
        return sha256_stream(handle, chunk_size)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def replace_with_retry(source: str | Path, destination: str | Path,
                       attempts: int = 5, base_delay_seconds: float = 0.05) -> None:
    """Retry transient Windows sharing violations without touching the prior destination."""
    source_path = Path(source)
    destination_path = Path(destination)
    for attempt in range(max(1, attempts)):
        try:
            os.replace(source_path, destination_path)
            return
        except OSError as exc:
            transient = (
                getattr(exc, "winerror", None) in {32, 33}
                or exc.errno in {errno.EACCES, errno.EBUSY, errno.EPERM}
            )
            if not transient or attempt + 1 >= max(1, attempts):
                raise
            time.sleep(min(0.5, base_delay_seconds * (2 ** attempt)))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        replace_with_retry(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")


def posix_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
