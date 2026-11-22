"""Build CSV/JSON summaries from the actual PR18 run artifacts (read-only source)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
PAPER = OUT / "papers" / "root-paper"


def main() -> None:
    dig = json.loads((PAPER / "digitization.json").read_text(encoding="utf-8"))
    panels = json.loads((PAPER / "panel_layout.json").read_text(encoding="utf-8"))["panels"]
    report = json.loads((OUT / "run_report.json").read_text(encoding="utf-8"))
    by_panel = {s["panel_id"]: s for s in dig["series"]}
    inv, digs, qcs = [], [], []
    for p in panels:
        s = by_panel[p["panel_id"]]
        m = s.get("metadata") or {}
        q = m.get("qc_report") or {}
        ts = m.get("trace_specification") or {}
        oc = p.get("ocr_status") or {}
        ax = q.get("axes") or {}
        inv.append({
            "panel_id": p["panel_id"], "bbox": json.dumps(p.get("bbox")),
            "segmentation_provenance": p.get("segmentation_provenance"),
            "segmentation_status": p.get("segmentation_status"),
            "segmentation_confidence": p.get("segmentation_confidence"),
            "evidence_image": p.get("evidence_image_path"),
            "ocr_status": oc.get("status"), "ocr_records": oc.get("record_count"),
        })
        digs.append({
            "panel_id": p["panel_id"], "chart_family": p.get("chart_family"),
            "trace_spec_status": ts.get("status"), "trace_spec_reason": ts.get("reason"),
            "automation_status": (ts.get("input_provenance") or {}).get("automation_status"),
            "color_detection_status": (m.get("color_detection") or {}).get("status", "NOT_RUN"),
            "color_reason": (m.get("color_detection") or {}).get("reason", ""),
            "x_anchors": (ax.get("x") or {}).get("anchor_count"),
            "y_anchors": (ax.get("y") or {}).get("anchor_count"),
            "x_calibration": (m.get("x_calibration") or {}).get("status", "NONE"),
            "y_calibration": (m.get("y_calibration") or {}).get("status", "NONE"),
            "extraction_method": s.get("extraction_method"),
            "extraction_status": s.get("extraction_status"),
            "points_count": s.get("points_count"), "reason": m.get("reason"),
        })
        qcs.append({
            "panel_id": p["panel_id"], "qc_status": s.get("qc_status"),
            "review_state": s.get("review_state"),
            "warnings": json.dumps(q.get("warnings", []), ensure_ascii=False),
            "calibration_state": q.get("calibration_state", ""),
            "scientific_acceptance": q.get("scientific_acceptance", ""),
            "ocr_status": oc.get("status"),
        })
    for name, rows in (("panel_inventory.csv", inv), ("digitization_summary.csv", digs), ("qc_summary.csv", qcs)):
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    summary = {
        "head": "33f0454b1d4a9a7bc9781fafaace58a0bdbf3706",
        "python": "3.13.9", "rapidocr": "3.10.0", "onnxruntime": "1.32.0",
        "image_sha256": "3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de",
        "job_state": report["job_state_counts"], "validate": "OK",
        "panels_detected": len(panels),
        "ocr_records_total": sum(r["ocr_records"] for r in inv),
        "ocr_all_succeeded": all(r["ocr_status"] == "SUCCEEDED" for r in inv),
        "x_anchor_total": sum(r["x_anchors"] for r in digs),
        "y_anchor_total": sum(r["y_anchors"] for r in digs),
        "both_axes_calibrated_panels": [r["panel_id"] for r in digs if r["x_calibration"] == "CALIBRATED_NUMERIC" and r["y_calibration"] == "CALIBRATED_NUMERIC"],
        "trace_spec_statuses": {r["panel_id"]: r["trace_spec_status"] for r in digs},
        "automation_statuses": {r["panel_id"]: r["automation_status"] for r in digs},
        "color_detection_runs": [r["panel_id"] for r in digs if r["color_detection_status"] != "NOT_RUN"],
        "series": len(dig["series"]),
        "data_points": sum(s.get("points_count", 0) for s in dig["series"]),
        "csv_data_rows": 0,
        "comparison_sheet": "papers/root-paper/comparisons/ALL_PANELS_COMPARISON.png",
        "reconstructed_pngs": [], "overlay_pngs": [],
        "elapsed_seconds": report["elapsed_seconds"],
        "peak_rss_bytes": report["peak_parent_and_worker_rss_bytes"],
        "llm_tokens": report["default_llm_tokens"],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
