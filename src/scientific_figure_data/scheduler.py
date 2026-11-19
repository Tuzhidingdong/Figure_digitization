from __future__ import annotations

import os
import time
import json
import traceback
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context
from pathlib import Path
from typing import Iterable

from .models import JobState, utc_now
from .storage import connect_catalog, Catalog
from .hashing import atomic_write_json


def _worker_initializer():
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    try:
        import cv2
        cv2.setNumThreads(1)
    except ImportError:
        pass


def _process_paper_task(input_root: str, paper_relative: str, output_root: str, options: dict) -> dict:
    from .pipeline import process_paper
    return process_paper(Path(input_root), Path(paper_relative), Path(output_root), options)


class JobLedger:
    def __init__(self, db_path: Path, lease_seconds: int = 180):
        self.con = connect_catalog(db_path)
        self.lease_seconds = lease_seconds

    def close(self):
        self.con.close()

    def event(self, paper_id: str, event_type: str, payload: dict):
        self.con.execute(
            "INSERT INTO job_events(paper_id,event_type,created_at,payload_json) VALUES(?,?,?,?)",
            (paper_id, event_type, utc_now(), json.dumps(payload, ensure_ascii=False)),
        )

    def prepare(self, paper_id: str) -> bool:
        with self.con:
            row = self.con.execute("SELECT state,lease_expires_at FROM jobs WHERE paper_id=?",
                                   (paper_id,)).fetchone()
            if row and row["state"] == JobState.RUNNING.value:
                if row["lease_expires_at"] is not None and row["lease_expires_at"] >= time.time():
                    return False
                self.event(paper_id, "INTERRUPTED_RECOVERY", {"previous_state": "RUNNING"})
                self.con.execute(
                    "UPDATE jobs SET state=?,lease_expires_at=NULL,updated_at=? WHERE paper_id=?",
                    (JobState.RETRY_WAIT.value, utc_now(), paper_id))
            self.con.execute(
                """INSERT INTO jobs(paper_id,state,updated_at) VALUES(?,?,?)
                   ON CONFLICT(paper_id) DO NOTHING""",
                (paper_id, JobState.PENDING.value, utc_now()),
            )
        return True

    def start(self, paper_id: str):
        now = time.time()
        with self.con:
            self.con.execute(
                """UPDATE jobs SET state=?,attempt_count=attempt_count+1,heartbeat_at=?,
                   lease_expires_at=?,current_stage=?,last_error=NULL,updated_at=? WHERE paper_id=?""",
                (JobState.RUNNING.value, now, now + self.lease_seconds,
                 "PAPER_PROCESSING", utc_now(), paper_id),
            )
            self.event(paper_id, "JOB_STARTED", {})

    def heartbeat(self, paper_id: str):
        now = time.time()
        with self.con:
            self.con.execute(
                "UPDATE jobs SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE paper_id=?",
                (now, now + self.lease_seconds, utc_now(), paper_id))

    def finish(self, paper_id: str, state: str, error: str | None = None):
        with self.con:
            self.con.execute(
                "UPDATE jobs SET state=?,lease_expires_at=NULL,updated_at=?,last_error=? WHERE paper_id=?",
                (state, utc_now(), error, paper_id))
            self.event(paper_id, state, {"error": error} if error else {})

    def attempt_count(self, paper_id: str) -> int:
        row = self.con.execute("SELECT attempt_count FROM jobs WHERE paper_id=?", (paper_id,)).fetchone()
        return int(row["attempt_count"]) if row else 0

    def status(self):
        return [dict(row) for row in self.con.execute(
            "SELECT state,COUNT(*) AS count FROM jobs GROUP BY state ORDER BY state"
        )]


