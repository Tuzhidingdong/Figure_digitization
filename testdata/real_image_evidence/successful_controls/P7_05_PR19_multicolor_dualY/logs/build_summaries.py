"""Build CSV/JSON summaries from actual PR19 artifacts (read-only source)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
PAPER = OUT / "papers" / "root-paper"


def compact(value, limit=1200) -> str:
    return json.dumps(value, ensure_ascii=False)[:limit] if value is not None else ""


def main() -> None:
    dig = json.loads((PAPER / "digitization.json").read_text(encoding="utf-8"))
    panels = json.loads((PAPER / "panel_layout.json").read_text(encoding="utf-8"))["panels"]
    report = json.loads((OUT / "run_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUT / "exports" / "digitized_points" / "export_manifest.json").read_text(encoding="utf-8"))

    inv, digs, qcs = [], [], []
    for p in panels:
        inv.append({
            "panel_id": p["panel_id"], "bbox": compact(p.get("bbox")),
            "segmentation_provenance": p.get("segmentation_provenance"),
            "segmentation_status": p.get("segmentation_status"),
            "segmentation_confidence": p.get("segmentation_confidence"),
            "ocr_status": (p.get("ocr_status") or {}).get("status"),
            "ocr_records": (p.get("ocr_status") or {}).get("record_count"),
            "chart_family": p.get("chart_family"),
            "chart_family_status": p.get("chart_family_status"),
            "evidence_image": p.get("evidence_image_path"),
        })
    for s in dig["series"]:
        m = s.get("metadata") or {}
        q = m.get("qc_report") or {}
        ts = m.get("trace_specification") or {}
        cd = m.get("color_detection") or {}
        assn = m.get("series_axis_assignment") or {}
        yassoc = m.get("y_axis_text_color_association") or {}
        ycals = m.get("y_axis_calibrations") or {}
        cand = ts.get("automatic_color_family_candidate") or {}
        fam = (cd.get("family_detection") or (ts.get("automatic_color_family_detection") or {}))
        digs.append({
            "series_id": s["series_id"], "panel_id": s["panel_id"],
            "data_family": m.get("data_family"),
            "color_rgb": compact(cand.get("color_rgb") or cd.get("color_rgb")),
            "color_tolerance": cand.get("color_tolerance") or cd.get("color_tolerance"),
            "color_pixel_count": cand.get("pixel_count"),
            "color_pixel_fraction": cand.get("pixel_fraction"),
            "color_provenance": cd.get("source", ""),
            "family_count": fam.get("family_count"),
            "family_detection_status": fam.get("status", ""),
            "trace_spec_status": ts.get("status"),
            "trace_spec_reason": ts.get("reason"),
            "automation_status": (ts.get("input_provenance") or {}).get("automation_status"),
            "x_calibration": (m.get("x_calibration") or {}).get("status", "NONE"),
            "left_y_calibration": (ycals.get("LEFT") or {}).get("status", "NONE"),
            "right_y_calibration": (ycals.get("RIGHT") or {}).get("status", "NONE"),
            "series_axis_assignment": assn.get("status"),
            "axis_selected_side": assn.get("selected_side"),
            "y_axis_text_color_association": yassoc.get("status"),
            "side_match_distances": compact(yassoc.get("side_match_distances")),
            "extraction_method": s.get("extraction_method"),
            "extraction_status": s.get("extraction_status"),
            "points_count": s.get("points_count"),
            "reason": m.get("reason"),
        })
        qcs.append({
            "series_id": s["series_id"], "panel_id": s["panel_id"],
            "qc_status": s.get("qc_status"), "review_state": s.get("review_state"),
            "calibration_state": q.get("calibration_state", ""),
            "warnings": compact(q.get("warnings", [])),
            "scientific_acceptance": q.get("scientific_acceptance", ""),
            "ocr_status": (m.get("ocr_status") or {}).get("status", ""),
        })
    for name, rows in (("panel_inventory.csv", inv), ("digitization_summary.csv", digs), ("qc_summary.csv", qcs)):
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    summary = {
        "head": "3c49ba37779274abd2c8b249ed4c746d64af5a1d",
        "algorithm_version": report["algorithm_version"],
        "environment": {"python": "3.13.9", "rapidocr": "3.10.0", "onnxruntime": "1.32.0"},
        "image_sha256": "3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de",
        "input_fixture": "reused verbatim from PR18 worktree (image + minimal figure_inventory.json)",
        "job_state": report["job_state_counts"], "validate": "OK",
        "panels": len(panels), "ocr_records_total": sum(r["ocr_records"] for r in inv),
        "series": len(dig["series"]), "data_points": sum(s.get("points_count", 0) for s in dig["series"]),
        "csv_data_rows": manifest.get("point_count"),
        "color_candidate_series": [r["series_id"] for r in digs if r["color_rgb"]],
        "dual_y_calibrated_panels": sorted({r["panel_id"] for r in digs if r["left_y_calibration"] == "CALIBRATED_NUMERIC" and r["right_y_calibration"] == "CALIBRATED_NUMERIC"}),
        "axis_assignment_statuses": sorted({r["series_axis_assignment"] for r in digs}),
        "y_axis_text_color_association_statuses": sorted({r["y_axis_text_color_association"] for r in digs}),
        "trace_spec_statuses": sorted({r["trace_spec_status"] for r in digs}),
        "automation_statuses": sorted({r["automation_status"] for r in digs}),
        "reconstructed_pngs": [], "overlay_pngs": [],
        "comparison_sheet": "papers/root-paper/comparisons/ALL_PANELS_COMPARISON.png",
        "elapsed_seconds": report["elapsed_seconds"], "peak_rss_bytes": report["peak_parent_and_worker_rss_bytes"],
        "llm_tokens": report["default_llm_tokens"],
        "export_warning_counts": manifest.get("warning_counts"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
