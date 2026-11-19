from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
import time
from pathlib import Path


def _rss_bytes() -> int | None:
    try:
        import psutil
        return int(psutil.Process(os.getpid()).memory_info().rss)
    except ImportError:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(counters)
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return int(counters.WorkingSetSize)
            except Exception:
                return None
        try:
            import resource
            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return int(value * (1024 if value < 10**9 else 1))
        except Exception:
            return None


def probe_pdf(path: Path, render_scale: float = 1.0) -> dict:
    result = {"path": str(path), "size_bytes": path.stat().st_size, "status": "NOT_RUN"}
    before = _rss_bytes()
    started = time.perf_counter()
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(path))
        page_count = len(doc)
        page_rows = []
        for page_index in range(page_count):
            page = doc[page_index]
            t0 = time.perf_counter()
            page_row = {"page": page_index + 1, "width": page.get_width(), "height": page.get_height()}
            try:
                text_page = page.get_textpage()
                try:
                    page_row["text_chars"] = len(text_page.get_text_range())
                finally:
                    text_page.close()
                bitmap = page.render(scale=render_scale)
                try:
                    pil_image = bitmap.to_pil()
                    page_row["render_size"] = list(pil_image.size)
                    pil_image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
            page_row["elapsed_seconds"] = round(time.perf_counter() - t0, 4)
            page_row["rss_bytes_after_page"] = _rss_bytes()
            page_rows.append(page_row)
        doc.close()
        result.update({"status": "OK", "backend": "pypdfium2", "page_count": page_count,
                       "pages": page_rows, "elapsed_seconds": round(time.perf_counter() - started, 4)})
        try:
            import pypdfium2.raw as raw
            symbols = dir(raw)
            result["raw_api_symbols"] = {
                "page_object_enumeration": [s for s in symbols if "FPDFPage_CountObjects" in s or "FPDFPage_GetObject" in s],
                "path_segments": [s for s in symbols if "FPDFPath" in s],
                "note": "Symbol presence is not proof of complete nested-object extraction."
            }
        except Exception as exc:
            result["raw_api_probe_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        result.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    result["peak_rss_bytes"] = _rss_bytes()
    result["rss_before_bytes"] = before
    result["platform"] = platform.platform()
    for module in ("pdfminer", "pikepdf", "fitz", "PIL", "cv2", "psutil"):
        result.setdefault("installed_modules", {})[module] = importlib.util.find_spec(module) is not None
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare PDF extraction/render behavior on supplied PDFs.")
    parser.add_argument("pdfs", nargs="*", type=Path)
    parser.add_argument("--out", type=Path, default=Path("backend_probe_report.json"))
    parser.add_argument("--render-scale", type=float, default=1.0)
    args = parser.parse_args(argv)
    if not args.pdfs:
        payload = {"status": "NO_INPUT_PDFS", "note": "Supply 3–5 representative PDFs for the required technical spike.",
                   "candidate_modules": {m: importlib.util.find_spec(m) is not None
                                         for m in ("pypdfium2", "pdfminer", "pikepdf", "fitz")}}
    else:
        if len(args.pdfs) > 5:
            parser.error("The initial spike accepts at most five PDFs per run.")
        payload = {"status": "COMPLETED_WITH_MEASUREMENTS",
                   "results": [probe_pdf(p, args.render_scale) for p in args.pdfs]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