def run_corpus(input_root: Path, output_root: Path, paper_paths: Iterable[Path],
               workers: int = 1, max_attempts: int = 2, lease_seconds: int = 180,
               dry_run: bool = False, options: dict | None = None) -> dict:
    if workers < 1 or workers > 4:
        raise ValueError("workers must be between 1 and 4; default is 1 for low-memory systems")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    input_root = input_root.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = time.perf_counter()
    peak_rss_bytes = 0
    if dry_run:
        count = sum(1 for _ in paper_paths)
        return {"planned_papers": count, "dry_run": True, "workers": workers}
    ledger = JobLedger(output_root / "catalog.sqlite", lease_seconds)
    catalog = Catalog(output_root / "catalog.sqlite")
    results = {"completed": 0, "completed_with_review": 0, "blocked_review_locked": 0,
               "failed": 0, "retried": 0, "cached": 0, "active_jobs_skipped": 0}
    source = iter(paper_paths)
    retry_queue = deque()
    source_exhausted = False
    total_seen = 0
    options = options or {}
    context = get_context("spawn")

    def new_executor():
        return ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                   initializer=_worker_initializer, max_tasks_per_child=5)

    executor = new_executor()
    running = {}
    try:
        while running or retry_queue or not source_exhausted:
            while len(running) < workers:
                if retry_queue:
                    paper, paper_id = retry_queue.popleft()
                elif not source_exhausted:
                    try:
                        paper = next(source)
                    except StopIteration:
                        source_exhausted = True
                        break
                    paper_id = paper.relative_to(input_root).as_posix()
                    if not ledger.prepare(paper_id):
                        results["active_jobs_skipped"] += 1
                        continue
                    total_seen += 1
                else:
                    break
                ledger.start(paper_id)
                future = executor.submit(_process_paper_task, str(input_root), paper_id,
                                         str(output_root), options)
                running[future] = (paper, paper_id)
            if not running:
                continue

            done, _ = wait(tuple(running), timeout=3, return_when=FIRST_COMPLETED)
            for future in tuple(done):
                if future not in running:
                    continue
                paper, paper_id = running.pop(future)
                try:
                    result = future.result()
                    if result.get("cached"):
                        results["cached"] += 1
                    if result.get("job_state") != JobState.BLOCKED.value:
                        from .models import PaperSnapshot, InputArtifact, SeriesRecord, SeriesPoint
                        snapshot_data = result["snapshot"]
                        snapshot = PaperSnapshot(
                            paper_id=snapshot_data["paper_id"], source_dir=snapshot_data["source_dir"],
                            detected_upstream_version=snapshot_data.get("detected_upstream_version"),
                            adapter_version=snapshot_data["adapter_version"], created_at=snapshot_data["created_at"],
                            artifacts=[InputArtifact(**a) for a in snapshot_data.get("artifacts", [])],
                            missing_roles=snapshot_data.get("missing_roles", []),
                            warnings=snapshot_data.get("warnings", []),
                            input_fingerprint=snapshot_data["input_fingerprint"],
                        )
                        series = []
                        for item in result.get("series", []):
                            series.append(SeriesRecord(**{
                                **item, "points": [SeriesPoint(**p) for p in item.get("points", [])]
                            }))
                        catalog.index_paper(snapshot, result.get("figures", []), result.get("panels", []),
                                            series, result["status"], result.get("artifact_paths"),
                                            paper_root=output_root / "papers" / snapshot.paper_id,
                                            batch_size=int(options.get("batch_size", 1000)))
                    state = result.get("job_state", JobState.COMPLETED.value)
                    ledger.finish(paper_id, state)
                    if state == JobState.BLOCKED.value:
                        results["blocked_review_locked"] += 1
                    elif state in {JobState.NEEDS_REVIEW.value, JobState.COMPLETED_WITH_REVIEW.value}:
                        results["completed_with_review"] += 1
                    else:
                        results["completed"] += 1
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"
                    attempt = ledger.attempt_count(paper_id)
                    retryable = isinstance(exc, (BrokenProcessPool, OSError, TimeoutError, MemoryError))
                    if retryable and attempt < max_attempts:
                        ledger.finish(paper_id, JobState.RETRY_WAIT.value, error)
                        retry_queue.append((paper, paper_id))
                        results["retried"] += 1
                    else:
                        ledger.finish(paper_id, JobState.FAILED_PERMANENT.value, error)
                        results["failed"] += 1
                    if isinstance(exc, BrokenProcessPool):
                        # A broken executor cannot accept more tasks. Unfinished tasks are
                        # requeued; completed canonical artifacts are reused on their retry.
                        for pending_future, (pending_paper, pending_id) in tuple(running.items()):
                            pending_future.cancel()
                            ledger.finish(pending_id, JobState.RETRY_WAIT.value, "WORKER_POOL_BROKEN")
                            if ledger.attempt_count(pending_id) < max_attempts:
                                retry_queue.append((pending_paper, pending_id))
                                results["retried"] += 1
                            else:
                                ledger.finish(pending_id, JobState.FAILED_PERMANENT.value,
                                              "WORKER_POOL_BROKEN: retry limit reached")
                                results["failed"] += 1
                            running.pop(pending_future, None)
                        executor.shutdown(wait=False, cancel_futures=True)
                        executor = new_executor()
            for _, paper_id in running.values():
                ledger.heartbeat(paper_id)
            try:
                import psutil
                process = psutil.Process()
                current_rss = process.memory_info().rss
                for child in process.children(recursive=True):
                    try:
                        current_rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                peak_rss_bytes = max(peak_rss_bytes, current_rss)
            except ImportError:
                pass
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        ledger.close()
        catalog.close()
    elapsed = max(0.0, time.perf_counter() - started_at)
    report = {
        **results,
        "papers_seen": total_seen + results["active_jobs_skipped"],
        "workers": workers,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_papers_per_minute": round((total_seen / elapsed) * 60, 3) if elapsed else 0.0,
        "peak_parent_and_worker_rss_bytes": peak_rss_bytes or None,
        "default_llm_tokens": 0,
        "algorithm_version": "0.1.0",
        "qc_threshold_status": "PROVISIONAL_UNCALIBRATED",
    }
    try:
        rows = ledger.con.execute(
            "SELECT last_error FROM jobs WHERE state='FAILED_PERMANENT' AND last_error IS NOT NULL"
        ).fetchall()
        categories = {}
        for row in rows:
            first_line = str(row["last_error"]).splitlines()[0]
            category = first_line.split(":", 1)[0]
            categories[category] = categories.get(category, 0) + 1
        report["failure_reason_distribution"] = categories
        report["job_state_counts"] = ledger.status()
    except Exception:
        report["failure_reason_distribution"] = {}
    atomic_write_json(output_root / "run_report.json", report)
    return report
