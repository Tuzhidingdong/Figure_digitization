from __future__ import annotations

import ctypes
import importlib
from contextlib import contextmanager
from pathlib import Path

from .errors import OptionalDependencyError


class PdfiumBackend:
    """Lazy PDFium adapter. Only the current page is rendered."""

    name = "pypdfium2"

    def __init__(self):
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise OptionalDependencyError(
                "PDF rendering requires the optional dependency: pip install '.[pdf]'"
            ) from exc
        self._pdfium = pdfium

    @contextmanager
    def open(self, path: Path):
        document = self._pdfium.PdfDocument(str(path))
        try:
            yield PdfDocumentView(document, self._pdfium)
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()


class PdfDocumentView:
    def __init__(self, document, pdfium):
        self._document = document
        self._pdfium = pdfium

    def __len__(self) -> int:
        return len(self._document)

    @contextmanager
    def page(self, page_number: int):
        if page_number < 1 or page_number > len(self._document):
            raise IndexError(f"PDF page number must be in 1..{len(self._document)}")
        page = self._document[page_number - 1]
        try:
            yield PdfPageView(page, self._pdfium)
        finally:
            close = getattr(page, "close", None)
            if callable(close):
                close()


class PdfPageView:
    TYPE_NAMES = {
        1: "TEXT", 2: "PATH", 3: "IMAGE", 4: "SHADING", 5: "FORM"
    }

    def __init__(self, page, pdfium):
        self._page = page
        self._pdfium = pdfium

    @property
    def size(self) -> tuple[float, float]:
        return float(self._page.get_width()), float(self._page.get_height())

    def render(self, scale: float = 1.5):
        if scale <= 0 or scale > 8:
            raise ValueError("render scale must be greater than 0 and no more than 8")
        bitmap = self._page.render(scale=scale)
        try:
            # Copy the pixels before closing PDFium's bitmap; some PIL modes share its buffer.
            return bitmap.to_pil().copy()
        finally:
            close = getattr(bitmap, "close", None)
            if callable(close):
                close()

    def text_page(self) -> str:
        textpage = self._page.get_textpage()
        try:
            return textpage.get_text_range()
        finally:
            close = getattr(textpage, "close", None)
            if callable(close):
                close()

    def inspect_native_objects(
        self, *, max_objects: int = 20000, max_total_path_segments: int = 30000,
        max_segments_per_path: int = 2000,
    ) -> dict:
        """Inventory native objects and bounded vector geometry for one PDF page.

        Textpage ownership is explicit because PDFium text objects returned by
        get_objects() need the associated PdfTextPage in order to extract text.
        Paths are geometry evidence only, never automatically classified as plotted curves.
        """
        try:
            raw = importlib.import_module("pypdfium2.raw")
        except ImportError:
            raw = None

        textpage = self._page.get_textpage()
        try:
            native_text = textpage.get_text_range()
        except Exception:
            native_text = ""
        summary = {
            "backend": self.name,
            "object_inventory_status": "UNAVAILABLE",
            "object_count": 0,
            "object_type_counts": {},
            "objects": [],
            "native_text": native_text,
            "path_geometry_complete": False,
            "truncation": None,
            "coordinate_system": "PDF_PAGE_SPACE",
        }
        if raw is None or not hasattr(self._page, "get_objects"):
            close = getattr(textpage, "close", None)
            if callable(close):
                close()
            return summary

        type_names = {}
        for constant_name, label in (
            ("FPDF_PAGEOBJ_TEXT", "TEXT"),
            ("FPDF_PAGEOBJ_PATH", "PATH"),
            ("FPDF_PAGEOBJ_IMAGE", "IMAGE"),
            ("FPDF_PAGEOBJ_SHADING", "SHADING"),
            ("FPDF_PAGEOBJ_FORM", "FORM"),
        ):
            value = getattr(raw, constant_name, None)
            if value is not None:
                type_names[int(value)] = label
        if not type_names:
            type_names = dict(self.TYPE_NAMES)

        total_segments = 0
        objects = []
        try:
            iterator = self._page.get_objects(max_depth=20, textpage=textpage)
            for object_index, obj in enumerate(iterator):
                if object_index >= max_objects:
                    summary["truncation"] = "MAX_OBJECTS"
                    break
                obj_type = int(getattr(obj, "type", -1))
                type_name = type_names.get(obj_type, f"UNKNOWN_{obj_type}")
                counts = summary["object_type_counts"]
                counts[type_name] = counts.get(type_name, 0) + 1
                row = {
                    "object_index": object_index,
                    "object_type": type_name,
                    "form_level": int(getattr(obj, "level", 0) or 0),
                    "bounds_pdf": None,
                    "path_matrix": None,
                }
                try:
                    row["bounds_pdf"] = [float(v) for v in obj.get_bounds()]
                except Exception:
                    pass
                if type_name == "TEXT":
                    try:
                        row["text"] = obj.extract()
                        row["font_size"] = float(obj.get_font_size())
                        font = obj.get_font()
                        if font is not None:
                            try:
                                row["font_name"] = font.get_base_name()
                            finally:
                                close_font = getattr(font, "close", None)
                                if callable(close_font):
                                    close_font()
                    except Exception as exc:
                        row["text_extract_error"] = f"{type(exc).__name__}: {exc}"
                elif type_name == "IMAGE":
                    try:
                        row["pixel_size"] = list(obj.get_px_size())
                    except Exception:
                        row["pixel_size"] = None
                    try:
                        row["matrix"] = list(obj.get_matrix().get())
                    except Exception:
                        pass
                elif type_name == "PATH":
                    row["segments"] = []
                    try:
                        matrix = obj.get_matrix()
                        row["path_matrix"] = [float(v) for v in matrix.get()]
                        count = int(raw.FPDFPath_CountSegments(obj))
                        row["segment_count"] = count
                        take = min(max(0, count), max_segments_per_path,
                                   max(0, max_total_path_segments - total_segments))
                        for segment_index in range(take):
                            segment = raw.FPDFPath_GetPathSegment(obj, segment_index)
                            if not segment:
                                continue
                            x = ctypes.c_float()
                            y = ctypes.c_float()
                            ok = raw.FPDFPathSegment_GetPoint(segment, ctypes.byref(x), ctypes.byref(y))
                            segment_type = int(raw.FPDFPathSegment_GetType(segment))
                            if ok:
                                page_x, page_y = matrix.on_point(float(x.value), float(y.value))
                                point = [float(page_x), float(page_y)]
                            else:
                                point = None
                            close_path = bool(raw.FPDFPathSegment_GetClose(segment))
                            row["segments"].append({
                                "index": segment_index, "type": segment_type,
                                "point_pdf": point, "closes_subpath": close_path,
                            })
                            total_segments += 1
                        if take < count:
                            row["segments_truncated"] = True
                    except Exception as exc:
                        row["path_extract_error"] = f"{type(exc).__name__}: {exc}"
                else:
                    try:
                        row["matrix"] = [float(v) for v in obj.get_matrix().get()]
                    except Exception:
                        pass
                objects.append(row)
        except Exception as exc:
            summary["object_inventory_status"] = "PARTIAL_ERROR"
            summary["object_inventory_error"] = f"{type(exc).__name__}: {exc}"
        else:
            summary["object_inventory_status"] = "OK"
        finally:
            close = getattr(textpage, "close", None)
            if callable(close):
                close()
        summary["objects"] = objects
        summary["object_count"] = len(objects)
        summary["path_segment_count"] = total_segments
        summary["path_geometry_complete"] = summary["object_inventory_status"] == "OK" and not summary["truncation"]
        return summary
