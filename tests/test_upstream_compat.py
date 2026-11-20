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
    assert figures[0]["image_asset_status"] == "HASH_MISMATCH"


def test_evidence_index_without_unique_figure_asset_routes_to_review(tmp_path: Path):
    input_root, package, _, _ = _make_chem_literature_package(tmp_path)
    evidence_path = package / "evidence_index.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["media_assets"] = []
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    snapshot = snapshot_paper(package, input_root)

    figures, _ = _inventory(package, snapshot)

    assert figures[0]["image_asset_status"] == "NO_EXACT_ASSET"
    assert "image_path" not in figures[0]


def test_unverified_upstream_asset_blocks_source_pdf_bbox_fallback():
    from scientific_figure_data.pipeline import _may_use_source_pdf_bbox_fallback

    assert not _may_use_source_pdf_bbox_fallback(
        {"image_asset_status": "HASH_MISMATCH"}, {}
    )
    assert not _may_use_source_pdf_bbox_fallback(
        {"image_asset_status": "VERIFIED"}, {}
    )
    assert _may_use_source_pdf_bbox_fallback({}, {})
    assert _may_use_source_pdf_bbox_fallback(
        {"image_asset_status": "HASH_MISMATCH"}, {"image_path": "manual.png"}
    )


def test_validate_rechecks_external_main_pdf_hash_through_upstream_reference(tmp_path: Path):
    from scientific_figure_data.cli import _validate_external_sources

    input_root, package, source_pdf, _ = _make_chem_literature_package(tmp_path)
    snapshot = snapshot_paper(package, input_root)
    snapshot_data = snapshot.to_dict()

    assert _validate_external_sources(input_root, snapshot_data, "paper_manifest") == []

    source_pdf.write_bytes(b"%PDF-1.7\nmutated after scan\n")
    errors = _validate_external_sources(input_root, snapshot_data, "paper_manifest")

    assert "external MAIN PDF SHA256 changed" in "\n".join(errors)
    assert "does not match evidence_index SHA256" in "\n".join(errors)


def test_validate_flags_unaccepted_external_main_pdf_integrity_state(tmp_path: Path):
    from scientific_figure_data.cli import _validate_external_sources

    input_root, package, _, _ = _make_chem_literature_package(tmp_path)
    snapshot = snapshot_paper(package, input_root)
    snapshot_data = snapshot.to_dict()
    snapshot_data["external_sources"][0]["status"] = "HASH_MISMATCH"

    errors = _validate_external_sources(input_root, snapshot_data, "paper_manifest")

    assert any("was not accepted (HASH_MISMATCH)" in error for error in errors)


def test_downstream_processing_preserves_upstream_package_and_external_main_pdf(
    tmp_path: Path,
):
    from PIL import Image
    from scientific_figure_data.pipeline import process_paper

    input_root, package, source_pdf, image_relative = _make_chem_literature_package(tmp_path)
    image_path = package / image_relative
    with Image.new("RGB", (24, 16), "white") as image:
        image.save(image_path, format="PNG")
    evidence_index = package / "evidence_index.json"
    evidence_payload = json.loads(evidence_index.read_text(encoding="utf-8"))
    for asset in evidence_payload["media_assets"]:
        if asset.get("figure_id") == "MAIN_FIG_P1_01":
            asset["sha256"] = _sha256(image_path.read_bytes())
    evidence_index.write_text(json.dumps(evidence_payload), encoding="utf-8")

    def upstream_snapshot():
        package_paths = {
            item.relative_to(input_root).as_posix()
            for item in input_root.rglob("*")
        }
        package_hashes = {
            item.relative_to(input_root).as_posix(): _sha256(item.read_bytes())
            for item in input_root.rglob("*") if item.is_file()
        }
        return (
            package_paths,
            package_hashes,
            source_pdf.stat().st_size,
            _sha256(source_pdf.read_bytes()),
        )

    before = upstream_snapshot()
    snapshot = snapshot_paper(package, input_root)
    result = process_paper(
        input_root,
        Path("10.1000_demo/01_preprocessing"),
        tmp_path / "downstream",
        options={"memory_limit_mb": 0, "temp_disk_limit_mb": 0},
        input_snapshot=snapshot,
    )
    after = upstream_snapshot()

    assert result["snapshot"]["external_sources"][0]["status"] == "HASH_VERIFIED"
    assert result["snapshot"]["external_sources"][0]["sha256"] == before[3]
    assert result["job_state"] in {"NEEDS_REVIEW", "COMPLETED", "COMPLETED_WITH_REVIEW"}
    assert result["figures"][0]["source_bbox"] == [20.0, 200.0, 570.0, 240.0]
    assert result["figures"][0]["source_bbox_role"] == "UPSTREAM_EVIDENCE_INDEX_BBOX_UNRESOLVED"
    assert result["panels"][0]["bbox"] is None
    assert result["panels"][0]["bbox_provenance"] == "NOT_PROVIDED"
    assert result["panels"][0]["segmentation_provenance"] == "SINGLE_PANEL_FALLBACK"
    assert result["panels"][0]["segmentation_status"] == "WHOLE_FIGURE_NOT_SEGMENTED"
    copied_image = (
        tmp_path / "downstream" / "papers" / result["snapshot"]["paper_id"]
        / "evidence" / "MAIN_FIG_P1_01_1.png"
    )
    assert copied_image.is_file()
    assert _sha256(copied_image.read_bytes()) == _sha256(image_path.read_bytes())
    assert result["figures"][0]["source_image_asset_path"] == image_relative
    assert after == before


def test_evidence_index_caption_bbox_is_not_relabelled_as_panel_boundary(tmp_path: Path):
    from scientific_figure_data.pipeline import _figure_panels

    figure = {
        "figure_id": "MAIN_FIG_P1_01",
        "bbox": [20.0, 200.0, 570.0, 240.0],
        "image_asset_status": "VERIFIED",
    }

    panel = _figure_panels(figure)[0]

    assert panel["bbox"] is None
    assert panel["segmentation_provenance"] == "SINGLE_PANEL_FALLBACK"
    assert panel["segmentation_status"] == "WHOLE_FIGURE_NOT_SEGMENTED"


def test_explicit_panel_geometry_retains_source_normalized_and_provenance_fields():
    from scientific_figure_data.pipeline import _figure_panels

    figure = {
        "panels": [{
            "panel_id": "a",
            "bbox": [10.0, 20.0, 410.0, 220.0],
            "normalized_bbox": [0.1, 0.2, 0.9, 0.8],
            "bbox_coordinate_space": "PDF_POINTS",
            "bbox_provenance": "UPSTREAM_ANNOTATION",
            "segmentation_confidence": 0.92,
            "segmentation_provenance": "HUMAN_ANNOTATION",
        }],
    }

    panel = _figure_panels(figure)[0]

    assert panel["bbox"] == [10.0, 20.0, 410.0, 220.0]
    assert panel["normalized_bbox"] == [0.1, 0.2, 0.9, 0.8]
    assert panel["bbox_coordinate_space"] == "PDF_POINTS"
    assert panel["bbox_provenance"] == "UPSTREAM_ANNOTATION"
    assert panel["segmentation_confidence"] == 0.92
    assert panel["segmentation_provenance"] == "HUMAN_ANNOTATION"
