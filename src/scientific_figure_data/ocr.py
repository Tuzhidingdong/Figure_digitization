from __future__ import annotations

from pathlib import Path
from typing import Any

_ENGINE = None


def run_ocr(image_path: Path) -> list[dict[str, Any]]:
    """Run optional on-demand OCR. The RapidOCR engine is process-local and reused."""
    global _ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError("OCR requires the optional extra: pip install '.[ocr]'") from exc
    if _ENGINE is None:
        _ENGINE = RapidOCR()
    result = _ENGINE(str(image_path))
    rows = result[0] if isinstance(result, tuple) else result
    output = []
    for row in rows or []:
        try:
            box, text, score = row
            output.append({"text": str(text), "confidence": float(score), "polygon": box})
        except (TypeError, ValueError):
            continue
    return output
