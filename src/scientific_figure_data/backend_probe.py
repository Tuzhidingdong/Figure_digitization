from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


def _memory_bytes() -> dict[str, int | None]:
    current = None
    peak = None
    try:
        import psutil
        info = psutil.Process(os.getpid()).memory_info()
        current = int(info.rss)
        # Windows exposes peak_wset; some other platforms expose peak_rss.
        peak_value = getattr(info, "peak_wset", None)
        if peak_value is None:
            peak_value = getattr(info, "peak_rss", None)
        peak = int(peak_value) if peak_value is not None else current
    except ImportError:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(counters)
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    current = int(counters.WorkingSetSize)
                    peak = int(counters.PeakWorkingSetSize)
            except Exception:
                pass
        else:
            try:
                import resource
                value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                # Linux reports KiB; macOS reports bytes.
                peak = value * 1024 if sys.platform.startswith("linux") else value
                current = peak
            except Exception:
                pass
    return {"rss_bytes": current, "peak_rss_bytes": peak}


def _module_version(module_name: str) -> str | None:
    distributions = {
        "pypdfium2": "pypdfium2",
        "pdfminer": "pdfminer.six",
        "pikepdf": "pikepdf",
    }
    try:
        return importlib.metadata.version(distributions.get(module_name, module_name))
    except importlib.metadata.PackageNotFoundError:
        return None


def _walk_layout(layout):
    """Yield one page's PDFMiner layout tree without retaining previous pages."""
    stack = [layout]
    while stack:
        item = stack.pop()
        yield item
        children = getattr(item, "_objs", None)
        if children:
            stack.extend(reversed(children))


