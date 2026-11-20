from __future__ import annotations

import os
import shutil
import time
import json
import traceback
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context
from pathlib import Path
from typing import Iterable

from .models import JobState, PaperSnapshot, utc_now
from .manifest import storage_paper_id
from .adapter import snapshot_paper
from .storage import connect_catalog, Catalog
from .hashing import atomic_write_json, sha256_json


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


def _process_paper_task(input_root: str, paper_relative: str, output_root: str,
                        options: dict, input_snapshot: PaperSnapshot) -> dict:
    from .pipeline import process_paper
    cpu_started = time.process_time()
    result = process_paper(
        Path(input_root), Path(paper_relative), Path(output_root), options,
        input_snapshot=input_snapshot,
    )
    result["_worker_pid"] = os.getpid()
    result["_worker_cpu_seconds"] = max(0.0, time.process_time() - cpu_started)
    return result


def _free_disk_bytes(path: Path) -> int | None:
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def _free_memory_bytes() -> int | None:
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except (ImportError, OSError):
        return None


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

    def start(self, paper_id: str, worker_id: str | None = None,
              input_fingerprint: str | None = None):
        now = time.time()
        with self.con:
            self.con.execute(
                """UPDATE jobs SET state=?,attempt_count=attempt_count+1,worker_id=?,worker_pid=NULL,
                   started_at=?,input_fingerprint=?,heartbeat_at=?,lease_expires_at=?,
                   current_stage=?,last_error=NULL,updated_at=? WHERE paper_id=?""",
                (JobState.RUNNING.value, worker_id or f"scheduler-{os.getpid()}",
                 utc_now(), input_fingerprint, now, now + self.lease_seconds,
                 "PAPER_PROCESSING", utc_now(), paper_id),
            )
            self.event(paper_id, "JOB_STARTED", {
                "worker_id": worker_id or f"scheduler-{os.getpid()}",
                "input_fingerprint": input_fingerprint,
            })

    def heartbeat(self, paper_id: str):
        now = time.time()
        with self.con:
            self.con.execute(
                "UPDATE jobs SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE paper_id=?",
                (now, now + self.lease_seconds, utc_now(), paper_id))

    def finish(self, paper_id: str, state: str, error: str | None = None,
               worker_pid: int | None = None):
        with self.con:
            self.con.execute(
                """UPDATE jobs SET state=?,worker_pid=COALESCE(?,worker_pid),
                   lease_expires_at=NULL,updated_at=?,last_error=? WHERE paper_id=?""",
                (state, worker_pid, utc_now(), error, paper_id))
            payload = {"error": error} if error else {}
            if worker_pid is not None:
                payload["worker_pid"] = worker_pid
            self.event(paper_id, state, payload)

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
    requested_workers = workers
    max_open_pdfs = int((options or {}).get("max_open_pdfs", workers))
    if max_open_pdfs < 1:
        raise ValueError("max_open_pdfs must be at least 1")
    workers = min(workers, max_open_pdfs)
    input_root = input_root.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = time.perf_counter()
    parent_cpu_started = time.process_time()
    completed_worker_cpu_seconds = 0.0
    total_paper_evidence_bytes = 0
    peak_paper_evidence_bytes = 0
    total_context_index_bytes = 0
    peak_context_index_bytes = 0
    peak_budgeted_paper_storage_bytes = 0
    peak_rss_bytes = 0
    options = options or {}
    min_free_disk_mb = max(0, int(options.get("min_free_disk_mb", 256)))
    min_free_memory_mb = max(0, int(options.get("min_free_memory_mb", 512)))
    free_disk_start = _free_disk_bytes(output_root)
    minimum_free_disk_bytes_observed = free_disk_start
    free_memory_start = _free_memory_bytes()
    minimum_free_memory_bytes_observed = free_memory_start
    resource_paused = False
    resource_pause_reason = None
    if dry_run:
        count = sum(1 for _ in paper_paths)
        already_cached = int((options or {}).get("resume_cached_skipped", 0))
        return {
            "planned_papers": count,
            "resume_cached_skipped": already_cached,
            "papers_seen": count + already_cached,
            "dry_run": True,
            "workers": workers,
            "discovered_papers": int((options or {}).get("discovered_papers", count + already_cached)),
            "eligible_papers": int((options or {}).get("eligible_papers", count)),
            "skipped_by_selection": int((options or {}).get("skipped_by_selection", 0)),
            "skipped_papers": int((options or {}).get("skipped_by_selection", 0)) + already_cached,
        }
    ledger = JobLedger(output_root / "catalog.sqlite", lease_seconds)
    catalog = Catalog(output_root / "catalog.sqlite")
    results = {"completed": 0, "completed_with_review": 0, "blocked_review_locked": 0,
               "failed": 0, "retried": 0, "cached": 0, "active_jobs_skipped": 0}
    source = iter(paper_paths)
    retry_queue = deque()
    source_exhausted = False
    total_seen = 0
    context = get_context("spawn")

    def new_executor():
        return ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                   initializer=_worker_initializer, max_tasks_per_child=5)

    executor_generation = 1
    executor = new_executor()
    running = {}
    try:
        while running or retry_queue or not source_exhausted:
            if resource_paused and not running:
                break
            while len(running) < workers:
                if min_free_memory_mb > 0:
                    available_memory = _free_memory_bytes()
                    if available_memory is not None:
                        minimum_free_memory_bytes_observed = (
                            available_memory if minimum_free_memory_bytes_observed is None
                            else min(minimum_free_memory_bytes_observed, available_memory)
                        )
                    memory_threshold = min_free_memory_mb * 1024 * 1024
                    if available_memory is None or available_memory < memory_threshold:
                        resource_paused = True
                        source_exhausted = True
                        resource_pause_reason = (
                            "MEMORY_USAGE_UNAVAILABLE" if available_memory is None
                            else f"FREE_MEMORY_BELOW_{min_free_memory_mb}_MB"
                        )
                        break
                if min_free_disk_mb > 0:
                    free_bytes = _free_disk_bytes(output_root)
                    if free_bytes is not None:
                        minimum_free_disk_bytes_observed = (
                            free_bytes if minimum_free_disk_bytes_observed is None
                            else min(minimum_free_disk_bytes_observed, free_bytes)
                        )
                    threshold_bytes = min_free_disk_mb * 1024 * 1024
                    if free_bytes is None or free_bytes < threshold_bytes:
                        resource_paused = True
                        source_exhausted = True
                        resource_pause_reason = (
                            "DISK_USAGE_UNAVAILABLE" if free_bytes is None
                            else f"FREE_DISK_BELOW_{min_free_disk_mb}_MB"
                        )
                        break
                if retry_queue:
                    paper, paper_id = retry_queue.popleft()
                    input_snapshot = snapshot_paper(paper, input_root)
                elif not source_exhausted:
                    try:
                        candidate = next(source)
                    except StopIteration:
                        source_exhausted = True
                        break
                    if (isinstance(candidate, tuple) and len(candidate) == 2
                            and isinstance(candidate[1], PaperSnapshot)):
                        paper, input_snapshot = candidate
                    else:
                        paper = candidate
                        input_snapshot = snapshot_paper(paper, input_root)
                    paper_relative = paper.relative_to(input_root).as_posix()
                    paper_id = input_snapshot.paper_id
                    if not ledger.prepare(paper_id):
                        results["active_jobs_skipped"] += 1
                        continue
                    total_seen += 1
                else:
                    break
                paper_relative = paper.relative_to(input_root).as_posix()
                occupied_slots = {slot for _, _, slot in running.values()}
                worker_slot = next(slot for slot in range(workers) if slot not in occupied_slots)
                worker_id = f"pool-{executor_generation}-slot-{worker_slot + 1}"
                ledger.start(paper_id, worker_id, input_snapshot.input_fingerprint)
                future = executor.submit(
                    _process_paper_task, str(input_root), paper_relative,
                    str(output_root), options, input_snapshot,
                )
                running[future] = (paper, paper_id, worker_slot)
            if not running:
                continue

            done, _ = wait(tuple(running), timeout=3, return_when=FIRST_COMPLETED)
            for future in tuple(done):
                if future not in running:
                    continue
                paper, paper_id, worker_slot = running.pop(future)
                try:
                    result = future.result()
                    completed_worker_cpu_seconds += max(0.0, float(result.get("_worker_cpu_seconds", 0.0)))
                    usage = result.get("resource_usage") or {}
                    evidence_bytes = max(0, int(usage.get("evidence_bytes", 0)))
                    context_bytes = max(0, int(usage.get("context_index_bytes", 0)))
                    budgeted_bytes = max(0, int(usage.get("budgeted_storage_bytes", evidence_bytes + context_bytes)))
                    total_paper_evidence_bytes += evidence_bytes
                    peak_paper_evidence_bytes = max(peak_paper_evidence_bytes, evidence_bytes)
                    total_context_index_bytes += context_bytes
                    peak_context_index_bytes = max(peak_context_index_bytes, context_bytes)
                    peak_budgeted_paper_storage_bytes = max(peak_budgeted_paper_storage_bytes, budgeted_bytes)
                    if result.get("cached"):
                        results["cached"] += 1
                    if result.get("job_state") != JobState.BLOCKED.value:
                        from .models import InputArtifact, SeriesRecord, SeriesPoint
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
                    ledger.finish(paper_id, state, worker_pid=result.get("_worker_pid"))
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
                        for pending_future, (pending_paper, pending_id, pending_slot) in tuple(running.items()):
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
                        executor_generation += 1
                        executor = new_executor()
            for _, paper_id, _ in running.values():
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
    resume_cached_skipped = int(options.get("resume_cached_skipped", 0))
    from .pipeline import ALGORITHM_VERSION, algorithm_implementation_fingerprint
    from .profiles import profile_registry_fingerprint
    from .qc import load_thresholds

    qc_threshold_path = Path(options["qc_thresholds"]) if options.get("qc_thresholds") else None
    qc_thresholds = load_thresholds(qc_threshold_path)
    parent_cpu_seconds = max(0.0, time.process_time() - parent_cpu_started)
    combined_cpu_seconds = parent_cpu_seconds + completed_worker_cpu_seconds
    report = {
        **results,
        "parent_cpu_seconds": round(parent_cpu_seconds, 3),
        "completed_worker_cpu_seconds": round(completed_worker_cpu_seconds, 3),
        "combined_cpu_seconds": round(combined_cpu_seconds, 3),
        "average_cpu_cores": round(combined_cpu_seconds / elapsed, 4) if elapsed else 0.0,
        "average_cpu_percent_of_worker_capacity": (
            round(combined_cpu_seconds / (elapsed * max(1, workers)) * 100, 2) if elapsed else 0.0
        ),
        "total_paper_evidence_bytes": total_paper_evidence_bytes,
        "peak_paper_evidence_bytes": peak_paper_evidence_bytes,
        "total_context_index_bytes": total_context_index_bytes,
        "peak_context_index_bytes": peak_context_index_bytes,
        "peak_budgeted_paper_storage_bytes": peak_budgeted_paper_storage_bytes,
        "disk_usage_measurement_scope": (
            "Per-paper evidence and context-index artifacts for workers that returned results; "
            "does not include the full OS temporary directory, series CSVs or version backups."
        ),
        "cached": results["cached"] + resume_cached_skipped,
        "resume_cached_skipped": resume_cached_skipped,
        "papers_seen": total_seen + results["active_jobs_skipped"] + resume_cached_skipped,
        "discovered_papers": int(options.get("discovered_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped)),
        "eligible_papers": int(options.get("eligible_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped)),
        "skipped_by_selection": int(options.get("skipped_by_selection", 0)),
        "skipped_cached_unchanged": resume_cached_skipped,
        "skipped_active_lease": results["active_jobs_skipped"],
        "selection_scan_complete": not resource_paused,
        "unexamined_due_to_resource_pressure": (
            max(0, int(options.get("discovered_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped))
                - int(options.get("eligible_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped))
                - int(options.get("skipped_by_selection", 0)))
            if resource_paused else 0
        ),
        "skipped_unstarted_resource_pressure": (
            max(0, int(options.get("discovered_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped))
                - int(options.get("eligible_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped))
                - int(options.get("skipped_by_selection", 0)))
            if resource_paused else 0
        ),
        "skipped_papers": (
            int(options.get("skipped_by_selection", 0))
            + resume_cached_skipped
            + results["active_jobs_skipped"]
            + (
                max(0, int(options.get("discovered_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped))
                    - int(options.get("eligible_papers", total_seen + results["active_jobs_skipped"] + resume_cached_skipped))
                    - int(options.get("skipped_by_selection", 0)))
                if resource_paused else 0
            )
        ),
        "workers": workers,
        "requested_workers": requested_workers,
        "max_open_pdfs": max_open_pdfs,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_papers_per_minute": round((total_seen / elapsed) * 60, 3) if elapsed else 0.0,
        "peak_parent_and_worker_rss_bytes": peak_rss_bytes or None,
        "min_free_disk_mb": min_free_disk_mb,
        "min_free_memory_mb": min_free_memory_mb,
        "free_memory_bytes_at_start": free_memory_start,
        "minimum_free_memory_bytes_observed": minimum_free_memory_bytes_observed,
        "free_memory_bytes_at_end": _free_memory_bytes(),
        "free_disk_bytes_at_start": free_disk_start,
        "minimum_free_disk_bytes_observed": minimum_free_disk_bytes_observed,
        "free_disk_bytes_at_end": _free_disk_bytes(output_root),
        "paused_for_resource_pressure": resource_paused,
        "resource_pressure_reason": resource_pause_reason,
        "default_llm_tokens": 0,
        "algorithm_version": ALGORITHM_VERSION,
        "algorithm_implementation_fingerprint": algorithm_implementation_fingerprint(),
        "profile_config_fingerprint": profile_registry_fingerprint(),
        "qc_threshold_source": str(qc_threshold_path) if qc_threshold_path else "BUILTIN_PROVISIONAL",
        "qc_threshold_fingerprint": sha256_json(qc_thresholds),
        "qc_threshold_status": qc_thresholds.get("status", "UNKNOWN"),
    }
    report_con = connect_catalog(output_root / "catalog.sqlite")
    try:
        rows = report_con.execute(
            "SELECT last_error FROM jobs WHERE state='FAILED_PERMANENT' AND last_error IS NOT NULL"
        ).fetchall()
        categories = {}
        for row in rows:
            first_line = str(row["last_error"]).splitlines()[0]
            category = first_line.split(":", 1)[0]
            categories[category] = categories.get(category, 0) + 1
        report["failure_reason_distribution"] = categories
        report["job_state_counts"] = [
            dict(row) for row in report_con.execute(
                "SELECT state,COUNT(*) AS count FROM jobs GROUP BY state ORDER BY state"
            )
        ]
    finally:
        report_con.close()
    atomic_write_json(output_root / "run_report.json", report)
    return report
