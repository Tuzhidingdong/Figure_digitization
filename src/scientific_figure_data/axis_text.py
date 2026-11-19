from __future__ import annotations

import math
import re
from typing import Any

NUMBER_RE = re.compile(
    r"^[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?$"
)


def _box_center(polygon: Any) -> tuple[float, float] | None:
    try:
        points = [(float(point[0]), float(point[1])) for point in polygon]
    except (TypeError, ValueError, IndexError):
        return None
    if len(points) < 2:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _parse_numeric(text: str) -> float | None:
    value = text.strip().replace("−", "-").replace("–", "-").replace(" ", "")
    if not NUMBER_RE.fullmatch(value):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _monotonic_anchors(anchors: list[dict]) -> bool:
    if len(anchors) < 2:
        return False
    ordered = sorted(anchors, key=lambda item: item["pixel"])
    pixels = [item["pixel"] for item in ordered]
    values = [item["value"] for item in ordered]
    if len(set(round(value, 5) for value in pixels)) < 2:
        return False
    differences = [b - a for a, b in zip(values, values[1:])]
    differences = [value for value in differences if abs(value) > 1e-9]
    if not differences:
        return False
    direction = 1 if differences[0] > 0 else -1
    return all(direction * value >= -1e-9 for value in differences)


def extract_numeric_axis_anchors(
    ocr_rows: list[dict],
    plot_box: tuple[float, float, float, float],
    *,
    min_confidence: float = 0.90,
    margin_fraction: float = 0.22,
    min_margin_pixels: float = 8.0,
) -> dict:
    """Extract only numeric tick candidates outside an explicit plot box.

    The method never pairs arbitrary numbers from inside the chart. OCR text
    must lie in a bottom (X) or left/right (Y) margin and the resulting values
    must be monotonic in pixel order. Returned anchors remain provisional.
    """
    x0, y0, x1, y1 = [float(value) for value in plot_box]
    if x1 <= x0 or y1 <= y0:
        raise ValueError("plot_box must have positive width and height")
    margin_x = max(min_margin_pixels, (x1 - x0) * margin_fraction)
    margin_y = max(min_margin_pixels, (y1 - y0) * margin_fraction)
    x_candidates = []
    y_left_candidates = []
    y_right_candidates = []
    evidence = []

    for row in ocr_rows:
        confidence = float(row.get("confidence", 0.0) or 0.0)
        text = str(row.get("text", "")).strip()
        value = _parse_numeric(text)
        center = _box_center(row.get("polygon"))
        if confidence < min_confidence or value is None or center is None:
            continue
        cx, cy = center
        item = {
            "text": text, "value": value, "pixel_x": cx, "pixel_y": cy,
            "confidence": confidence, "polygon": row.get("polygon"),
        }
        if x0 <= cx <= x1 and y1 < cy <= y1 + margin_y:
            x_candidates.append({"pixel": cx, "value": value, "evidence": item})
        elif x0 - margin_x <= cx <= x0 and y0 - margin_y <= cy <= y1 + margin_y:
            y_left_candidates.append({"pixel": cy, "value": value, "evidence": item})
        elif x1 <= cx <= x1 + margin_x and y0 - margin_y <= cy <= y1 + margin_y:
            y_right_candidates.append({"pixel": cy, "value": value, "evidence": item})
        else:
            continue
        evidence.append(item)

    def normalize(items):
        by_pixel = {}
        for item in items:
            key = round(item["pixel"], 1)
            current = by_pixel.get(key)
            if current is None or item["evidence"]["confidence"] > current["evidence"]["confidence"]:
                by_pixel[key] = item
        values = list(by_pixel.values())
        return sorted(values, key=lambda item: item["pixel"])

    x_values = normalize(x_candidates)
    y_left = normalize(y_left_candidates)
    y_right = normalize(y_right_candidates)

    x_anchors = [{"pixel": item["pixel"], "value": item["value"]} for item in x_values]
    y_left_anchors = [{"pixel": item["pixel"], "value": item["value"]} for item in y_left]
    y_right_anchors = [{"pixel": item["pixel"], "value": item["value"]} for item in y_right]

    if not _monotonic_anchors(x_anchors):
        x_anchors = []
    if not _monotonic_anchors(y_left_anchors):
        y_left_anchors = []
    if not _monotonic_anchors(y_right_anchors):
        y_right_anchors = []

    return {
        "x_anchors": x_anchors,
        "y_left_anchors": y_left_anchors,
        "y_right_anchors": y_right_anchors,
        "x_evidence": [item["evidence"] for item in x_values] if x_anchors else [],
        "y_left_evidence": [item["evidence"] for item in y_left] if y_left_anchors else [],
        "y_right_evidence": [item["evidence"] for item in y_right] if y_right_anchors else [],
        "status": "NUMERIC_TICKS_CANDIDATES_FOUND" if x_anchors or y_left_anchors or y_right_anchors
                  else "NO_CONFIDENT_NUMERIC_TICKS",
        "min_confidence": min_confidence,
        "provisional": True,
    }


