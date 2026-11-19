from __future__ import annotations

import json
import os
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
from multiprocessing import get_context
from pathlib import Path

from .models import JobState, utc_now
from .storage import connect_catalog, Catalog


def _worker_initializer():
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    try:
        import cv2
        cv2.setNumThreads(1)
    except ImportError:
        pass


def _process_paper_task(input_root: str, paper_relative: str, output_root: str) -> dict:
    from .pipeline import process_paper
    return process_paper(Path(input_root), Path(paper_relative), Path(output_root))


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

    def prepare(self, paper_id: str):
        with self.con:
            row = self.con.execute("SELECT state,lease_expires_at FROM jobs WHERE paper_id=?",
                                   (paper_id,)).fetchone()
            if row and row["state"] == JobState.RUNNING.value:
                if row["lease_expires_at"] is None or row["lease_expires_at"] < time.time():
                    self.event(paper_id, "INTERRUPTED_RECOVERY", {"previous_state": "RUNNING"})
                    self.con.execute("UPDATE jobs SET state=?,lease_expires_at=NULL,updated_at=? WHERE paper_id=?",
                                     (JobState.RETRY_WAIT.value, utc_now(), paper_id))
            self.con.execute(
                """INSERT INTO jobs(paper_id,state,updated_at) VALUES(?,?,?)
                   ON CONFLICT(paper_id) DO NOTHING""",
                (paper_id, JobState.PENDING.value, utc_now()),
            )

    def start(self, paper_id: str):
        now = time.time()
        with self.con:
            self.con.execute(
                """UPDATE jobs SET state=?,attempt_count=attempt_count+1,heartbeat_at=?,
                   lease_expires_at=?,current_stage=?,last_error=NULL,updated_at=? WHERE paper_id=?""",
                (JobState.RUNNING.value, now, now + self.lease_seconds, "PAPER_PROCESSING", utc_now(), paper_id),
            )
            self.event(paper_id, "JOB_STARTED", {})

    def heartbeat(self, paper_id: str):
        now = time.time()
        with self.con:
            self.con.execute("UPDATE jobs SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE paper_id=?",
                             (now, now + self.lease_seconds, utc_now(), paper_id))

    def finish(self, paper_id: str, state: str, error: str | None = None):
        with self.con:
            self.con.execute(
                "UPDATE jobs SET state=?,lease_expires_at=NULL,updated_at=?,last_error=? WHERE paper_id=?",
                (state, utc_now(), error, paper_id),
            )
            self.event(paper_id, state, {"error": error} if error else {})

    def status(self):
        return [dict(row) for row in self.con.execute(
            "SELECT state,COUNT(*) AS count FROM jobs GROUP BY state ORDER BY state"
        )]


def run_corpus(input_root: Path, output_root: Path, paper_paths: list[Path],
               workers: int = 1, max_attempts: int = 2, lease_seconds: int = 180,
               dry_run: bool = False) -> dict:
    if workers < 1 or workers > 4:
        raise ValueError("workers must be between 1 and 4; default is 1 for low-memory systems")
    db_path = output_root / "catalog.sqlite"
    output_root.mkdir(parents=True, exist_ok=True)
    ledger = JobLedger(db_path, lease_seconds)
    catalog = Catalog(db_path)
    for paper in paper_paths:
        ledger.prepare(paper.relative_to(input_root).as_posix())
    if dry_run:
        ledger.close()
        catalog.close()
        return {"planned_papers": len(paper_paths), "dry_run": True}

    pending = [p for p in paper_paths]
    results = {"completed": 0, "completed_with_review": 0, "failed": 0, "retried": 0}
    context = get_context("spawn")
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                   initializer=_worker_initializer, max_tasks_per_child=5)
    running = {}
    cursor = 0
    try:
        while cursor < len(pending) or running:
            while cursor < len(pending) and len(running) < workers:
                paper = pending[cursor]
                cursor += 1
                paper_id = paper.relative_to(input_root).as_posix()
                ledger.start(paper_id)
                future = executor.submit(_process_paper_task, str(input_root), paper_id, str(output_root))
                running[future] = (paper_id, paper)
            if not running:
                continue
            done, _ = wait(running, timeout=5, return_when=FIRST_COMPLETED)
            for future in list(running):
                paper_id, paper = running[future]
                if future not in done:
                    ledger.heartbeat(paper_id)
                    continue
                running.pop(future)
                try:
                    result = future.result()
                    snapshot_dict = result["snapshot"]
                    from .models import PaperSnapshot, InputArtifact, SeriesRecord, SeriesPoint
                    snapshot = PaperSnapshot(
                        paper_id=snapshot_dict["paper_id"], source_dir=snapshot_dict["source_dir"],
                        detected_upstream_version=snapshot_dict.get("detected_upstream_version"),
                        adapter_version=snapshot_dict["adapter_version"], created_at=snapshot_dict["created_at"],
                        artifacts=[InputArtifact(**a) for a in snapshot_dict.get("artifacts", [])],
                        missing_roles=snapshot_dict.get("missing_roles", []),
                        warnings=snapshot_dict.get("warnings", []),
                        input_fingerprint=snapshot_dict["input_fingerprint"],
                    )
                    series = []
                    for item in result.get("series", []):
                        series.append(SeriesRecord(**{
                            **item, "points": [SeriesPoint(**p) for p in item.get("points", [])]
                        }))
                    catalog.index_paper(snapshot, result.get("figures", []), result.get("panels", []),
                                        series, result["status"], result.get("artifact_paths"))
                    ledger.finish(paper_id, result["job_state"])
                    results["completed_with_review" if result["job_state"] in {
                        JobState.COMPLETED_WITH_REVIEW.value, JobState.NEEDS_REVIEW.value
                    } else "completed"] += 1
                except BrokenProcessPool as exc:
                    error = f"WORKER_POOL_BROKEN: {exc}"
                    ledger.finish(paper_id, JobState.RETRY_WAIT.value, error)
                    results["retried"] += 1
                    executor.shutdown(wait=False, cancel_futures=True)
                    executor = ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                                   initializer=_worker_initializer, max_tasks_per_child=5)
                    # Requeue remaining paper including failed task, bounded by attempts.
                    pending[cursor:cursor] = [paper]
                    cursor = max(0, cursor - 0)
                except Exception as exc:
                    ledger.finish(paper_id, JobState.FAILED_PERMANENT.value,
                                  f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}")
                    results["failed"] += 1
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        ledger.close()
        catalog.close()
    return {**results, "papers_submitted": len(paper_paths)}
