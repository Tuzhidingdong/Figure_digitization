from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any


def _box(width: int, height: int, values: tuple[float, float, float, float]):
    values = [float(v) for v in values]
    if max(abs(v) for v in values) <= 1.01:
        values[0] *= width
        values[2] *= width
        values[1] *= height
        values[3] *= height
    x0, y0, x1, y1 = (int(round(v)) for v in values)
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def _mask(pixels, threshold: float, edge_fraction: float):
    import numpy as np
    background = np.percentile(pixels.reshape(-1, 3).astype(float), 92, axis=0)
    contrast = np.sqrt(np.mean((pixels.astype(float) - background) ** 2, axis=2))
    mask = contrast >= threshold
    h, w = mask.shape
    edge = max(1, round(min(h, w) * edge_fraction))
    mask[:edge] = False
    mask[-edge:] = False
    mask[:, :edge] = False
    mask[:, -edge:] = False
    return background, contrast, mask


def _column_nodes(pixels, contrast, mask, x0: int, y0: int,
                  max_runs: int, max_height: int):
    import numpy as np
    nodes: list[dict[str, Any]] = []
    for local_x in range(mask.shape[1]):
        rows = np.flatnonzero(mask[:, local_x])
        if not rows.size:
            continue
        splits = np.flatnonzero(np.diff(rows) > 1) + 1
        column = []
        for run in np.split(rows, splits):
            if run.size > max_height:
                continue
            values = contrast[run, local_x]
            peak = int(np.argmax(values))
            y = int(run[peak])
            width = int(run.size)
            mean_score = float(np.mean(values))
            reward = (0.30 + min(1.50, mean_score / 42.0)
                      + min(0.18, 0.06 * (width - 1))
                      - max(0, width - 5) * 0.10)
            if reward <= 0:
                continue
            column.append({
                "x": local_x + x0, "y": y + y0, "width": width,
                "rgb": [int(v) for v in pixels[y, local_x]],
                "contrast": mean_score, "peak_contrast": float(values[peak]),
                "reward": reward,
            })
        column.sort(key=lambda node: (-node["reward"], node["y"], node["width"]))
        nodes.extend(column[:max_runs])
    return nodes


def _best_path(nodes: list[dict], *, max_gap: int, max_slope: float,
               slope_step: float, max_slope_change: float,
               curve_cost: float, gap_cost: float, color_cost: float,
               width_cost: float, start_cost: float):
    import math
    import numpy as np
    from bisect import bisect_left
    if not nodes:
        return [], 0.0
    nodes = sorted(nodes, key=lambda n: (n["x"], n["y"]))
    xs = [int(n["x"]) for n in nodes]
    slopes = np.arange(-max_slope, max_slope + slope_step * 0.5, slope_step)
    count = int(slopes.size)
    none = count
    scores = np.full((len(nodes), count + 1), -np.inf)
    prev_node = np.full((len(nodes), count + 1), -1, dtype=np.int32)
    prev_state = np.full((len(nodes), count + 1), -1, dtype=np.int16)
    for i, current in enumerate(nodes):
        scores[i, none] = current["reward"] - start_cost
        first = bisect_left(xs, current["x"] - max_gap - 1, 0, i)
        for j in range(first, i):
            previous = nodes[j]
            dx = current["x"] - previous["x"]
            if dx < 1 or dx > max_gap + 1:
                continue
            slope = (current["y"] - previous["y"]) / dx
            if abs(slope) > max_slope:
                continue
            si = max(0, min(count - 1, round((slope - slopes[0]) / slope_step)))
            qs = float(slopes[si])
            if abs(slope - qs) > slope_step * 0.75:
                continue
            color_delta = math.sqrt(sum(
                (current["rgb"][k] - previous["rgb"][k]) ** 2 for k in range(3)
            ) / 3) / 255
            width_delta = abs(current["width"] - previous["width"]) / max(
                1, current["width"], previous["width"]
            )
            base = gap_cost * (dx - 1) + color_cost * color_delta + width_cost * width_delta
            transition = curve_cost * np.abs(slopes - qs)
            valid = np.abs(slopes - qs) <= max_slope_change
            candidates = np.where(valid, scores[j, :count] - transition, -np.inf)
            state = int(np.argmax(candidates))
            value = float(candidates[state])
            if scores[j, none] > value:
                state, value = none, float(scores[j, none])
            candidate = value - base + current["reward"]
            if candidate > scores[i, si]:
                scores[i, si] = candidate
                prev_node[i, si] = j
                prev_state[i, si] = state
    end_node, end_state = np.unravel_index(int(np.argmax(scores)), scores.shape)
    best_score = float(scores[end_node, end_state])
    indices, seen = [], set()
    i, state = int(end_node), int(end_state)
    while i >= 0 and (i, state) not in seen:
        seen.add((i, state))
        indices.append(i)
        i, state = int(prev_node[i, state]), int(prev_state[i, state])
    indices.reverse()
    return [nodes[i] for i in indices], best_score


