"""Build labelled contact sheets for visual applicability triage (diagnostic only)."""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
ROOT = Path(r"E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805")
SHEET = OUT / "images"


def sheet(paths: list[Path], labels: list[str], target: Path, cols: int, cell: tuple[int, int]) -> None:
    tw, th = cell
    rows = (len(paths) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + 26)), "white")
    draw = ImageDraw.Draw(canvas)
    for idx, (path, label) in enumerate(zip(paths, labels)):
        col, row = idx % cols, idx // cols
        x, y = col * tw, row * (th + 26)
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((tw - 8, th - 8))
            canvas.paste(im, (x + (tw - im.width) // 2, y + 4))
        draw.text((x + 4, y + th + 2), label[:52], fill="black")
    canvas.save(target)
    print(target, canvas.size)


def main() -> None:
    with (OUT / "inventory.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    images = [r for r in rows if r["width"]]
    main_rows = [r for r in images if "/MAIN/" in r["relative_path"]]
    si_rows = [r for r in images if "/embedded_images/" in r["relative_path"]]
    sheet(
        [ROOT / r["relative_path"] for r in main_rows],
        [f"{r['figure_id']} {r['width']}x{r['height']}" for r in main_rows],
        SHEET / "contact_MAIN.png",
        2,
        (560, 300),
    )
    for part in range(2):
        chunk = si_rows[part * 14 : (part + 1) * 14]
        sheet(
            [ROOT / r["relative_path"] for r in chunk],
            [Path(r["relative_path"]).name + f" {r['width']}x{r['height']}" for r in chunk],
            SHEET / f"contact_SI_{part + 1}.png",
            3,
            (400, 220),
        )


if __name__ == "__main__":
    main()
