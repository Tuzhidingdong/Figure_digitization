"""Read-only analysis of PR19 artifacts."""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
PAPER = OUT / "papers" / "root-paper"


def brief(value, limit=900):
    return json.dumps(value, ensure_ascii=False)[:limit]


def main() -> None:
    dig = json.loads((PAPER / "digitization.json").read_text(encoding="utf-8"))
    panels = json.loads((PAPER / "panel_layout.json").read_text(encoding="utf-8"))["panels"]
    report = json.loads((OUT / "run_report.json").read_text(encoding="utf-8"))
    for s in dig["series"]:
        m = s.get("metadata") or {}
        q = m.get("qc_report") or {}
        ts = m.get("trace_specification") or {}
        cd = m.get("color_detection") or {}
        print("=== SERIES", s["series_id"], "panel", s["panel_id"], "===")
        print("label:", s.get("label"), "| technique:", s.get("technique"), "| family:", m.get("data_family"))
        print("extraction:", s.get("extraction_method"), s.get("extraction_status"), "points", s.get("points_count"), "reason", m.get("reason"))
        print("trace_spec:", brief(ts))
        print("color_detection:", brief(cd))
        print("y_axis_calibrations:", brief(m.get("y_axis_calibrations")))
        print("series_axis_assignment:", brief(m.get("series_axis_assignment")))
        print("y_axis_text_color_association:", brief(m.get("y_axis_text_color_association")))
        print("x_cal:", brief(m.get("x_calibration"), 400), "y_cal:", brief(m.get("y_calibration"), 400))
        print("qc:", q.get("calibration_state"), brief(q.get("warnings"), 400))
    print("\n=== PANEL SUMMARY ===")
    for p in panels:
        print(p["panel_id"], p.get("bbox"), p.get("chart_family"), p.get("ocr_status"), "conf", p.get("segmentation_confidence"))
    csv_path = OUT / "exports" / "digitized_points" / "dataset.csv"
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    manifest = json.loads((OUT / "exports" / "digitized_points" / "export_manifest.json").read_text(encoding="utf-8"))
    print("\n=== EXPORT ===", "rows", len(rows), "series", manifest.get("series_count"), "points", manifest.get("point_count"))
    print("warnings", brief(manifest.get("warning_counts"), 600))
    print("JOB", report["job_state_counts"], "elapsed", report["elapsed_seconds"], "rss", report["peak_parent_and_worker_rss_bytes"])


if __name__ == "__main__":
    main()
