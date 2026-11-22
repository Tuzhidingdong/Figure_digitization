"""Build per-panel comparisons and ALL_PANELS_COMPARISON.png from automatic results only.

No reconstructed curve is drawn because the automatic run produced zero data points.
The middle column explicitly states this instead of showing a fabricated plot.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
ORDER = ["WHOLE_IMAGE", "PANEL_A", "PANEL_B", "PANEL_C", "PANEL_D", "PANEL_E", "PANEL_F"]
CELL_W, CELL_H = 440, 300


def read(name: str) -> dict[str, dict[str, str]]:
    with (OUT / name).open(encoding="utf-8") as f:
        return {r["figure_id"]: r for r in csv.DictReader(f)}


def wrap(text: str, width: int = 52) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            lines.append(cur); cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines


def panel_image(fid: str) -> Image.Image:
    src = OUT / "input" / "extracted_figures" / "MAIN" / f"{fid}.png"
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((CELL_W - 12, CELL_H - 12))
        return im.copy()


def main() -> None:
    dig = read("digitization_summary.csv")
    ext = read("extractability_assessment.csv")
    (OUT / "comparisons").mkdir(exist_ok=True)
    (OUT / "evidence" / "plot_regions").mkdir(parents=True, exist_ok=True)
    (OUT / "evidence" / "calibration").mkdir(parents=True, exist_ok=True)

    (OUT / "evidence" / "calibration" / "no_anchor_evidence.json").write_text(
        json.dumps(
            {
                "reason": "Automatic run found 0 numeric axis anchors for all 7 figures; "
                          "no calibration was performed, so no calibration artifact was generated.",
                "calibration_states": sorted({r["calibration_state"] for r in dig.values()}),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    for fid in ORDER:
        img = panel_image(fid)
        drow, erow = dig[fid], ext[fid]
        bbox = json.loads(drow["plot_bbox"]) if drow["plot_bbox"] else None
        # Auto plot-region evidence overlay on the unmodified source crop.
        with Image.open(OUT / "input" / "extracted_figures" / "MAIN" / f"{fid}.png") as im:
            overlay = im.convert("RGB").copy()
        if bbox:
            ImageDraw.Draw(overlay).rectangle(tuple(bbox), outline=(0, 170, 255), width=3)
        overlay.save(OUT / "evidence" / "plot_regions" / f"{fid.lower()}_auto_plotbox.png")

        note = (
            f"AUTO POINTS: {drow['points_count']} | "
            f"PLOT BOX: {drow['plot_detection_status']} {bbox or ''} | "
            f"ANCHORS: 0 | CLASS: {drow['extraction_status']} | "
            f"CATEGORY: {erow['category']}"
        )
        cell_mid = Image.new("RGB", (CELL_W, CELL_H), (245, 245, 245))
        dm = ImageDraw.Draw(cell_mid)
        dm.text((10, 12), "RECONSTRUCTED FROM EXTRACTED DATA", fill=(80, 80, 80))
        dm.text((10, 32), "NO AUTOMATIC DATA POINTS -> NO PLOT DRAWN", fill=(200, 0, 0))
        for i, line in enumerate(wrap(note)[:8]):
            dm.text((10, 56 + i * 16), line, fill=(20, 20, 20))
        why = "Reason: " + erow["reason"]
        for i, line in enumerate(wrap(why, 60)[:10]):
            dm.text((10, 180 + i * 12), line, fill=(60, 60, 60))

        cell_right = Image.new("RGB", (CELL_W, CELL_H), "white")
        dr = ImageDraw.Draw(cell_right)
        dr.text((10, 12), "STATUS / EVIDENCE", fill=(80, 80, 80))
        lines = [
            f"figure: {fid}",
            f"skill class: {drow['extraction_status']}",
            f"qc: {erow['skill_classification']}/NEEDS_REVIEW",
            f"calibration: {drow['calibration_state']}",
            f"reconstruction: NOT AVAILABLE (0 points)",
        ]
        for i, line in enumerate(lines):
            dr.text((10, 38 + i * 18), line, fill=(20, 20, 20))

        per = Image.new("RGB", (CELL_W * 2, CELL_H + 30), "white")
        dp = ImageDraw.Draw(per)
        dp.text((10, 6), f"{fid} - ORIGINAL (left) vs RECONSTRUCTION (right, unavailable)", fill="black")
        per.paste(img, ((CELL_W - img.width) // 2, 30))
        per.paste(cell_mid.crop((0, 0, CELL_W, CELL_H)), (CELL_W, 30))
        per.save(OUT / "comparisons" / f"{fid.lower()}_comparison.png")

    rows = len(ORDER)
    canvas = Image.new("RGB", (CELL_W * 3, (CELL_H + 34) * rows + 40), "white")
    d = ImageDraw.Draw(canvas)
    d.text((10, 6), "ALL PANELS COMPARISON - automatic Skill run only (manual inputs: NONE)", fill="black")
    d.text((10, 22), "Left: original crop | Middle: reconstruction from extracted data (none available) | Right: status", fill=(80, 80, 80))
    for r, fid in enumerate(ORDER):
        y = 40 + r * (CELL_H + 34)
        img = panel_image(fid)
        d.text((10, y - 14), fid, fill="black")
        canvas.paste(img, (10, y))
        drow, erow = dig[fid], ext[fid]
        bbox = json.loads(drow["plot_bbox"]) if drow["plot_bbox"] else None
        mid = Image.new("RGB", (CELL_W, CELL_H), (245, 245, 245))
        dm = ImageDraw.Draw(mid)
        dm.text((10, 12), "NO AUTOMATIC DATA POINTS", fill=(200, 0, 0))
        dm.text((10, 32), "NO PLOT DRAWN (no fabricated data)", fill=(200, 0, 0))
        note = f"plot_box: {bbox or 'none'} | anchors: 0 | reason: {erow['reason']}"
        for i, line in enumerate(wrap(note, 60)[:12]):
            dm.text((10, 58 + i * 14), line, fill=(20, 20, 20))
        right = Image.new("RGB", (CELL_W, CELL_H), "white")
        dr = ImageDraw.Draw(right)
        info = [
            f"category: {erow['category']}",
            f"extraction: {drow['extraction_status']}",
            f"points: {drow['points_count']}",
            f"qc: {drow['calibration_state']}",
            "scientific accuracy: NOT assessed",
        ]
        for i, line in enumerate(info):
            dr.text((10, 20 + i * 20), line, fill=(20, 20, 20))
        canvas.paste(mid, (CELL_W + 10, y))
        canvas.paste(right, (CELL_W * 2 + 10, y))
    dest = OUT / "comparisons" / "ALL_PANELS_COMPARISON.png"
    canvas.save(dest)
    print("saved", dest, canvas.size)


if __name__ == "__main__":
    main()
