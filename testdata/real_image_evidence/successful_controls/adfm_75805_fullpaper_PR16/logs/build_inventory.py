"""Phase A: read-only inventory of the upstream preprocessing package."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(r"E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805")
OUT = Path(__file__).resolve().parent.parent


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    for name in ("logs", "images", "data", "manual_inputs"):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    ea = json.loads((ROOT / "evidence_index.json").read_text(encoding="utf-8"))
    assets = {a["relative_path"]: a for a in ea.get("media_assets", []) if a.get("relative_path")}
    figs = {f["figure_id"]: f for f in ea.get("figures", [])}
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        rec = {
            "relative_path": rel,
            "size_bytes": path.stat().st_size,
            "sha256": sha(path),
            "ext": path.suffix.lower(),
            "width": "",
            "height": "",
            "mode": "",
            "doc_type": "",
            "figure_id": "",
            "asset_id": "",
            "page": "",
            "caption_head": "",
            "role": "",
            "notes": "",
        }
        asset = assets.get(rel)
        if asset:
            rec.update(
                doc_type=asset.get("doc_type", ""),
                figure_id=asset.get("figure_id", ""),
                asset_id=asset.get("asset_id", ""),
                page=asset.get("page_number", ""),
                caption_head=str(asset.get("caption") or "").replace("\n", " ")[:160],
                role=asset.get("asset_type", ""),
            )
        figure = figs.get(rec["figure_id"])
        if figure and not rec["caption_head"]:
            rec["caption_head"] = str(figure.get("caption") or "").replace("\n", " ")[:160]
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            try:
                with Image.open(path) as im:
                    rec["width"], rec["height"], rec["mode"] = im.size[0], im.size[1], im.mode
            except Exception as exc:  # pragma: no cover - diagnostic only
                rec["notes"] = f"UNREADABLE:{type(exc).__name__}"
        rows.append(rec)
    with (OUT / "inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    images = [r for r in rows if r["width"] != ""]
    exts = Counter(r["ext"] for r in rows)
    dups = {
        digest: [r["relative_path"] for r in rows if r["sha256"] == digest]
        for digest, count in Counter(r["sha256"] for r in rows).items()
        if count > 1
    }
    lines = [
        "# Inventory summary — 10.1002_adfm.75805",
        "",
        f"- total files: {len(rows)}",
        "",
        "## extensions",
        "",
    ]
    lines += [f"- {k}: {v}" for k, v in sorted(exts.items())]
    lines += ["", f"## images: {len(images)}", ""]
    for row in images:
        lines.append(
            f"- {row['relative_path']} | {row['width']}x{row['height']} {row['mode']} | "
            f"figure={row['figure_id'] or '-'} page={row['page'] or '-'} | sha={row['sha256'][:12]}"
        )
    lines += ["", "## duplicate hashes", ""]
    for digest, paths in dups.items():
        lines.append(f"- {digest[:16]}: {paths}")
    if not dups:
        lines.append("- none")
    lines += [
        "",
        "## notes",
        "- P8_06 strip is 1549x89 (previously diagnosed as likely mis-crop).",
        "- SI figure composites are page-level, not uniquely associated to individual figures by upstream data.",
    ]
    (OUT / "inventory_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"files={len(rows)} images={len(images)} duplicate_hash_groups={len(dups)}")


if __name__ == "__main__":
    main()
