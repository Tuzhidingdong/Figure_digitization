from __future__ import annotations

from pathlib import Path
from typing import Any


def _finite_points(points):
    output = []
    for point in points:
        try:
            x, y = float(point.x), float(point.y)
        except (TypeError, ValueError, OverflowError):
            continue
        if not (x == x and y == y and abs(x) != float("inf") and abs(y) != float("inf")):
            continue
        output.append((int(point.point_index), x, y, point.pixel_x, point.pixel_y))
    return sorted(output, key=lambda item: item[0])


def _fmt(value: float) -> str:
    return f"{value:.4g}"


def _display_text(value: Any) -> str:
    """Keep the built-in Pillow font from failing on non-Latin axis labels."""
    return str(value).encode("ascii", errors="replace").decode("ascii")


def render_series_artifacts(
    series,
    source_image: Path,
    output_root: Path,
    plot_box: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """Write an independent numeric reconstruction and a pixel-coordinate overlay."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Reconstruction rendering requires Pillow: pip install '.[images]'"
        ) from exc

    points = _finite_points(series.points)
    if len(points) < 2:
        return {"status": "NOT_RENDERED", "reason": "FEWER_THAN_TWO_NUMERIC_POINTS"}
    if any(item[3] is None or item[4] is None for item in points):
        return {"status": "NOT_RENDERED", "reason": "PIXEL_PROVENANCE_INCOMPLETE"}

    output_root.mkdir(parents=True, exist_ok=True)
    safe = "".join(char if char.isalnum() or char in "-_." else "_" for char in series.series_id)
    reconstructed = output_root / f"{safe}_reconstructed.png"
    overlay = output_root / f"{safe}_overlay.png"

    xs = [item[1] for item in points]
    ys = [item[2] for item in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax <= xmin or ymax <= ymin:
        return {"status": "NOT_RENDERED", "reason": "DEGENERATE_NUMERIC_RANGE"}
    xpad = (xmax - xmin) * 0.04
    ypad = (ymax - ymin) * 0.06
    xmin, xmax = xmin - xpad, xmax + xpad
    ymin, ymax = ymin - ypad, ymax + ypad

    width, height = 1000, 720
    left, top, right, bottom = 120, 55, 45, 110
    plot_width, plot_height = width - left - right, height - top - bottom
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    x0, y0, x1, y1 = left, top, width - right, height - bottom
    draw.line((x0, y0, x0, y1, x1, y1), fill=(25, 25, 25), width=3)

    for index in range(6):
        fraction = index / 5
        tx = x0 + fraction * plot_width
        ty = y1 - fraction * plot_height
        xvalue = xmin + fraction * (xmax - xmin)
        yvalue = ymin + fraction * (ymax - ymin)
        draw.line((tx, y1, tx, y1 + 7), fill=(25, 25, 25), width=2)
        draw.line((x0 - 7, ty, x0, ty), fill=(25, 25, 25), width=2)
        draw.text((tx - 18, y1 + 15), _fmt(xvalue), fill=(20, 20, 20), font=font)
        draw.text((x0 - 78, ty - 5), _fmt(yvalue), fill=(20, 20, 20), font=font)

    def map_x(value):
        return x0 + (value - xmin) / (xmax - xmin) * plot_width

    def map_y(value):
        return y1 - (value - ymin) / (ymax - ymin) * plot_height

    coords = [(map_x(item[1]), map_y(item[2])) for item in points]
    color = (205, 45, 65)
    draw.line(coords, fill=color, width=3, joint="curve")
    for px, py in coords:
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color)

    x_label = _display_text(series.x_label or "X")
    y_label = _display_text(series.y_label or "Y")
    if series.x_unit:
        x_label = f"{x_label} ({series.x_unit})"
    if series.y_unit:
        y_label = f"{y_label} ({series.y_unit})"
    draw.text((left + plot_width // 2 - 100, height - 42), x_label, fill=(20, 20, 20), font=font)
    draw.text((12, top + plot_height // 2), y_label, fill=(20, 20, 20), font=font)
    draw.text((left, 15), _display_text(f"Digitized reconstruction - {series.label or series.series_id}"),
              fill=(20, 20, 20), font=font)
    image.save(reconstructed, format="PNG")

    with Image.open(source_image) as source:
        original = source.convert("RGB")
        overlay_draw = ImageDraw.Draw(original)
        pixel_coords = [(float(item[3]), float(item[4])) for item in points]
        overlay_draw.line(pixel_coords, fill=(0, 190, 80), width=2)
        radius = 3
        for px, py in pixel_coords:
            overlay_draw.ellipse((px-radius, py-radius, px+radius, py+radius),
                                 outline=(0, 120, 50), width=2)
        if plot_box:
            overlay_draw.rectangle(tuple(int(v) for v in plot_box), outline=(30, 100, 240), width=2)
        original.save(overlay, format="PNG")

    return {
        "status": "RENDERED",
        "reconstructed_path": reconstructed.as_posix(),
        "overlay_path": overlay.as_posix(),
        "point_count": len(points),
        "point_order": "PRESERVED",
        "source_image_sha256": series.evidence[0].get("source_image_sha256")
        if series.evidence else None,
    }


def build_panel_comparison_sheet(items: list[dict], output_path: Path) -> dict[str, Any]:
    """Create an all-panels contact sheet; missing reconstructions are explicit."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError(
            "Comparison-sheet rendering requires Pillow: pip install '.[images]'"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    column_widths = (420, 420, 260)
    header_height, row_height = 42, 250
    total_width = sum(column_widths)
    total_height = header_height + max(1, len(items)) * row_height
    sheet = Image.new("RGB", (total_width, total_height), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), "Original panel", fill=(20, 20, 20), font=font)
    draw.text((column_widths[0] + 12, 12), "Independent reconstruction", fill=(20, 20, 20), font=font)
    draw.text((sum(column_widths[:2]) + 12, 12), "Automatic result", fill=(20, 20, 20), font=font)

    for index, item in enumerate(items):
        top = header_height + index * row_height
        sources = (item.get("original_path"), item.get("reconstructed_path"))
        for column, source_path in enumerate(sources):
            x = sum(column_widths[:column])
            draw.rectangle((x, top, x + column_widths[column] - 1, top + row_height - 1),
                           outline=(205, 205, 205), width=1)
            if source_path and Path(source_path).is_file():
                with Image.open(source_path) as source:
                    thumb = ImageOps.contain(source.convert("RGB"),
                                             (column_widths[column] - 16, row_height - 40))
                    sheet.paste(thumb, (x + 8, top + 28))
            else:
                draw.text((x + 16, top + 95), "NO AUTOMATIC DATA / NO PLOT",
                          fill=(140, 30, 30), font=font)

        third_x = sum(column_widths[:2])
        draw.rectangle((third_x, top, total_width - 1, top + row_height - 1),
                       outline=(205, 205, 205), width=1)
        draw.text((third_x + 12, top + 12), _display_text(item.get("panel_id", f"panel-{index+1}")),
                  fill=(20, 20, 20), font=font)
        draw.text((third_x + 12, top + 42), _display_text(item.get("status", "UNKNOWN")),
                  fill=(20, 20, 20), font=font)
        reason = _display_text(item.get("reason") or "")
        if reason:
            for line_index in range(0, min(len(reason), 180), 36):
                draw.text((third_x + 12, top + 70 + (line_index // 36) * 18),
                          reason[line_index:line_index + 36],
                          fill=(90, 50, 50), font=font)

    sheet.save(output_path, format="PNG")
    return {"status": "WRITTEN", "path": output_path.as_posix(),
            "panel_count": len(items), "image_size": list(sheet.size)}
