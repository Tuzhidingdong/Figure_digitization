from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
panels = sorted((OUT / "panels").glob("panel_*/source_crop.png"))
cell = (480, 360)
canvas = Image.new("RGB", (cell[0] * 2, cell[1] * 3), "white")
draw = ImageDraw.Draw(canvas)
for i, p in enumerate(panels):
    with Image.open(p) as im:
        im = im.convert("RGB")
        im.thumbnail((cell[0] - 10, cell[1] - 30))
        x, y = (i % 2) * cell[0], (i // 2) * cell[1]
        canvas.paste(im, (x + 5, y + 5))
        draw.text((x + 6, y + cell[1] - 22), p.parent.name, fill="black")
canvas.save(OUT / "images" / "panel_crops_check.png") if (OUT / "images").exists() else canvas.save(OUT / "panels" / "panel_crops_check.png")
print("saved", len(panels))
