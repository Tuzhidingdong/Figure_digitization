"""Prepare a single-image Skill input package (no digitization overrides).

Panel crops are Agent visual *image preparation* only. No plot_box, anchors,
curve points, axis labels or technique labels are supplied to the Skill.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

SRC = Path(
    r"E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805"
    r"\extracted_figures\MAIN\MAIN_MAIN_FIG_P7_05.png"
)
OUT = Path(__file__).resolve().parent.parent
EXPECTED_SHA = "3b860297e333f07e54618a4e1059191682fb538339b4c75c6e3f862a6ecc10de"

# Agent-visual crop boxes for enumerating subpanels; used ONLY to cut images.
PANELS = {
    "PANEL_A": (18, 12, 442, 322),
    "PANEL_B": (442, 12, 922, 322),
    "PANEL_C": (930, 12, 1400, 318),
    "PANEL_D": (15, 322, 442, 674),
    "PANEL_E": (442, 322, 922, 674),
    "PANEL_F": (930, 322, 1400, 674),
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    for name in (
        "original", "panels", "data", "reconstructed", "comparisons",
        "evidence", "logs", "input/extracted_figures/MAIN",
    ):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    before = sha(SRC)
    if before != EXPECTED_SHA:
        raise SystemExit(f"source SHA changed before test: {before}")
    shutil.copy2(SRC, OUT / "original" / "source_image.png")
    with Image.open(SRC) as im:
        im.load()
        size, fmt, mode = im.size, im.format, im.mode

    inventory = []
    figures = []
    assets = []
    whole_rel = "extracted_figures/MAIN/WHOLE_IMAGE.png"
    shutil.copy2(SRC, OUT / "input" / whole_rel)
    figures.append({
        "figure_id": "WHOLE_IMAGE", "doc_type": "MAIN", "page_number": 7,
        "caption": "FIGURE 5 Electrochemical performance of full cell with limited zinc supply. "
                   "(a) CV curves at 1 mV s-1; (b) rate performance; (c) schematic illustration; "
                   "(d,e) cycling performance; (f) comparison of energy density and areal capacity.",
    })
    assets.append({
        "asset_id": "ASSET_WHOLE", "doc_type": "MAIN", "asset_type": "figure",
        "relative_path": whole_rel, "sha256": sha(OUT / "input" / whole_rel),
        "extraction_method": "verbatim_copy_of_target_image", "page_number": 7,
        "figure_id": "WHOLE_IMAGE", "caption": "",
    })
    inventory.append({
        "panel_id": "WHOLE_IMAGE", "box_px": "", "crop_file": whole_rel,
        "width": size[0], "height": size[1], "preparation": "verbatim copy",
    })

    with Image.open(SRC) as im:
        for pid, box in PANELS.items():
            crop = im.crop(box)
            panel_dir = OUT / "panels" / pid.lower()
            panel_dir.mkdir(parents=True, exist_ok=True)
            crop_path = panel_dir / "source_crop.png"
            crop.save(crop_path)
            rel = f"extracted_figures/MAIN/{pid}.png"
            shutil.copy2(crop_path, OUT / "input" / rel)
            figures.append({"figure_id": pid, "doc_type": "MAIN", "page_number": 7, "caption": ""})
            assets.append({
                "asset_id": f"ASSET_{pid}", "doc_type": "MAIN", "asset_type": "figure",
                "relative_path": rel, "sha256": sha(OUT / "input" / rel),
                "extraction_method": "agent_visual_crop_preparation", "page_number": 7,
                "figure_id": pid, "caption": "",
            })
            inventory.append({
                "panel_id": pid, "box_px": json.dumps(box),
                "crop_file": str(crop_path.relative_to(OUT)),
                "width": crop.width, "height": crop.height,
                "preparation": "Agent visual crop only; no labels/anchors/points supplied",
            })

    with (OUT / "panel_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(inventory[0].keys()))
        w.writeheader(); w.writerows(inventory)

    evidence = {
        "package_version": "1.1.0",
        "paper_id": "single-figure-p7-05",
        "metadata": {
            "doi": "10.1002/adfm.75805",
            "note": "Single-image controlled test. 6 subpanel crops are Agent visual image "
                    "preparation only; no plot_box, axis anchors, curve points or axis labels "
                    "were supplied to the Skill.",
        },
        "inventory": {},
        "figures": figures,
        "media_assets": assets,
    }
    (OUT / "input" / "evidence_index.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "input" / "main_analysis.md").write_text(
        "# Single-image test marker\n\nAdapter discovery marker only. No scientific content.\n",
        encoding="utf-8",
    )
    info = {
        "path": str(SRC), "bytes": SRC.stat().st_size, "sha256_before": before,
        "sha256_after": sha(SRC), "format": fmt, "mode": mode, "size_px": list(size),
        "opened_ok": True, "sha256_unchanged": sha(SRC) == EXPECTED_SHA,
        "panel_crop_boxes_agent_visual": PANELS,
    }
    (OUT / "original" / "source_image_info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
