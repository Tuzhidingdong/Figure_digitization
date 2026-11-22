"""OPTIONAL isolated diagnostic: reconstruct panel A from an existing MANUAL-assisted CSV.

This is NOT part of the automatic test statistics. All plot_box/anchors/points
came from a previously documented manual annotation, not from Skill automation.
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent.parent
SRC_CSV = Path(
    r"E:\Zinc_batters_datas\Figure_digitization_pr16_test\test_outputs"
    r"\chem-literacy_10.1002_adfm.75805\data\Figure5_panel_a_4th_cycle_manual.csv"
)
ORIGINAL = BASE / "original" / "source_image.png"


def main() -> None:
    data_dir = BASE / "manual_assisted_diagnostic" / "data"
    rec_dir = BASE / "manual_assisted_diagnostic" / "reconstructed"
    cmp_dir = BASE / "manual_assisted_diagnostic" / "comparisons"
    for d in (data_dir, rec_dir, cmp_dir):
        d.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / "panel_a_manual_series.csv"
    shutil.copy2(SRC_CSV, csv_path)
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    xs = [float(r["x_value"]) for r in rows]
    ys = [float(r["y_value"]) for r in rows]
    px = [float(r["pixel_x"]) for r in rows]
    py = [float(r["pixel_y"]) for r in rows]

    W, H = 900, 620
    pad_l, pad_r, pad_t, pad_b = 90, 40, 70, 70
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.text((20, 14), "PANEL A RECONSTRUCTED FROM MANUAL-ASSISTED EXTRACTED DATA (25 points)", fill=(150, 0, 0))
    d.text((20, 32), "NOT an automatic Skill extraction; diagnostic only", fill=(150, 0, 0))
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    xspan, yspan = (xmax - xmin) or 1, (ymax - ymin) or 1
    x0, x1 = pad_l, W - pad_r
    y0, y1 = pad_t, H - pad_b
    d.rectangle((x0, y0, x1, y1), outline="black", width=2)
    for i in range(6):
        yy = y0 + (y1 - y0) * i / 5
        val = ymax - yspan * i / 5
        d.line((x0, yy, x1, yy), fill=(225, 225, 225))
        d.text((8, yy - 6), f"{val:.2f}", fill="black")
    for i in range(7):
        xx = x0 + (x1 - x0) * i / 6
        val = xmin + xspan * i / 6
        d.text((xx - 12, y1 + 6), f"{val:.2f}", fill="black")
    d.text((W // 2 - 60, H - 28), "Voltage (V)", fill="black")
    d.text((12, H // 2 - 60), "Current (A g-1)", fill="black")
    pts = [
        (x0 + (x - xmin) / xspan * (x1 - x0), y0 + (ymax - y) / yspan * (y1 - y0))
        for x, y in zip(xs, ys)
    ]
    d.line(pts, fill=(220, 0, 0), width=3)
    for p in pts:
        d.ellipse((p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3), fill=(220, 0, 0))
    d.text((x0 + 10, y0 + 10), "series: PVO // modified Cu, 4th cycle anodic (manual)", fill=(220, 0, 0))
    im.save(rec_dir / "panel_a_reconstructed.png")

    # Original crop from this run's input package (panel A region).
    with Image.open(BASE / "input" / "extracted_figures" / "MAIN" / "PANEL_A.png") as src:
        original = src.convert("RGB")
    original.thumbnail((600, 420))
    panel_a = original
    # Manual CSV pixel coordinates are in the WHOLE-image frame; PANEL_A crop
    # origin is (18, 12). Subtract the crop origin before overlaying.
    ox, oy = 18, 12
    overlay = Image.open(BASE / "input" / "extracted_figures" / "MAIN" / "PANEL_A.png").convert("RGB")
    od = ImageDraw.Draw(overlay)
    cx = [x - ox for x in px]
    cy = [y - oy for y in py]
    od.line(list(zip(cx, cy)), fill=(255, 0, 0), width=2)
    for x, y in zip(cx, cy):
        od.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 0, 0))
    overlay.thumbnail((600, 420))

    W2, H2 = 1280, 520
    cmp = Image.new("RGB", (W2, H2), "white")
    dc = ImageDraw.Draw(cmp)
    dc.text((10, 8), "MANUAL-ASSISTED DIAGNOSTIC (NOT part of automatic results)", fill=(150, 0, 0))
    dc.text((10, 470), "Left: original panel A | Middle: reconstruction from 25 extracted points | Right: extracted points overlaid", fill="black")
    cmp.paste(panel_a, (10, 40))
    cmp.paste(Image.open(rec_dir / "panel_a_reconstructed.png").resize((600, 420)), (430, 40))
    cmp.paste(overlay, (860, 40))
    cmp.save(cmp_dir / "panel_a_comparison_manual_assisted.png")
    print("manual diagnostic written; points =", len(rows))


if __name__ == "__main__":
    main()
