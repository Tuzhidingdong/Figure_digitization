from __future__ import annotations

import os
import tempfile
from pathlib import Path

from scientific_figure_data.scheduler import _directory_file_bytes, _worker_initializer


def test_directory_file_bytes_counts_nested_regular_files(tmp_path: Path):
    root = tmp_path / "scratch"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (root / "root.bin").write_bytes(b"12345")
    (nested / "nested.bin").write_bytes(b"abcdefg")

    assert _directory_file_bytes(root) == 12
    assert _directory_file_bytes(root / "missing") == 0


def test_worker_initializer_redirects_all_temp_variables_to_run_scope(tmp_path: Path):
    temp_root = tmp_path / "isolated-temp"
    temp_root.mkdir()
    original_tempdir = tempfile.tempdir
    try:
        _worker_initializer(str(temp_root))
        assert tempfile.gettempdir() == str(temp_root)
        assert os.environ["TMP"] == str(temp_root)
        assert os.environ["TEMP"] == str(temp_root)
        assert os.environ["TMPDIR"] == str(temp_root)
    finally:
        tempfile.tempdir = original_tempdir
