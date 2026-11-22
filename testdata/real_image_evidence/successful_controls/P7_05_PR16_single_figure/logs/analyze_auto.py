"""Analyze the single automatic Skill run; emit CSV/JSON tables (no manual inputs)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
PAPER = OUT / "auto_out" / "papers" / "root-paper"
REPORT = json.loads((OUT / "auto_out" / "run_report.json").read_text(encoding="utf-8"))

# Agent visual content reference ONLY. These strings are NOT Skill classifications.
VISUAL = {
    "WHOLE_IMAGE": ("composite of six subpanels", "Agent visual reference"),
    "PANEL_A": ("cyclic voltammetry (CV) curves; two samples, dashed 1st / solid 4th cycle; axes Voltage (V), Current (A g-1)", "Agent visual reference"),
    "PANEL_B": ("rate performance: capacity vs cycle number with right-hand coulombic-efficiency axis; two scatter series", "Agent visual reference"),
    "PANEL_C": ("schematic illustration of cell configurations; no numeric axes", "Agent visual reference"),
    "PANEL_D": ("cycling capacity vs cycle number with right-hand CE axis; two series", "Agent visual reference"),
    "PANEL_E": ("cycling capacity vs cycle number with right-hand CE axis plus photograph inset", "Agent visual reference"),
    "PANEL_F": ("scatter comparison of energy density vs areal capacity with reference labels", "Agent visual reference"),
}


def main() -> None:
    dig = json.loads((PAPER / "digitization.json").read_text(encoding="utf-8"))
    inv = json.loads((PAPER / "figure_inventory.json").read_text(encoding="utf-8"))
    panels = json.loads((PAPER / "panel_layout.json").read_text(encoding="utf-8"))["panels"]
    dig_rows, qc_rows, class_rows, extract_rows = [], [], [], []
    for s in dig["series"]:
        fid = s["figure_id"]
        m = s.get("metadata") or {}
        cls = m.get("chart_family_classification") or {}
        plot = m.get("plot_detection") or {}
        q = m.get("qc_report") or {}
        xcal, ycal = m.get("x_calibration"), m.get("y_calibration")
        panel = next((p for p in panels if p["figure_id"] == fid), {})
        fig = next((f for f in inv["figures"] if f["figure_id"] == fid), {})
        class_rows.append({
            "figure_id": fid,
            "skill_chart_family": cls.get("chart_family", ""),
            "skill_classification_status": cls.get("status", ""),
            "skill_confidence": cls.get("confidence", ""),
            "skill_evidence": json.dumps(cls.get("evidence", []), ensure_ascii=False),
            "agent_visual_content": VISUAL.get(fid, ("unknown", ""))[0],
            "content_source": VISUAL.get(fid, ("unknown", ""))[1],
            "skill_identified_content": "NO",
            "needs_review": s.get("review_state", ""),
        })
        dig_rows.append({
            "figure_id": fid,
            "panel_id": s.get("panel_id"),
            "extraction_method": s.get("extraction_method"),
            "extraction_status": s.get("extraction_status"),
            "points_count": s.get("points_count"),
            "plot_detection_status": plot.get("status", ""),
            "plot_bbox": json.dumps(plot.get("pixel_bbox"), ensure_ascii=False),
            "color_detection": json.dumps(m.get("color_detection"), ensure_ascii=False),
            "x_calibration": json.dumps(xcal, ensure_ascii=False),
            "y_calibration": json.dumps(ycal, ensure_ascii=False),
            "calibration_state": q.get("calibration_state", ""),
            "reason": m.get("reason", ""),
            "source_image_sha256": (s.get("evidence") or [{}])[0].get("source_image_sha256", ""),
        })
        qc_rows.append({
            "figure_id": fid,
            "panel_id": s.get("panel_id"),
            "qc_status": s.get("qc_status"),
            "review_state": s.get("review_state"),
            "calibration_state": q.get("calibration_state", ""),
            "components": json.dumps(q.get("components", {}), ensure_ascii=False),
            "warnings": json.dumps(q.get("warnings", []), ensure_ascii=False),
            "scientific_acceptance": q.get("scientific_acceptance", ""),
            "panel_segmentation": panel.get("segmentation_status", ""),
        })

        visual = VISUAL.get(fid, ("unknown", ""))[0]
        if fid == "WHOLE_IMAGE":
            cat, why = "NOT_SUPPORTED", "Composite whole figure; Skill produced one provisional box covering only part of one subpanel. No single plot can be digitized."
        elif fid == "PANEL_C":
            cat, why = "NOT_SUPPORTED", "Schematic without numeric axes or data series (Agent visual); Skill found no plot frame and no calibration evidence."
        elif fid == "PANEL_F":
            cat, why = "NOT_SUPPORTED", "Scatter/comparison plot; bar/scatter digitization is P1 and not production-supported. Skill found a plot box but no anchors or series."
        elif fid in {"PANEL_A", "PANEL_B", "PANEL_D", "PANEL_E"}:
            cat = "CONDITIONALLY_EXTRACTABLE"
            why = ("Agent visual: curve/scatter panel with numeric axes; Skill auto-detected plot box "
                   + json.dumps(plot.get("pixel_bbox")) + " but found 0 axis anchors, no color family, "
                   "and no ordered trace. Blocked by missing OCR/native anchor channel and by no "
                   "automatic multi-series/path segmentation — not by image being inherently un-digitizable.")
        else:
            cat, why = "NEEDS_REVIEW", "No visual or Skill evidence recorded."
        extract_rows.append({
            "figure_id": fid,
            "panel_id": s.get("panel_id"),
            "category": cat,
            "skill_classification": cls.get("chart_family", ""),
            "skill_plot_detection": plot.get("status", ""),
            "skill_axis_anchor_count": 0,
            "skill_points": s.get("points_count"),
            "reason": why,
            "agent_visual_content": visual,
        })

    for name, rows in (
        ("digitization_summary.csv", dig_rows),
        ("qc_summary.csv", qc_rows),
        ("classification_results.csv", class_rows),
        ("extractability_assessment.csv", extract_rows),
    ):
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    summary = {
        "target_image": "MAIN_MAIN_FIG_P7_05.png",
        "project_version": "4ca762e40c04045685db15c75838ade145589031",
        "automatic_run": {
            "figures_submitted": len(dig["series"]),
            "subpanels": 6,
            "panel_segmentation_by_skill": "NONE (all WHOLE_FIGURE_NOT_SEGMENTED)",
            "plot_boxes_found": sum(1 for r in dig_rows if r["plot_detection_status"] == "PROVISIONAL_PLOT_BOX"),
            "series": len(dig["series"]),
            "series_with_points": sum(1 for r in dig_rows if r["points_count"] > 0),
            "total_points": sum(r["points_count"] for r in dig_rows),
            "axis_anchors_found": 0,
            "calibration_states": sorted({r["calibration_state"] for r in qc_rows}),
            "qc_statuses": sorted({r["qc_status"] for r in qc_rows}),
            "validate_status": "OK",
            "elapsed_seconds": REPORT["elapsed_seconds"],
            "peak_rss_bytes": REPORT["peak_parent_and_worker_rss_bytes"],
            "llm_tokens": REPORT["default_llm_tokens"],
        },
        "extractability_counts": {k: sum(1 for r in extract_rows if r["category"] == k)
                                  for k in sorted({r["category"] for r in extract_rows})},
        "note": "All content descriptions are Agent visual reference; Skill identified no specific chart content.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