def _stats(path: list[dict], plot_width: int):
    import math
    import statistics
    path = sorted(path, key=lambda n: n["x"])
    xs, ys = [n["x"] for n in path], [n["y"] for n in path]
    widths = [n["width"] for n in path]
    gaps = [max(0, xs[i] - xs[i - 1] - 1) for i in range(1, len(xs))]
    lengths, current = [], 1
    for gap in gaps:
        if gap:
            lengths.append(current)
            current = 1
        else:
            current += 1
    lengths.append(current)
    positive_gaps = [g for g in gaps if g]
    gap_cv = (statistics.pstdev(positive_gaps) / statistics.mean(positive_gaps)
              if len(positive_gaps) > 1 else None)
    length_cv = (statistics.pstdev(lengths) / statistics.mean(lengths)
                 if len(lengths) > 1 else None)
    slopes = [(ys[i] - ys[i - 1]) / max(1, xs[i] - xs[i - 1])
              for i in range(1, len(xs))]
    curv = [abs(slopes[i] - slopes[i - 1]) for i in range(1, len(slopes))]
    median_curv = statistics.median(curv) if curv else 0.0
    mean_width = statistics.mean(widths)
    width_cv = statistics.pstdev(widths) / mean_width if mean_width else 0.0
    segments = len(lengths)
    dashed = (segments >= 3 and gap_cv is not None and length_cv is not None
              and gap_cv <= 0.75 and length_cv <= 0.75)
    small_gaps = (segments <= 3 and len(positive_gaps) <= 2
                  and (not positive_gaps or max(positive_gaps) <= max(2, round(plot_width * .02))))
    style = ("DASHED_CANDIDATE" if dashed else
             "SOLID_CANDIDATE" if segments == 1 else
             "SOLID_WITH_OCCLUSION_CANDIDATE" if small_gaps else
             "DISCONTINUOUS_UNRESOLVED")
    x_span = max(1, xs[-1] - xs[0] + 1)
    active = len(set(xs)) / x_span
    coverage = x_span / max(1, plot_width)
    rgb_median = [statistics.median(n["rgb"][k] for n in path) for k in range(3)]
    color_spread = statistics.median(
        math.sqrt(sum((n["rgb"][k] - rgb_median[k]) ** 2 for k in range(3)) / 3) / 255
        for n in path
    )
    confidence = (0.28 * min(1, coverage / .65)
                  + 0.24 * min(1, active / (.58 if dashed else .90))
                  + 0.24 * math.exp(-median_curv / 1.25)
                  + 0.14 * math.exp(-color_spread / .12)
                  + 0.10 * math.exp(-max(0, width_cv - .20)))
    return {
        "point_count": len(path), "segment_count": segments,
        "segment_lengths_columns": lengths, "gap_lengths_columns": positive_gaps,
        "gap_cv": round(gap_cv, 4) if gap_cv is not None else None,
        "segment_length_cv": round(length_cv, 4) if length_cv is not None else None,
        "x_range": [xs[0], xs[-1]], "y_range": [min(ys), max(ys)],
        "x_coverage_fraction": round(coverage, 4),
        "active_column_fraction": round(active, 4),
        "median_abs_curvature": round(median_curv, 4),
        "median_run_width": round(statistics.median(widths), 3),
        "run_width_cv": round(width_cv, 4),
        "line_style_candidate": style, "confidence": round(confidence, 4),
    }


