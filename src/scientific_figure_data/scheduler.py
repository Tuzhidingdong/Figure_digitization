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
from .adapter import snapshot_paper, validate_disjoint_roots
from .storage import connect_catalog, Catalog
from .hashing import atomic_write_json, sha256_json


def _worker_initializer(
    temp_directory: str | None = None,
    worker_log_directory: str | None = None,
):
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    if temp_directory:
        for variable in ("TMP", "TEMP", "TMPDIR"):
            os.environ[variable] = temp_directory
        import tempfile
        tempfile.tempdir = temp_directory

    # A spawned worker must not keep the caller's stdout/stderr pipe open.
    # This is especially important on Windows, where a surviving child can
    # otherwise prevent PowerShell/Tee-Object from observing end-of-file after
    # an abnormal parent exit. Keep worker diagnostics in a per-run log instead.
    if worker_log_directory:
        from pathlib import Path
        Path(worker_log_directory).mkdir(parents=True, exist_ok=True)
        log_path = Path(worker_log_directory) / f"worker-{os.getpid()}.log"
        try:
            import sys
            for stream in (sys.stdout, sys.stderr):
                try:
                    stream.flush()
                except Exception:
                    pass
            log_handle = open(log_path, "a", encoding="utf-8", buffering=1)
            os.dup2(log_handle.fileno(), 1)
            os.dup2(log_handle.fileno(), 2)
            log_handle.close()
        except OSError:
            # Fall back to os.devnull so the worker still releases inherited
            # console/pipe handles even when the diagnostic directory is not writable.
            devnull = open(os.devnull, "w", encoding="utf-8")
            os.dup2(devnull.fileno(), 1)
            os.dup2(devnull.fileno(), 2)
            devnull.close()

    try:
        import cv2
        cv2.setNumThreads(1)
    except ImportError:
        pass

    # ProcessPoolExecutor workers may be executing native OCR/image code when
    # their parent disappears. The parent sentinel is more reliable than PID
    # polling (which can be confused by PID reuse); exit promptly if orphaned.
    try:
        from multiprocessing import parent_process
        from threading import Thread

        parent = parent_process()
        if parent is not None:
            def watch_parent():
                while True:
                    try:
                        if not parent.is_alive():
                            os._exit(0)
                    except Exception:
                        os._exit(0)
                    time.sleep(1.0)

            Thread(
                target=watch_parent,
                name="sfd-parent-liveness-guard",
                daemon=True,
            ).start()
    except Exception:
        # The bounded executor shutdown remains the fallback if a runtime does
        # not expose parent_process() as expected.
        pass


def _shutdown_executor_bounded(executor, grace_seconds: float = 8.0) -> dict:
    """Stop only this executor's children, with a bounded wait and escalation.

    ProcessPoolExecutor.shutdown(wait=True) can wait forever for a stuck native
    worker. Capture the executor-owned process handles, request normal shutdown,
    then terminate/kill only those exact children if they do not exit in time.
    """
    if executor is None:
        return {"status": "NOT_CREATED", "workers": []}

    processes = list((getattr(executor, "_processes", None) or {}).values())
    shutdown_error = None
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        try:
            executor.shutdown(wait=False)
        except Exception as exc:
            shutdown_error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        shutdown_error = f"{type(exc).__name__}: {exc}"

    deadline = time.monotonic() + max(0.0, float(grace_seconds))
    for process in processes:
        try:
            process.join(timeout=max(0.0, deadline - time.monotonic()))
        except (AssertionError, OSError, ValueError):
            continue

    worker_reports = []
    for process in processes:
        try:
            alive = process.is_alive()
        except (AssertionError, OSError, ValueError):
            alive = False
        action = "EXITED_GRACEFULLY"
        if alive:
            action = "TERMINATE_SENT"
            try:
                process.terminate()
                process.join(timeout=2.0)
            except (AssertionError, OSError, ValueError):
                pass
            try:
                alive = process.is_alive()
            except (AssertionError, OSError, ValueError):
                alive = False
        if alive and callable(getattr(process, "kill", None)):
            action = "KILL_SENT"
            try:
                process.kill()
                process.join(timeout=2.0)
            except (AssertionError, OSError, ValueError):
                pass
            try:
                alive = process.is_alive()
            except (AssertionError, OSError, ValueError):
                alive = False
        worker_reports.append({
            "pid": getattr(process, "pid", None),
            "exitcode": getattr(process, "exitcode", None),
            "action": action,
            "still_alive": bool(alive),
        })

    return {
        "status": (
            "WORKERS_REAPED" if not any(item["still_alive"] for item in worker_reports)
            else "WORKER_REMAINS_AFTER_KILL"
        ),
        "shutdown_error": shutdown_error,
        "workers": worker_reports,
    }