def extract_native_numeric_axis_anchors(
    native_page: dict,
    plot_bbox_pdf: tuple[float, float, float, float],
    crop_mapping: dict,
    *,
    margin_fraction: float = 0.22,
    min_margin_pdf_points: float = 4.0,
) -> dict:
    """Read numeric tick labels directly from PDF text objects without OCR."""
    x0, y0, x1, y1 = [float(value) for value in plot_bbox_pdf]
    if x1 <= x0 or y1 <= y0:
        raise ValueError("plot_bbox_pdf must have positive width and height")
    margin_x = max(min_margin_pdf_points, (x1 - x0) * margin_fraction)
    margin_y = max(min_margin_pdf_points, (y1 - y0) * margin_fraction)
    crop_left = float(crop_mapping["crop_left_pdf"])
    crop_top = float(crop_mapping["crop_top_pdf"])
    render_scale = float(crop_mapping["render_scale"])
    if render_scale <= 0:
        raise ValueError("crop_mapping render_scale must be positive")

    x_candidates = []
    y_left_candidates = []
    y_right_candidates = []
    for obj in native_page.get("objects", []):
        if obj.get("object_type") != "TEXT":
            continue
        value = _parse_numeric(str(obj.get("text", "")))
        bounds = obj.get("bounds_pdf")
        if value is None or not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            continue
        left, bottom, right, top = [float(item) for item in bounds]
        cx = (left + right) / 2
        cy = (bottom + top) / 2
        evidence = {
            "object_index": obj.get("object_index"),
            "text": str(obj.get("text", "")),
            "value": value,
            "bounds_pdf": list(bounds),
            "font_size_pdf": obj.get("font_size"),
            "font_name": obj.get("font_name"),
        }
        if x0 <= cx <= x1 and y0 - margin_y <= cy < y0:
            x_candidates.append({
                "pixel": (cx - crop_left) * render_scale,
                "value": value, "evidence": evidence,
            })
        elif x0 - margin_x <= cx < x0 and y0 <= cy <= y1:
            y_left_candidates.append({
                "pixel": (crop_top - cy) * render_scale,
                "value": value, "evidence": evidence,
            })
        elif x1 < cx <= x1 + margin_x and y0 <= cy <= y1:
            y_right_candidates.append({
                "pixel": (crop_top - cy) * render_scale,
                "value": value, "evidence": evidence,
            })

    def normalize(items):
        by_pixel = {}
        for item in items:
            key = round(item["pixel"], 1)
            current = by_pixel.get(key)
            if current is None:
                by_pixel[key] = item
            else:
                current_text_len = len(current["evidence"]["text"])
                new_text_len = len(item["evidence"]["text"])
                if new_text_len > current_text_len:
                    by_pixel[key] = item
        return sorted(by_pixel.values(), key=lambda item: item["pixel"])

    x_values = normalize(x_candidates)
    y_left = normalize(y_left_candidates)
    y_right = normalize(y_right_candidates)
    x_anchors = [{"pixel": item["pixel"], "value": item["value"]} for item in x_values]
    y_left_anchors = [{"pixel": item["pixel"], "value": item["value"]} for item in y_left]
    y_right_anchors = [{"pixel": item["pixel"], "value": item["value"]} for item in y_right]
    if not _monotonic_anchors(x_anchors):
        x_anchors = []
    if not _monotonic_anchors(y_left_anchors):
        y_left_anchors = []
    if not _monotonic_anchors(y_right_anchors):
        y_right_anchors = []
    return {
        "x_anchors": x_anchors,
        "y_left_anchors": y_left_anchors,
        "y_right_anchors": y_right_anchors,
        "x_evidence": [item["evidence"] for item in x_values] if x_anchors else [],
        "y_left_evidence": [item["evidence"] for item in y_left] if y_left_anchors else [],
        "y_right_evidence": [item["evidence"] for item in y_right] if y_right_anchors else [],
        "status": "NATIVE_NUMERIC_TICKS_FOUND" if x_anchors or y_left_anchors or y_right_anchors
                  else "NO_NATIVE_NUMERIC_TICKS",
        "source": "PDF_NATIVE_TEXT",
        "provisional": True,
    }
