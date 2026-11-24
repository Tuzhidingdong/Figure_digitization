"""Replay the archived real-image extraction exactly as the regression tests do.

This script only calls the existing production pipeline with the cached OCR rows
that are already stored in ``tests/fixtures/real_figures``.  It does not touch
source code, does not run an OCR model, and does not read the original papers.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from PIL import Image  # noqa: E402

from scientific_figure_data import ocr  # noqa: E402
from scientific_figure_data.adapter import snapshot_paper  # noqa: E402
from scientific_figure_data.panel_segmentation import detect_panel_regions  # noqa: E402
from scientific_figure_data.pipeline import process_paper  # noqa: E402

FIXTURES = PROJECT / "tests" / "fixtures" / "real_figures"
RUN_DIR = Path(__file__).resolve().parent
EXTRACT = RUN_DIR / "extraction"


def make_cached_ocr(cached_rows: list[dict], panel_map: dict, full_name: str):
    def cached_panel_ocr(panel_image_path: Path) -> list[dict]:
        if Path(panel_image_path).name == full_name:
            return [dict(row) for row in cached_rows]
        stem = Path(panel_image_path).stem
        matched_panel = next(
            (
                panel for panel_id, panel in panel_map.items()
                if stem.endswith("_" + panel_id)
            ),
            None,
        )
        if matched_panel is None:
            return []
        x0, y0, x1, y1 = matched_panel["bbox"]
        local_rows = []
        for row in cached_rows:
            polygon = row.get("polygon")
            if not isinstance(polygon, list) or not polygon:
                continue
            try:
                points = [(float(p[0]), float(p[1])) for p in polygon]
            except (TypeError, ValueError, IndexError):
                continue
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            if not (x0 <= cx < x1 and y0 <= cy < y1):
                continue
            local = dict(row)
            local["polygon"] = [[p[0] - x0, p[1] - y0] for p in points]
            local_rows.append(local)
        return local_rows

    return cached_panel_ocr


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_p3() -> dict:
    source_image = FIXTURES / "P3_02.png"
    cached_rows = json.loads(
        (FIXTURES / "P3_02_ocr.json").read_text(encoding="utf-8")
    )["rows"]
    segmentation = detect_panel_regions(source_image)
    panel_map = {p["panel_id"]: p for p in segmentation.get("panels", [])}

    root = EXTRACT / "P3_02"
    if root.exists():
        shutil.rmtree(root)
    input_root = root / "runs" / "preprocessed"
    paper_dir = input_root / "paper-p3-real" / "01_preprocessing"
    image_relative = "extracted_figures/MAIN/P3_02.png"
    image_path = paper_dir / image_relative
    image_path.parent.mkdir(parents=True)
    shutil.copy2(source_image, image_path)

    source_pdf = root / "papers_pdf" / "paper-p3-real.pdf"
    source_pdf.parent.mkdir(parents=True)
    source_pdf_bytes = b"%PDF-1.7\narchived test fixture only\n"
    source_pdf.write_bytes(source_pdf_bytes)
    pdf_sha = hashlib.sha256(source_pdf_bytes).hexdigest()
    image_sha = sha256(image_path)
    with Image.open(image_path) as image:
        width, height = image.size

    (paper_dir / "main_analysis.md").write_text(
        "# Main Analysis\nP3_02 real-image regression fixture.\n",
        encoding="utf-8",
    )
    evidence_index = {
        "package_version": "1.1.0",
        "paper_id": "paper-p3-real",
        "metadata": {
            "doi": "10.0000/p3-real-regression",
            "title": "P3_02 real-image regression fixture",
            "has_si": False,
        },
        "inventory": {
            "main_pdf": {
                "path": str(source_pdf.resolve()),
                "sha256": pdf_sha,
                "size_bytes": len(source_pdf_bytes),
                "page_count": 1,
            },
            "si_pdf": None,
            "supplementary_files": [],
        },
        "pages": [],
        "tables": [],
        "figures": [{
            "figure_id": "MAIN_FIG_P3_02",
            "doc_type": "MAIN",
            "page_number": 1,
            "bbox": [0.0, 0.0, 500.0, 350.0],
            "caption": "P3_02 archived figure used for regression testing",
        }],
        "si_references": [],
        "media_assets": [{
            "asset_id": "ASSET_P3_02",
            "doc_type": "MAIN",
            "asset_type": "figure",
            "source_file": source_pdf.name,
            "source_sha256": pdf_sha,
            "relative_path": image_relative,
            "sha256": image_sha,
            "extraction_method": "archived_real_image_fixture",
            "page_number": 1,
            "bbox": [0.0, 0.0, 500.0, 350.0],
            "figure_id": "MAIN_FIG_P3_02",
            "table_id": None,
            "caption": "P3_02 archived figure used for regression testing",
            "width": width,
            "height": height,
            "mime_type": "image/png",
            "is_tiny_icon": False,
        }],
        "processing_summary": {
            "total_main_pages": 1,
            "total_si_pages": 0,
            "total_tables_detected": 0,
            "total_figures_detected": 1,
            "total_si_references": 0,
            "scanned_pages_detected": 0,
            "images_extracted": 1,
            "grobid_status": "DISABLED",
            "warnings": [],
            "status": "COMPLETE",
        },
    }
    (paper_dir / "evidence_index.json").write_text(
        json.dumps(evidence_index, ensure_ascii=False), encoding="utf-8"
    )

    snapshot = snapshot_paper(paper_dir, input_root)
    original_run_ocr = ocr.run_ocr
    ocr.run_ocr = make_cached_ocr(cached_rows, panel_map, "P3_02.png")
    try:
        result = process_paper(
            input_root,
            Path("paper-p3-real/01_preprocessing"),
            root / "output",
            options={"ocr": True, "memory_limit_mb": 1024, "temp_disk_limit_mb": 512},
            input_snapshot=snapshot,
        )
    finally:
        ocr.run_ocr = original_run_ocr
    return {
        "case": "P3_02",
        "source_image": str(source_image),
        "source_image_sha256": sha256(source_image),
        "segmentation": segmentation,
        "result": result,
        "output_paper_dir": str(Path(result["artifact_paths"]["manifest_path"]).parent),
    }


def run_p8() -> dict:
    source_image = FIXTURES / "P8_06.png"
    cached_rows = json.loads(
        (FIXTURES / "P8_06_ocr.json").read_text(encoding="utf-8")
    )["rows"]
    segmentation = detect_panel_regions(source_image)
    panel_map = {p["panel_id"]: p for p in segmentation.get("panels", [])}

    root = EXTRACT / "P8_06"
    if root.exists():
        shutil.rmtree(root)
    input_root = root / "input"
    paper_dir = input_root / "paper-p8-real"
    paper_dir.mkdir(parents=True)
    shutil.copy2(source_image, paper_dir / "P8_06.png")
    (paper_dir / "figure_inventory.json").write_text(
        json.dumps({
            "figures": [{
                "figure_id": "P8_06",
                "image_path": "P8_06.png",
                "panels": [],
            }]
        }),
        encoding="utf-8",
    )

    original_run_ocr = ocr.run_ocr
    ocr.run_ocr = make_cached_ocr(cached_rows, panel_map, "P8_06.png")
    try:
        result = process_paper(
            input_root,
            Path("paper-p8-real"),
            root / "output",
            options={"ocr": True, "memory_limit_mb": 1024, "temp_disk_limit_mb": 512},
        )
    finally:
        ocr.run_ocr = original_run_ocr
    return {
        "case": "P8_06",
        "source_image": str(source_image),
        "source_image_sha256": sha256(source_image),
        "segmentation": segmentation,
        "result": result,
        "output_paper_dir": str(Path(result["artifact_paths"]["manifest_path"]).parent),
    }


def main() -> None:
    EXTRACT.mkdir(parents=True, exist_ok=True)
    records = []
    for runner in (run_p3, run_p8):
        record = runner()
        records.append({
            key: value for key, value in record.items() if key != "segmentation"
        })
        print(
            json.dumps({
                "case": record["case"],
                "source_image": record["source_image"],
                "source_image_sha256": record["source_image_sha256"],
                "pipeline": {
                    key: record["result"].get(key)
                    for key in ("status", "figure_count", "panel_count", "series_count")
                },
                "output_paper_dir": record["output_paper_dir"],
            })
        )
    (RUN_DIR / "extraction_run.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
