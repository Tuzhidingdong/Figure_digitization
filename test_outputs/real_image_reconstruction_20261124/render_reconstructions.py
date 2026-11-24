"""Render reconstructions, overlays and side-by-side sheets from extracted points.

All plotted values come from the per-panel ``panel_series.csv`` files produced by
the extraction run in ``extraction/``.  Nothing is interpolated, smoothed or
invented.  Series whose Y axis is UNASSIGNED are never given physical values.
"""

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
EXTRACT = RUN_DIR / "extraction"
PROJECT = RUN_DIR.parents[1]
FIXTURES = PROJECT / "tests" / "fixtures" / "real_figures"

CASES = {
    "P3_02": {
        "source": FIXTURES / "P3_02.png",
        "paper_dir": EXTRACT / "P3_02" / "output" / "papers" / "paper-p3-real__01_preprocessing",
    },
    "P8_06": {
        "source": FIXTURES / "P8_06.png",
        "paper_dir": EXTRACT / "P8_06" / "output" / "papers" / "paper-p8-real",
    },
}


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_case(case: str) -> dict:
    cfg = CASES[case]
    paper_dir: Path = cfg["paper_dir"]
    digitization = json.loads((paper_dir / "digitization.json").read_text(encoding="utf-8"))
    layout = json.loads((paper_dir / "panel_layout.json").read_text(encoding="utf-8"))
    series_meta = {row["series_id"]: row for row in digitization["series"]}
    panels = {row["panel_id"]: row for row in layout.get("panels", [])}

    series = OrderedDict()
    for csv_path in sorted(paper_dir.glob("series/*/panel_series.csv")):
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        grouped: dict[str, list[dict]] = OrderedDict()
        for row in rows:
            grouped.setdefault(row["series_id"], []).append(row)
        for series_id, points in grouped.items():
            points.sort(key=lambda row: int(row["point_index"]))
            meta = series_meta.get(series_id, {})
            md = meta.get("metadata", {}) or {}
            color = (md.get("color_detection") or {}).get("color_rgb")
            series[series_id] = {
                "series_id": series_id,
                "panel_id": meta.get("panel_id") or points[0].get("panel_id"),
                "points": points,
                "color_rgb": color,
                "y_axis_side": points[0].get("y_axis_side"),
                "y_mapping_status": points[0].get("y_mapping_status"),
                "y_label": meta.get("y_label"),
                "x_label": meta.get("x_label"),
                "plot_box": md.get("plot_box_pixels"),
                "x_calibration": md.get("x_calibration"),
                "y_calibrations": md.get("y_axis_calibrations") or {},
                "points_count": len(points),
            }
    return {
        "case": case,
        "source": cfg["source"],
        "panels": panels,
        "series": series,
        "digitization": digitization,
    }


def short_label(series_id: str) -> str:
    tail = series_id.split("_auto")[-1]
    match = re.match(r"_color_(\d+)(?:_branch_(\d+))?", tail)
    if match:
        text = f"color {int(match.group(1))}"
        if match.group(2):
            text += f" b{int(match.group(2))}"
        return text
    return tail.strip("_")


def rgb(color) -> tuple[float, float, float]:
    if not color:
        return (0.35, 0.35, 0.35)
    return tuple(channel / 255.0 for channel in color)


def numeric_points(points, field):
    out = []
    for row in points:
        raw = row.get(field) or ""
        if raw == "":
            continue
        try:
            out.append((float(row["x_value"]), float(raw)))
        except (TypeError, ValueError):
            continue
    return out


