from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scientific_figure_data.adapter import discover_papers, locate_pdf, snapshot_paper
from scientific_figure_data.pipeline import _inventory


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_chem_literature_package(tmp_path: Path):
    input_root = tmp_path / "runs" / "preprocessed"
    package = input_root / "10.1000_demo" / "01_preprocessing"
    (package / "extracted_figures" / "MAIN").mkdir(parents=True)
    (package / "extracted_tables").mkdir()
    source_pdf = tmp_path / "papers_pdf" / "10.1000_demo.pdf"
    source_pdf.parent.mkdir()
    pdf_bytes = b"%PDF-1.7\n% fixture source PDF bytes\n"
    source_pdf.write_bytes(pdf_bytes)

    image_relative = "extracted_figures/MAIN/MAIN_MAIN_FIG_P1_01.png"
    image_bytes = b"fixture-main-figure-crop"
    (package / image_relative).write_bytes(image_bytes)
    (package / "main_analysis.md").write_text(
        "# Main Analysis\nSample A was tested vs Ag/AgCl.\n", encoding="utf-8"
    )
    (package / "si_analysis.md").write_text(
        "# Supporting Information Analysis\nMean ± SD, n=3.\n", encoding="utf-8"
    )
    (package / "extracted_tables" / "table_1.csv").write_text(
        "sample,capacity\nA,100\n", encoding="utf-8"
    )
    payload = {
        "package_version": "1.1.0",
        "paper_id": "10.1000_demo",
        "metadata": {"doi": "10.1000/demo", "title": "Fixture", "has_si": True},
        "inventory": {
            "main_pdf": {
                "path": str(source_pdf.resolve()),
                "sha256": _sha256(pdf_bytes),
                "size_bytes": len(pdf_bytes),
                "page_count": 1,
            },
            "si_pdf": None,
            "supplementary_files": [],
        },
        "pages": [],
        "tables": [],
        "figures": [{
            "figure_id": "MAIN_FIG_P1_01", "doc_type": "MAIN", "page_number": 1,
            "bbox": [20.0, 200.0, 570.0, 240.0], "caption": "Figure 1. Test curve",
        }],
        "si_references": [],
        "media_assets": [{
            "asset_id": "ASSET_00001", "doc_type": "MAIN", "asset_type": "figure",
            "source_file": source_pdf.name, "source_sha256": _sha256(pdf_bytes),
            "relative_path": image_relative, "sha256": _sha256(image_bytes),
            "extraction_method": "pymupdf_vector_image_layout_fallback", "page_number": 1,
            "bbox": [20.0, 20.0, 570.0, 180.0], "figure_id": "MAIN_FIG_P1_01",
            "table_id": None, "caption": "Figure 1. Test curve", "width": 1528,
            "height": 444, "mime_type": "image/png", "is_tiny_icon": False,
        }],
        "processing_summary": {
            "total_main_pages": 1, "total_si_pages": 0, "total_tables_detected": 0,
            "total_figures_detected": 1, "total_si_references": 0, "scanned_pages_detected": 0,
            "images_extracted": 1, "grobid_status": "DISABLED", "warnings": [],
            "status": "COMPLETE",
        },
    }
    (package / "evidence_index.json").write_text(json.dumps(payload), encoding="utf-8")
    return input_root, package, source_pdf, image_relative


def test_current_chem_literature_package_is_discovered_as_one_paper(tmp_path: Path):
    input_root, package, source_pdf, _ = _make_chem_literature_package(tmp_path)

    discovered = list(discover_papers(input_root))
    assert discovered == [package]

    snapshot = snapshot_paper(package, input_root)
    assert snapshot.detected_upstream_version == "1.1.0"
    assert "main_pdf" not in snapshot.missing_roles
    assert "figure_inventory" not in snapshot.missing_roles
    assert snapshot.resolved_main_pdf == source_pdf.resolve()
    assert snapshot.external_sources[0]["status"] == "HASH_VERIFIED"
    assert snapshot.external_sources[0]["sha256"] == _sha256(source_pdf.read_bytes())
    assert {item.role for item in snapshot.artifacts} >= {
        "evidence_index", "main_text", "si_text", "table_data", "figure_image",
    }
    assert locate_pdf(package, input_root, snapshot) == source_pdf.resolve()

    serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False)
    assert str(source_pdf.resolve()) not in serialized
    assert "resolved_main_pdf" not in snapshot.to_dict()


def test_referenced_main_pdf_hash_mismatch_blocks_source_pdf_and_invalidates_fingerprint(
    tmp_path: Path,
):
    input_root, package, source_pdf, _ = _make_chem_literature_package(tmp_path)
    original = snapshot_paper(package, input_root)

    source_pdf.write_bytes(b"%PDF-1.7\nchanged source bytes\n")
    changed = snapshot_paper(package, input_root)

    assert changed.input_fingerprint != original.input_fingerprint
    assert changed.resolved_main_pdf is None
    assert changed.external_sources[0]["status"] == "HASH_MISMATCH"
    assert "main_pdf" in changed.missing_roles
    assert locate_pdf(package, input_root, changed) is None


def test_inventory_uses_hash_verified_upstream_figure_crop(tmp_path: Path):
    input_root, package, _, image_relative = _make_chem_literature_package(tmp_path)
    snapshot = snapshot_paper(package, input_root)

    figures, evidence_path = _inventory(package, snapshot)

    assert evidence_path == package / "evidence_index.json"
    assert len(figures) == 1
    assert figures[0]["image_path"] == image_relative
    assert figures[0]["image_asset_sha256"] == _sha256((package / image_relative).read_bytes())


def test_inventory_does_not_attach_tampered_upstream_figure_crop(tmp_path: Path):
    input_root, package, _, image_relative = _make_chem_literature_package(tmp_path)
    (package / image_relative).write_bytes(b"tampered figure crop")
    snapshot = snapshot_paper(package, input_root)

    figures, _ = _inventory(package, snapshot)

    assert "image_path" not in figures[0]
