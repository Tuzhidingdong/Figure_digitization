"""Read-only analysis of the PR18 single-image run outputs."""
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
    series_by_panel = {s["panel_id"]: s for s in dig["series"]}
    print("=== EXTRA KEYS ===", sorted(dig["extra"].keys()))
    for key, value in dig["extra"].items():
        if key in {"native_page_evidence", "context_index_fingerprint"}:
            continue
        print("extra:", key, json.dumps(value, ensure_ascii=False)[:400])

    print("\n=== PANELS ===")
    for panel in panels:
        pid = panel["panel_id"]
        s = series_by_panel.get(pid, {})
        m = s.get("metadata") or {}
        q = m.get("qc_report") or {}
        ts = m.get("trace_specification") or {}
        oc = m.get("ocr_status") or {}
        ax = q.get("axes") or {}
        print(json.dumps({
            "panel_id": pid,
            "bbox": panel.get("bbox"),
            "segmentation_provenance": panel.get("segmentation_provenance"),
            "segmentation_status": panel.get("segmentation_status"),
            "segmentation_confidence": panel.get("segmentation_confidence"),
            "ocr_status": oc,
            "chart_family": panel.get("chart_family"),
            "chart_family_status": panel.get("chart_family_status"),
            "trace_specification": ts,
            "color_detection": m.get("color_detection"),
            "plot_detection": m.get("plot_detection"),
            "x_calibration": m.get("x_calibration"),
            "y_calibration": m.get("y_calibration"),
            "calibration_errors": m.get("calibration_errors"),
            "axis_anchor_counts": {"x": (ax.get("x") or {}).get("anchor_count"), "y": (ax.get("y") or {}).get("anchor_count")},
            "axis_label_evidence": m.get("axis_label_evidence"),
            "extraction_method": s.get("extraction_method"),
            "extraction_status": s.get("extraction_status"),
            "points_count": s.get("points_count"),
            "qc_status": s.get("qc_status"),
            "qc_warnings": q.get("warnings"),
            "reason": m.get("reason"),
        }, ensure_ascii=False))

    csv_path = OUT / "exports" / "digitized_points" / "dataset.csv"
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    manifest = json.loads((OUT / "exports" / "digitized_points" / "export_manifest.json").read_text(encoding="utf-8"))
    print("\n=== EXPORT ===")
    print("data_rows", len(rows), "exported_series", manifest.get("series_count"), "exported_points", manifest.get("point_count"))
    print("warning_counts", json.dumps(manifest.get("warning_counts"), ensure_ascii=False))
    print("\n=== JOB ===")
    print("state", report.get("job_state_counts"), "elapsed", report.get("elapsed_seconds"), "peak_rss", report.get("peak_parent_and_worker_rss_bytes"))


if __name__ == "__main__":
    main()
