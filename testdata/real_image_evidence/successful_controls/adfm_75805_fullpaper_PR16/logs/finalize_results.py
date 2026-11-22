"""Collect manual-assisted extraction evidence, overlay image, and final summary."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
MANUAL = OUT / "run_manual" / "out" / "papers" / "root-paper"
SRC_IMG = OUT / "manual_inputs" / "input" / "extracted_figures" / "MAIN" / "MAIN_MAIN_FIG_P7_05.png"


def main() -> None:
    dig = json.loads((MANUAL / "digitization.json").read_text(encoding="utf-8"))
    series = dig["series"][0]
    meta = series["metadata"]
    qc = meta["qc_report"]
    xcal, ycal = meta["x_calibration"], meta["y_calibration"]
    csv_src = MANUAL / "series" / "MAIN_FIG_P7_05__1" / "panel_series.csv"
    csv_dst = OUT / "data" / "Figure5_panel_a_4th_cycle_manual.csv"
    shutil.copy2(csv_src, csv_dst)

    # Overlay: plot box, axis anchors, ordered points (manual assistance, explicitly labelled).
    with Image.open(SRC_IMG) as im:
        overlay = im.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((83, 45, 421, 296), outline=(0, 170, 255), width=3)
    for px, py in ((83.5, 65.5), (83.5, 274.5), (420.5, 296)):
        draw.ellipse((px - 5, py - 5, px + 5, py + 5), outline=(255, 128, 0), width=3)
    pts = []
    with csv_dst.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pts.append((float(row["pixel_x"]), float(row["pixel_y"])))
    if pts:
        draw.line(pts, fill=(255, 0, 0), width=2)
        for idx, (x, y) in enumerate(pts):
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 0, 0))
            if idx in (0, len(pts) - 1):
                draw.text((x + 4, y - 12), f"p{idx}", fill=(255, 0, 0))
    draw.text((90, 30), "MANUAL plot_box/anchors/points - NOT automatic", fill=(200, 0, 0))
    overlay.save(OUT / "images" / "Figure5_panel_a_manual_overlay.png")

    manual_result = {
        "source": "manual-assisted controlled validation (PR16 worktree code)",
        "figure_id": series["figure_id"],
        "panel_id": series["panel_id"],
        "series_id": series["series_id"],
        "extraction_method": series["extraction_method"],
        "extraction_status": series["extraction_status"],
        "point_count": series["points_count"],
        "x_calibration": xcal,
        "y_calibration": ycal,
        "calibration_state": qc.get("calibration_state"),
        "qc_status": series["qc_status"],
        "review_state": series["review_state"],
        "warnings": qc.get("warnings"),
        "scientific_acceptance": qc.get("scientific_acceptance"),
        "data_file": str(csv_dst.relative_to(OUT)),
        "overlay_file": "images/Figure5_panel_a_manual_overlay.png",
    }
    (OUT / "manual_inputs" / "manual_result.json").write_text(
        json.dumps(manual_result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Append manual panel to the two result tables.
    with (OUT / "digitization_summary.csv").open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            series["figure_id"], series["panel_id"], series["series_id"],
            series["extraction_method"], series["extraction_status"], series["points_count"],
            json.dumps(xcal, ensure_ascii=False), json.dumps(ycal, ensure_ascii=False),
            qc.get("calibration_state", ""),
            json.dumps({"status": "MANUAL_PLOT_BOX", "source": "manual_inputs"}, ensure_ascii=False),
            "N/A", json.dumps(meta.get("calibration_errors"), ensure_ascii=False),
        ])
    with (OUT / "qc_summary.csv").open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            series["figure_id"], series["panel_id"], series["qc_status"], series["review_state"],
            json.dumps(qc.get("components", {}), ensure_ascii=False), qc.get("calibration_state", ""),
            json.dumps(qc.get("warnings", []), ensure_ascii=False), qc.get("scientific_acceptance", ""),
            "MANUAL_PLOT_BOX",
        ])

    auto = json.loads((OUT / "summary_auto.json").read_text(encoding="utf-8"))
    final = {
        "test_target": "10.1002_adfm.75805",
        "project_version": "4ca762e40c04045685db15c75838ade145589031",
        "automatic_pipeline": auto,
        "manual_assisted_case": manual_result,
        "totals": {
            "input_files": 70,
            "images": 34,
            "pipeline_figures": auto["auto_run"]["figures"],
            "pipeline_panels": auto["auto_run"]["panels"],
            "pipeline_series": auto["auto_run"]["series"],
            "automatic_points": auto["auto_run"]["total_points"],
            "manual_assisted_points": series["points_count"],
        },
    }
    (OUT / "summary.json").write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manual_result, indent=2, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main()
