from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scientific_figure_data import hashing
from scientific_figure_data.pipeline import _bounded_render_scale, _check_memory_budget


def test_render_scale_obeys_both_pixel_area_and_long_edge_limits():
    area_limited = _bounded_render_scale(
        render_scale=4.0, page_width=2000, page_height=3000,
        max_render_pixels=3_000_000, max_render_long_edge=3200,
    )
    assert area_limited == pytest.approx(0.70710678)

    edge_limited = _bounded_render_scale(
        render_scale=4.0, page_width=1000, page_height=3000,
        max_render_pixels=20_000_000, max_render_long_edge=3200,
    )
    assert edge_limited == pytest.approx(1.06666667)


def test_memory_soft_limit_runs_best_effort_gc_and_records_trigger(monkeypatch):
    values = iter([150 * 1024 * 1024, 90 * 1024 * 1024])

    class FakeProcess:
        def memory_info(self):
            return SimpleNamespace(rss=next(values))

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=FakeProcess))
    result = _check_memory_budget(soft_limit_mb=100, hard_limit_mb=200)
    assert result["soft_limit_triggered"] is True
    assert result["soft_limit_exceeded_after_gc"] is False
    assert result["rss_before_gc_bytes"] > result["rss_bytes"]


def test_memory_hard_limit_raises_after_best_effort_gc(monkeypatch):
    values = iter([250 * 1024 * 1024, 220 * 1024 * 1024])

    class FakeProcess:
        def memory_info(self):
            return SimpleNamespace(rss=next(values))

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=FakeProcess))
    with pytest.raises(MemoryError, match="hard limit"):
        _check_memory_budget(soft_limit_mb=100, hard_limit_mb=200)


def test_atomic_replace_retries_transient_windows_sharing_violation(tmp_path: Path, monkeypatch):
    destination = tmp_path / "manifest.json"
    destination.write_bytes(b"old")
    original_replace = os.replace
    calls = {"count": 0}

    def flaky_replace(source, target):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError(13, "sharing violation")
        return original_replace(source, target)

    monkeypatch.setattr(hashing.os, "replace", flaky_replace)
    monkeypatch.setattr(hashing.time, "sleep", lambda _: None)
    hashing.atomic_write_bytes(destination, b"new")
    assert calls["count"] == 3
    assert destination.read_bytes() == b"new"


def test_atomic_replace_failure_preserves_previous_valid_artifact(tmp_path: Path, monkeypatch):
    destination = tmp_path / "manifest.json"
    destination.write_bytes(b"previous-valid")
    monkeypatch.setattr(
        hashing.os, "replace",
        lambda *_args: (_ for _ in ()).throw(PermissionError(13, "sharing violation")),
    )
    monkeypatch.setattr(hashing.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        hashing.atomic_write_bytes(destination, b"new-invalid")
    assert destination.read_bytes() == b"previous-valid"
    assert list(tmp_path.glob("*.tmp")) == []


def test_v21_cli_defaults_match_worker_and_overview_limits():
    from scientific_figure_data.cli import build_parser

    args = build_parser().parse_args([
        "run", "--all", "--input-root", "E:/input", "--output-root", "E:/output",
    ])
    assert args.memory_soft_limit == 1434
    assert args.memory_limit == 1843
    assert args.max_render_long_edge == 3200
    assert args.max_render_pixels == 10_240_000
