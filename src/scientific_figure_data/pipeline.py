from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .adapter import locate_pdf, snapshot_paper
from .calibration import calibration_to_dict, fit_linear_axis, map_pixel
from .axis_text import (extract_axis_labels, extract_native_numeric_axis_anchors,
                        extract_numeric_axis_anchors, split_axis_label_unit)
from .chart_classifier import classify_chart_family
from .context_index import PaperContextIndex
from .entities import SubjectEntity, link_series_to_subject
from .semantic_extraction import build_semantic_package, build_semantic_pass1
from .errors import OptionalDependencyError
from .hashing import atomic_write_json, sha256_file, sha256_json
from .models import AxisCalibration, JobState, PaperSnapshot, SeriesPoint, SeriesRecord, safe_id, namespaced_id
from .pdf_backend import PdfiumBackend
from .raster import (map_explicit_polyline, trace_monotonic_color,
                     detect_monotonic_color_branches)
from .profiles import profile_registry_fingerprint
from .plot_region import (detect_plot_box, detect_single_trace_color, detect_chromatic_color_families, detect_colored_y_axis_spines, estimate_ocr_text_ink_color)
from .panel_segmentation import detect_panel_regions
from .trace_spec import generate_trace_specification
from .reconstruction import render_series_artifacts, build_panel_comparison_sheet
from .qc import build_series_qc_report, load_thresholds
from .storage import write_paper_artifacts, append_panel_series_csv
from .vector_paths import choose_vector_paths, pdf_points_to_crop_pixels


ALGORITHM_VERSION = "0.8.2"


_ALGORITHM_SOURCE_FILES = (
    "pipeline.py", "adapter.py", "manifest.py", "models.py",
    "pdf_backend.py", "vector_paths.py", "plot_region.py", "chart_classifier.py",
    "axis_text.py", "raster.py", "calibration.py", "semantics.py",
    "entities.py", "context_index.py", "storage.py", "profiles.py",
    "qc.py", "hashing.py", "ocr.py", "panel_segmentation.py", "trace_spec.py",
    "reconstruction.py", "semantic_extraction.py",
)
_ALGORITHM_FINGERPRINT_CACHE: str | None = None


def algorithm_implementation_fingerprint() -> str:
    """Content fingerprint for all modules that can affect persisted scientific results."""
    global _ALGORITHM_FINGERPRINT_CACHE
    if _ALGORITHM_FINGERPRINT_CACHE is None:
        package_root = Path(__file__).resolve().parent
        files = []
        for name in _ALGORITHM_SOURCE_FILES:
            path = package_root / name
            if path.is_file():
                files.append((name, sha256_file(path)))
        _ALGORITHM_FINGERPRINT_CACHE = sha256_json(files)
    return _ALGORITHM_FINGERPRINT_CACHE


def processing_stage_state(
    snapshot: PaperSnapshot, paper_dir: Path, output_root: Path, options: dict | None = None,
) -> dict:
    options = options or {}
    overrides = _load_overrides(paper_dir, output_root, snapshot.paper_id)
    threshold_path = Path(options["qc_thresholds"]) if options.get("qc_thresholds") else None
    thresholds = load_thresholds(threshold_path)
    algorithm_fingerprint = algorithm_implementation_fingerprint()
    profile_fingerprint = profile_registry_fingerprint()
    relevant_options = {
        "render_scale": float(options.get("render_scale", 1.5)),
        "max_render_pixels": int(options.get("max_render_pixels", 12_000_000)),
        "temp_disk_limit_mb": int(options.get("temp_disk_limit_mb", 2048)),
        "context_memory_budget": int(options.get("context_memory_budget", 500_000)),
        "ocr": bool(options.get("ocr", False)),
    }
    payload = {
        "input_fingerprint": snapshot.input_fingerprint,
        "algorithm_version": ALGORITHM_VERSION,
        "algorithm_implementation_fingerprint": algorithm_fingerprint,
        "profile_config_fingerprint": profile_fingerprint,
        "qc_thresholds": thresholds,
        "overrides": overrides,
        "options": relevant_options,
    }
    return {
        "stage_fingerprint": sha256_json(payload),
        "algorithm_version": ALGORITHM_VERSION,
        "algorithm_implementation_fingerprint": algorithm_fingerprint,
        "profile_config_fingerprint": profile_fingerprint,
        "qc_thresholds": thresholds,
        "overrides": overrides,
        "options": relevant_options,
    }


def bundle_is_intact(paper_root: Path) -> bool:
    bundle_path = paper_root / "paper_bundle.json"
    if not bundle_path.is_file():
        return False
    try:
        bundle = _json_file(bundle_path)
        digitization = _json_file(paper_root / "digitization.json")
        if (bundle.get("input_fingerprint") != digitization.get("input_fingerprint")
                or bundle.get("stage_fingerprint") != digitization.get("stage_fingerprint")):
            return False
        hashes = bundle.get("content_hashes", {})
        required = {
            "paper_manifest.json", "figure_inventory.json", "panel_layout.json",
            "digitization.json",
        }
        if not required.issubset(hashes):
            return False
        for relative, expected_hash in hashes.items():
            artifact = (paper_root / relative).resolve()
            try:
                artifact.relative_to(paper_root.resolve())
            except ValueError:
                return False
            if not artifact.is_file() or sha256_file(artifact) != expected_hash:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False



def _json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _paper_relative_artifact(artifact_path: str, paper_relative: str) -> str:
    path = Path(artifact_path)
    base = Path(paper_relative)
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _inventory(paper_dir: Path, snapshot: PaperSnapshot) -> tuple[list[dict], Path | None]:
    preferred = {"figure_inventory": 0, "evidence_index": 1}
    candidates = sorted(
        (artifact for artifact in snapshot.artifacts
         if artifact.role in preferred and Path(artifact.path).suffix.lower() == ".json"),
        key=lambda item: (preferred[item.role], item.path.casefold()),
    )
    for artifact in candidates:
        rel = _paper_relative_artifact(artifact.path, snapshot.source_dir)
        path = paper_dir / rel
        if not path.is_file():
            continue
        try:
            data = _json_file(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, list):
            figures = data
        elif isinstance(data, dict):
            figures = None
            for key in ("figures", "items", "figure_inventory", "figure_index"):
                value = data.get(key)
                if isinstance(value, list):
                    figures = value
                    break
                if isinstance(value, dict) and isinstance(value.get("figures"), list):
                    figures = value["figures"]
                    break
        else:
            figures = None
        if figures is not None:
            normalized = [dict(item) for item in figures if isinstance(item, dict)]
            # Chem-Literature links MAIN figure crops through media_assets. The
            # figure bbox may be a caption bbox, so failed asset verification must
            # not fall back to cropping that bbox from the source PDF.
            if isinstance(data, dict) and path.name == "evidence_index.json":
                assets_by_figure: dict[tuple[str, str], list[dict[str, Any]]] = {}
                media_assets = data.get("media_assets")
                if isinstance(media_assets, list):
                    for asset in media_assets:
                        if not isinstance(asset, dict) or asset.get("asset_type") != "figure":
                            continue
                        figure_id = str(asset.get("figure_id") or "").strip()
                        if not figure_id:
                            continue
                        doc_type = str(asset.get("doc_type") or "MAIN").upper()
                        relative_path = asset.get("relative_path")
                        status = "VERIFIED"
                        asset_path = _safe_local_file(paper_dir, relative_path)
                        if not isinstance(relative_path, str) or not relative_path:
                            status = "MISSING_PATH"
                        elif asset_path is None:
                            candidate = (paper_dir / relative_path).resolve()
                            try:
                                candidate.relative_to(paper_dir.resolve())
                                status = "MISSING_FILE"
                            except ValueError:
                                status = "PATH_OUTSIDE_PACKAGE"
                        else:
                            expected_hash = str(asset.get("sha256") or "").strip().lower()
                            if not expected_hash:
                                status = "MISSING_SHA256"
                            else:
                                try:
                                    if sha256_file(asset_path) != expected_hash:
                                        status = "HASH_MISMATCH"
                                except OSError:
                                    status = "UNREADABLE"
                        key = (figure_id, doc_type)
                        assets_by_figure.setdefault(key, []).append({
                            "asset": asset, "status": status,
                        })

                for figure in normalized:
                    key = (str(figure.get("figure_id") or figure.get("id") or "").strip(),
                           str(figure.get("doc_type") or "MAIN").upper())
                    candidates = assets_by_figure.get(key, [])
                    if not candidates:
                        if figure.get("image_path"):
                            local_image = _safe_local_file(paper_dir, str(figure["image_path"]))
                            figure["image_asset_status"] = (
                                "LOCAL_PATH_VERIFIED" if local_image else "MISSING_FILE"
                            )
                        else:
                            figure["image_asset_status"] = "NO_EXACT_ASSET"
                        continue
                    unique_claims = {
                        (item["asset"].get("relative_path"), item["asset"].get("sha256"))
                        for item in candidates
                    }
                    if len(unique_claims) > 1:
                        figure["image_asset_status"] = "AMBIGUOUS"
                        continue
                    selected = candidates[0]
                    asset = selected["asset"]
                    status = selected["status"]
                    figure["image_asset_status"] = status
                    figure["media_asset_metadata"] = {
                        key: asset.get(key) for key in (
                            "asset_id", "bbox", "page_number", "extraction_method",
                            "coordinate_space", "bbox_coordinate_space", "page_rotation_degrees",
                            "page_width_pdf", "page_height_pdf", "source_pdf_sha256",
                        ) if asset.get(key) is not None
                    }
                    if status == "VERIFIED" and asset.get("relative_path") and not figure.get("image_path"):
                        figure["image_path"] = asset["relative_path"]
                        figure["image_asset_sha256"] = asset.get("sha256")
                        figure["image_asset_id"] = asset.get("asset_id")
            for figure in normalized:
                if not figure.get("image_path"):
                    continue
                if figure.get("image_asset_status") not in {
                    None, "LOCAL_PATH_VERIFIED", "NO_EXACT_ASSET",
                }:
                    continue
                local_image = _safe_local_file(paper_dir, str(figure["image_path"]))
                if local_image is None:
                    figure["image_asset_status"] = "MISSING_FILE"
                    figure.pop("image_path", None)
                    continue
                relative_image = local_image.relative_to(paper_dir.resolve()).as_posix()
                source_prefix = (
                    "" if snapshot.source_dir in {"", ".", "root-paper"}
                    else snapshot.source_dir.replace("\\", "/").strip("/")
                )
                snapshot_path = "/".join(
                    part for part in (source_prefix, relative_image) if part
                )
                artifact = next(
                    (item for item in snapshot.artifacts if item.path == snapshot_path),
                    None,
                )
                if artifact is None:
                    figure["image_asset_status"] = "UNTRACKED_SOURCE_IMAGE"
                    figure.pop("image_path", None)
                    continue
                try:
                    actual_hash = sha256_file(local_image)
                except OSError:
                    figure["image_asset_status"] = "UNREADABLE"
                    figure.pop("image_path", None)
                    continue
                figure["image_asset_sha256"] = artifact.sha256
                if actual_hash != artifact.sha256:
                    figure["image_asset_status"] = "HASH_MISMATCH"
                    figure.pop("image_path", None)
                elif figure.get("image_asset_status") in {None, "LOCAL_PATH_VERIFIED", "NO_EXACT_ASSET"}:
                    figure["image_asset_status"] = "LOCAL_PATH_HASH_VERIFIED"
            return normalized, path
    return [], None


def _copy_image_asset_to_evidence(
    source_path: Path, destination: Path, expected_sha256: str | None = None,
) -> Path | None:
    """Copy a source image atomically, rechecking its upstream content hash."""
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = sha256_file(source_path)
        if expected_sha256 and source_hash != expected_sha256:
            return None
        shutil.copyfile(source_path, temporary)
        if expected_sha256 and sha256_file(temporary) != expected_sha256:
            temporary.unlink()
            return None
        temporary.replace(destination)
        return destination
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        return None


def _may_use_source_pdf_bbox_fallback(source_figure: dict, panel: dict) -> bool:
    """Do not guess a PDF crop when an upstream evidence_index asset is unresolved."""
    return not source_figure.get("image_asset_status") or bool(panel.get("image_path"))


