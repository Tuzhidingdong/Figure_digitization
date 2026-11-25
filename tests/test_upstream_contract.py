from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scientific_figure_data.adapter import snapshot_paper
from scientific_figure_data.manifest import storage_paper_id
from scientific_figure_data.upstream_contract import (
    SUPPORTED_PACKAGE_VERSION,
    load_corpus_packages,
    validate_evidence_index,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _package(root: Path, package_id: str = "DOI_10.1000_example") -> Path:
    package = root / package_id / "01_preprocessing"
    (package / "extracted_figures" / "MAIN").mkdir(parents=True)
    image = b"verified-figure-crop"
    image_path = package / "extracted_figures" / "MAIN" / "figure.png"
    image_path.write_bytes(image)
    payload = {
        "package_version": SUPPORTED_PACKAGE_VERSION,
        "paper_id": "10.1000/example_authoritative_id",
        "metadata": {"doi": "10.1000/example", "title": "Example", "has_si": True},
        "inventory": {
            "main_pdf": {
                "path": "papers_pdf/example.pdf", "sha256": "a" * 64,
                "size_bytes": 123, "page_count": 2,
            },
            "si_pdf": None, "supplementary_files": [],
        },
        "pages": [], "tables": [],
        "figures": [{
            "figure_id": "MAIN_FIG_P1_01", "doc_type": "MAIN", "page_number": 1,
            "bbox": [10, 20, 300, 200], "caption": "Figure 1",
        }],
        "si_references": [],
        "media_assets": [{
            "asset_id": "ASSET_1", "doc_type": "MAIN", "asset_type": "figure",
            "source_file": "example.pdf", "source_sha256": "b" * 64,
            "relative_path": "extracted_figures/MAIN/figure.png", "sha256": _sha(image),
            "extraction_method": "fixture", "page_number": 1,
            "bbox": [10, 20, 300, 200], "figure_id": "MAIN_FIG_P1_01",
            "table_id": None, "caption": "Figure 1", "width": 10, "height": 10,
            "mime_type": "image/png", "is_tiny_icon": False,
        }],
        "processing_summary": {
            "total_main_pages": 2, "total_si_pages": 1, "total_tables_detected": 0,
            "total_figures_detected": 1, "total_si_references": 0,
            "scanned_pages_detected": 0, "images_extracted": 1,
            "grobid_status": "DISABLED", "warnings": [], "status": "COMPLETE",
        },
    }
    (package / "evidence_index.json").write_text(json.dumps(payload), encoding="utf-8")
    return package


def test_pinned_package_version_and_verified_media_asset(tmp_path: Path):
    package = _package(tmp_path)
    payload, errors, warnings = validate_evidence_index(package)
    assert payload["paper_id"] == "10.1000/example_authoritative_id"
    assert errors == []
    assert warnings == []


def test_unknown_package_version_is_rejected(tmp_path: Path):
    package = _package(tmp_path)
    path = package / "evidence_index.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["package_version"] = "1.2.0"
    path.write_text(json.dumps(payload), encoding="utf-8")
    _, errors, _ = validate_evidence_index(package)
    assert any("unsupported package_version" in item for item in errors)


def test_media_hash_mismatch_is_rejected(tmp_path: Path):
    package = _package(tmp_path)
    (package / "extracted_figures" / "MAIN" / "figure.png").write_bytes(b"tampered")
    _, errors, _ = validate_evidence_index(package)
    assert any("SHA256 mismatch" in item for item in errors)


def test_media_path_traversal_is_rejected(tmp_path: Path):
    package = _package(tmp_path)
    path = package / "evidence_index.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["media_assets"][0]["relative_path"] = "../../outside.png"
    path.write_text(json.dumps(payload), encoding="utf-8")
    _, errors, _ = validate_evidence_index(package)
    assert any("escapes package" in item for item in errors)


def test_csv_paths_resolve_from_workflow_cwd_and_paper_id_is_authoritative(tmp_path: Path):
    cwd = tmp_path / "upstream_workdir"
    input_root = cwd / "runs" / "preprocessed"
    package = _package(input_root)
    pdf_path = cwd / "papers_pdf" / "example.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_bytes = b"%PDF-1.7\\ncorpus fixture\\n"
    pdf_path.write_bytes(pdf_bytes)
    evidence_path = package / "evidence_index.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["inventory"]["main_pdf"].update({
        "path": "papers_pdf/example.pdf", "sha256": _sha(pdf_bytes),
        "size_bytes": len(pdf_bytes),
    })
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    csv_path = cwd / "research_corpus_paired.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "doi", "local_pdf_path", "local_si_info", "preprocessing_path",
            "preprocessing_status",
        ])
        writer.writeheader()
        writer.writerow({
            "doi": "10.1000/example", "local_pdf_path": "papers_pdf/example.pdf",
            "local_si_info": "papers_si/example.zip",
            "preprocessing_path": "runs/preprocessed/DOI_10.1000_example/01_preprocessing",
            "preprocessing_status": "COMPLETE",
        })

    packages, skipped = load_corpus_packages(csv_path, cwd, input_root)
    assert len(packages) == 1
    assert packages[0].paper_id == "10.1000/example_authoritative_id"
    assert packages[0].paper_dir == package
    assert skipped == []


