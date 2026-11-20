from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .adapter import (
    discover_papers, ensure_unique_paper_ids, snapshot_paper, validate_disjoint_roots,
)
from .exporter import export_dataset
from .hashing import atomic_write_json, sha256_file
from .manifest import storage_paper_id
from .pipeline import bundle_is_intact, processing_stage_state
from .review import apply_review_patch
from .scheduler import JobLedger, run_corpus
from .storage import Catalog, connect_catalog


def _roots(parser):
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)


def _filters(args) -> dict:
    return {key: getattr(args, key, None) for key in (
        "paper_id", "entity_id", "entity", "condition", "analyte", "technique", "domain",
        "series_role", "qc_status", "review_state"
    )}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sfd", description="Scientific Figure Data")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="discover upstream paper outputs and snapshot them")
    _roots(scan)

    run = sub.add_parser("run", help="process papers incrementally")
    _roots(run)
    selection = run.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--resume", action="store_true")
    selection.add_argument("--failed-only", action="store_true")
    selection.add_argument("--paper-id")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--max-attempts", type=int, default=2)
    run.add_argument("--lease-seconds", type=int, default=180)
    run.add_argument("--memory-limit", type=int, default=2048, help="soft per-process memory budget in MiB")
    run.add_argument("--render-scale", type=float, default=1.5)
    run.add_argument("--temp-disk-limit", type=int, default=2048,
                     help="per-paper evidence + context-index disk budget in MiB; 0 disables the budget")
    run.add_argument("--min-free-disk-mb", type=int, default=256,
                     help="pause new paper dispatch when free disk space falls below this threshold; 0 disables the guard")
    run.add_argument("--min-free-memory-mb", type=int, default=512,
                     help="pause new paper dispatch when available system memory falls below this threshold; 0 disables the guard")
    run.add_argument("--context-memory-budget", type=int, default=500000)
    run.add_argument("--max-render-pixels", type=int, default=12000000)
    run.add_argument("--max-open-pdfs", type=int, default=1)
    run.add_argument("--batch-size", type=int, default=1000)
    run.add_argument("--qc-thresholds", type=Path,
                     help="Optional JSON/YAML QC thresholds; calibrated values must be evidence-backed")
    run.add_argument("--ocr", action="store_true")
    run.add_argument("--force-recompute-reviewed", action="store_true")
    run.add_argument("--dry-run", action="store_true")

    for command in ("status", "report"):
        item = sub.add_parser(command)
        item.add_argument("--output-root", type=Path, required=True)

    query = sub.add_parser("query", help="query extracted scientific series")
    query.add_argument("--output-root", type=Path, required=True)
    query.add_argument("--paper-id")
    query.add_argument("--entity-id")
    query.add_argument("--entity")
    query.add_argument("--analyte")
    query.add_argument("--condition")
    query.add_argument("--technique")
    query.add_argument("--domain")
    query.add_argument("--series-role")
    query.add_argument("--qc-status")
    query.add_argument("--review-state")
    query.add_argument("--limit", type=int, default=500)
    query.add_argument("--format", choices=("json",), default="json")

    export = sub.add_parser("export", help="export filtered ML-oriented point data")
    export.add_argument("--output-root", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--paper-id")
    export.add_argument("--entity-id")
    export.add_argument("--entity")
    export.add_argument("--analyte")
    export.add_argument("--condition")
    export.add_argument("--technique")
    export.add_argument("--domain")
    export.add_argument("--series-role")
    export.add_argument("--qc-status")
    export.add_argument("--review-state")
    export.add_argument("--format", choices=("csv", "json"), default="csv")
    export.add_argument("--reviewed-only", action="store_true")

    review = sub.add_parser("review", help="review queue and patch operations")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_list = review_sub.add_parser("list")
    review_list.add_argument("--output-root", type=Path, required=True)
    apply = review_sub.add_parser("apply")
    apply.add_argument("--output-root", type=Path, required=True)
    apply.add_argument("--patch", type=Path, required=True)
    apply.add_argument("--dry-run", action="store_true")

    index = sub.add_parser("index")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    rebuild = index_sub.add_parser("rebuild")
    rebuild.add_argument("--output-root", type=Path, required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--output-root", type=Path, required=True)
    validate.add_argument("--input-root", type=Path)

    probe = sub.add_parser("backend-probe", help="run PDF backend measurements on supplied PDFs")
    probe.add_argument("pdfs", nargs="*", type=Path)
    probe.add_argument("--out", type=Path, default=Path("backend_probe_report.json"))
    probe.add_argument("--render-scale", type=float, default=1.0)
    return parser


def _scan(args) -> int:
    if not args.input_root:
        raise ValueError("--input-root is required")
    input_root, output_root = validate_disjoint_roots(args.input_root, args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_root / "corpus_manifest.jsonl"
    temporary = jsonl_path.with_suffix(".jsonl.tmp")
    count = 0
    with temporary.open("w", encoding="utf-8") as stream:
        for paper_dir in ensure_unique_paper_ids(discover_papers(input_root), input_root):
            snapshot = snapshot_paper(paper_dir, input_root)
            stream.write(json.dumps(snapshot.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    temporary.replace(jsonl_path)
    atomic_write_json(output_root / "corpus_manifest.json", {
        "schema_version": "1.0", "input_root_name": input_root.name,
        "paper_count": count, "paper_manifest_stream": "corpus_manifest.jsonl",
    })
    print(json.dumps({"discovered": count, "manifest": str(output_root / "corpus_manifest.json"),
                      "paper_stream": str(jsonl_path)}, indent=2))
    return 0


def _run(args) -> int:
    if not args.input_root:
        raise ValueError("--input-root is required")
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    if output_root == input_root or input_root in output_root.parents:
        raise ValueError("Output root must be separate from, and outside, the upstream input root")

    options = {
        "memory_limit_mb": args.memory_limit,
        "render_scale": args.render_scale,
        "temp_disk_limit_mb": args.temp_disk_limit,
        "min_free_disk_mb": args.min_free_disk_mb,
        "min_free_memory_mb": args.min_free_memory_mb,
        "context_memory_budget": args.context_memory_budget,
        "max_render_pixels": args.max_render_pixels,
        "max_open_pdfs": args.max_open_pdfs,
        "batch_size": args.batch_size,
        "qc_thresholds": str(args.qc_thresholds) if args.qc_thresholds else None,
        "ocr": args.ocr,
        "force_recompute_reviewed": args.force_recompute_reviewed,
        "resume_cached_skipped": 0,
        "discovered_papers": sum(1 for _ in ensure_unique_paper_ids(discover_papers(input_root), input_root)),
        "eligible_papers": 0,
        "skipped_by_selection": 0,
    }
    selected_states = None
    prior_fingerprints: dict[str, str] = {}
    prior_job_states: dict[str, str] = {}
    if args.failed_only or args.resume:
        db = output_root / "catalog.sqlite"
        if db.is_file():
            con = connect_catalog(db)
            prior_fingerprints = {
                row["paper_id"]: row["input_fingerprint"]
                for row in con.execute("SELECT paper_id,input_fingerprint FROM papers")
            }
            prior_job_states = {
                row["paper_id"]: row["state"]
                for row in con.execute("SELECT paper_id,state FROM jobs")
            }
            if args.resume:
                states = ("PENDING", "RETRY_WAIT")
                placeholders = ",".join("?" for _ in states)
                selected_states = {row["paper_id"] for row in con.execute(
                    f"SELECT paper_id FROM jobs WHERE state IN ({placeholders})", states
                )}
                # Include all RUNNING jobs. JobLedger.prepare() skips active leases
                # and recovers expired/orphaned leases deterministically.
                selected_states.update(row["paper_id"] for row in con.execute(
                    "SELECT paper_id FROM jobs WHERE state='RUNNING'"
                ))
            else:
                states = ("RETRY_WAIT", "FAILED_PERMANENT")
                placeholders = ",".join("?" for _ in states)
                selected_states = {row["paper_id"] for row in con.execute(
                    f"SELECT paper_id FROM jobs WHERE state IN ({placeholders})", states
                )}
            con.close()
        elif args.failed_only:
            selected_states = set()
        else:
            # A first-time resume is equivalent to an initial run.
            selected_states = None

    def selected_papers():
        for paper in ensure_unique_paper_ids(discover_papers(input_root), input_root):
            relative = paper.relative_to(input_root).as_posix()
            storage_id = storage_paper_id("root-paper" if relative == "." else relative)
            if args.paper_id and relative != args.paper_id and storage_id != args.paper_id and paper.name != args.paper_id:
                options["skipped_by_selection"] += 1
                continue
            if args.failed_only:
                if selected_states is None or storage_id not in selected_states:
                    options["skipped_by_selection"] += 1
                    continue
                options["eligible_papers"] += 1
                yield paper
                continue
            options["eligible_papers"] += 1
            if args.resume and selected_states is not None and storage_id not in selected_states:
                previous_fingerprint = prior_fingerprints.get(storage_id)
                previous_job_state = prior_job_states.get(storage_id)
                if previous_fingerprint is None or previous_job_state is None:
                    yield paper
                    continue
                if previous_job_state not in {
                    "COMPLETED", "COMPLETED_WITH_REVIEW", "NEEDS_REVIEW", "BLOCKED"
                }:
                    yield paper
                    continue
                current_snapshot = snapshot_paper(paper, input_root)
                if current_snapshot.input_fingerprint != previous_fingerprint:
                    yield (paper, current_snapshot)
                    continue
                paper_root = output_root / "papers" / storage_id
                bundle_path = paper_root / "paper_bundle.json"
                stage_state = processing_stage_state(current_snapshot, paper, output_root, options)
                try:
                    bundle = json.loads(bundle_path.read_text(encoding="utf-8")) if bundle_path.is_file() else {}
                    same_stage = bundle.get("stage_fingerprint") == stage_state["stage_fingerprint"]
                except (OSError, ValueError, TypeError):
                    same_stage = False
                if not same_stage or not bundle_is_intact(paper_root):
                    yield (paper, current_snapshot)
                    continue
                if args.force_recompute_reviewed:
                    digitization_path = paper_root / "digitization.json"
                    try:
                        digitization = json.loads(digitization_path.read_text(encoding="utf-8"))
                        reviewed = any(
                            item.get("review_state") == "REVIEWED_ACCEPTED"
                            for item in digitization.get("series", [])
                        )
                    except (OSError, ValueError, TypeError):
                        reviewed = False
                    if reviewed:
                        yield (paper, current_snapshot)
                        continue
                options["resume_cached_skipped"] += 1
                continue
            yield paper

    result = run_corpus(input_root, output_root, selected_papers(), args.workers,
                        args.max_attempts, args.lease_seconds, args.dry_run, options)
    print(json.dumps(result, indent=2))
    return 0 if result.get("failed", 0) == 0 else 1


def _status(args) -> int:
    db = args.output_root / "catalog.sqlite"
    if not db.is_file():
        print(json.dumps({"status": "NO_CATALOG"}))
        return 0
    ledger = JobLedger(db)
    counts = ledger.status()
    ledger.close()
    if args.command == "report":
        report_path = args.output_root / "run_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        report["current_job_state_counts"] = counts
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"jobs": counts}, indent=2))
    return 0


def _query(args) -> int:
    catalog = Catalog(args.output_root / "catalog.sqlite")
    try:
        rows = catalog.query_series(_filters(args), args.limit)
    finally:
        catalog.close()
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _export(args) -> int:
    catalog = Catalog(args.output_root / "catalog.sqlite")
    try:
        manifest = export_dataset(catalog, args.output_root, args.out, _filters(args),
                                 include_review_required=not args.reviewed_only, fmt=args.format)
    finally:
        catalog.close()
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def _review(args) -> int:
    if args.review_command == "apply":
        result = apply_review_patch(args.output_root, args.patch, args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] in {"REVIEWED_ACCEPTED", "DRY_RUN_OK", "ALREADY_APPLIED"} else 2
    catalog = Catalog(args.output_root / "catalog.sqlite")
    try:
        rows = catalog.list_reviews()
    finally:
        catalog.close()
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _rebuild(args) -> int:
    catalog = Catalog(args.output_root / "catalog.sqlite")
    try:
        print(json.dumps(catalog.rebuild_from_artifacts(args.output_root), indent=2))
    finally:
        catalog.close()
    return 0


def _validate(args) -> int:
    root = args.output_root
    errors = []
    checked = 0
    for paper_root in sorted((root / "papers").glob("*")) if (root / "papers").exists() else []:
        for name in ("paper_manifest.json", "figure_inventory.json", "panel_layout.json",
                     "digitization.json", "paper_bundle.json"):
            path = paper_root / name
            if not path.is_file():
                errors.append(f"{path}: missing")
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
                checked += 1
            except Exception as exc:
                errors.append(f"{path}: {type(exc).__name__}: {exc}")
        bundle_path = paper_root / "paper_bundle.json"
        if bundle_path.is_file():
            try:
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
                for relative, expected_hash in bundle.get("content_hashes", {}).items():
                    artifact = (paper_root / relative).resolve()
                    try:
                        artifact.relative_to(paper_root.resolve())
                    except ValueError:
                        errors.append(f"{bundle_path}: unsafe artifact path {relative}")
                        continue
                    if not artifact.is_file():
                        errors.append(f"{artifact}: bundle artifact missing")
                    elif sha256_file(artifact) != expected_hash:
                        errors.append(f"{artifact}: bundle SHA256 mismatch")
            except Exception as exc:
                errors.append(f"{bundle_path}: bundle hash validation failed: {type(exc).__name__}: {exc}")
        if args.input_root:
            manifest_path = paper_root / "paper_manifest.json"
            if manifest_path.is_file():
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for artifact in data.get("artifacts", []):
                        expected = artifact.get("sha256")
                        if not expected or str(expected).startswith("UNREADABLE:"):
                            continue
                        source = (args.input_root.resolve() / artifact["path"]).resolve()
                        try:
                            source.relative_to(args.input_root.resolve())
                        except ValueError:
                            errors.append(f"{source}: unsafe upstream path")
                            continue
                        if not source.is_file():
                            errors.append(f"{source}: upstream source missing")
                        elif sha256_file(source) != expected:
                            errors.append(f"{source}: upstream SHA256 changed")
                except Exception as exc:
                    errors.append(f"{manifest_path}: {type(exc).__name__}: {exc}")
    if args.input_root:
        stream_path = root / "corpus_manifest.jsonl"
        if stream_path.is_file():
            with stream_path.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    try:
                        snapshot = json.loads(line)
                    except json.JSONDecodeError:
                        errors.append(f"{stream_path}:{line_number}: invalid JSONL record")
                        continue
                    for artifact in snapshot.get("artifacts", []):
                        expected = artifact.get("sha256")
                        if not expected or str(expected).startswith("UNREADABLE:"):
                            continue
                        source = (args.input_root.resolve() / artifact["path"]).resolve()
                        try:
                            source.relative_to(args.input_root.resolve())
                        except ValueError:
                            errors.append(f"{stream_path}:{line_number}: unsafe upstream path")
                            continue
                        if not source.is_file():
                            errors.append(f"{source}: upstream source missing")
                        elif sha256_file(source) != expected:
                            errors.append(f"{source}: upstream SHA256 changed since scan")
    print(json.dumps({"checked_json_artifacts": checked, "errors": errors,
                      "status": "OK" if not errors else "INVALID"}, indent=2))
    return 0 if not errors else 1


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            return _scan(args)
        if args.command == "run":
            return _run(args)
        if args.command in {"status", "report"}:
            return _status(args)
        if args.command == "query":
            return _query(args)
        if args.command == "export":
            return _export(args)
        if args.command == "review":
            return _review(args)
        if args.command == "index":
            return _rebuild(args)
        if args.command == "validate":
            return _validate(args)
        if args.command == "backend-probe":
            from .backend_probe import main as probe_main
            return probe_main([*(str(p) for p in args.pdfs), "--out", str(args.out),
                               "--render-scale", str(args.render_scale)])
    except Exception as exc:
        print(f"sfd: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 2