def _safe_local_file(paper_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    candidate = (paper_dir / value).resolve()
    try:
        candidate.relative_to(paper_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _normalize_bbox(bbox: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(v) for v in bbox]
    except (TypeError, ValueError, OverflowError):
        return None
    if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.01:
        x0, x1 = x0 * width, x1 * width
        y0, y1 = y0 * height, y1 * height
    coords = (max(0, int(x0)), max(0, int(y0)), min(width, int(x1)), min(height, int(y1)))
    if coords[2] <= coords[0] or coords[3] <= coords[1]:
        return None
    return coords



def _source_image_crop_mapping(
    source_path: Path, bbox: Any, crop_path: Path,
) -> dict | None:
    """Record an image-pixel crop transform without pretending it is a PDF mapping."""
    try:
        from PIL import Image
        with Image.open(source_path) as image:
            coords = _normalize_bbox(bbox, image.width, image.height)
            if not coords:
                return None
            x0, y0, x1, y1 = coords
            return {
                "coordinate_space": "SOURCE_IMAGE_PIXELS",
                "source_image_sha256": sha256_file(source_path),
                "source_image_size": [image.width, image.height],
                "crop_bbox_source_pixels": list(coords),
                "crop_width_pixels": x1 - x0,
                "crop_height_pixels": y1 - y0,
                "crop_image_path": crop_path.name,
                "render_scale": 1.0,
            }
    except (OSError, ImportError):
        return None


def _validated_normalized_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        coords = [float(item) for item in value]
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(item) and 0.0 <= item <= 1.0 for item in coords):
        return None
    x0, y0, x1, y1 = coords
    if x1 <= x0 or y1 <= y0:
        return None
    return coords


def _figure_panels(figure: dict) -> list[dict]:
    panels = figure.get("panels")
    if isinstance(panels, list) and panels:
        normalized = []
        for item in panels:
            panel = dict(item) if isinstance(item, dict) else {"label": str(item)}
            has_bbox = bool(panel.get("bbox") or panel.get("bounding_box"))
            panel.setdefault("segmentation_provenance", "UPSTREAM_PANEL_INVENTORY")
            panel.setdefault(
                "segmentation_status",
                "BOUNDARY_SUPPLIED" if has_bbox else "BOUNDARY_UNSPECIFIED",
            )
            normalized.append(panel)
        return normalized

    # A Chem-Literature evidence_index bbox can describe only the caption.
    # Never relabel it as panel geometry when the figure image is a separately
    # extracted media asset. Preserve the raw figure bbox on the Figure record.
    bbox = None if figure.get("image_asset_status") else (
        figure.get("bbox") or figure.get("bounding_box")
    )
    return [{
        "panel_id": "1",
        "label": figure.get("panel_label", "whole-figure"),
        "bbox": bbox,
        "segmentation_provenance": "SINGLE_PANEL_FALLBACK",
        "segmentation_status": "WHOLE_FIGURE_NOT_SEGMENTED",
    }]


def _load_overrides(paper_dir: Path, output_root: Path, paper_id: str) -> dict:
    # The upstream-side override is read-only. A separate downstream override takes precedence.
    candidates = [
        paper_dir / "digitization_overrides.json",
        output_root / "overrides" / paper_id / "digitization_overrides.json",
    ]
    merged = {}
    for path in candidates:
        if path.is_file():
            data = _json_file(path)
            if isinstance(data, dict):
                merged = {**merged, **data}
    return merged


def _series_overrides(overrides: dict, figure_id: str, panel_id: str) -> list[dict]:
    figures = overrides.get("figures", {})
    figure = figures.get(figure_id, {}) if isinstance(figures, dict) else {}
    panels = figure.get("panels", {}) if isinstance(figure, dict) else {}
    panel = panels.get(panel_id, {}) if isinstance(panels, dict) else {}
    series = panel.get("series", []) if isinstance(panel, dict) else []
    return series if isinstance(series, list) else []


def _cached_result(paper_root: Path, snapshot: PaperSnapshot, locked: bool = False,
                   expected_stage_fingerprint: str | None = None) -> dict | None:
    digitization_path = paper_root / "digitization.json"
    manifest_path = paper_root / "paper_manifest.json"
    figures_path = paper_root / "figure_inventory.json"
    panels_path = paper_root / "panel_layout.json"
    if not all(p.is_file() for p in (digitization_path, manifest_path, figures_path, panels_path)):
        return None
    digitization = _json_file(digitization_path)
    bundle_path = paper_root / "paper_bundle.json"
    if not bundle_path.is_file():
        return None
    bundle = _json_file(bundle_path)
    if (bundle.get("input_fingerprint") != digitization.get("input_fingerprint")
            or bundle.get("stage_fingerprint") != digitization.get("stage_fingerprint")):
        return None
    for relative, expected_hash in bundle.get("content_hashes", {}).items():
        artifact = (paper_root / relative).resolve()
        try:
            artifact.relative_to(paper_root.resolve())
        except ValueError:
            return None
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            return None
    if not locked:
        if digitization.get("input_fingerprint") != snapshot.input_fingerprint:
            return None
        if expected_stage_fingerprint and digitization.get("stage_fingerprint") != expected_stage_fingerprint:
            return None
    figures = _json_file(figures_path).get("figures", [])
    panels = _json_file(panels_path).get("panels", [])
    series = []
    accepted_fields = {
        "series_id", "paper_id", "figure_id", "panel_id", "technique", "domain", "label",
        "x_label", "y_label", "x_unit", "y_unit", "measurement_id", "y_axis_side", "extraction_method",
        "extraction_status", "qc_status", "review_state", "subject_links", "conditions",
        "evidence", "metadata",
    }
    for item in digitization.get("series", []):
        payload = {key: value for key, value in item.items() if key in accepted_fields}
        payload.setdefault("points", [])
        series.append(payload)
    status = "BLOCKED_REVIEW_LOCKED" if locked else digitization.get("status", "COMPLETED")
    job_state = JobState.BLOCKED.value if locked else (
        JobState.NEEDS_REVIEW.value if status in {"NEEDS_REVIEW", "COMPLETED_WITH_REVIEW"} else JobState.COMPLETED.value
    )
    return {
        "cached": True, "snapshot": snapshot.to_dict(), "figures": figures, "panels": panels,
        "series": series, "status": status, "job_state": job_state,
        "reason": "REVIEWED_RESULT_PROTECTED" if locked else "UNCHANGED_INPUT_AND_ALGORITHM",
    }


def _check_memory_budget(memory_limit_mb: int):
    if memory_limit_mb <= 0:
        return
    try:
        import psutil
        rss = psutil.Process().memory_info().rss
        if rss > memory_limit_mb * 1024 * 1024:
            raise MemoryError(f"Worker RSS {rss // (1024 * 1024)} MiB exceeds configured budget {memory_limit_mb} MiB")
    except ImportError:
        return


def _plot_box_pixels(image_path: Path | None, plot_box: Any) -> tuple[int, int, int, int] | None:
    if image_path is None or not plot_box or len(plot_box) != 4:
        return None
    try:
        from PIL import Image
        with Image.open(image_path) as image:
            width, height = image.size
        return _normalize_bbox(plot_box, width, height)
    except (ImportError, OSError, TypeError, ValueError):
        return None


def _plot_box_to_pdf(
    plot_box_pixels: tuple[int, int, int, int] | None,
    crop_mapping: dict | None,
) -> tuple[float, float, float, float] | None:
    if not plot_box_pixels or not crop_mapping:
        return None
    if crop_mapping.get("coordinate_space", "PDF_PAGE_POINTS") != "PDF_PAGE_POINTS":
        return None
    if crop_mapping.get("page_rotation_degrees", 0) != 0:
        return None
    if not all(key in crop_mapping for key in ("crop_left_pdf", "crop_top_pdf", "render_scale")):
        return None
    scale = float(crop_mapping.get("render_scale", 0))
    if scale <= 0:
        return None
    left = float(crop_mapping["crop_left_pdf"])
    top = float(crop_mapping["crop_top_pdf"])
    x0, y0, x1, y1 = plot_box_pixels
    return (
        left + x0 / scale,
        top - y1 / scale,
        left + x1 / scale,
        top - y0 / scale,
    )




def _standardization_request_from_definition(definition: dict) -> dict | None:
    """Validate explicit per-axis target units without guessing any unit."""
    if "standardization" not in definition:
        return None
    supplied = definition.get("standardization")
    if not isinstance(supplied, dict):
        return {
            "status": "INVALID_CONFIGURATION",
            "configuration_errors": ["standardization must be an object"],
            "provided": supplied,
        }
    allowed = {"x_target_unit", "y_target_unit"}
    errors = [f"unsupported key: {key}" for key in sorted(set(supplied) - allowed)]
    targets: dict[str, str | None] = {"x_target_unit": None, "y_target_unit": None}
    for key in allowed:
        if key not in supplied:
            continue
        value = supplied[key]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 64:
            errors.append(f"{key} must be a non-empty unit string of at most 64 characters")
        else:
            targets[key] = value.strip()
    if errors:
        return {"status": "INVALID_CONFIGURATION", "configuration_errors": errors, "provided": supplied}
    if not any(targets.values()):
        return {"status": "NOT_REQUESTED", **targets}
    return {"status": "REQUESTED", **targets}


def _attach_standardization_request(record: SeriesRecord, definition: dict) -> None:
    request = _standardization_request_from_definition(definition)
    if request is None:
        return
    if not isinstance(record.metadata, dict):
        record.metadata = {}
    record.metadata["standardization"] = request

def _extract_panel(
    image_path: Path | None, paper_id: str, figure_id: str, panel_id: str,
    panel: dict, figure: dict, overrides: dict, context: PaperContextIndex,
    pdf_page: int | None, native_page_evidence: dict | None = None,
    ocr_evidence: list[dict] | None = None,
    source_pdf_sha256: str | None = None, input_fingerprint: str | None = None,
    native_page_path: Path | None = None, crop_mapping: dict | None = None,
) -> list[SeriesRecord]:
    definitions = _series_overrides(overrides, figure_id, panel_id)
    generated_default_definition = not definitions
    native_text_preview = str((native_page_evidence or {}).get("native_text_preview", ""))
    base_technique = panel.get("technique") or figure.get("technique")
    if not definitions:
        definitions = [{
            "series_id": f"{figure_id}_{panel_id}_unassigned", "label": None,
            "technique": base_technique,
            "domain": panel.get("domain") or figure.get("domain"),
        }]

    # Expand only an unconfigured default record, and only when chart semantics
    # and plot geometry support ordered-X connected 2-D raster paths. Explicit series definitions
    # are never replaced or reinterpreted by this visual candidate pass.
    if (
        generated_default_definition and image_path and len(definitions) == 1
        and not definitions[0].get("color_rgb")
        and not definitions[0].get("pixel_points")
    ):
        base_definition = definitions[0]
        pre_plot_box = base_definition.get("plot_box") or panel.get("plot_box")
        pre_plot_detection = None
        if not pre_plot_box:
            try:
                pre_plot_detection = detect_plot_box(image_path)
                if pre_plot_detection.get("status") == "PROVISIONAL_PLOT_BOX":
                    pre_plot_box = pre_plot_detection.get("pixel_bbox")
            except OptionalDependencyError:
                pre_plot_detection = {"status": "UNAVAILABLE"}
        pre_plot_box_pixels = _plot_box_pixels(image_path, pre_plot_box) if pre_plot_box else None
        pre_axis_labels = {}
        if ocr_evidence and pre_plot_box_pixels:
            try:
                pre_axis_labels = extract_axis_labels(ocr_evidence, tuple(pre_plot_box_pixels))
            except (TypeError, ValueError):
                pre_axis_labels = {}
        pre_x_label = (
            base_definition.get("x_label") or panel.get("x_label")
            or pre_axis_labels.get("x_label")
        )
        pre_classification = classify_chart_family(
            base_definition.get("technique") or panel.get("technique") or figure.get("technique"),
            pre_x_label,
            base_definition.get("y_label") or panel.get("y_label"),
            figure.get("caption"),
            native_text_preview,
        )
        pre_family = str(
            base_definition.get("data_family")
            or pre_classification.get("chart_family")
            or "UNCLASSIFIED"
        ).upper()
        from .trace_spec import is_supported_monotonic_x_label
        ordered_x_supported = (
            is_supported_monotonic_x_label(pre_x_label)
            or pre_family in {"TIME_SERIES", "SPECTRUM"}
        )
        if (
            pre_plot_box_pixels and ordered_x_supported
            and pre_family not in {"CV", "EIS", "NON_MONOTONIC", "NON_MONOTONIC_CURVE"}
        ):
            family_detection = detect_chromatic_color_families(
                image_path, tuple(pre_plot_box_pixels)
            )
            candidates = family_detection.get("families", [])
            if (
                family_detection.get("status") in {
                    "UNIQUE_CHROMATIC_FAMILY", "MULTIPLE_CHROMATIC_FAMILIES",
                }
                and candidates
                and not family_detection.get("truncated", False)
            ):
                expanded = []
                base_id = str(base_definition.get("series_id") or f"{figure_id}_{panel_id}_unassigned")
                multiple_families = (
                    family_detection.get("status") == "MULTIPLE_CHROMATIC_FAMILIES"
                    and len(candidates) >= 2
                )
                for color_index, candidate in enumerate(candidates, 1):
                    branch_detection = detect_monotonic_color_branches(
                        str(image_path),
                        tuple(int(value) for value in candidate["color_rgb"]),
                        int(candidate.get("color_tolerance", 24)),
                        plot_box=tuple(pre_plot_box_pixels),
                        color_match=candidate.get("color_match"),
                    )
                    branch_count = (
                        int(branch_detection.get("branch_count", 1))
                        if branch_detection.get("status") == "MULTIPLE_MONOTONIC_COLOR_BRANCHES"
                        else 1
                    )
                    for branch_index in range(branch_count):
                        definition = dict(base_definition)
                        color_id = (
                            f"{base_id}_auto_color_{color_index:02d}"
                            if multiple_families else base_id
                        )
                        if multiple_families or branch_count > 1:
                            definition["series_id"] = (
                                f"{color_id}_branch_{branch_index + 1:02d}"
                                if branch_count > 1 else color_id
                            )
                        definition["color_rgb"] = list(candidate["color_rgb"])
                        definition["_auto_color_candidate"] = dict(candidate)
                        definition["_auto_color_detection"] = family_detection
                        definition["_auto_plot_box_pixels"] = list(pre_plot_box_pixels)
                        definition["_auto_plot_detection"] = pre_plot_detection
                        definition["_auto_trace_branch_detection"] = branch_detection
                        if branch_count > 1:
                            definition["_auto_trace_branch_index"] = branch_index
                            definition["_auto_trace_branch_count"] = branch_count
                        expanded.append(definition)
                if expanded:
                    definitions = expanded

    evidence = {
        "figure_id": figure_id, "panel_id": panel_id, "source_page": pdf_page,
        "source_image_asset_status": figure.get("source_asset_status"),
        "source_image": image_path.name if image_path else None,
        "source_image_upstream_path": figure.get("source_image_asset_path"),
        "source_pdf_integrity_status": figure.get("source_pdf_integrity_status"),
        "source_image_sha256": sha256_file(image_path) if image_path and image_path.is_file() else None,
        "source_pdf_sha256": source_pdf_sha256,
        "paper_input_fingerprint": input_fingerprint,
        "extraction_channel": "UNRESOLVED",
        "algorithm_version": ALGORITHM_VERSION,
        "context_reference_candidates": context.search("reference_electrode"),
        "context_statistics_candidates": context.search("statistics"),
        "native_page_evidence": native_page_evidence or {},
        "ocr_evidence": ocr_evidence or [],
    }
    results: list[SeriesRecord] = []
    for index, definition in enumerate(definitions, 1):
        local_series_id = str(definition.get("series_id") or f"{figure_id}_{panel_id}_series{index}")
        series_id = namespaced_id(paper_id, local_series_id)
        record = SeriesRecord(
            series_id=series_id, paper_id=paper_id, figure_id=figure_id, panel_id=panel_id,
            technique=definition.get("technique") or panel.get("technique") or figure.get("technique"),
            domain=definition.get("domain") or panel.get("domain") or figure.get("domain"),
            label=definition.get("label"), x_label=definition.get("x_label"),
            y_label=definition.get("y_label"), x_unit=definition.get("x_unit"),
            y_unit=definition.get("y_unit"),
            measurement_id=namespaced_id(
                paper_id, str(definition.get("measurement_id") or f"measurement:{series_id}")
            ),
            y_axis_side=definition.get("y_axis_side", "UNASSIGNED"),
            extraction_method="UNRESOLVED", extraction_status="NEEDS_REVIEW",
            qc_status="PROVISIONAL_UNCALIBRATED", review_state="NEEDS_REVIEW",
            evidence=[evidence], metadata={"reason": "INSUFFICIENT_EXPLICIT_DIGITIZATION_EVIDENCE"},
        )
        for link in definition.get("subject_links", []):
            entity_data = link.get("entity") or {}
            source_entity_id = str(entity_data.get("entity_id") or "").strip()
            requested_scope = str(
                entity_data.get("identity_scope") or link.get("identity_scope") or "PAPER"
            ).upper()
            if entity_data and source_entity_id and source_entity_id != "UNKNOWN":
                scoped_entity_id = (
                    source_entity_id if requested_scope == "GLOBAL"
                    else namespaced_id(paper_id, source_entity_id)
                )
                entity = SubjectEntity(
                    entity_id=scoped_entity_id,
                    canonical_name=str(entity_data.get("canonical_name", "")),
                    entity_type=str(entity_data.get("entity_type", "unknown")),
                    domain=entity_data.get("domain"), aliases=entity_data.get("aliases", []),
                )
            else:
                entity = None
                requested_scope = "PAPER"
            linked = link_series_to_subject(
                series_id, entity, str(link.get("role_in_series", "unknown")),
                link.get("evidence"), exact_match=bool(link.get("exact_match", False)),
            )
            if linked.get("status") == "ASSIGNED_WITH_EVIDENCE":
                linked["identity_scope"] = "GLOBAL" if requested_scope == "GLOBAL" else "PAPER"
                linked["source_entity_id"] = source_entity_id
            record.subject_links.append(linked)
        record.conditions = []
        for condition_index, source_condition in enumerate(definition.get("conditions", [])):
            condition = dict(source_condition)
            local_condition_id = str(
                condition.get("condition_id") or f"{series_id}:condition:{condition_index}"
            )
            condition["source_condition_id"] = local_condition_id
            condition["condition_id"] = namespaced_id(paper_id, local_condition_id)
            record.conditions.append(condition)
        relationships = []
        for source_relationship in definition.get("entity_relationships", []):
            relationship = dict(source_relationship)
            scope = str(relationship.get("identity_scope") or "PAPER").upper()
            for id_key in ("parent_entity_id", "child_entity_id"):
                if relationship.get(id_key) and scope != "GLOBAL":
                    relationship[f"source_{id_key}"] = relationship[id_key]
                    relationship[id_key] = namespaced_id(paper_id, relationship[id_key])
            relationship["identity_scope"] = "GLOBAL" if scope == "GLOBAL" else "PAPER"
            relationships.append(relationship)
        if relationships:
            record.metadata["entity_relationships"] = relationships
        explicit_semantics = definition.get("measurement_semantics")
        if isinstance(explicit_semantics, dict):
            record.metadata["measurement_semantics"] = dict(explicit_semantics)
        explicit_compatibility = definition.get("compatibility_warnings")
        if isinstance(explicit_compatibility, list):
            record.metadata["compatibility_warnings"] = [
                str(item) for item in explicit_compatibility if isinstance(item, str)
            ]
        classification = classify_chart_family(
            definition.get("technique") or panel.get("technique") or figure.get("technique"),
            definition.get("x_label") or panel.get("x_label"),
            definition.get("y_label") or panel.get("y_label"),
            figure.get("caption"), native_text_preview,
        )
        if not record.technique and classification.get("technique"):
            record.technique = classification["technique"]
        explicit_family = str(definition.get("data_family", "")).upper()
        family = explicit_family or str(classification.get("chart_family", "UNCLASSIFIED")).upper()
        record.metadata["chart_family_classification"] = classification

        plot_box = (
            definition.get("plot_box")
            or definition.get("_auto_plot_box_pixels")
            or panel.get("plot_box")
        )
        plot_detection = definition.get("_auto_plot_detection")
        if not plot_box and image_path:
            try:
                plot_detection = detect_plot_box(image_path)
                if plot_detection.get("status") == "PROVISIONAL_PLOT_BOX":
                    plot_box = plot_detection["pixel_bbox"]
            except OptionalDependencyError:
                plot_detection = {"status": "UNAVAILABLE", "reason": "OPTIONAL_IMAGE_DEPENDENCY_MISSING"}
        plot_box_pixels = _plot_box_pixels(image_path, plot_box)
        if (plot_box_pixels is None and image_path is None
                and isinstance(plot_box, (list, tuple)) and len(plot_box) == 4):
            try:
                numeric_plot_box = tuple(float(value) for value in plot_box)
                if max(abs(value) for value in numeric_plot_box) > 1.01:
                    plot_box_pixels = tuple(int(round(value)) for value in numeric_plot_box)
            except (TypeError, ValueError, OverflowError):
                plot_box_pixels = None
        if plot_box and image_path and plot_box_pixels is None:
            plot_detection = {"status": "NEEDS_REVIEW", "reason": "INVALID_MANUAL_PLOT_BOX"}


        axis_label_evidence = {
            "status": "NOT_RUN",
            "reason": "OCR_EVIDENCE_OR_PLOT_REGION_UNAVAILABLE",
        }
        x_axis_label_text = definition.get("x_label") or panel.get("x_label")
        y_axis_label_text = definition.get("y_label") or panel.get("y_label")
        if ocr_evidence and plot_box_pixels:
            try:
                axis_label_evidence = extract_axis_labels(ocr_evidence, tuple(plot_box_pixels))
            except (TypeError, ValueError):
                axis_label_evidence = {"status": "NEEDS_REVIEW", "reason": "AXIS_LABEL_PARSE_ERROR"}
            ocr_x_label = axis_label_evidence.get("x_label")
            if not x_axis_label_text and ocr_x_label:
                x_axis_label_text = ocr_x_label
                parsed_label, parsed_unit = split_axis_label_unit(ocr_x_label)
                record.x_label = parsed_label
                if not record.x_unit:
                    record.x_unit = parsed_unit
            requested_y_side = str(
                definition.get("y_axis_side") or panel.get("y_axis_side") or "UNASSIGNED"
            ).upper()
            left_y_label = axis_label_evidence.get("y_left_label")
            right_y_label = axis_label_evidence.get("y_right_label")
            selected_y_label = (
                right_y_label if requested_y_side == "RIGHT" else
                left_y_label if requested_y_side == "LEFT" else
                left_y_label if left_y_label and not right_y_label else
                right_y_label if right_y_label and not left_y_label else None
            )
            if not y_axis_label_text and selected_y_label:
                y_axis_label_text = selected_y_label
                parsed_label, parsed_unit = split_axis_label_unit(selected_y_label)
                record.y_label = parsed_label
                if not record.y_unit:
                    record.y_unit = parsed_unit
            if requested_y_side == "UNASSIGNED" and selected_y_label:
                record.y_axis_side = "RIGHT" if selected_y_label == right_y_label else "LEFT"

        classification = classify_chart_family(
            definition.get("technique") or panel.get("technique") or figure.get("technique"),
            x_axis_label_text, y_axis_label_text, figure.get("caption"), native_text_preview,
        )
        if not record.technique and classification.get("technique"):
            record.technique = classification["technique"]
        explicit_family = str(definition.get("data_family", "")).upper()
        family = explicit_family or str(classification.get("chart_family", "UNCLASSIFIED")).upper()
        record.metadata["chart_family_classification"] = classification
        record.metadata["axis_label_evidence"] = axis_label_evidence

        plot_bbox_pdf = definition.get("plot_bbox_pdf")
        if plot_bbox_pdf is None:
            plot_bbox_pdf = _plot_box_to_pdf(plot_box_pixels, crop_mapping)
        vector_indices = definition.get("vector_object_indices")
        axis_text_evidence = None
        native_axis_evidence = None
        ocr_axis_evidence = None
        native_payload = None
        x_axis_anchors = definition.get("x_axis_anchors", [])
        y_axis_anchors = definition.get("y_axis_anchors", [])
        explicit_y_side = definition.get("y_axis_side") or panel.get("y_axis_side")
        automatic_color_candidate = isinstance(
            definition.get("_auto_color_candidate"), dict
        )
        requested_y_side = str(
            explicit_y_side
            or (record.y_axis_side if not automatic_color_candidate else "UNASSIGNED")
            or "UNASSIGNED"
        ).upper()
        if requested_y_side not in {"LEFT", "RIGHT"}:
            requested_y_side = "UNASSIGNED"
        # An OCR axis title identifies a panel axis, not necessarily the Y axis
        # used by every automatically discovered color family. For dual-axis
        # plots, leave each automatic family unassigned until color evidence is
        # evaluated against both calibrated sides.
        if automatic_color_candidate and explicit_y_side is None:
            record.y_axis_side = "UNASSIGNED"
        y_axis_anchors_by_side = {"LEFT": [], "RIGHT": []}
        if len(y_axis_anchors) >= 2 and requested_y_side in y_axis_anchors_by_side:
            y_axis_anchors_by_side[requested_y_side] = list(y_axis_anchors)
        x_anchor_source = "MANUAL_OVERRIDE" if x_axis_anchors else None
        y_anchor_source = "MANUAL_OVERRIDE" if y_axis_anchors else None
        explicit_relative_signal = str(definition.get("y_signal_mode", "")).upper() in {
            "ARBITRARY_RELATIVE", "SERIES_RELATIVE_SIGNAL"
        }
        relative_signal = explicit_relative_signal or (
            family == "SPECTRUM" and len(y_axis_anchors) < 2
            and not any(len(values) >= 2 for values in y_axis_anchors_by_side.values())
        )

        if (native_page_path and native_page_path.is_file() and plot_bbox_pdf and crop_mapping
                and crop_mapping.get("coordinate_space", "PDF_PAGE_POINTS") == "PDF_PAGE_POINTS"
                and crop_mapping.get("page_rotation_degrees", 0) == 0):
            try:
                native_payload = _json_file(native_page_path)
                native_axis_evidence = extract_native_numeric_axis_anchors(
                    native_payload, tuple(float(value) for value in plot_bbox_pdf), crop_mapping
                )
            except (OSError, KeyError, TypeError, ValueError):
                native_axis_evidence = None

        def use_y_axis_candidates(axis_candidates):
            nonlocal y_axis_anchors
            if explicit_relative_signal or not axis_candidates:
                return
            for side, key in (("LEFT", "y_left_anchors"), ("RIGHT", "y_right_anchors")):
                values = axis_candidates.get(key, [])
                if len(values) >= 2 and not y_axis_anchors_by_side[side]:
                    y_axis_anchors_by_side[side] = list(values)

            available = [
                side for side, values in y_axis_anchors_by_side.items()
                if len(values) >= 2
            ]
            if len(y_axis_anchors) >= 2 and requested_y_side == "UNASSIGNED":
                return
            if requested_y_side in {"LEFT", "RIGHT"}:
                if len(y_axis_anchors_by_side[requested_y_side]) >= 2:
                    y_axis_anchors = y_axis_anchors_by_side[requested_y_side]
                    record.y_axis_side = requested_y_side
                else:
                    y_axis_anchors = []
            elif len(available) == 1:
                selected_side = available[0]
                y_axis_anchors = y_axis_anchors_by_side[selected_side]
                record.y_axis_side = selected_side
            elif len(available) == 2:
                y_axis_anchors = []
                record.y_axis_side = "UNASSIGNED"

        if native_axis_evidence:
            if len(x_axis_anchors) < 2 and len(native_axis_evidence["x_anchors"]) >= 2:
                x_axis_anchors = native_axis_evidence["x_anchors"]
                x_anchor_source = "PDF_NATIVE_TEXT"
            previous_y_state = tuple(len(values) for values in y_axis_anchors_by_side.values())
            use_y_axis_candidates(native_axis_evidence)
            current_y_state = tuple(len(values) for values in y_axis_anchors_by_side.values())
            if current_y_state != previous_y_state or len(y_axis_anchors) >= 2:
                y_anchor_source = "PDF_NATIVE_TEXT"
        if not explicit_relative_signal and family == "SPECTRUM":
            relative_signal = len(y_axis_anchors) < 2 and not any(
                len(values) >= 2 for values in y_axis_anchors_by_side.values()
            )

        if ocr_evidence and plot_box_pixels and (
            len(x_axis_anchors) < 2 or (not explicit_relative_signal and len(y_axis_anchors) < 2)
        ):
            ocr_axis_evidence = extract_numeric_axis_anchors(ocr_evidence, tuple(plot_box_pixels))
            if len(x_axis_anchors) < 2 and len(ocr_axis_evidence["x_anchors"]) >= 2:
                x_axis_anchors = ocr_axis_evidence["x_anchors"]
                x_anchor_source = "OCR"
            previous_y_state = tuple(len(values) for values in y_axis_anchors_by_side.values())
            use_y_axis_candidates(ocr_axis_evidence)
            current_y_state = tuple(len(values) for values in y_axis_anchors_by_side.values())
            if current_y_state != previous_y_state or len(y_axis_anchors) >= 2:
                y_anchor_source = "OCR"
            if not explicit_relative_signal and family == "SPECTRUM":
                relative_signal = len(y_axis_anchors) < 2 and not any(
                    len(values) >= 2 for values in y_axis_anchors_by_side.values()
                )

        if native_axis_evidence or ocr_axis_evidence:
            axis_text_evidence = {
                "native": native_axis_evidence,
                "ocr": ocr_axis_evidence,
                "source": (
                    "PDF_NATIVE_TEXT" if native_axis_evidence and (
                        native_axis_evidence["x_anchors"] or native_axis_evidence["y_left_anchors"]
                        or native_axis_evidence["y_right_anchors"]
                    ) else "OCR" if ocr_axis_evidence else "NONE"
                ),
                "provisional": True,
            }

        x_cal = None
        y_cal = None
        calibration_errors = {}
        try:
            x_cal = fit_linear_axis("x", x_axis_anchors, definition.get("x_unit"))
        except (ValueError, TypeError) as exc:
            calibration_errors["x"] = f"{type(exc).__name__}: {exc}"

        y_axis_calibrations = {}
        if relative_signal:
            try:
                if not plot_box_pixels:
                    raise ValueError("Relative signal requires a resolved plot box and panel image")
                _, by0, _, by1 = plot_box_pixels
                y_cal = AxisCalibration(
                    "y", None, -1.0 / (by1 - by0), by1 / (by1 - by0), [],
                    0.0, status="SERIES_RELATIVE_SIGNAL",
                )
            except (ValueError, TypeError, ImportError) as exc:
                calibration_errors["y"] = f"{type(exc).__name__}: {exc}"
        else:
            for side, anchors in y_axis_anchors_by_side.items():
                if len(anchors) < 2:
                    continue
                try:
                    y_axis_calibrations[side] = fit_linear_axis(
                        "y", anchors, definition.get("y_unit")
                    )
                except (ValueError, TypeError) as exc:
                    calibration_errors[f"y_{side.lower()}"] = f"{type(exc).__name__}: {exc}"

            y_cal = None
            if len(y_axis_anchors) >= 2:
                try:
                    y_cal = fit_linear_axis("y", y_axis_anchors, definition.get("y_unit"))
                except (ValueError, TypeError) as exc:
                    calibration_errors["y"] = f"{type(exc).__name__}: {exc}"
            elif requested_y_side in {"LEFT", "RIGHT"}:
                y_cal = y_axis_calibrations.get(requested_y_side)
                if y_cal is None:
                    calibration_errors["y"] = f"REQUESTED_{requested_y_side}_Y_AXIS_NOT_CALIBRATED"
            elif len(y_axis_calibrations) == 1:
                selected_side, y_cal = next(iter(y_axis_calibrations.items()))
                record.y_axis_side = selected_side
            elif len(y_axis_calibrations) > 1:
                calibration_errors["y"] = "AMBIGUOUS_DUAL_Y_AXIS_SERIES_ASSOCIATION"
            else:
                try:
                    y_cal = fit_linear_axis("y", y_axis_anchors, definition.get("y_unit"))
                except (ValueError, TypeError) as exc:
                    calibration_errors["y"] = f"{type(exc).__name__}: {exc}"

        series_axis_assignment = {
            "status": (
                "RELATIVE_SIGNAL" if relative_signal else
                "ASSIGNED" if y_cal is not None and record.y_axis_side in {"LEFT", "RIGHT"} else
                "AMBIGUOUS_DUAL_Y_AXIS" if len(y_axis_calibrations) > 1 else
                "UNRESOLVED"
            ),
            "selected_side": record.y_axis_side if y_cal is not None else None,
            "available_sides": list(y_axis_calibrations),
            "reason": (
                "SERIES_TO_Y_AXIS_MAPPING_REQUIRED"
                if len(y_axis_calibrations) > 1 and y_cal is None else None
            ),
        }
        pixel_points = definition.get("pixel_points")
        color_rgb = definition.get("color_rgb")
        color_detection = None
        if definition.get("_auto_color_candidate"):
            candidate = definition["_auto_color_candidate"]
            color_detection = {
                "status": "UNIQUE_CHROMATIC_FAMILY",
                "color_rgb": list(candidate["color_rgb"]),
                "color_tolerance": int(candidate.get("color_tolerance", 24)),
                "color_match": candidate.get("color_match"),
                "source": "AUTOMATIC_HUE_COLOR_FAMILY_CANDIDATE",
                "candidate_evidence": candidate,
                "family_detection": definition.get("_auto_color_detection"),
            }
        if (not color_rgb and image_path and plot_box_pixels
                and family not in {"NON_MONOTONIC", "NON_MONOTONIC_CURVE", "CV", "EIS"}):
            try:
                color_detection = detect_single_trace_color(image_path, plot_box_pixels)
                if color_detection.get("status") == "UNIQUE_CHROMATIC_FAMILY":
                    color_rgb = color_detection["color_rgb"]
            except OptionalDependencyError:
                color_detection = {"status": "UNAVAILABLE", "reason": "OPTIONAL_IMAGE_DEPENDENCY_MISSING"}
        y_axis_text_color_association = {"status": "NOT_EVALUATED"}
        trace_color_rgb = (
            color_detection.get("color_rgb") if isinstance(color_detection, dict)
            else color_rgb
        )
        if (
            y_cal is None
            and len(y_axis_calibrations) > 1
            and image_path is not None
            and isinstance(trace_color_rgb, (list, tuple))
            and len(trace_color_rgb) == 3
            and isinstance(axis_label_evidence, dict)
            and isinstance(axis_label_evidence.get("candidates"), dict)
        ):
            axis_ocr_rows = ocr_axis_evidence if isinstance(ocr_axis_evidence, dict) else {}
            side_matches = []
            side_color_evidence = {}
            try:
                axis_spine_detection = detect_colored_y_axis_spines(
                    image_path, tuple(plot_box_pixels)
                )
            except OptionalDependencyError:
                axis_spine_detection = {
                    "status": "UNAVAILABLE",
                    "reason": "OPTIONAL_IMAGE_DEPENDENCY_MISSING",
                    "sides": {},
                }
            curve_color_match = (
                color_detection.get("color_match")
                if isinstance(color_detection, dict) else None
            )
            curve_hue = (
                float(curve_color_match["hue_center_degrees"])
                if isinstance(curve_color_match, dict)
                and curve_color_match.get("space") == "HSV_HUE_FAMILY"
                and curve_color_match.get("hue_center_degrees") is not None
                else None
            )
            for side, evidence_key, label_key in (
                ("LEFT", "y_left_evidence", "y_left"),
                ("RIGHT", "y_right_evidence", "y_right"),
            ):
                tick_ink = estimate_ocr_text_ink_color(
                    image_path, axis_ocr_rows.get(evidence_key, [])
                )
                label_rows = (
                    axis_label_evidence.get("candidates", {}).get(label_key, [])
                    if isinstance(axis_label_evidence, dict) else []
                )
                title_ink = estimate_ocr_text_ink_color(
                    image_path, label_rows[:1], minimum_colored_labels=1
                ) if label_rows else {
                    "status": "NO_AXIS_TITLE_COLOR_EVIDENCE",
                    "colored_label_count": 0,
                }
                spine_evidence = (
                    axis_spine_detection.get("sides", {}).get(side, {})
                    if isinstance(axis_spine_detection, dict) else {}
                )
                spine_ink = {
                    "status": (
                        "CHROMATIC_TEXT_COLOR_DETECTED"
                        if spine_evidence.get("status") == "CHROMATIC_Y_AXIS_SPINE_DETECTED"
                        else spine_evidence.get("status", "NO_AXIS_SPINE_COLOR_EVIDENCE")
                    ),
                    "color_rgb": spine_evidence.get("color_rgb"),
                    "hue_degrees": spine_evidence.get("hue_center_degrees"),
                    "hue_purity": spine_evidence.get("hue_purity"),
                    "vertical_row_coverage": spine_evidence.get("vertical_row_coverage"),
                    "longest_vertical_run_fraction": spine_evidence.get(
                        "longest_vertical_run_fraction"
                    ),
                    "chromatic_pixel_count": spine_evidence.get("chromatic_pixel_count", 0),
                }
                candidate_inks = []
                for source_name, ink in (
                    ("NUMERIC_TICK_LABELS", tick_ink),
                    ("AXIS_TITLE", title_ink),
                    ("AXIS_SPINE", spine_ink),
                ):
                    if (
                        ink.get("status") == "CHROMATIC_TEXT_COLOR_DETECTED"
                        and isinstance(ink.get("color_rgb"), (list, tuple))
                        and len(ink["color_rgb"]) == 3
                    ):
                        candidate_inks.append({"source": source_name, **ink})

                def ink_distance(ink):
                    if curve_hue is not None and ink.get("hue_degrees") is not None:
                        return abs(
                            (float(ink["hue_degrees"]) - curve_hue + 180.0) % 360.0 - 180.0
                        ), "HUE_DEGREES"
                    return math.sqrt(sum(
                        (float(trace_color_rgb[index]) - float(ink["color_rgb"][index])) ** 2
                        for index in range(3)
                    )), "RGB_DISTANCE"

                distances = [
                    (ink_distance(ink)[0], ink, ink_distance(ink)[1])
                    for ink in candidate_inks
                ]
                conflicting_sources = (
                    len(distances) > 1
                    and any(
                        abs(
                            (float(first[1]["hue_degrees"]) -
                             float(second[1]["hue_degrees"]) + 180.0) % 360.0 - 180.0
                        ) > 16.0
                        for index, first in enumerate(distances)
                        for second in distances[index + 1:]
                        if first[1].get("hue_degrees") is not None
                        and second[1].get("hue_degrees") is not None
                    )
                )
                matching = [
                    item for item in distances
                    if item[0] <= (14.0 if item[2] == "HUE_DEGREES" else 68.0)
                ]
                side_color_evidence[side] = {
                    "tick_labels": tick_ink,
                    "axis_title": title_ink,
                    "axis_spine": spine_evidence,
                    "candidate_inks": candidate_inks,
                    "conflicting_color_sources": conflicting_sources,
                }
                if not conflicting_sources and matching:
                    selected_ink = min(matching, key=lambda item: item[0])
                    side_matches.append((
                        side, selected_ink[0], selected_ink[1], selected_ink[2]
                    ))

            y_axis_text_color_association = {
                "status": "MATCHED" if len(side_matches) == 1 else
                          "AMBIGUOUS" if len(side_matches) > 1 else "NO_UNIQUE_MATCH",
                "curve_color_rgb": [int(value) for value in trace_color_rgb],
                "curve_hue_degrees": curve_hue,
                "side_color_evidence": side_color_evidence,
                "side_match_distances": {
                    side: round(distance, 3)
                    for side, distance, _, _ in side_matches
                },
                "axis_spine_detection": axis_spine_detection,
                "matching_rule": "UNIQUE_CURVE_TO_CHROMATIC_Y_AXIS_TEXT_OR_SPINE_COLOR",
            }
            if len(side_matches) == 1:
                selected_side, distance, selected_ink, distance_kind = side_matches[0]
                y_cal = y_axis_calibrations[selected_side]
                y_axis_anchors = y_axis_anchors_by_side[selected_side]
                record.y_axis_side = selected_side
                y_axis_text_color_association["status"] = "MATCHED"
                y_axis_text_color_association["selected_side"] = selected_side
                calibration_errors.pop("y", None)
            elif not side_matches and automatic_color_candidate and len(y_axis_calibrations) == 2:
                # Some dual-axis figures color only one Y axis. If exactly two
                # independently detected hue families exist and exactly one
                # family is uniquely tied to one chromatic axis, the other hue
                # family may be assigned to the sole remaining axis by
                # exclusion. This is recorded as provisional evidence, never
                # treated as an explicit user-side assignment.
                family_detection = (
                    definition.get("_auto_color_detection")
                    or (color_detection.get("family_detection")
                        if isinstance(color_detection, dict) else None)
                )
                family_candidates = (
                    family_detection.get("families", [])
                    if isinstance(family_detection, dict) else []
                )
                if len(family_candidates) == 2 and curve_hue is not None:
                    sibling_hues = [
                        float(item["color_match"]["hue_center_degrees"])
                        for item in family_candidates
                        if isinstance(item.get("color_match"), dict)
                        and item["color_match"].get("hue_center_degrees") is not None
                        and abs(
                            (float(item["color_match"]["hue_center_degrees"])
                             - curve_hue + 180.0) % 360.0 - 180.0
                        ) > 2.0
                    ]
                    if len(sibling_hues) == 1:
                        sibling_matches = []
                        for side, evidence in side_color_evidence.items():
                            for ink in evidence.get("candidate_inks", []):
                                ink_hue = ink.get("hue_degrees")
                                if ink_hue is None:
                                    continue
                                distance = abs(
                                    (float(ink_hue) - sibling_hues[0] + 180.0) % 360.0 - 180.0
                                )
                                if distance <= 14.0:
                                    sibling_matches.append(side)
                                    break
                        sibling_sides = sorted(set(sibling_matches))
                        if len(sibling_sides) == 1:
                            sibling_side = sibling_sides[0]
                            residual_side = next(
                                side for side in ("LEFT", "RIGHT")
                                if side != sibling_side
                            )
                            sibling_evidence = side_color_evidence.get(sibling_side, {})
                            residual_evidence = side_color_evidence.get(residual_side, {})
                            sibling_has_spine = (
                                sibling_evidence.get("axis_spine", {}).get("status")
                                == "CHROMATIC_Y_AXIS_SPINE_DETECTED"
                            )
                            residual_has_color = bool(
                                residual_evidence.get("candidate_inks")
                            )
                            if (
                                sibling_has_spine
                                and not residual_has_color
                                and not sibling_evidence.get("conflicting_color_sources")
                                and not residual_evidence.get("conflicting_color_sources")
                            ):
                                y_cal = y_axis_calibrations[residual_side]
                                y_axis_anchors = y_axis_anchors_by_side[residual_side]
                                record.y_axis_side = residual_side
                                y_axis_text_color_association = {
                                    **y_axis_text_color_association,
                                    "status": "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
                                    "selected_side": residual_side,
                                    "sibling_color_hue_degrees": sibling_hues[0],
                                    "sibling_selected_side": sibling_side,
                                    "assignment_basis": (
                                        "TWO_HUE_FAMILIES_ONE_CHROMATIC_Y_AXIS_SPINE"
                                    ),
                                }
                                calibration_errors.pop("y", None)
            association_status = y_axis_text_color_association.get("status")
            if association_status == "MATCHED":
                selected_side = y_axis_text_color_association["selected_side"]
                selected_match = next(
                    item for item in side_matches if item[0] == selected_side
                )
                distance, selected_ink, distance_kind = selected_match[1:]
                series_axis_assignment = {
                    "status": "COLOR_MATCHED_TO_Y_AXIS_TEXT",
                    "selected_side": selected_side,
                    "available_sides": list(y_axis_calibrations),
                    "reason": None,
                    "evidence": {
                        "curve_color_rgb": [int(value) for value in trace_color_rgb],
                        "axis_color_evidence_rgb": selected_ink["color_rgb"],
                        "axis_color_evidence_source": selected_ink["source"],
                        # Preserve prior text-specific keys without
                        # mislabelling an axis spine as text.
                        "axis_text_color_rgb": (
                            selected_ink["color_rgb"]
                            if selected_ink["source"] != "AXIS_SPINE" else None
                        ),
                        "axis_text_evidence_source": (
                            selected_ink["source"]
                            if selected_ink["source"] != "AXIS_SPINE" else None
                        ),
                        "distance_kind": distance_kind,
                        "color_distance": round(distance, 3),
                    },
                }
            elif association_status == "ASSIGNED_BY_DUAL_AXIS_EXCLUSION":
                series_axis_assignment = {
                    "status": "ASSIGNED_BY_DUAL_AXIS_EXCLUSION",
                    "selected_side": y_axis_text_color_association["selected_side"],
                    "available_sides": list(y_axis_calibrations),
                    "reason": None,
                    "evidence": y_axis_text_color_association,
                }
            else:
                series_axis_assignment = {
                    "status": "AMBIGUOUS_DUAL_Y_AXIS",
                    "selected_side": None,
                    "available_sides": list(y_axis_calibrations),
                    "reason": "SERIES_TO_Y_AXIS_MAPPING_REQUIRED",
                    "evidence": y_axis_text_color_association,
                }

        plot_box_source = (
            "AUTO_PLOT_FRAME" if plot_detection and plot_detection.get("status") == "PROVISIONAL_PLOT_BOX"
            else "UPSTREAM_PANEL_GEOMETRY" if panel.get("plot_box") is not None
            else "MANUAL_OVERRIDE" if definition.get("plot_box") is not None else "UNRESOLVED"
        )
        manual_monotonic_override = (
            bool(definition.get("color_rgb"))
            and not definition.get("_auto_color_candidate")
            and isinstance(definition.get("x_axis_anchors"), list)
            and len(definition.get("x_axis_anchors", [])) >= 2
            and isinstance(definition.get("y_axis_anchors"), list)
            and len(definition.get("y_axis_anchors", [])) >= 2
        )
        trace_specification = generate_trace_specification(
            image_path, plot_box_pixels, color_detection, x_cal, y_cal, family,
            record.x_label or x_axis_label_text,
            allow_unlabelled_manual_override=manual_monotonic_override,
            allow_geometry_only=True,
        ) if image_path else {"status": "NEEDS_REVIEW", "reason": "SOURCE_IMAGE_UNAVAILABLE"}
        if definition.get("_auto_color_candidate"):
            trace_specification["automatic_color_family_candidate"] = definition["_auto_color_candidate"]
            trace_specification["automatic_color_family_detection"] = definition.get("_auto_color_detection")
        trace_specification["series_axis_assignment"] = series_axis_assignment
        trace_specification["y_axis_text_color_association"] = y_axis_text_color_association
        trace_specification["input_provenance"] = {
            "plot_box": plot_box_source,
            "x_axis_anchors": x_anchor_source or "UNRESOLVED",
            "y_axis_anchors": y_anchor_source or "UNRESOLVED",
            "color": "AUTOMATIC_COLOR_DETECTOR" if color_detection else "UNRESOLVED",
            "ocr": "OCR_EVIDENCE_PRESENT" if ocr_evidence else "NO_OCR_EVIDENCE",
        }
        if any(value == "MANUAL_OVERRIDE" for value in trace_specification["input_provenance"].values()):
            trace_specification["input_provenance"]["automation_status"] = "CONTAINS_MANUAL_OVERRIDE"
        elif trace_specification.get("status") == "READY":
            trace_specification["input_provenance"]["automation_status"] = (
                "FULLY_AUTOMATIC" if trace_specification["specification"].get(
                    "numeric_mapping_status"
                ) == "CALIBRATED_NUMERIC" else "FULLY_AUTOMATIC_GEOMETRY_ONLY"
            )
        else:
            trace_specification["input_provenance"]["automation_status"] = "NOT_READY"
        vector_selection = None
        vector_requested = bool(vector_indices) or (
            bool(plot_bbox_pdf) and not pixel_points
        )
        if (vector_requested and native_page_path and native_page_path.is_file() and plot_bbox_pdf
                and crop_mapping and crop_mapping.get("page_rotation_degrees", 0) == 0):
            try:
                if native_payload is None:
                    native_payload = _json_file(native_page_path)
                selected_paths, vector_selection = choose_vector_paths(
                    native_payload, tuple(float(value) for value in plot_bbox_pdf),
                    [int(value) for value in vector_indices] if vector_indices else None,
                )
                if selected_paths and len(selected_paths) == 1:
                    clean_points = pdf_points_to_crop_pixels(
                        selected_paths[0].points_pdf,
                        crop_left_pdf=float(crop_mapping["crop_left_pdf"]),
                        crop_top_pdf=float(crop_mapping["crop_top_pdf"]),
                        render_scale=float(crop_mapping["render_scale"]),
                    )
                    record.points = [
                        SeriesPoint(
                            point_index=point_index,
                            x=map_pixel(x_cal, point[0]) if x_cal else None,
                            y=map_pixel(y_cal, point[1]) if y_cal else None,
                            pixel_x=float(point[0]), pixel_y=float(point[1]),
                        )
                        for point_index, point in enumerate(clean_points)
                    ]
                    record.extraction_method = "PDFIUM_NATIVE_VECTOR_POLYLINE"
                    record.extraction_status = (
                        "EXTRACTED_PROVISIONAL" if x_cal and y_cal and len(record.points) >= 2
                        else "GEOMETRY_ONLY_NEEDS_REVIEW"
                    )
                    record.metadata = {
                        "path_order": "PRESERVED",
                        "data_family": family,
                        "chart_family_classification": classification,
                        "vector_object_index": selected_paths[0].object_index,
                        "vector_bbox_pdf": list(selected_paths[0].bbox_pdf),
                        "vector_stroke_rgba": selected_paths[0].stroke_rgba,
                        "vector_stroke_width_pdf": selected_paths[0].stroke_width_pdf,
                        "vector_selection": vector_selection,
                        "plot_detection": plot_detection,
                        "color_detection": color_detection,
                        "axis_text_evidence": axis_text_evidence,
                        "crop_mapping": crop_mapping,
                        "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                        "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "y_axis_calibrations": {
                            side: calibration_to_dict(calibration)
                            for side, calibration in y_axis_calibrations.items()
                        },
                        "series_axis_assignment": series_axis_assignment,
                        "y_axis_text_color_association": y_axis_text_color_association,
                        "calibration_errors": calibration_errors,
                    }
                else:
                    record.metadata = {
                        "reason": "VECTOR_PATH_CANDIDATES_REQUIRE_REVIEW",
                        "vector_selection": vector_selection,
                        "plot_detection": plot_detection,
                        "data_family": family,
                        "chart_family_classification": classification,
                        "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                        "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "y_axis_calibrations": {
                            side: calibration_to_dict(calibration)
                            for side, calibration in y_axis_calibrations.items()
                        },
                        "series_axis_assignment": series_axis_assignment,
                        "y_axis_text_color_association": y_axis_text_color_association,
                        "calibration_errors": calibration_errors,
                    }
            except (OSError, KeyError, TypeError, ValueError) as exc:
                record.metadata = {
                    "reason": "VECTOR_PATH_SELECTION_ERROR",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "data_family": family,
                    "chart_family_classification": classification,
                }
            if record.points:
                record.qc_status = "PROVISIONAL_UNCALIBRATED"
                record.review_state = "NEEDS_REVIEW"
                _attach_standardization_request(record, definition)
                results.append(record)
                continue
            if vector_selection and vector_selection.get("status") == "NEEDS_REVIEW":
                if vector_indices or not color_rgb:
                    _attach_standardization_request(record, definition)
                    results.append(record)
                    continue
                record.metadata["vector_fallback"] = "UNIQUE_RASTER_COLOR_FAMILY_AVAILABLE"
        elif vector_requested and (vector_indices or not color_rgb):
            record.metadata = {
                "reason": "VECTOR_PATH_MAPPING_UNAVAILABLE",
                "note": "Vector extraction requires an unrotated PDF page, explicit plot_bbox_pdf, crop geometry, and PDFium native path evidence.",
                "vector_object_indices": vector_indices,
                "plot_bbox_pdf": plot_bbox_pdf,
                "chart_family_classification": classification,
                "plot_detection": plot_detection,
                "calibration_errors": calibration_errors,
            }
            _attach_standardization_request(record, definition)
            results.append(record)
            continue
        record.metadata.setdefault("trace_specification", trace_specification)
        record.metadata.setdefault("axis_label_evidence", axis_label_evidence)
        if isinstance(pixel_points, list) and len(pixel_points) >= 2:
            clean_points = [(float(p[0]), float(p[1])) for p in pixel_points
                            if isinstance(p, (list, tuple)) and len(p) == 2]
            record.points = [
                SeriesPoint(
                    point_index=point_index,
                    x=map_pixel(x_cal, point[0]) if x_cal else None,
                    y=map_pixel(y_cal, point[1]) if y_cal else None,
                    pixel_x=float(point[0]), pixel_y=float(point[1]),
                )
                for point_index, point in enumerate(clean_points)
            ]
            record.extraction_method = "EXPLICIT_ORDERED_PIXEL_POLYLINE"
            record.extraction_status = (
                "EXTRACTED_PROVISIONAL" if x_cal and y_cal and len(record.points) >= 2
                else "GEOMETRY_ONLY_NEEDS_REVIEW"
            )
            record.metadata = {"path_order": "PRESERVED", "data_family": family,
                               "chart_family_classification": classification,
                               "plot_detection": plot_detection, "color_detection": color_detection,
                               "axis_text_evidence": axis_text_evidence,
                               "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                               "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "y_axis_calibrations": {
                            side: calibration_to_dict(calibration)
                            for side, calibration in y_axis_calibrations.items()
                        },
                        "series_axis_assignment": series_axis_assignment,
                        "y_axis_text_color_association": y_axis_text_color_association,
                               "calibration_errors": calibration_errors}
        elif image_path and trace_specification.get("status") == "READY":
            specification = trace_specification["specification"]
            branch_index = definition.get("_auto_trace_branch_index")
            branch_count = definition.get("_auto_trace_branch_count")
            record.points, qc = trace_monotonic_color(
                str(image_path), tuple(int(v) for v in specification["color_rgb"]),
                int(specification["color_tolerance"]),
                x_cal, y_cal,
                plot_box=tuple(specification["plot_box_pixels"]),
                color_match=specification.get("color_match"),
                branch_index=int(branch_index) if branch_index is not None else None,
                branch_count=int(branch_count) if branch_count is not None else None,
            )
            if definition.get("_auto_trace_branch_detection"):
                qc["branch_detection"] = definition["_auto_trace_branch_detection"]
            record.extraction_method = qc.get("method", "RASTER_COLOR")
            if record.points and (
                qc.get("review_required")
                or qc.get("status") == "EXTRACTED_PROVISIONAL_NEEDS_REVIEW"
            ):
                record.extraction_status = "EXTRACTED_PROVISIONAL_NEEDS_REVIEW"
                record.qc_status = qc.get("qc_status", "NEEDS_REVIEW_PARTIAL_PATH")
                record.review_state = "NEEDS_REVIEW"
            else:
                record.extraction_status = (
                    "EXTRACTED_PROVISIONAL" if record.points and x_cal and y_cal
                    else "GEOMETRY_ONLY_NEEDS_REVIEW" if record.points else "NEEDS_REVIEW"
                )
            record.metadata = {"x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                               "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "y_axis_calibrations": {
                            side: calibration_to_dict(calibration)
                            for side, calibration in y_axis_calibrations.items()
                        },
                        "series_axis_assignment": series_axis_assignment,
                        "y_axis_text_color_association": y_axis_text_color_association,
                               "calibration_errors": calibration_errors,
                               "raster_qc": qc, "axis_text_evidence": axis_text_evidence,
                               "vector_selection": vector_selection,
                               "vector_fallback": (
                                   "UNIQUE_RASTER_COLOR_FAMILY_AVAILABLE"
                                   if vector_selection and vector_selection.get("status") == "NEEDS_REVIEW"
                                   and color_rgb else None
                               ),
                               "plot_detection": plot_detection, "color_detection": color_detection,
                               "chart_family_classification": classification,
                               "axis_label_evidence": axis_label_evidence,
                               "trace_specification": trace_specification,
                               "crop_mapping": crop_mapping,
                               "plot_box_pixels": list(plot_box_pixels) if plot_box_pixels else None,
                               "y_signal_mode": "SERIES_RELATIVE_SIGNAL" if relative_signal else "CALIBRATED_NUMERIC"}
        else:
            record.metadata = {
                "reason": "NO_SUPPORTED_TRACE_SPECIFICATION",
                "note": "Automatic tracing requires supported monotonic X-axis semantics, a resolved plot region, and a separable chromatic family. Numeric axis mapping is recorded separately and may remain unresolved.",
                "trace_specification": trace_specification,
                "data_family": family,
                "plot_detection": plot_detection,
                "color_detection": color_detection,
                "chart_family_classification": classification,
                "axis_label_evidence": axis_label_evidence,
                "color_detection": color_detection,
                "trace_specification": trace_specification,
                "crop_mapping": crop_mapping,
                "plot_box_pixels": list(plot_box_pixels) if plot_box_pixels else None,
                "x_calibration": calibration_to_dict(x_cal) if x_cal else None,
                "y_calibration": calibration_to_dict(y_cal) if y_cal else None,
                        "y_axis_calibrations": {
                            side: calibration_to_dict(calibration)
                            for side, calibration in y_axis_calibrations.items()
                        },
                        "series_axis_assignment": series_axis_assignment,
                        "y_axis_text_color_association": y_axis_text_color_association,
                "calibration_errors": calibration_errors,
            }
        if record.points:
            raster_qc = record.metadata.get("raster_qc", {})
            if (
                raster_qc.get("review_required")
                or raster_qc.get("status") == "EXTRACTED_PROVISIONAL_NEEDS_REVIEW"
            ):
                # Never downgrade an explicitly partial raster trace to a
                # successful/provisional-unreviewed state in the pipeline tail.
                record.extraction_status = "EXTRACTED_PROVISIONAL_NEEDS_REVIEW"
                record.qc_status = raster_qc.get(
                    "qc_status", "NEEDS_REVIEW_PARTIAL_PATH"
                )
                record.review_state = "NEEDS_REVIEW"
            else:
                record.qc_status = "PROVISIONAL_UNCALIBRATED"
                record.review_state = "NEEDS_REVIEW"
        _attach_standardization_request(record, definition)
        results.append(record)
    return results


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for directory, _, filenames in __import__("os").walk(path):
        for name in filenames:
            try:
                total += (Path(directory) / name).stat().st_size
            except OSError:
                continue
    return total


def _paper_disk_usage(paper_output: Path) -> dict[str, int]:
    evidence_bytes = _directory_size(paper_output / "evidence")
    context_bytes = _directory_size(paper_output / "context")
    return {
        "evidence_bytes": evidence_bytes,
        "context_index_bytes": context_bytes,
        "budgeted_storage_bytes": evidence_bytes + context_bytes,
        "paper_output_bytes": _directory_size(paper_output),
    }


def _within_paper_disk_budget(
    paper_output: Path, budget_mb: int, context_index_bytes: int,
    additional_bytes: int = 0,
) -> bool:
    if budget_mb <= 0:
        return True
    evidence_bytes = _directory_size(paper_output / "evidence")
    projected_bytes = (
        evidence_bytes + max(0, context_index_bytes) + max(0, int(additional_bytes))
    )
    return projected_bytes < budget_mb * 1024 * 1024


def _crop_local_image(source_path: Path, bbox: Any, output_path: Path) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return source_path
    with Image.open(source_path) as image:
        coords = _normalize_bbox(bbox, image.width, image.height)
        if not coords:
            return source_path
        crop = image.crop(coords)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(output_path, format="PNG")
        crop.close()
    return output_path


def process_paper(input_root: Path, paper_relative: Path, output_root: Path,
                  options: dict | None = None, input_snapshot: PaperSnapshot | None = None) -> dict:
    """Process one paper with lazy pages, compact text context, and immutable inputs."""
    options = options or {}
    input_root = input_root.resolve()
    output_root = output_root.resolve()
    paper_dir = (input_root / paper_relative).resolve()
    try:
        paper_dir.relative_to(input_root)
    except ValueError as exc:
        raise ValueError("Paper path escapes input root") from exc
    relative_source = paper_dir.relative_to(input_root).as_posix()
    if input_snapshot is not None:
        if input_snapshot.source_dir != relative_source:
            raise ValueError("Supplied input snapshot does not match the requested paper directory")
        snapshot = input_snapshot
    else:
        snapshot = snapshot_paper(paper_dir, input_root)
    paper_output = output_root / "papers" / snapshot.paper_id
    existing = paper_output / "digitization.json"
    force_reviewed = bool(options.get("force_recompute_reviewed", False))
    stage_state = processing_stage_state(snapshot, paper_dir, output_root, options)
    overrides = stage_state["overrides"]
    thresholds = stage_state["qc_thresholds"]
    stage_fingerprint = stage_state["stage_fingerprint"]
    if existing.is_file():
        old = _json_file(existing)
        accepted = any(s.get("review_state") == "REVIEWED_ACCEPTED" for s in old.get("series", []))
        unchanged = (old.get("input_fingerprint") == snapshot.input_fingerprint
                     and old.get("algorithm_version") == ALGORITHM_VERSION
                     and old.get("stage_fingerprint") == stage_fingerprint)
        if unchanged and not (force_reviewed and accepted):
            cached = _cached_result(paper_output, snapshot, expected_stage_fingerprint=stage_fingerprint)
            if cached:
                cached["artifact_paths"] = {
                    "manifest_path": str(paper_output / "paper_manifest.json"),
                    "bundle_path": str(paper_output / "paper_bundle.json"),
                }
                cached["resource_usage"] = _paper_disk_usage(paper_output)
                return cached
        elif accepted and not force_reviewed:
            locked = _cached_result(paper_output, snapshot, locked=True)
            if locked:
                locked["artifact_paths"] = {
                    "manifest_path": str(paper_output / "paper_manifest.json"),
                    "bundle_path": str(paper_output / "paper_bundle.json"),
                }
                locked["resource_usage"] = _paper_disk_usage(paper_output)
                return locked
            # A broken or mismatched bundle must never cause accepted data to be
            # silently recomputed. Stop and preserve the reviewed files for recovery.
            return {
                "cached": True,
                "snapshot": snapshot.to_dict(),
                "figures": [], "panels": [], "series": [],
                "status": "BLOCKED_REVIEW_LOCKED",
                "job_state": JobState.BLOCKED.value,
                "reason": "REVIEWED_ARTIFACT_INTEGRITY_FAILURE",
                "resource_usage": _paper_disk_usage(paper_output),
            }
    if existing.is_file() and (force_reviewed or not accepted or old.get("input_fingerprint") != snapshot.input_fingerprint
                                or old.get("algorithm_version") != ALGORITHM_VERSION):
        version_key = snapshot.input_fingerprint[:12] + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        version_dir = paper_output / "versions" / f"pre-recompute-{version_key}"
        version_dir.mkdir(parents=True, exist_ok=True)
        for name in ("digitization.json", "paper_manifest.json", "figure_inventory.json", "panel_layout.json"):
            candidate = paper_output / name
            if candidate.is_file():
                shutil.copy2(candidate, version_dir / candidate.name)
        series_dir = paper_output / "series"
        if series_dir.exists():
            shutil.copytree(series_dir, version_dir / "series", dirs_exist_ok=True)
            shutil.rmtree(series_dir)
        evidence_dir = paper_output / "evidence"
        if evidence_dir.exists():
            shutil.copytree(evidence_dir, version_dir / "evidence", dirs_exist_ok=True)
            shutil.rmtree(evidence_dir)
    elif not existing.is_file():
        # A previous worker may have died after streaming panel CSVs but before
        # committing digitization.json. Such partial rows are not resumable truth.
        for partial_name in ("series", "evidence"):
            partial_path = paper_output / partial_name
            if partial_path.exists():
                shutil.rmtree(partial_path)

    memory_limit_mb = int(options.get("memory_limit_mb", 2048))
    render_scale = float(options.get("render_scale", 1.5))
    max_render_pixels = int(options.get("max_render_pixels", 12_000_000))
    temp_disk_limit_mb = int(options.get("temp_disk_limit_mb", 2048))
    _check_memory_budget(memory_limit_mb)
    context = PaperContextIndex.build(
        paper_dir, paper_output / "context",
        memory_budget_bytes=int(options.get("context_memory_budget", 500_000)),
    )
    context_index_bytes = _directory_size(paper_output / "context")
    figures_raw, inventory_path = _inventory(paper_dir, snapshot)
    semantic_figures_for_pass1 = [
        {
            "figure_id": safe_id(str(item.get("figure_id") or item.get("id") or f"Figure{index}")),
            "caption": item.get("caption") or item.get("title"),
        }
        for index, item in enumerate(figures_raw, 1) if isinstance(item, dict)
    ]
    semantic_pass1 = build_semantic_pass1(
        snapshot.paper_id, semantic_figures_for_pass1, context,
    )
    pdf_expected = "main_pdf" not in snapshot.missing_roles
    pdf_path = locate_pdf(paper_dir, input_root, snapshot)
    pdf_integrity_issue = pdf_path is None and pdf_expected
    if pdf_integrity_issue:
        snapshot.warnings.append("MAIN_PDF_CHANGED_OR_UNAVAILABLE_AFTER_SNAPSHOT")
        if "main_pdf" not in snapshot.missing_roles:
            snapshot.missing_roles.append("main_pdf")
        for source in snapshot.external_sources:
            if source.get("status") in {"HASH_VERIFIED", "HASH_COMPUTED_NO_EXPECTED_SHA256"}:
                source["status"] = "CHANGED_AFTER_SNAPSHOT"
    pdf_sha256 = None
    if pdf_path is not None:
        resolved_pdf = pdf_path.resolve()
        pdf_sha256 = next(
            (artifact.sha256 for artifact in snapshot.artifacts
             if artifact.role == "main_pdf"
             and (input_root / artifact.path).resolve() == resolved_pdf),
            None,
        )
        if pdf_sha256 is None:
            pdf_sha256 = next(
                (str(source.get("sha256")) for source in snapshot.external_sources
                 if source.get("status") in {"HASH_VERIFIED", "HASH_COMPUTED_NO_EXPECTED_SHA256"}
                 and source.get("sha256")),
                None,
            )

    figures: list[dict] = []
    panels: list[dict] = []
    series: list[SeriesRecord] = []
    review_needed = pdf_integrity_issue or "main_pdf" in snapshot.missing_roles
    backend = None
    native_evidence_by_page: dict[int, dict] = {}
    panel_comparison_items: list[dict[str, Any]] = []
    for figure_index, source_figure in enumerate(figures_raw, 1):
        if not isinstance(source_figure, dict):
            continue
        figure_id = safe_id(str(source_figure.get("figure_id") or source_figure.get("id") or f"Figure{figure_index}"))
        page_number = source_figure.get("page") or source_figure.get("page_number")
        source_doc_type = str(source_figure.get("doc_type") or "MAIN").strip().upper()
        is_main_pdf_figure = source_doc_type not in {"SI", "SUPPLEMENT", "SUPPLEMENTARY"}
        figure = {
            "figure_id": figure_id, "page": int(page_number) if page_number else None,
            "source_doc_type": source_doc_type,
            "source_asset_status": source_figure.get("image_asset_status"),
            "source_pdf_integrity_status": (
                "CHANGED_AFTER_SNAPSHOT" if pdf_integrity_issue
                else "HASH_VERIFIED" if pdf_path is not None else "NOT_AVAILABLE"
            ),
            "source_image_asset_path": source_figure.get("image_path"),
            "source_image_asset_sha256": source_figure.get("image_asset_sha256"),
            "source_image_asset_id": source_figure.get("image_asset_id"),
            "source_media_asset_metadata": source_figure.get("media_asset_metadata"),
            "source_bbox": source_figure.get("bbox") or source_figure.get("bounding_box"),
            "source_bbox_role": (
                "UPSTREAM_EVIDENCE_INDEX_BBOX_UNRESOLVED"
                if source_figure.get("image_asset_status") else "UPSTREAM_FIGURE_BBOX"
            ),
            "caption": source_figure.get("caption") or source_figure.get("title"),
            "shared_legends": source_figure.get("shared_legends") or source_figure.get("legend") or [],
            "technique": source_figure.get("technique"), "domain": source_figure.get("domain"),
        }
        if isinstance(figure["shared_legends"], str):
            figure["shared_legends"] = [{"text": figure["shared_legends"], "scope": "FIGURE"}]
        figures.append(figure)
        if pdf_path and figure["page"] and is_main_pdf_figure:
            page_number_int = int(figure["page"])
            if page_number_int not in native_evidence_by_page:
                try:
                    if backend is None:
                        backend = PdfiumBackend()
                    with backend.open(pdf_path) as doc:
                        with doc.page(page_number_int) as native_page:
                            native_payload = native_page.inspect_native_objects(
                                max_objects=5000, max_total_path_segments=12000,
                                max_segments_per_path=1500,
                            )
                    native_path = paper_output / "evidence" / f"page_{page_number_int:04d}_native.json"
                    if _within_paper_disk_budget(paper_output, temp_disk_limit_mb, context_index_bytes):
                        atomic_write_json(native_path, native_payload)
                        native_artifact = native_path.relative_to(paper_output).as_posix()
                        native_hash = sha256_file(native_path)
                    else:
                        native_artifact = None
                        native_hash = None
                    native_evidence_by_page[page_number_int] = {
                        "artifact": native_artifact,
                        "sha256": native_hash,
                        "status": "STORED" if native_artifact else "EVIDENCE_DISK_BUDGET_EXCEEDED",
                        "object_inventory_status": native_payload.get("object_inventory_status"),
                        "object_count": native_payload.get("object_count"),
                        "object_type_counts": native_payload.get("object_type_counts", {}),
                        "path_segment_count": native_payload.get("path_segment_count", 0),
                        "native_text_preview": native_payload.get("native_text", "")[:3000],
                    }
                except Exception as exc:
                    native_evidence_by_page[page_number_int] = {
                        "status": "NATIVE_EVIDENCE_UNAVAILABLE",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
        panel_sources = _figure_panels(source_figure)
        figure_layout_ocr_evidence: list[dict] = []
        if (
            len(panel_sources) == 1
            and panel_sources[0].get("segmentation_provenance") == "SINGLE_PANEL_FALLBACK"
            and source_figure.get("image_path")
        ):
            figure_image = _safe_local_file(paper_dir, str(source_figure.get("image_path")))
            if figure_image is not None:
                try:
                    # OCR boxes are useful layout evidence: axis titles, ticks and
                    # subfigure labels can otherwise bridge otherwise empty
                    # inter-panel whitespace in geometric projections. Reuse
                    # this one full-figure OCR pass for each resulting crop.
                    if options.get("ocr"):
                        try:
                            from .ocr import run_ocr
                            figure_layout_ocr_evidence = run_ocr(figure_image)
                        except Exception as ocr_exc:
                            snapshot.warnings.append(
                                f"OCR_LAYOUT_PROBE_FAILED:{figure_id}:{type(ocr_exc).__name__}"
                            )
                    # Always inspect the complete figure for multiple panel frames
                    # before accepting any one large rectangle as the only plot.
                    segmentation = detect_panel_regions(
                        figure_image,
                        ocr_rows=figure_layout_ocr_evidence or None,
                    )
                    figure["panel_segmentation"] = segmentation
                    if segmentation.get("status") == "PROVISIONAL_PANELS_DETECTED":
                        panel_sources = segmentation["panels"]
                    elif segmentation.get("status") == "SINGLE_PLOT_FRAME_DETECTED":
                        frame_box = segmentation.get("plot_frame_bbox_pixels")
                        if isinstance(frame_box, list) and len(frame_box) == 4:
                            panel_sources = [{
                                "panel_id": "auto-single-frame",
                                "plot_box": frame_box,
                                "segmentation_provenance": "AUTO_SINGLE_PLOT_FRAME_CANDIDATE",
                                "segmentation_status": "SINGLE_PLOT_FRAME_RETAINED",
                            }]
                            figure["panel_segmentation"] = {
                                "status": "SINGLE_PANEL_FRAME_RETAINED",
                                "reason": "ONE_SUPPORTED_PLOT_FRAME",
                                "plot_frame_detection": segmentation.get("plot_frame_detection"),
                                "plot_frame_bbox_pixels": frame_box,
                            }
                    else:
                        whole_plot = detect_plot_box(figure_image)
                        if whole_plot.get("status") == "PROVISIONAL_PLOT_BOX":
                            panel_sources = [{
                                "panel_id": "auto-whole-frame",
                                "plot_box": whole_plot.get("pixel_bbox"),
                                "segmentation_provenance": "AUTO_SINGLE_PLOT_FRAME_FALLBACK",
                                "segmentation_status": "SINGLE_PLOT_FRAME_RETAINED",
                            }]
                            figure["panel_segmentation"] = {
                                "status": "SINGLE_PANEL_FRAME_RETAINED",
                                "reason": "ONE_PLOT_FRAME_FALLBACK_AFTER_MULTI_PANEL_SCAN",
                                "plot_detection": whole_plot,
                                "multi_panel_detection": segmentation,
                            }
                except OptionalDependencyError as exc:
                    figure["panel_segmentation"] = {
                        "status": "UNAVAILABLE", "reason": str(exc),
                    }
        for panel_index, source_panel in enumerate(panel_sources, 1):
            panel = dict(source_panel)
            panel_id = safe_id(str(panel.get("panel_id") or panel.get("id") or panel.get("label") or panel_index))
            panel["panel_id"] = panel_id
            bbox = panel.get("bbox") or panel.get("bounding_box")
            if bbox is None and not source_figure.get("image_asset_status"):
                bbox = source_figure.get("bbox") or source_figure.get("bounding_box")
            panel_specific_image = bool(panel.get("image_path") or source_figure.get("image_path"))
            panel_path = _safe_local_file(paper_dir, panel.get("image_path") or source_figure.get("image_path"))
            saved_crop = None
            crop_mapping = None
            auto_panel_bbox = panel.get("segmentation_provenance") in {
                "AUTO_RASTER_WHITESPACE_SEGMENTATION",
                "AUTO_PLOT_FRAME_CANDIDATE_SEGMENTATION",
            }
            if panel_path and bbox and (not panel_specific_image or auto_panel_bbox):
                if _within_paper_disk_budget(paper_output, temp_disk_limit_mb, context_index_bytes):
                    saved_crop = _crop_local_image(
                        panel_path, bbox, paper_output / "evidence" / f"{figure_id}_{panel_id}.png")
                    if saved_crop is not None:
                        crop_mapping = _source_image_crop_mapping(panel_path, bbox, saved_crop)
            elif panel_path:
                try:
                    source_image_bytes = int(panel_path.stat().st_size)
                except OSError:
                    source_image_bytes = -1
                if source_image_bytes >= 0 and _within_paper_disk_budget(
                    paper_output, temp_disk_limit_mb, context_index_bytes,
                    additional_bytes=source_image_bytes,
                ):
                    suffix = panel_path.suffix.lower()
                    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
                        suffix = ".img"
                    evidence_image = (
                        paper_output / "evidence" / f"{figure_id}_{panel_id}{suffix}"
                    )
                    saved_crop = _copy_image_asset_to_evidence(
                        panel_path, evidence_image,
                        expected_sha256=figure.get("source_image_asset_sha256"),
                    )
                    if saved_crop is not None:
                        try:
                            from PIL import Image
                            with Image.open(panel_path) as source_image:
                                identity_bbox = (0, 0, source_image.width, source_image.height)
                            crop_mapping = _source_image_crop_mapping(
                                panel_path, identity_bbox, saved_crop
                            )
                        except (OSError, ImportError):
                            crop_mapping = None
                    if saved_crop is None:
                        figure["source_asset_status"] = "COPY_FAILED_OR_HASH_CHANGED_AFTER_INVENTORY"
                        source_figure["image_asset_status"] = (
                            "COPY_FAILED_OR_HASH_CHANGED_AFTER_INVENTORY"
                        )
            if (
                saved_crop is None
                and pdf_path
                and figure["page"]
                and is_main_pdf_figure
                and _may_use_source_pdf_bbox_fallback(source_figure, panel)
                and _within_paper_disk_budget(paper_output, temp_disk_limit_mb, context_index_bytes)
            ):
                if backend is None:
                    backend = PdfiumBackend()
                with backend.open(pdf_path) as doc:
                    with doc.page(int(figure["page"])) as pdf_page:
                        page_width, page_height = pdf_page.size
                        safe_scale = min(render_scale, (max_render_pixels / max(1, page_width * page_height)) ** 0.5)
                        safe_scale = max(0.25, safe_scale)
                        rendered = pdf_page.render(scale=safe_scale)
                        try:
                            coords = _normalize_bbox(bbox, rendered.width, rendered.height)
                            if coords:
                                crop = rendered.crop(coords)
                                saved_crop = paper_output / "evidence" / f"{figure_id}_{panel_id}.png"
                                saved_crop.parent.mkdir(parents=True, exist_ok=True)
                                crop.save(saved_crop, format="PNG")
                                crop.close()
                                crop_mapping = {
                                    "crop_left_pdf": coords[0] / safe_scale,
                                    "crop_top_pdf": page_height - coords[1] / safe_scale,
                                    "crop_right_pdf": coords[2] / safe_scale,
                                    "crop_bottom_pdf": page_height - coords[3] / safe_scale,
                                    "render_scale": safe_scale,
                                    "page_width_pdf": page_width,
                                    "page_height_pdf": page_height,
                                    "page_rotation_degrees": pdf_page.rotation_degrees,
                                }
                        finally:
                            rendered.close()
            _check_memory_budget(memory_limit_mb)
            ocr_evidence = []
            ocr_status = {"status": "NOT_REQUESTED"}
            if options.get("ocr"):
                if (
                    saved_crop
                    and figure_layout_ocr_evidence
                    and auto_panel_bbox
                    and isinstance(bbox, (list, tuple))
                    and len(bbox) == 4
                ):
                    # Localize full-figure OCR polygons into the saved panel crop.
                    # The crop is an unscaled pixel slice of the source image.
                    x0, y0, x1, y1 = [float(value) for value in bbox]
                    for row in figure_layout_ocr_evidence:
                        if not isinstance(row, dict):
                            continue
                        polygon = row.get("polygon")
                        if not isinstance(polygon, list) or len(polygon) < 4:
                            continue
                        try:
                            points = [
                                [float(point[0]), float(point[1])]
                                for point in polygon
                                if isinstance(point, (list, tuple)) and len(point) >= 2
                            ]
                            if len(points) < 4:
                                continue
                            center_x = sum(point[0] for point in points) / len(points)
                            center_y = sum(point[1] for point in points) / len(points)
                        except (TypeError, ValueError, OverflowError, IndexError):
                            continue
                        if x0 <= center_x < x1 and y0 <= center_y < y1:
                            localized = dict(row)
                            localized["polygon"] = [
                                [point[0] - x0, point[1] - y0]
                                for point in points
                            ]
                            ocr_evidence.append(localized)
                    ocr_status = {
                        "status": "FIGURE_OCR_REUSED" if ocr_evidence else "FIGURE_OCR_EMPTY_FOR_PANEL",
                        "record_count": len(ocr_evidence),
                        "source": "FULL_FIGURE_OCR",
                    }
                if saved_crop and not ocr_evidence:
                    try:
                        from .ocr import run_ocr
                        ocr_evidence = run_ocr(saved_crop)
                        ocr_status = {
                            "status": "SUCCEEDED" if ocr_evidence else "SUCCEEDED_EMPTY",
                            "record_count": len(ocr_evidence),
                            "source": "PANEL_CROP_OCR",
                        }
                    except Exception as exc:
                        error_message = str(exc).strip() or "No error message supplied."
                        ocr_status = {
                            "status": "FAILED",
                            "error_type": type(exc).__name__,
                            "message": error_message[:500],
                        }
                        snapshot.warnings.append(
                            f"OCR_FAILED:{figure_id}/{panel_id}:{type(exc).__name__}"
                        )
                        review_needed = True
                elif not saved_crop:
                    ocr_status = {
                        "status": "NOT_RUN",
                        "reason": "NO_SAVED_PANEL_IMAGE",
                    }
            native_summary = (
                native_evidence_by_page.get(int(figure["page"]))
                if figure["page"] and is_main_pdf_figure else None
            )
            native_file_path = (
                paper_output / native_summary["artifact"]
                if native_summary and native_summary.get("artifact") else None
            )
            extracted = _extract_panel(
                saved_crop, snapshot.paper_id, figure_id, panel_id, panel, figure,
                overrides, context, figure["page"],
                native_summary, ocr_evidence, pdf_sha256, snapshot.input_fingerprint,
                native_file_path, crop_mapping,
            )
            for item in extracted:
                item.metadata["ocr_status"] = ocr_status
            append_panel_series_csv(paper_output, figure_id, panel_id, extracted)
            has_points = any(item.points for item in extracted)
            needs_series_review = any(
                item.review_state != "REVIEWED_ACCEPTED" for item in extracted
            )
            panel_status = (
                "EXTRACTED_NEEDS_REVIEW" if has_points and needs_series_review
                else "EXTRACTED" if has_points
                else "NEEDS_REVIEW"
            )
            panel_renderings: list[dict[str, Any]] = []
            for item in extracted:
                item.evidence[0]["extraction_channel"] = item.extraction_method
                if saved_crop is not None and item.points:
                    try:
                        rendering = render_series_artifacts(
                            item, saved_crop, paper_output / "reconstructed",
                            plot_box=tuple(item.metadata.get("plot_box_pixels") or ()),
                        )
                    except (OSError, ValueError, TypeError, OptionalDependencyError) as exc:
                        rendering = {
                            "status": "RENDER_FAILED",
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    if rendering.get("status") in {"RENDERED", "GEOMETRY_ONLY_OVERLAY"}:
                        for path_key in ("reconstructed_path", "overlay_path"):
                            path_value = rendering.get(path_key)
                            if not path_value:
                                rendering[path_key] = None
                                continue
                            try:
                                rendering[path_key] = Path(path_value).resolve().relative_to(
                                    paper_output.resolve()
                                ).as_posix()
                            except (OSError, ValueError, TypeError):
                                rendering[path_key] = None
                    item.metadata["reconstruction"] = rendering
                    panel_renderings.append(rendering)
                segmentation_confidence = panel.get("segmentation_confidence")
                segmentation_confidence_status = panel.get(
                    "segmentation_confidence_status",
                    "PROVIDED_UNCALIBRATED" if segmentation_confidence is not None else "NOT_CALIBRATED",
                )
                qc_panel_context = {
                    "bbox": bbox,
                    "status": panel_status,
                    "segmentation_confidence": segmentation_confidence,
                    "segmentation_confidence_status": segmentation_confidence_status,
                    "segmentation_provenance": panel.get("segmentation_provenance"),
                    "shared_legend_refs": figure["shared_legends"],
                }
                qc_report = build_series_qc_report(item, qc_panel_context, thresholds)
                item.metadata["qc_report"] = qc_report
                item.metadata["qc_components"] = qc_report["components"]
            # Keep only compact per-series metadata in the paper worker; point batches are already persisted.
            for item in extracted:
                item.metadata.setdefault("points_count", len(item.points))
            reconstructed_absolute = None
            overlay_absolute = None
            for rendering in panel_renderings:
                if rendering.get("status") == "RENDERED":
                    relative = rendering.get("reconstructed_path")
                    candidate = paper_output / relative if relative else None
                    if candidate and candidate.is_file():
                        reconstructed_absolute = candidate
                        break
                if rendering.get("status") == "GEOMETRY_ONLY_OVERLAY":
                    relative = rendering.get("overlay_path")
                    candidate = paper_output / relative if relative else None
                    if candidate and candidate.is_file():
                        overlay_absolute = candidate
            first_metadata = extracted[0].metadata if extracted else {}
            trace_info = first_metadata.get("trace_specification") or {}
            failure_reason = (
                "AUTOMATIC_DIGITIZATION_AND_RECONSTRUCTION_COMPLETED"
                if reconstructed_absolute else
                "PIXEL_GEOMETRY_EXTRACTED_NUMERIC_AXIS_MAPPING_UNRESOLVED"
                if overlay_absolute else
                trace_info.get("reason")
                or first_metadata.get("reason")
                or first_metadata.get("raster_qc", {}).get("reason")
                or "NO_AUTOMATIC_DATA_POINTS"
            )
            panel_comparison_items.append({
                "panel_id": panel_id,
                "original_path": str(saved_crop) if saved_crop else None,
                "reconstructed_path": (
                    str(reconstructed_absolute or overlay_absolute)
                    if reconstructed_absolute or overlay_absolute else None
                ),
                "status": (
                    "RECONSTRUCTED" if reconstructed_absolute else
                    "GEOMETRY_ONLY_TRACE_OVERLAY" if overlay_absolute else
                    trace_info.get("status", "NEEDS_REVIEW")
                ),
                "reason": failure_reason,
            })
            visual_legend_candidates = []
            ignored_visual_labels = {
                "potential", "voltage", "current", "intensity", "wavenumber",
                "frequency", "capacity", "time", "temperature", "sample",
                "scan rate", "current density", "cycle number", "vs", "figure",
            }
            for ocr_row in ocr_evidence:
                if not isinstance(ocr_row, dict):
                    continue
                visual_text = " ".join(str(
                    ocr_row.get("text") or ocr_row.get("txt") or ocr_row.get("label") or ""
                ).split())
                if (
                    len(visual_text) < 2 or len(visual_text) > 64
                    or visual_text.casefold() in ignored_visual_labels
                    or not any(character.isalpha() for character in visual_text)
                    or re.fullmatch(r"[+-]?[0-9.,]+", visual_text)
                ):
                    continue
                visual_legend_candidates.append({
                    "label": visual_text,
                    "figure_id": figure_id, "panel_id": panel_id,
                    "source_type": "OCR_TEXT_CANDIDATE",
                    "evidence_id": "visual_" + sha256_json({
                        "paper_id": snapshot.paper_id, "figure_id": figure_id,
                        "panel_id": panel_id, "text": visual_text,
                        "polygon": ocr_row.get("polygon"),
                    })[:16],
                    "polygon": ocr_row.get("polygon"),
                    "confidence": ocr_row.get("score"),
                })
            deduplicated_visual = {
                (item["label"].casefold(), json.dumps(item.get("polygon"), sort_keys=True)): item
                for item in visual_legend_candidates
            }
            visual_legend_candidates = list(deduplicated_visual.values())
            for item in extracted:
                item.metadata["visual_legend_candidates"] = visual_legend_candidates
                item.points.clear()
            series.extend(extracted)
            review_needed = review_needed or panel_status in {"NEEDS_REVIEW", "EXTRACTED_NEEDS_REVIEW"}
            bbox_values_valid = (
                isinstance(bbox, (list, tuple)) and len(bbox) == 4
                and all(isinstance(value, (int, float)) for value in bbox)
            )
            inferred_normalized_bbox = (
                _validated_normalized_bbox(bbox) if bbox_values_valid else None
            )
            bbox_is_normalized = inferred_normalized_bbox is not None
            normalized_bbox = _validated_normalized_bbox(panel.get("normalized_bbox"))
            explicit_normalized_bbox_invalid = (
                panel.get("normalized_bbox") is not None and normalized_bbox is None
            )
            if normalized_bbox is None and bbox_is_normalized:
                normalized_bbox = inferred_normalized_bbox
            source_bbox = panel.get("source_bbox")
            if source_bbox is None and bbox is not None and not bbox_is_normalized:
                source_bbox = bbox
            bbox_coordinate_space = panel.get("bbox_coordinate_space")
            if explicit_normalized_bbox_invalid:
                bbox_coordinate_space = "INVALID_NORMALIZED_BBOX"
            elif not bbox_coordinate_space:
                bbox_coordinate_space = (
                    "NORMALIZED_0_1" if bbox_is_normalized
                    else "UNSPECIFIED_SOURCE_COORDINATES" if bbox is not None
                    else "NOT_PROVIDED"
                )
            segmentation_confidence = panel.get("segmentation_confidence")
            segmentation_confidence_status = panel.get(
                "segmentation_confidence_status",
                "PROVIDED_UNCALIBRATED" if segmentation_confidence is not None else "NOT_CALIBRATED",
            )
            segmentation_status = (
                "INVALID_NORMALIZED_BBOX" if explicit_normalized_bbox_invalid
                else panel.get("segmentation_status", "UNSPECIFIED")
            )
            if explicit_normalized_bbox_invalid:
                panel_status = "NEEDS_REVIEW"
                review_needed = True
            panels.append({
                "figure_id": figure_id, "panel_id": panel_id,
                "bbox": bbox,
                "source_bbox": source_bbox,
                "normalized_bbox": normalized_bbox,
                "bbox_coordinate_space": bbox_coordinate_space,
                "bbox_provenance": panel.get(
                    "bbox_provenance",
                    (
                        "FIGURE_BBOX_FALLBACK"
                        if panel.get("segmentation_provenance") == "SINGLE_PANEL_FALLBACK" and bbox is not None
                        else "UPSTREAM_PANEL_BOUNDARY" if bbox is not None else "NOT_PROVIDED"
                    ),
                ),
                "segmentation_provenance": panel.get("segmentation_provenance", "UNKNOWN"),
                "segmentation_status": segmentation_status,
                "plot_box": panel.get("plot_box"),
                "plot_box_coordinate_space": panel.get(
                    "plot_box_coordinate_space",
                    "PANEL_IMAGE_PIXELS" if auto_panel_bbox else "SOURCE_IMAGE_PIXELS",
                ),
                "plot_frame_bbox_pixels": panel.get("plot_frame_bbox_pixels"),
                "plot_frame_score": panel.get("plot_frame_score"),
                "evidence_image_path": (
                    saved_crop.relative_to(paper_output).as_posix() if saved_crop else None
                ),
                "crop_mapping": crop_mapping,
                "status": panel_status,
                "ocr_status": ocr_status,
                "segmentation_confidence": segmentation_confidence,
                "segmentation_confidence_status": segmentation_confidence_status,
                "chart_family": (
                    extracted[0].metadata.get("chart_family_classification", {}).get("chart_family", "UNCLASSIFIED")
                    if extracted else "UNCLASSIFIED"
                ),
                "chart_family_status": (
                    extracted[0].metadata.get("chart_family_classification", {}).get("status", "NEEDS_REVIEW")
                    if extracted else "NEEDS_REVIEW"
                ),
                "shared_legend_refs": figure["shared_legends"],
            })

    panel_comparison = {"status": "NOT_CREATED", "panel_count": len(panel_comparison_items)}
    if panel_comparison_items:
        comparison_path = paper_output / "comparisons" / "ALL_PANELS_COMPARISON.png"
        try:
            panel_comparison = build_panel_comparison_sheet(
                panel_comparison_items, comparison_path
            )
            panel_comparison["path"] = comparison_path.relative_to(paper_output).as_posix()
        except (OSError, ValueError, TypeError, OptionalDependencyError) as exc:
            panel_comparison = {
                "status": "RENDER_FAILED",
                "reason": f"{type(exc).__name__}: {exc}",
                "panel_count": len(panel_comparison_items),
            }

    if pdf_path is not None and pdf_sha256:
        try:
            final_pdf_hash = sha256_file(pdf_path)
        except OSError:
            final_pdf_hash = None
        if final_pdf_hash != pdf_sha256:
            snapshot.warnings.append("MAIN_PDF_CHANGED_DURING_PROCESSING")
            if "main_pdf" not in snapshot.missing_roles:
                snapshot.missing_roles.append("main_pdf")
            for source in snapshot.external_sources:
                if source.get("sha256") == pdf_sha256:
                    source["status"] = "CHANGED_DURING_PROCESSING"
            for figure in figures:
                figure["source_pdf_integrity_status"] = "CHANGED_DURING_PROCESSING"
            for panel in panels:
                panel["source_pdf_integrity_status"] = "CHANGED_DURING_PROCESSING"
            for record in series:
                for evidence in record.evidence:
                    evidence["source_pdf_integrity_status"] = "CHANGED_DURING_PROCESSING"
            review_needed = True

    if not figures:
        status = "NEEDS_REVIEW"
        review_needed = True
    else:
        status = "COMPLETED_WITH_REVIEW" if review_needed else "COMPLETED"
    job_state = JobState.NEEDS_REVIEW.value if review_needed else JobState.COMPLETED.value
    semantic_package = build_semantic_package(
        snapshot.paper_id, snapshot.input_fingerprint, figures, panels, series, context,
        pass1_state=semantic_pass1,
    )
    disk_usage = _paper_disk_usage(paper_output)
    artifacts = write_paper_artifacts(
        output_root, snapshot, figures, panels, series, status,
        semantic_artifacts=semantic_package,
        extra={"algorithm_version": ALGORITHM_VERSION,
               "context_index_fingerprint": context.fingerprint,
               "figure_inventory_source": inventory_path.name if inventory_path else None,
               "pdf_source": pdf_path.name if pdf_path else None,
               "native_page_evidence": native_evidence_by_page,
               "stage_fingerprint": stage_fingerprint,
               "memory_limit_mb": memory_limit_mb, "render_scale": render_scale,
               "temp_disk_limit_mb": temp_disk_limit_mb,
               "evidence_bytes": disk_usage["evidence_bytes"],
               "context_index_bytes": disk_usage["context_index_bytes"],
               "budgeted_storage_bytes": disk_usage["budgeted_storage_bytes"],
               "qc_threshold_status": thresholds["status"],
               "qc_thresholds": thresholds,
               "algorithm_implementation_fingerprint": stage_state["algorithm_implementation_fingerprint"],
               "profile_config_fingerprint": stage_state["profile_config_fingerprint"],
               "llm_tokens": 0,
               "panel_comparison": panel_comparison},
    )
    return {
        "cached": False, "snapshot": snapshot.to_dict(), "figures": figures, "panels": panels,
        "series": [asdict(s) for s in series], "status": status, "job_state": job_state,
        "artifact_paths": {
            "manifest_path": str(Path(artifacts["paper_root"]) / "paper_manifest.json"),
            "bundle_path": str(Path(artifacts["paper_root"]) / "paper_bundle.json"),
        },
        "context_fingerprint": context.fingerprint,
        "resource_usage": disk_usage,
        "figure_count": len(figures), "panel_count": len(panels), "series_count": len(series),
        "panel_comparison": panel_comparison,
        "semantic_status": semantic_package["cross_validation"]["status"],
        "semantic_artifacts": {
            "caption_semantics": str(Path(artifacts["paper_root"]) / "caption_semantics.json"),
            "sample_registry": str(Path(artifacts["paper_root"]) / "sample_registry.json"),
            "synthesis_processes": str(Path(artifacts["paper_root"]) / "synthesis_processes.json"),
            "experiments": str(Path(artifacts["paper_root"]) / "experiments.json"),
            "cross_validation": str(Path(artifacts["paper_root"]) / "cross_validation.json"),
        },
    }