def geometry_points(points):
    out = []
    for row in points:
        try:
            out.append((float(row["pixel_x"]), float(row["pixel_y"])))
        except (TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------------- #
# reconstructed figures
# --------------------------------------------------------------------------- #
def render_p3(case: dict, out_path: Path) -> dict:
    panel_id = "auto-03"
    items = [item for item in case["series"].values() if item["panel_id"] == panel_id]

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 6.8))
    candidate_specs = [
        ("y_left_candidate", "LEFT-axis candidate scale"),
        ("y_right_candidate", "RIGHT-axis candidate scale"),
    ]
    plotted = {"LEFT": 0, "RIGHT": 0, "GEOMETRY": 0}
    for ax, (field, title) in zip(axes[:2], candidate_specs):
        for item in items:
            pts = numeric_points(item["points"], field)
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=rgb(item["color_rgb"]), linewidth=0.9,
                    marker=".", markersize=2.2, alpha=0.85,
                    label=f"{short_label(item['series_id'])} ({len(pts)} pts)")
            plotted["LEFT" if field == "y_left_candidate" else "RIGHT"] += 1
        ax.set_title(f"{title}\n(NOT ASSIGNED - candidate only)", fontsize=9)
        ax.set_xlabel("x from CALIBRATED_NUMERIC x-axis (unit unresolved)", fontsize=8)
        ax.set_ylabel(f"{field} (unit unresolved)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, linewidth=0.3, alpha=0.4)
    for item in items:
        pts = geometry_points(item["points"])
        if not pts:
            continue
        xs, ys = zip(*pts)
        axes[2].plot(xs, ys, color=rgb(item["color_rgb"]), linewidth=0.9,
                     marker=".", markersize=2.2, alpha=0.85,
                     label=f"{short_label(item['series_id'])} ({len(pts)} pts)")
        plotted["GEOMETRY"] += 1
    axes[2].invert_yaxis()
    axes[2].set_title("Pixel geometry (source panel pixels)\nno physical Y implied", fontsize=9)
    axes[2].set_xlabel("pixel_x (panel-local)", fontsize=8)
    axes[2].set_ylabel("pixel_y (panel-local, inverted)", fontsize=8)
    axes[2].tick_params(labelsize=7)
    axes[2].grid(True, linewidth=0.3, alpha=0.4)

    handles = [
        Line2D([0], [0], color=rgb(item["color_rgb"]), linewidth=2,
               label=f"{short_label(item['series_id'])}  [{item['y_axis_side']}]  {len(item['points'])} pts")
        for item in items
    ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.075),
               ncol=6, fontsize=6.8, frameon=False)
    fig.suptitle(
        "P3_02 (10.1002/adma.202001469) panel auto-03 - reconstruction from extracted pixel paths\n"
        "Y axis is UNASSIGNED (AMBIGUOUS_DUAL_Y_AXIS): both candidate scales are shown; neither is a result",
        fontsize=10,
    )
    fig.text(
        0.5, 0.012,
        "All 6 traced series (1100 points) keep measured pixel geometry; y_value is empty for every point (no interpolation or axis choice).\n"
        "Consecutive point_index values alternate between two same-colour curves (pixel_y 163.5 -> 226.5 -> 170.5 at pixel_x 60-62),\n"
        "so each drawn line is the raw extraction order, not a validated single curve.",
        ha="center", fontsize=7.2, color="#444444",
    )
    fig.tight_layout(rect=(0, 0.20, 1, 0.90))
    fig.savefig(out_path, dpi=170)
    plt.close(fig)
    return {"panel": panel_id, "series_plotted": plotted, "path": str(out_path)}


