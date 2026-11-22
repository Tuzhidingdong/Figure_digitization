"""Analyze the automatic Skill run and emit structured result tables."""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
PAPER = OUT / "run_auto" / "out" / "papers" / "root-paper"


def main() -> None:
    dig = json.loads((PAPER / "digitization.json").read_text(encoding="utf-8"))
    inv = json.loads((PAPER / "figure_inventory.json").read_text(encoding="utf-8"))
    panels = json.loads((PAPER / "panel_layout.json").read_text(encoding="utf-8"))["panels"]
    report = json.loads((OUT / "run_auto" / "out" / "run_report.json").read_text(encoding="utf-8"))

    class_rows = []
    dig_rows = []
    qc_rows = []
    for figure in inv["figures"]:
        fid = figure["figure_id"]
        panel = next((p for p in panels if p["figure_id"] == fid), {})
        series = [s for s in dig["series"] if s["figure_id"] == fid]
        classification = (series[0].get("metadata") or {}).get("chart_family_classification") if series else None
        caption = str(figure.get("caption") or "").replace("\n", " ")
        class_rows.append(
            {
                "figure_id": fid,
                "page": figure.get("page"),
                "doc_type": figure.get("source_doc_type"),
                "image_width": "",
                "image_height": "",
                "caption_head": caption[:200],
                "source_asset_status": figure.get("source_asset_status"),
                "pdf_integrity": figure.get("source_pdf_integrity_status"),
                "chart_family": (classification or {}).get("chart_family", ""),
                "classification_status": (classification or {}).get("status", ""),
                "confidence": (classification or {}).get("confidence", ""),
                "evidence": json.dumps((classification or {}).get("evidence", []), ensure_ascii=False),
                "technique": (series[0].get("technique") if series else "") or "",
                "data_family": (series[0].get("metadata") or {}).get("data_family", "") if series else "",
                "entered_digitization": "YES" if series else "NO",
                "reason": (series[0].get("metadata") or {}).get("reason", "") if series else "",
            }
        )
        for s in series:
            meta = s.get("metadata") or {}
            qc = meta.get("qc_report") or {}
            dig_rows.append(
                {
                    "figure_id": fid,
                    "panel_id": s.get("panel_id"),
                    "series_id": s.get("series_id"),
                    "extraction_method": s.get("extraction_method"),
                    "extraction_status": s.get("extraction_status"),
                    "points_count": s.get("points_count"),
                    "x_calibration": json.dumps(meta.get("x_calibration"), ensure_ascii=False),
                    "y_calibration": json.dumps(meta.get("y_calibration"), ensure_ascii=False),
                    "calibration_state": qc.get("calibration_state", ""),
                    "plot_detection": json.dumps(meta.get("plot_detection"), ensure_ascii=False),
                    "color_detection": json.dumps(meta.get("color_detection"), ensure_ascii=False),
                    "calibration_errors": json.dumps(meta.get("calibration_errors"), ensure_ascii=False),
                }
            )
            qc_rows.append(
                {
                    "figure_id": fid,
                    "panel_id": s.get("panel_id"),
                    "qc_status": s.get("qc_status"),
                    "review_state": s.get("review_state"),
                    "qc_components": json.dumps(qc.get("components", {}), ensure_ascii=False),
                    "calibration_state": qc.get("calibration_state", ""),
                    "warnings": json.dumps(qc.get("warnings", []), ensure_ascii=False),
                    "scientific_acceptance": qc.get("scientific_acceptance", ""),
                    "panel_segmentation_status": panel.get("segmentation_status", ""),
                }
            )

    for filename, rows in (
        ("classification_results.csv", class_rows),
        ("digitization_summary.csv", dig_rows),
        ("qc_summary.csv", qc_rows),
    ):
        with (OUT / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    summary = {
        "auto_run": {
            "paper_status": dig["status"],
            "figures": len(inv["figures"]),
            "panels": len(panels),
            "series": len(dig["series"]),
            "total_points": sum(s.get("points_count", 0) for s in dig["series"]),
            "elapsed_seconds": report["elapsed_seconds"],
            "peak_rss_bytes": report["peak_parent_and_worker_rss_bytes"],
            "llm_tokens": report["default_llm_tokens"],
            "algorithm_implementation_fingerprint": report["algorithm_implementation_fingerprint"],
        },
        "classifications": [r["chart_family"] + "/" + r["classification_status"] for r in class_rows],
        "calibration_states": [r["calibration_state"] for r in qc_rows],
        "qc_statuses": [r["qc_status"] for r in qc_rows],
    }
    (OUT / "summary_auto.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
