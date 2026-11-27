from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")

from scientific_figure_data.trajectory import (
    detect_monotonic_raster_trajectories,
    write_trajectory_artifacts,
)

PLOT_BOX = (35, 30, 565, 360)


def _canvas():
    image = Image.new("RGB", (600, 400), "white")
    return image, ImageDraw.Draw(image)


def _dash(draw, fn, color, period=28, length=17):
    for left in range(60, 530, period):
        right = min(left + length, 530)
        draw.line([(x, int(fn(x))) for x in range(left, right)], fill=color, width=3)


def _run(path):
    return detect_monotonic_raster_trajectories(
        path, PLOT_BOX, max_tracks=10, min_active_columns=50
    )


def test_two_solid_traces_are_separated(tmp_path: Path):
    image, draw = _canvas()
    draw.line([(x, int(260 - 150 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(220, 30, 40), width=3)
    draw.line([(x, int(300 - 100 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(110, 110, 110), width=3)
    path = tmp_path / "two_solid.png"
    image.save(path)
    candidates = [t for t in _run(path)["tracks"] if t["eligible_for_review"]]
    assert len(candidates) == 2
    assert all(t["line_style_candidate"] == "SOLID_CANDIDATE" for t in candidates)
    assert all(t["x_coverage_fraction"] >= 0.80 for t in candidates)


def test_solid_and_dashed_paths_keep_real_gaps(tmp_path: Path):
    image, draw = _canvas()
    draw.line([(x, int(260 - 150 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(220, 30, 40), width=3)
    _dash(draw, lambda x: 150 - 50 * (x - 60) / 470, (110, 110, 110))
    path = tmp_path / "solid_dashed.png"
    image.save(path)
    candidates = [t for t in _run(path)["tracks"] if t["eligible_for_review"]]
    assert len(candidates) == 2
    dashed = next(t for t in candidates if t["line_style_candidate"] == "DASHED_CANDIDATE")
    assert dashed["segment_count"] >= 10
    assert dashed["gap_lengths_columns"]


def test_four_mixed_paths_are_independently_traced(tmp_path: Path):
    image, draw = _canvas()
    draw.line([(x, int(260 - 150 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(220, 30, 40), width=3)
    draw.line([(x, int(300 - 100 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(110, 110, 110), width=3)
    _dash(draw, lambda x: 150 - 50 * (x - 60) / 470, (135, 135, 135))
    _dash(draw, lambda x: 180 + 40 * (x - 60) / 470, (160, 160, 160),
          period=30, length=18)
    path = tmp_path / "four_paths.png"
    image.save(path)
    result = _run(path)
    candidates = [t for t in result["tracks"] if t["eligible_for_review"]]
    assert len(candidates) == 4, result
    styles = [t["line_style_candidate"] for t in candidates]
    assert sum(s.startswith("SOLID") for s in styles) == 2
    assert sum(s == "DASHED_CANDIDATE" for s in styles) == 2
    assert all(t["source_points_are_mask_members"] for t in candidates)
    assert result["source_pixel_integrity"]["status"] == "PASS"
    assert result["source_pixel_integrity"]["generated_pixels"] == 0
    assert result["source_pixel_integrity"]["interpolated_pixels"] == 0


def test_crossing_paths_are_not_collapsed(tmp_path: Path):
    image, draw = _canvas()
    draw.line([(x, int(270 - 170 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(220, 30, 40), width=3)
    draw.line([(x, int(80 + 180 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(110, 110, 110), width=3)
    path = tmp_path / "crossing.png"
    image.save(path)
    candidates = [t for t in _run(path)["tracks"] if t["eligible_for_review"]]
    assert len(candidates) == 2
    assert all(t["point_count"] > 350 for t in candidates)


def test_short_legend_swatches_are_not_full_tracks(tmp_path: Path):
    image, draw = _canvas()
    draw.line([(x, int(250 - 130 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(210, 30, 40), width=3)
    for y, color in ((295, (100, 100, 100)), (310, (130, 130, 130)), (325, (160, 160, 160))):
        draw.line((390, y, 420, y), fill=color, width=3)
    path = tmp_path / "legend.png"
    image.save(path)
    candidates = [t for t in _run(path)["tracks"] if t["eligible_for_review"]]
    assert len(candidates) == 1


def test_blank_plot_returns_no_candidates(tmp_path: Path):
    image, _ = _canvas()
    path = tmp_path / "blank.png"
    image.save(path)
    result = _run(path)
    assert result["status"] == "NO_TRAJECTORY_CANDIDATES"
    assert result["tracks"] == []


def test_artifact_writer_checks_source_pixels_and_refuses_overwrite(tmp_path: Path):
    image, draw = _canvas()
    draw.line([(x, int(240 - 100 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(180, 60, 60), width=3)
    source = tmp_path / "source.png"
    image.save(source)
    output = tmp_path / "review"
    result = write_trajectory_artifacts(source, PLOT_BOX, output, min_active_columns=50)
    assert (output / "index.html").is_file()
    assert (output / "04_all_series_overlay.png").is_file()
    assert result["source_pixel_integrity"]["status"] == "PASS"
    with pytest.raises(FileExistsError):
        write_trajectory_artifacts(source, PLOT_BOX, output)


def test_cli_accepts_trace_image_command():
    from scientific_figure_data.cli import build_parser

    args = build_parser().parse_args([
        "trace-image", "figure.png", "--plot-box", "1", "2", "300", "220",
        "--out", "review",
    ])
    assert args.command == "trace-image"
    assert args.plot_box == [1.0, 2.0, 300.0, 220.0]

def test_short_regular_dash_pattern_is_reviewable_below_solid_point_threshold(tmp_path: Path):
    image, draw = _canvas()
    for left in (80, 106, 132, 158):
        draw.line((left, 250, left + 15, 247), fill=(110, 110, 110), width=3)
    path = tmp_path / "short_regular_dash.png"
    image.save(path)
    result = _run(path)
    candidates = [track for track in result["tracks"] if track["eligible_for_review"]]
    assert len(candidates) == 1, result
    assert candidates[0]["line_style_candidate"] == "DASHED_CANDIDATE"
    assert candidates[0]["point_count"] < max(50, round(530 * 0.18))
    assert candidates[0]["review_reason"] == "PERIODIC_DASH_PATTERN"


def test_irregular_fragment_path_is_not_promoted_by_coverage_alone():
    from scientific_figure_data.trajectory import _stats

    spans = [(20, 8), (33, 3), (66, 15), (82, 1), (121, 6)]
    nodes = []
    for left, length in spans:
        for x in range(left, left + length):
            nodes.append({
                "x": x, "y": 180 - (x // 20), "width": 3,
                "rgb": [130, 130, 130], "reward": 1.5,
            })
    stats = _stats(nodes, 160)
    assert stats["line_style_candidate"] == "DISCONTINUOUS_UNRESOLVED"
    assert stats["dash_periodicity_score"] < 0.30


def test_global_path_selection_is_node_disjoint():
    image, draw = _canvas()
    draw.line([(x, int(260 - 150 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(220, 30, 40), width=3)
    draw.line([(x, int(300 - 100 * (x - 60) / 470)) for x in range(60, 531)],
              fill=(110, 110, 110), width=3)
    path = Path("global_node_disjoint.png")
    image.save(path)
    result = _run(path)
    assert result["flow_diagnostics"]["status"] == "PASS"
    assert result["flow_diagnostics"]["node_disjoint"] is True
    coordinates = [
        (point["pixel_x"], point["pixel_y"])
        for track in result["tracks"] for point in track["point_records"]
    ]
    assert len(coordinates) == len(set(coordinates))