def _process_paper_task(input_root: str, paper_relative: str, output_root: str,
                        options: dict, input_snapshot: PaperSnapshot) -> dict:
    from .pipeline import process_paper
    cpu_started = time.process_time()
    result = process_paper(
        Path(input_root), Path(paper_relative), Path(output_root), options,
        input_snapshot=input_snapshot,
    )
    import tempfile
    result["_worker_pid"] = os.getpid()
    result["_worker_cpu_seconds"] = max(0.0, time.process_time() - cpu_started)
    result["_worker_temp_directory"] = tempfile.gettempdir()
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


def _directory_file_bytes(root: Path) -> int:
    """Measure regular-file bytes under an application-owned directory without following links."""
    if not root.is_dir():
        return 0
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += int(entry.stat(follow_symlinks=False).st_size)
                    except OSError:
                        continue
        except OSError:
            continue
    return total


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
    input_root, output_root = validate_disjoint_roots(input_root, output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = time.perf_counter()
    parent_cpu_started = time.process_time()
    completed_worker_cpu_seconds = 0.0
    total_paper_evidence_bytes = 0
    peak_paper_evidence_bytes = 0
    total_context_index_bytes = 0
    peak_context_index_bytes = 0
    peak_budgeted_paper_storage_bytes = 0
    total_returned_paper_output_bytes = 0
    peak_single_paper_output_bytes = 0
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
    import tempfile
    temp_parent = output_root / ".sfd-runtime-tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    run_temp_directory = Path(tempfile.mkdtemp(prefix=f"run-{os.getpid()}-", dir=temp_parent))
    worker_log_directory = (
        output_root / "logs" / f"workers-run-{os.getpid()}-{time.time_ns()}"
    )
    worker_log_directory.mkdir(parents=True, exist_ok=False)
    original_tempdir = tempfile.tempdir
    original_temp_env = {name: os.environ.get(name) for name in ("TMP", "TEMP", "TMPDIR")}
    for name in ("TMP", "TEMP", "TMPDIR"):
        os.environ[name] = str(run_temp_directory)
    tempfile.tempdir = str(run_temp_directory)
    temp_limit_mb = max(0, int(options.get("temp_disk_limit_mb", 2048)))
    temp_limit_bytes = temp_limit_mb * 1024 * 1024
    peak_sfd_temp_bytes = 0
    sfd_temp_bytes_before_cleanup = 0
    sfd_temp_cleanup_succeeded = False
    sfd_worker_temp_isolation_verified = None
    executor_shutdown_reports = []
    run_temp_relative = run_temp_directory.relative_to(output_root).as_posix()

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
        return ProcessPoolExecutor(
            max_workers=workers, mp_context=context,
            initializer=_worker_initializer,
            initargs=(str(run_temp_directory), str(worker_log_directory)),
            max_tasks_per_child=1,
        )

    executor_generation = 1
    executor = None
    running = {}
    try:
        executor = new_executor()
        while running or retry_queue or not source_exhausted:
            if resource_paused and not running:
                break
            while len(running) < workers:
                temp_bytes_now = _directory_file_bytes(run_temp_directory)
                peak_sfd_temp_bytes = max(peak_sfd_temp_bytes, temp_bytes_now)
                if temp_limit_bytes and temp_bytes_now > temp_limit_bytes:
                    resource_paused = True
                    source_exhausted = True
                    resource_pause_reason = f"SFD_TEMP_DISK_LIMIT_EXCEEDED_{temp_limit_mb}_MB"
                    break
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
                    try:
                        if options.get("corpus_root"):
                            input_snapshot = snapshot_paper(
                                paper, input_root,
                                paper_id=(options.get("upstream_paper_ids") or {}).get(str(paper.resolve())),
                                external_path_root=Path(options["corpus_root"]),
                            )
                        else:
                            input_snapshot = snapshot_paper(paper, input_root)
                        paper_relative = paper.relative_to(input_root).as_posix()
                    except Exception as exc:
                        ledger.finish(
                            paper_id,
                            JobState.FAILED_PERMANENT.value,
                            f"INPUT_SNAPSHOT_FAILED_ON_RETRY: {type(exc).__name__}: {exc}",
                        )
                        results["failed"] += 1
                        continue
                elif not source_exhausted:
                    try:
                        candidate = next(source)
                    except StopIteration:
                        source_exhausted = True
                        break
                    paper = candidate[0] if (
                        isinstance(candidate, tuple) and len(candidate) == 2
                        and isinstance(candidate[1], PaperSnapshot)
                    ) else candidate
                    total_seen += 1
                    try:
                        paper_relative = paper.relative_to(input_root).as_posix()
                        if (
                            isinstance(candidate, tuple) and len(candidate) == 2
                            and isinstance(candidate[1], PaperSnapshot)
                        ):
                            input_snapshot = candidate[1]
                        else:
                            if options.get("corpus_root"):
                                input_snapshot = snapshot_paper(
                                    paper, input_root,
                                    paper_id=(options.get("upstream_paper_ids") or {}).get(str(paper.resolve())),
                                    external_path_root=Path(options["corpus_root"]),
                                )
                            else:
                                input_snapshot = snapshot_paper(paper, input_root)
                        paper_id = input_snapshot.paper_id
                    except Exception as exc:
                        fallback_relative = (
                            paper.relative_to(input_root).as_posix()
                            if paper.is_relative_to(input_root)
                            else paper.resolve().as_posix()
                        )
                        fallback_id = storage_paper_id(fallback_relative)
                        if ledger.prepare(fallback_id):
                            ledger.start(
                                fallback_id,
                                worker_id=f"scheduler-preflight-{os.getpid()}",
                                input_fingerprint=None,
                            )
                            ledger.finish(
                                fallback_id,
                                JobState.FAILED_PERMANENT.value,
                                f"INPUT_SNAPSHOT_FAILED: {type(exc).__name__}: {exc}",
                            )
                            results["failed"] += 1
                        else:
                            results["active_jobs_skipped"] += 1
                        continue
                    if not ledger.prepare(paper_id):
                        results["active_jobs_skipped"] += 1
                        continue
                else:
                    break
                paper_relative = paper.relative_to(input_root).as_posix()
                occupied_slots = {slot for _, _, slot in running.values()}
                worker_slot = next(slot for slot in range(workers) if slot not in occupied_slots)
                worker_id = f"pool-{executor_generation}-slot-{worker_slot + 1}"
                ledger.start(paper_id, worker_id, input_snapshot.input_fingerprint)
                try:
                    future = executor.submit(
                        _process_paper_task, str(input_root), paper_relative,
                        str(output_root), options, input_snapshot,
                    )
                except BrokenProcessPool as exc:
                    error = f"WORKER_POOL_SUBMIT_FAILED: {type(exc).__name__}: {exc}"
                    attempt = ledger.attempt_count(paper_id)
                    if attempt < max_attempts:
                        ledger.finish(paper_id, JobState.RETRY_WAIT.value, error)
                        retry_queue.append((paper, paper_id))
                        results["retried"] += 1
                    else:
                        ledger.finish(paper_id, JobState.FAILED_PERMANENT.value, error)
                        results["failed"] += 1
                    if not running:
                        executor_shutdown_reports.append(
                            _shutdown_executor_bounded(executor, grace_seconds=1.0)
                        )
                        executor_generation += 1
                        executor = new_executor()
                    break
                except Exception as exc:
                    ledger.finish(
                        paper_id,
                        JobState.FAILED_PERMANENT.value,
                        f"WORKER_SUBMIT_FAILED: {type(exc).__name__}: {exc}",
                    )
                    results["failed"] += 1
                    continue
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
                    worker_temp = result.get("_worker_temp_directory")
                    if worker_temp:
                        matched = Path(worker_temp).resolve() == run_temp_directory.resolve()
                        sfd_worker_temp_isolation_verified = (
                            matched if sfd_worker_temp_isolation_verified is None
                            else sfd_worker_temp_isolation_verified and matched
                        )
                    completed_worker_cpu_seconds += max(0.0, float(result.get("_worker_cpu_seconds", 0.0)))
                    usage = result.get("resource_usage") or {}
                    evidence_bytes = max(0, int(usage.get("evidence_bytes", 0)))
                    context_bytes = max(0, int(usage.get("context_index_bytes", 0)))
                    budgeted_bytes = max(0, int(usage.get("budgeted_storage_bytes", evidence_bytes + context_bytes)))
                    paper_output_bytes = max(0, int(usage.get("paper_output_bytes", 0)))
                    total_returned_paper_output_bytes += paper_output_bytes
                    peak_single_paper_output_bytes = max(peak_single_paper_output_bytes, paper_output_bytes)
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
                            external_sources=snapshot_data.get("external_sources", []),
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
                        executor_shutdown_reports.append(
                            _shutdown_executor_bounded(executor, grace_seconds=1.0)
                        )
                        executor_generation += 1
                        executor = new_executor()
            for _, paper_id, _ in running.values():
                ledger.heartbeat(paper_id)
            peak_sfd_temp_bytes = max(
                peak_sfd_temp_bytes, _directory_file_bytes(run_temp_directory)
            )
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
        try:
            if executor is not None:
                executor_shutdown_reports.append(
                    _shutdown_executor_bounded(executor, grace_seconds=8.0)
                )
        finally:
            sfd_temp_bytes_before_cleanup = _directory_file_bytes(run_temp_directory)
            peak_sfd_temp_bytes = max(peak_sfd_temp_bytes, sfd_temp_bytes_before_cleanup)
            try:
                shutil.rmtree(run_temp_directory)
                sfd_temp_cleanup_succeeded = True
            except OSError:
                sfd_temp_cleanup_succeeded = not run_temp_directory.exists()
            try:
                temp_parent.rmdir()
            except OSError:
                pass
            for name, value in original_temp_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            tempfile.tempdir = original_tempdir
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
        "completed_papers": results["completed"],
        "review_required_papers": results["completed_with_review"],
        "permanently_failed_papers": results["failed"],
        "blocked_review_locked_papers": results["blocked_review_locked"],
        "retried_papers": results["retried"],
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
        "total_returned_paper_output_bytes": total_returned_paper_output_bytes,
        "peak_single_paper_output_bytes": peak_single_paper_output_bytes,
        "disk_usage_measurement_scope": (
            "Paper-output footprint is measured after each returned paper and includes its "
            "canonical JSON, series CSVs, evidence, context index and version directories. "
            "Evidence/context subtotals are reported separately. The peak SFD run-scoped "
            "TEMP/TMP/TMPDIR footprint is measured separately; this is not OS temporary-directory "
            "peak usage for unrelated applications and excludes transient renderer/native-library memory."
        ),
        "sfd_temp_directory_relative": run_temp_relative,
        "sfd_temp_peak_bytes": peak_sfd_temp_bytes,
        "sfd_temp_bytes_before_cleanup": sfd_temp_bytes_before_cleanup,
        "sfd_temp_limit_mb": temp_limit_mb,
        "sfd_temp_cleanup_succeeded": sfd_temp_cleanup_succeeded,
        "sfd_worker_temp_isolation_verified": sfd_worker_temp_isolation_verified,
        "sfd_temp_measurement_scope": (
            "Run-local scratch directory supplied as TMP, TEMP and TMPDIR to the scheduler and "
            "spawned workers. File-byte peak sampled during scheduling and before cleanup; "
            "other applications' global temporary folders are excluded."
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
        "worker_log_directory": worker_log_directory.as_posix(),
        "worker_shutdown": executor_shutdown_reports,
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