def test_failed_csv_rows_are_reported_not_treated_as_packages(tmp_path: Path):
    cwd = tmp_path / "upstream_workdir"
    input_root = cwd / "runs" / "preprocessed"
    input_root.mkdir(parents=True)
    csv_path = cwd / "research_corpus_paired.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "doi", "local_pdf_path", "local_si_info", "preprocessing_path",
            "preprocessing_status",
        ])
        writer.writeheader()
        writer.writerow({
            "doi": "10.1000/failed", "local_pdf_path": "a.pdf",
            "local_si_info": "", "preprocessing_path": "",
            "preprocessing_status": "FAILED",
        })
    packages, skipped = load_corpus_packages(csv_path, cwd, input_root)
    assert packages == []
    assert skipped == [{
        "row": 2, "doi": "10.1000/failed", "reason": "UPSTREAM_PREPROCESSING_FAILED",
    }]



def test_snapshot_uses_upstream_paper_id_and_resolves_main_pdf_from_workflow_cwd(
    tmp_path: Path,
):
    cwd = tmp_path / "upstream_workdir"
    input_root = cwd / "runs" / "preprocessed"
    package = _package(input_root)
    pdf_path = cwd / "papers_pdf" / "example.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_bytes = b"%PDF-1.7\\ncontract fixture\\n"
    pdf_path.write_bytes(pdf_bytes)

    evidence_path = package / "evidence_index.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["inventory"]["main_pdf"].update({
        "path": "papers_pdf/example.pdf",
        "sha256": _sha(pdf_bytes),
        "size_bytes": len(pdf_bytes),
    })
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    snapshot = snapshot_paper(
        package, input_root, paper_id=payload["paper_id"], external_path_root=cwd,
    )

    assert snapshot.paper_id == storage_paper_id(payload["paper_id"])
    assert snapshot.external_sources[0]["status"] == "HASH_VERIFIED"
    assert snapshot.external_sources[0]["sha256"] == _sha(pdf_bytes)
    assert str(pdf_path.resolve()) not in json.dumps(snapshot.to_dict())


def test_run_cli_accepts_authoritative_csv_handoff():
    from scientific_figure_data.cli import build_parser

    args = build_parser().parse_args([
        "run", "--all",
        "--input-root", "E:/upstream/runs/preprocessed",
        "--corpus-csv", "E:/upstream/research_corpus_paired.csv",
        "--corpus-root", "E:/upstream",
        "--output-root", "E:/sfd-output",
    ])

    assert args.corpus_csv.name == "research_corpus_paired.csv"
    assert args.corpus_root == Path("E:/upstream")