def _probe_pdfium(path: Path, render_scale: float) -> dict:
    from .pdf_backend import PdfiumBackend

    result = {
        "backend": "pypdfium2",
        "version": _module_version("pypdfium2"),
        "status": "NOT_RUN",
        "pages": [],
    }
    started = time.perf_counter()
    max_rss = _memory_bytes().get("peak_rss_bytes")
    try:
        backend = PdfiumBackend()
        with backend.open(path) as document:
            result["page_count"] = len(document)
            for page_number in range(1, len(document) + 1):
                page_started = time.perf_counter()
                with document.page(page_number) as page:
                    width, height = page.size
                    native = page.inspect_native_objects(
                        max_objects=5000,
                        max_total_path_segments=12000,
                        max_segments_per_path=1500,
                    )
                    image = page.render(scale=render_scale)
                    try:
                        render_size = list(image.size)
                    finally:
                        image.close()
                memory = _memory_bytes()
                if memory["peak_rss_bytes"] is not None:
                    max_rss = max(max_rss or 0, memory["peak_rss_bytes"])
                result["pages"].append({
                    "page": page_number,
                    "width_pdf_points": width,
                    "height_pdf_points": height,
                    "render_size_pixels": render_size,
                    "native_text_chars": len(native.get("native_text", "")),
                    "object_inventory_status": native.get("object_inventory_status"),
                    "object_count": native.get("object_count"),
                    "object_type_counts": native.get("object_type_counts", {}),
                    "path_segment_count": native.get("path_segment_count", 0),
                    "path_geometry_complete": native.get("path_geometry_complete", False),
                    "elapsed_seconds": round(time.perf_counter() - page_started, 4),
                    "rss_bytes_after_page": memory["rss_bytes"],
                    "peak_rss_bytes_after_page": memory["peak_rss_bytes"],
                    "native_inventory_error": native.get("object_inventory_error"),
                })
        result["status"] = "OK"
    except Exception as exc:
        result.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    result["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    result["peak_rss_bytes_observed"] = max_rss
    return result


def _probe_pdfminer(path: Path) -> dict:
    result = {
        "backend": "pdfminer.six",
        "version": _module_version("pdfminer"),
        "status": "NOT_INSTALLED",
        "pages": [],
        "limitations": "PDFMiner layout objects are evidence of text/curve/image layout, not a lossless PDF object model.",
    }
    if importlib.util.find_spec("pdfminer") is None:
        return result

    started = time.perf_counter()
    max_rss = _memory_bytes().get("peak_rss_bytes")
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTCurve, LTImage, LTTextContainer

        result["pages"] = []
        for page_number, layout in enumerate(extract_pages(str(path), laparams=None, caching=False), 1):
            page_started = time.perf_counter()
            counts = Counter()
            text_chars = 0
            for item in _walk_layout(layout):
                if isinstance(item, LTTextContainer):
                    text_chars += len(item.get_text())
                if isinstance(item, LTCurve):
                    counts["curve_like_layout_objects"] += 1
                if isinstance(item, LTImage):
                    counts["images"] += 1
                counts[type(item).__name__] += 1
            memory = _memory_bytes()
            if memory["peak_rss_bytes"] is not None:
                max_rss = max(max_rss or 0, memory["peak_rss_bytes"])
            result["pages"].append({
                "page": page_number,
                "width_pdf_points": float(getattr(layout, "width", 0.0)),
                "height_pdf_points": float(getattr(layout, "height", 0.0)),
                "text_chars": text_chars,
                "layout_object_counts": dict(counts),
                "elapsed_seconds": round(time.perf_counter() - page_started, 4),
                "rss_bytes_after_page": memory["rss_bytes"],
                "peak_rss_bytes_after_page": memory["peak_rss_bytes"],
            })
            del layout
        result["page_count"] = len(result["pages"])
        result["status"] = "OK"
    except Exception as exc:
        result.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    result["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    result["peak_rss_bytes_observed"] = max_rss
    return result


def _probe_pikepdf(path: Path) -> dict:
    result = {
        "backend": "pikepdf/QPDF",
        "version": _module_version("pikepdf"),
        "status": "NOT_INSTALLED",
        "pages": [],
        "limitations": (
            "Content-stream operator inventory is not a semantic trace extractor. "
            "This probe does not recursively interpret all Form XObject graphics state."
        ),
    }
    if importlib.util.find_spec("pikepdf") is None:
        return result

    started = time.perf_counter()
    max_rss = _memory_bytes().get("peak_rss_bytes")
    try:
        pikepdf = importlib.import_module("pikepdf")
        path_ops = {"m", "l", "c", "v", "y", "h", "re"}
        paint_ops = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n"}
        text_ops = {"BT", "ET", "Tj", "TJ", "'", '"'}
        with pikepdf.open(path) as pdf:
            result["page_count"] = len(pdf.pages)
            for page_number, page in enumerate(pdf.pages, 1):
                page_started = time.perf_counter()
                counts = Counter()
                # Parsing is performed one page at a time; no corpus-wide stream list is retained.
                instructions = pikepdf.parse_content_stream(page)
                for instruction in instructions:
                    if hasattr(instruction, "operator"):
                        operator = str(instruction.operator)
                    elif isinstance(instruction, tuple) and len(instruction) >= 2:
                        operator = str(instruction[1])
                    else:
                        counts["unclassified_instructions"] += 1
                        continue
                    counts[f"operator:{operator}"] += 1
                    if operator in path_ops:
                        counts["path_construction_ops"] += 1
                    if operator in paint_ops:
                        counts["path_paint_ops"] += 1
                    if operator in text_ops:
                        counts["text_ops"] += 1
                    if operator == "Do":
                        counts["xobject_invocations"] += 1
                    if operator == "BI":
                        counts["inline_images"] += 1
                resources = page.obj.get("/Resources", {})
                xobjects = resources.get("/XObject", {}) if resources else {}
                xobject_types = Counter()
                try:
                    for _, xobject in xobjects.items():
                        xobject_types[str(xobject.get("/Subtype", "/Unknown"))] += 1
                except Exception:
                    pass
                memory = _memory_bytes()
                if memory["peak_rss_bytes"] is not None:
                    max_rss = max(max_rss or 0, memory["peak_rss_bytes"])
                result["pages"].append({
                    "page": page_number,
                    "operator_counts": dict(counts),
                    "path_construction_ops": counts["path_construction_ops"],
                    "path_paint_ops": counts["path_paint_ops"],
                    "xobject_invocations": counts["xobject_invocations"],
                    "xobject_resource_types": dict(xobject_types),
                    "elapsed_seconds": round(time.perf_counter() - page_started, 4),
                    "rss_bytes_after_page": memory["rss_bytes"],
                    "peak_rss_bytes_after_page": memory["peak_rss_bytes"],
                })
                del instructions
        result["status"] = "OK"
    except Exception as exc:
        result.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    result["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    result["peak_rss_bytes_observed"] = max_rss
    return result


def probe_pdf(path: Path, render_scale: float = 1.0) -> dict:
    if not path.is_file():
        return {"path": str(path), "status": "MISSING_FILE"}
    before = _memory_bytes()
    result = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "platform": platform.platform(),
        "render_scale": render_scale,
        "rss_before_bytes": before["rss_bytes"],
        "peak_rss_before_bytes": before["peak_rss_bytes"],
        "candidates": {},
    }
    result["candidates"]["pypdfium2"] = _probe_pdfium(path, render_scale)
    result["candidates"]["pdfminer.six"] = _probe_pdfminer(path)
    result["candidates"]["pikepdf/QPDF"] = _probe_pikepdf(path)
    result["status"] = "COMPLETED_WITH_MEASUREMENTS"
    after = _memory_bytes()
    result["rss_after_bytes"] = after["rss_bytes"]
    result["peak_rss_after_bytes"] = after["peak_rss_bytes"]
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure PDFium, PDFMiner, and pikepdf/QPDF on 3–5 representative PDFs."
    )
    parser.add_argument("pdfs", nargs="*", type=Path)
    parser.add_argument("--out", type=Path, default=Path("backend_probe_report.json"))
    parser.add_argument("--render-scale", type=float, default=1.0)
    args = parser.parse_args(argv)
    if not 0.1 <= args.render_scale <= 4:
        parser.error("--render-scale must be between 0.1 and 4")
    if not args.pdfs:
        candidates = {}
        for module in ("pypdfium2", "pdfminer", "pikepdf"):
            candidates[module] = {
                "installed": importlib.util.find_spec(module) is not None,
                "version": _module_version(module),
            }
        payload = {
            "status": "NO_INPUT_PDFS",
            "note": "Supply 3–5 user-approved representative PDFs; no backend selection is made without measurements.",
            "candidate_modules": candidates,
        }
    else:
        if not 3 <= len(args.pdfs) <= 5:
            parser.error("The backend technical spike requires 3–5 representative PDFs.")
        payload = {
            "status": "COMPLETED_WITH_MEASUREMENTS",
            "candidate_scope": ["pypdfium2/PDFium", "pdfminer.six", "pikepdf/QPDF"],
            "results": [probe_pdf(p, args.render_scale) for p in args.pdfs],
            "selection_policy": (
                "Do not select a backend from package names or license alone. Compare measured "
                "page coverage, vector/object evidence, text, memory, timing, clipping, rotation, "
                "Form XObjects, and path fragmentation. Manual visual inspection remains required."
            ),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
