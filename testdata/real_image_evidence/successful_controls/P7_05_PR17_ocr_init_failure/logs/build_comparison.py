"""Agent-assembled diagnostic overview from actual pipeline evidence.

This is NOT a Skill reconstruction output: the PR17 pipeline aborted before
digitization, so no reconstructed PNG exists. The image below shows the single
auto-detected crop and the recorded failure state.
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
crop = OUT / "papers" / "root-paper" / "evidence" / "P7_05_auto-01.png"
dest_dir = OUT / "comparisons"
dest_dir.mkdir(exist_ok=True)

with Image.open(crop) as im:
    original = im.convert("RGB")
original.thumbnail((400, 400))

W, H = 1320, 540
canvas = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(canvas)
d.text((10, 8), "ALL PANELS COMPARISON - Agent-assembled diagnostic (NOT a pipeline reconstruction)", fill=(150, 0, 0))
d.text((10, 26), "PR17 run FAILED_PERMANENT at OCR engine init; no automatic data points, no Skill reconstruction.", fill=(150, 0, 0))
d.text((10, 58), "AUTO PANEL auto-01 (real pipeline crop)", fill="black")
canvas.paste(original, (10, 82))

mid = Image.new("RGB", (420, 420), (245, 245, 245))
dm = ImageDraw.Draw(mid)
lines = [
    "RECONSTRUCTED FROM EXTRACTED DATA",
    "NOT AVAILABLE - 0 automatic points",
    "",
    "pipeline: FAILED_PERMANENT",
    "error: TypeError",
    "The value of Det.engine_type",
    "must be Enum Type.",
    "",
    "source: ocr.py:43",
    "RapidOCR(params=...)",
    "",
    "no trace_specification",
    "no calibration, no CSV rows",
]
for i, line in enumerate(lines):
    dm.text((10, 10 + i * 30), line, fill=(190, 0, 0) if i < 2 else (25, 25, 25))
canvas.paste(mid, (450, 82))

right = Image.new("RGB", (420, 420), "white")
dr = ImageDraw.Draw(right)
info = [
    "STATUS / EVIDENCE",
    "auto panels emitted: 1",
    "panel_layout.json: NOT WRITTEN",
    "OCR rows: 0",
    "numeric anchors: 0",
    "trace specs: 0",
    "series / points: 0 / 0",
    "validate: INVALID (5 missing)",
    "export rows: 0",
    "CV/EIS safety: no wrong trace",
]
for i, line in enumerate(info):
    dr.text((10, 10 + i * 30), line, fill=(25, 25, 25))
canvas.paste(right, (890, 82))
canvas.save(dest_dir / "ALL_PANELS_COMPARISON.png")
print("saved", dest_dir / "ALL_PANELS_COMPARISON.png")