def detect_monotonic_raster_trajectories(
    image_path: str | Path, plot_box: tuple[float, float, float, float], *,
    max_tracks: int = 12, max_gap_columns: int = 12, max_abs_slope: float = 6.0,
    slope_step: float = 0.5, min_contrast: float = 12.0, max_run_height: int = 12,
    max_nodes_per_column: int = 16, min_x_coverage: float = 0.25,
    min_active_columns: int = 48, min_active_fraction: float = 0.20,
    start_penalty: float = 4.0, max_slope_change: float = 1.5,
    curvature_penalty: float = 0.32, gap_penalty: float = 0.10,
    color_penalty: float = 2.4, width_penalty: float = 0.30,
    boundary_exclusion_fraction: float = 0.012,
    max_candidate_pixels: int = 250_000,
) -> dict:
    """Discover review-only trajectories from original pixels, not components."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError("Install Pillow and NumPy with the images extra.") from exc
    path = Path(image_path)
    if not path.is_file():
        return {"status": "NEEDS_REVIEW", "reason": "SOURCE_IMAGE_UNAVAILABLE", "tracks": []}
    with Image.open(path) as source:
        image_width, image_height = source.size
        x0, y0, x1, y1 = _box(image_width, image_height, plot_box)
        if x1 <= x0 or y1 <= y0:
            return {"status": "NEEDS_REVIEW", "reason": "INVALID_PLOT_BOX", "tracks": []}
        pixels = np.asarray(source.convert("RGB").crop((x0, y0, x1, y1)), dtype=np.uint8)
    region_height, region_width = pixels.shape[:2]
    if region_width < 32 or region_height < 16:
        return {"status": "NEEDS_REVIEW", "reason": "PLOT_BOX_TOO_SMALL", "tracks": []}
    background, contrast, mask = _mask(pixels, min_contrast, boundary_exclusion_fraction)
    candidate_count = int(mask.sum())
    if candidate_count > max_candidate_pixels:
        return {"status": "NEEDS_REVIEW", "reason": "CANDIDATE_PIXEL_BUDGET_EXCEEDED",
                "candidate_pixel_count": candidate_count, "tracks": []}
    if candidate_count < min_active_columns:
        return {"status": "NO_TRAJECTORY_CANDIDATES",
                "reason": "INSUFFICIENT_CONTRAST_PIXELS", "tracks": []}
    nodes = _column_nodes(pixels, contrast, mask, x0, y0,
                          max_nodes_per_column, max_run_height)
    remaining = list(nodes)
    tracks, rejected = [], []
    minimum_nodes = max(min_active_columns, round(region_width * .18))
    for track_index in range(max_tracks):
        if not remaining:
            break
        path, score = _best_path(
            remaining, max_gap=max_gap_columns, max_slope=max_abs_slope,
            slope_step=slope_step, max_slope_change=max_slope_change,
            curve_cost=curvature_penalty, gap_cost=gap_penalty,
            color_cost=color_penalty, width_cost=width_penalty,
            start_cost=start_penalty,
        )
        if not path:
            break
        stats = _stats(path, region_width)
        eligible = (
            len(path) >= minimum_nodes
            and stats["x_coverage_fraction"] >= min_x_coverage
            and stats["active_column_fraction"] >= min_active_fraction
            and stats["median_run_width"] <= max(8.0, max_run_height * .70)
            and stats["median_abs_curvature"] <= 1.6
            and score >= max(8.0, len(path) * .08)
        )
        segments, segment, previous_x = [], [], None
        for node in path:
            point = [int(node["x"]), int(node["y"])]
            if previous_x is not None and node["x"] > previous_x + 1:
                if segment:
                    segments.append(segment)
                segment = []
            segment.append(point)
            previous_x = node["x"]
        if segment:
            segments.append(segment)
        record = {
            "track_id": f"TR{track_index + 1:02d}",
            "status": "CANDIDATE_REVIEW" if eligible else "REJECTED_WEAK_PATH",
            "eligible_for_review": bool(eligible), "path_score": round(float(score), 4),
            "median_source_rgb": [
                int(round(float(np.median([n["rgb"][k] for n in path]))))
                for k in range(3)
            ],
            **stats,
            "segments": segments,
            "point_records": [
                {"pixel_x": int(n["x"]), "pixel_y": int(n["y"]),
                 "source_rgb": n["rgb"], "source_run_width": n["width"],
                 "mean_contrast": float(n["contrast"]),
                 "peak_contrast": float(n["peak_contrast"])}
                for n in path
            ],
            "source_points_are_mask_members": all(
                mask[int(n["y"] - y0), int(n["x"] - x0)] for n in path
            ),
            "source_pixel_policy": "ONE_REAL_SOURCE_PIXEL_PER_ACTIVE_COLUMN",
        }
        record["segment_count"] = len(segments)
        record["point_count"] = sum(len(s) for s in segments)
        tracks.append(record)
        if not eligible:
            rejected.append(record["track_id"])
        used = {id(node) for node in path}
        remaining = [node for node in remaining if id(node) not in used]
        if score < max(8.0, minimum_nodes * .08):
            break
    review_count = sum(bool(t["eligible_for_review"]) for t in tracks)
    return {
        "status": "CANDIDATE_TRACKS_FOUND" if review_count else "NO_CONFIDENT_TRAJECTORY_CANDIDATES",
        "method": "COLUMN_RUN_SECOND_ORDER_DYNAMIC_PROGRAMMING",
        "experimental": True, "plot_box": [x0, y0, x1, y1],
        "image_size": [image_width, image_height],
        "estimated_background_rgb": [round(float(v), 2) for v in background],
        "candidate_pixel_count": candidate_count, "candidate_run_count": len(nodes),
        "review_candidate_count": review_count, "rejected_candidate_track_ids": rejected,
        "tracks": tracks,
        "parameters": {
            "max_tracks": max_tracks, "max_gap_columns": max_gap_columns,
            "max_abs_slope": max_abs_slope, "slope_step": slope_step,
            "min_contrast": min_contrast, "max_run_height": max_run_height,
            "max_nodes_per_column": max_nodes_per_column,
            "min_x_coverage": min_x_coverage, "min_active_columns": minimum_nodes,
            "min_active_fraction": min_active_fraction, "start_penalty": start_penalty,
            "max_slope_change": max_slope_change, "curvature_penalty": curvature_penalty,
            "gap_penalty": gap_penalty, "color_penalty": color_penalty,
            "width_penalty": width_penalty,
            "boundary_exclusion_fraction": boundary_exclusion_fraction,
        },
        "source_pixel_integrity": {
            "status": "PASS" if all(t["source_points_are_mask_members"] for t in tracks) else "FAIL",
            "generated_pixels": 0, "interpolated_pixels": 0,
        },
        "note": "Review hypotheses only; not accepted scientific measurements.",
    }


def write_trajectory_artifacts(image_path: str | Path,
                               plot_box: tuple[float, float, float, float],
                               output_dir: str | Path, **options) -> dict:
    """Write offline overlays, point CSV, inventory, and source-pixel diagnostics."""
    import html
    import numpy as np
    from PIL import Image, ImageDraw
    source_path = Path(image_path).resolve()
    output = Path(output_dir).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if output == source_path.parent or source_path.is_relative_to(output):
        raise ValueError("Output directory must not contain or replace the source image")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    result = detect_monotonic_raster_trajectories(source_path, plot_box, **options)
    shutil.copy2(source_path, output / "01_original.png")
    with Image.open(source_path) as src:
        original = src.convert("RGB")
        width, height = original.size
        x0, y0, x1, y1 = _box(width, height, plot_box)
        crop = np.asarray(original.crop((x0, y0, x1, y1)), dtype=np.uint8)
    _, _, local_mask = _mask(
        crop, float(result.get("parameters", {}).get("min_contrast", 12)),
        float(result.get("parameters", {}).get("boundary_exclusion_fraction", .012)),
    )
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y0:y1, x0:x1] = local_mask.astype(np.uint8) * 255
    Image.fromarray(full_mask).save(output / "02_candidate_mask.png")
    palette = [(255, 40, 150), (0, 160, 255), (255, 170, 0), (0, 190, 120),
               (160, 80, 255), (230, 60, 50), (30, 180, 180), (120, 90, 40)]
    combined = original.copy()
    point_fields = ["track_id", "segment_index", "point_index", "pixel_x", "pixel_y",
                    "source_r", "source_g", "source_b", "source_run_width",
                    "mean_contrast", "peak_contrast", "source_pixel_verified"]
    inventory_fields = ["track_id", "status", "eligible_for_review", "point_count",
                        "segment_count", "x_start", "x_end", "y_min", "y_max",
                        "x_coverage_fraction", "active_column_fraction",
                        "line_style_candidate", "confidence", "path_score",
                        "median_source_rgb", "median_run_width", "run_width_cv",
                        "gap_lengths_columns", "segment_lengths_columns"]
    rows = []
    with (output / "all_series_digitized.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=point_fields)
        writer.writeheader()
        for index, track in enumerate(result.get("tracks", [])):
            color = palette[index % len(palette)]
            individual = original.copy()
            segment_map = {
                (int(x), int(y)): sid
                for sid, segment in enumerate(track["segments"]) for x, y in segment
            }
            for point_index, record in enumerate(track["point_records"]):
                x, y = int(record["pixel_x"]), int(record["pixel_y"])
                verified = 0 <= x < width and 0 <= y < height and full_mask[y, x] > 0
                rgb = record["source_rgb"]
                writer.writerow({
                    "track_id": track["track_id"],
                    "segment_index": segment_map.get((x, y), -1),
                    "point_index": point_index, "pixel_x": x, "pixel_y": y,
                    "source_r": rgb[0], "source_g": rgb[1], "source_b": rgb[2],
                    "source_run_width": record["source_run_width"],
                    "mean_contrast": record["mean_contrast"],
                    "peak_contrast": record["peak_contrast"],
                    "source_pixel_verified": verified,
                })
                if verified:
                    ImageDraw.Draw(combined).point((x, y), fill=color)
                    ImageDraw.Draw(individual).point((x, y), fill=color)
            individual.save(output / f"track_{track['track_id']}_overlay.png")
            xr, yr = track["x_range"], track["y_range"]
            rows.append({
                "track_id": track["track_id"], "status": track["status"],
                "eligible_for_review": track["eligible_for_review"],
                "point_count": track["point_count"], "segment_count": track["segment_count"],
                "x_start": xr[0], "x_end": xr[1], "y_min": yr[0], "y_max": yr[1],
                "x_coverage_fraction": track["x_coverage_fraction"],
                "active_column_fraction": track["active_column_fraction"],
                "line_style_candidate": track["line_style_candidate"],
                "confidence": track["confidence"], "path_score": track["path_score"],
                "median_source_rgb": json.dumps(track["median_source_rgb"]),
                "median_run_width": track["median_run_width"],
                "run_width_cv": track["run_width_cv"],
                "gap_lengths_columns": json.dumps(track["gap_lengths_columns"]),
                "segment_lengths_columns": json.dumps(track["segment_lengths_columns"]),
            })
    combined.save(output / "03_reconstructed_trajectories.png")
    combined.save(output / "04_all_series_overlay.png")
    with (output / "trajectory_inventory.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=inventory_fields)
        writer.writeheader()
        writer.writerows(rows)
    result["artifact_summary"] = {
        "output_dir": str(output), "source_image": str(source_path),
        "tracks_written": len(result.get("tracks", [])),
        "review_candidates": result.get("review_candidate_count", 0),
    }
    (output / "trajectory_diagnostics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    images = ["01_original.png", "02_candidate_mask.png",
              "03_reconstructed_trajectories.png", "04_all_series_overlay.png"]
    images += sorted(p.name for p in output.glob("track_TR*_overlay.png"))
    cards = "".join(
        f"<figure><img src='{html.escape(name, quote=True)}' alt='{html.escape(name)}'>"
        f"<figcaption>{html.escape(name)}</figcaption></figure>" for name in images
    )
    table = "".join(
        f"<tr><td>{r['track_id']}</td><td>{r['status']}</td>"
        f"<td>{r['line_style_candidate']}</td><td>{r['point_count']}</td>"
        f"<td>{r['segment_count']}</td><td>{r['x_coverage_fraction']}</td></tr>"
        for r in rows
    )
    document = (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Experimental raster trajectory hypotheses</title>"
        "<style>body{font:15px system-ui,sans-serif;margin:24px;color:#222}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}"
        "figure{margin:0}img{max-width:100%;height:auto;border:1px solid #bbb}"
        "figcaption{margin-top:6px}table{border-collapse:collapse;margin:16px 0}"
        "td,th{border:1px solid #ccc;padding:5px 8px;text-align:left}</style>"
        "<h1>Experimental raster trajectory hypotheses</h1>"
        "<p>Candidate paths only, not accepted scientific measurements. "
        "Every point is a source pixel; no gap interpolation or smoothing.</p>"
        f"<p>Review candidates: {result.get('review_candidate_count', 0)}</p>"
        f"<div class='grid'>{cards}</div><h2>Inventory</h2>"
        "<table><tr><th>ID</th><th>Status</th><th>Style</th><th>Points</th>"
        f"<th>Segments</th><th>X coverage</th></tr>{table}</table>"
        "<p><a href='trajectory_inventory.csv'>Inventory CSV</a> · "
        "<a href='all_series_digitized.csv'>Point CSV</a> · "
        "<a href='trajectory_diagnostics.json'>Diagnostics JSON</a></p></html>"
    )
    (output / "index.html").write_text(document, encoding="utf-8")
    return result