def render_p8(case: dict, out_path: Path) -> dict:
    fig = plt.figure(figsize=(16.5, 6.8))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.18, 1.0], wspace=0.22)

    # --- panel auto-frame-01: single LEFT axis --------------------------------
    ax1 = fig.add_subplot(grid[0, 0])
    items_01 = [s for s in case["series"].values() if s["panel_id"] == "auto-frame-01"]
    handles_01 = []
    for item in items_01:
        pts = numeric_points(item["points"], "y_value")
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax1.plot(xs, ys, color=rgb(item["color_rgb"]), linewidth=1.0,
                 label=f"{short_label(item['series_id'])} ({len(pts)} pts)")
        handles_01.append(Line2D([0], [0], color=rgb(item["color_rgb"]), linewidth=2,
                                 label=f"{short_label(item['series_id'])} [{item['y_axis_side']}] {len(pts)} pts"))
    ax1.set_title("auto-frame-01  (LEFT axis CALIBRATED_NUMERIC; mapping ASSIGNED)", fontsize=9)
    ax1.set_xlabel("x (unit unresolved)", fontsize=8)
    ax1.set_ylabel("LEFT y (unit unresolved)", fontsize=8)
    ax1.tick_params(labelsize=7)
    ax1.grid(True, linewidth=0.3, alpha=0.4)

    # --- panel auto-frame-04: dual axis --------------------------------------
    ax2 = fig.add_subplot(grid[0, 1])
    ax2r = ax2.twinx()
    items_04 = [s for s in case["series"].values() if s["panel_id"] == "auto-frame-04"]
    handles_04 = []
    for item in items_04:
        pts = numeric_points(item["points"], "y_value")
        if not pts:
            continue
        xs, ys = zip(*pts)
        target = ax2 if item["y_axis_side"] == "LEFT" else ax2r
        target.plot(xs, ys, color=rgb(item["color_rgb"]), linewidth=1.0,
                    marker=".", markersize=2.4, alpha=0.9,
                    label=f"{short_label(item['series_id'])} ({len(pts)} pts)")
        handles_04.append(Line2D([0], [0], color=rgb(item["color_rgb"]), linewidth=2,
                                 label=f"{short_label(item['series_id'])} [{item['y_axis_side']}] {len(pts)} pts\n  {item['y_mapping_status']}"))
    ax2.set_title("auto-frame-04  (LEFT + RIGHT both CALIBRATED_NUMERIC)", fontsize=9)
    ax2.set_xlabel("x (unit unresolved)", fontsize=8)
    ax2.set_ylabel("LEFT y (unit unresolved)", fontsize=8)
    ax2r.set_ylabel("RIGHT y (unit unresolved)", fontsize=8)
    ax2.tick_params(labelsize=7)
    ax2r.tick_params(labelsize=7)
    ax2.grid(True, linewidth=0.3, alpha=0.4)

    fig.legend(handles=handles_01 + handles_04, loc="lower center",
               bbox_to_anchor=(0.5, 0.145), ncol=4, fontsize=7, frameon=False)
    fig.suptitle(
        "P8_06 (10.1002/adma.202404834) reconstruction from extracted pixel paths\n"
        "Panels auto-frame-02 and auto-frame-03 produced 0 traced points and are not drawn",
        fontsize=10,
    )
    fig.text(
        0.5, 0.012,
        "auto-frame-04 red branches are LEFT by ASSIGNED_BY_DUAL_AXIS_EXCLUSION (weaker evidence); the blue series is RIGHT by "
        "COLOR_MATCHED_TO_Y_AXIS_TEXT. Units remain unresolved. The two isolated excursions to ~2.2 V and ~2.6 V in auto-frame-01\n"
        "coincide with red dashed annotation rectangles in the source image, i.e. annotation pixels were traced as data.",
        ha="center", fontsize=7.2, color="#444444",
    )
    fig.subplots_adjust(top=0.85, bottom=0.27, left=0.055, right=0.945, wspace=0.30)
    fig.savefig(out_path, dpi=170)
    plt.close(fig)
    return {
        "panel_01_series": len([i for i in items_01 if i["points_count"]]),
        "panel_04_series": len([i for i in items_04 if i["points_count"]]),
        "path": str(out_path),
    }


# --------------------------------------------------------------------------- #
# overlay on the unmodified original
# --------------------------------------------------------------------------- #
def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def draw_dashed_rect(draw, box, color, width=1, dash=6):
    x0, y0, x1, y1 = box
    for x in range(x0, x1, dash * 2):
        draw.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=width)
        draw.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=width)
    for y in range(y0, y1, dash * 2):
        draw.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=width)
        draw.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=width)


