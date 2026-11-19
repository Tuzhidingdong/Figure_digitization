from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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
            return bitmap.to_pil()
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