def render_overlay(case: dict, out_path: Path) -> dict:
    source = Image.open(case["source"]).convert("RGB")
    overlay = Image.new("RGBA", source.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    panel_box_layer = Image.new("RGBA", source.size, (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel_box_layer)

    marker_total = 0
    for item in case["series"].values():
        if not item["points"]:
            continue
        panel = case["panels"].get(item["panel_id"], {})
        bbox = panel.get("bbox")
        if not bbox:
            continue
        ox, oy = bbox[0], bbox[1]
        if item["plot_box"]:
            pb = item["plot_box"]
            draw_dashed_rect(pdraw, (ox + pb[0], oy + pb[1], ox + pb[2], oy + pb[3]),
                             (0, 90, 200, 200), width=1, dash=5)
        pts = geometry_points(item["points"])
        if not pts:
            continue
        step = max(1, len(pts) // 130)
        colour = tuple(item["color_rgb"] or [40, 40, 40])
        for index, (px, py) in enumerate(pts):
            if index % step:
                continue
            x, y = ox + px, oy + py
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=colour + (150,),
                         outline=(20, 20, 20, 235), width=1)
            marker_total += 1

    for panel_id, panel in case["panels"].items():
        bbox = panel.get("bbox")
        if not bbox:
            continue
        draw_dashed_rect(pdraw, tuple(bbox), (90, 90, 90, 170), width=1, dash=8)

    composed = Image.alpha_composite(source.convert("RGBA"), panel_box_layer)
    composed = Image.alpha_composite(composed, overlay)

    # legend strip below the untouched figure area
    lines = []
    for item in case["series"].values():
        if not item["points"]:
            continue
        lines.append((
            tuple(item["color_rgb"] or [40, 40, 40]),
            f"{item['panel_id']} / {short_label(item['series_id'])}  |  {item['points_count']} pts  |  "
            f"Y {item['y_axis_side']}  |  {item['y_mapping_status']}",
        ))
    lines.append(((120, 120, 120), "dashed grey = panel bbox; dashed blue = detected plot box; "
                                   "markers = extracted pixel geometry (no physical values implied)"))
    line_height = 17
    strip_height = 26 + line_height * len(lines)
    canvas = Image.new("RGB", (source.width, source.height + strip_height), "white")
    canvas.paste(composed.convert("RGB"), (0, 0))
    cdraw = ImageDraw.Draw(canvas)
    cdraw.text((8, source.height + 4), "Extracted pixel geometry over the unmodified original",
               fill=(0, 0, 0), font=font(13))
    y = source.height + 22
    for colour, text in lines:
        cdraw.rectangle((10, y + 2, 22, y + 10), fill=colour, outline=(0, 0, 0))
        cdraw.text((28, y), text, fill=(20, 20, 20), font=font(11))
        y += line_height
    canvas.save(out_path)
    return {"markers": marker_total, "path": str(out_path)}


# --------------------------------------------------------------------------- #
# side by side
# --------------------------------------------------------------------------- #
def render_side_by_side(case_name: str, original_path: Path, recon_path: Path,
                        out_path: Path, sha256_hex: str) -> dict:
    original = Image.open(original_path).convert("RGB")
    recon = Image.open(recon_path).convert("RGB")
    target_h = original.height
    scale = target_h / recon.height
    recon = recon.resize((int(recon.width * scale), target_h), Image.LANCZOS)

    margin, header, footer = 18, 40, 46
    width = margin * 3 + original.width + recon.width
    canvas = Image.new("RGB", (width, target_h + header + footer), "white")
    canvas.paste(original, (margin, header))
    canvas.paste(recon, (margin * 2 + original.width, header))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 10), f"{case_name} - LEFT: original (unmodified, SHA256 {sha256_hex[:16]}...)",
              fill=(0, 0, 0), font=font(14))
    draw.text((margin * 2 + original.width, 10),
              "RIGHT: reconstruction from extracted points", fill=(0, 0, 0), font=font(14))
    draw.line([(margin * 2 + original.width - margin // 2, header),
               (margin * 2 + original.width - margin // 2, header + target_h)],
              fill=(170, 170, 170), width=1)
    draw.text((margin, header + target_h + 10),
              "Original pixels are copied unchanged; the reconstruction uses only panel_series.csv values.",
              fill=(70, 70, 70), font=font(11))
    canvas.save(out_path)
    return {"path": str(out_path), "size": canvas.size}


def main() -> None:
    results = {}
    for case_name, cfg in CASES.items():
        case = load_case(case_name)
        source = cfg["source"]
        sha = __import__("hashlib").sha256(source.read_bytes()).hexdigest()

        recon_path = RUN_DIR / f"{case_name}_reconstructed.png"
        if case_name == "P3_02":
            recon_info = render_p3(case, recon_path)
        else:
            recon_info = render_p8(case, recon_path)

        overlay_path = RUN_DIR / f"{case_name}_overlay.png"
        overlay_info = render_overlay(case, overlay_path)

        side_path = RUN_DIR / f"{case_name}_side_by_side.png"
        side_info = render_side_by_side(case_name, source, recon_path, side_path, sha)

        plotted = []
        for item in case["series"].values():
            if not item["points"]:
                continue
            plotted.append({
                "series_id": item["series_id"],
                "panel_id": item["panel_id"],
                "points": item["points_count"],
                "color_rgb": item["color_rgb"],
                "y_axis_side": item["y_axis_side"],
                "y_mapping_status": item["y_mapping_status"],
                "physical_points": len(numeric_points(item["points"], "y_value")),
                "left_candidate_points": len(numeric_points(item["points"], "y_left_candidate")),
                "right_candidate_points": len(numeric_points(item["points"], "y_right_candidate")),
            })
        results[case_name] = {
            "source_image": str(source.resolve()),
            "source_sha256": sha,
            "reconstruction": recon_info,
            "overlay": overlay_info,
            "side_by_side": side_info,
            "plotted_series": plotted,
        }

    (RUN_DIR / "reconstruction_manifest.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    for case_name, info in results.items():
        print(f"[{case_name}] source: {info['source_image']}")
        print(f"[{case_name}] sha256: {info['source_sha256']}")
        for key in ("reconstruction", "overlay", "side_by_side"):
            path = Path(info[key]["path"]).resolve()
            print(f"[{case_name}] {key}: {path} exists={path.is_file()} bytes={path.stat().st_size if path.is_file() else 0}")


if __name__ == "__main__":
    main()
