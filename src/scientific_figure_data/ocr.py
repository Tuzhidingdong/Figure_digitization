from __future__ import annotations

from pathlib import Path
from typing import Any

_ENGINE = None

# Explicit CPU-only, single-threaded inference. RapidOCR currently defaults
# ONNX Runtime thread counts to -1 (auto); that is unsafe when several native
# libraries coexist on a low-resource Windows worker.
_RAPIDOCR_PARAMS = {
    "Det.engine_type": "onnxruntime",
    "Cls.engine_type": "onnxruntime",
    "Rec.engine_type": "onnxruntime",
    "EngineConfig.onnxruntime.use_cuda": False,
    "EngineConfig.onnxruntime.use_dml": False,
    "EngineConfig.onnxruntime.intra_op_num_threads": 1,
    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
}


def _as_list(value):
    if value is None:
        return []
    converter = getattr(value, "tolist", None)
    return converter() if callable(converter) else list(value)


def run_ocr(image_path: Path) -> list[dict[str, Any]]:
    """Run optional CPU OCR with a process-local lazily initialized engine.

    OCR is deterministic/local preprocessing, not an LLM call. The engine is
    constructed once per paper worker and reused across selected figures.
    """
    global _ENGINE
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError("OCR requires the optional extra: pip install '.[ocr]'") from exc

    if _ENGINE is None:
        _ENGINE = RapidOCR(params=dict(_RAPIDOCR_PARAMS))

    result = _ENGINE(str(image_path))
    if result is None:
        return []

    boxes = _as_list(getattr(result, "boxes", None))
    texts = list(getattr(result, "txts", ()) or ())
    scores = list(getattr(result, "scores", ()) or ())
    if not (len(boxes) == len(texts) == len(scores)):
        raise RuntimeError(
            "RapidOCR returned inconsistent boxes/txts/scores lengths; "
            f"received {len(boxes)}/{len(texts)}/{len(scores)}"
        )
    output = []
    for box, text, score in zip(boxes, texts, scores):
        try:
            output.append({
                "text": str(text),
                "confidence": float(score),
                "polygon": _as_list(box),
            })
        except (TypeError, ValueError, OverflowError):
            continue
    return output


def reset_ocr_engine_for_tests() -> None:
    """Clear the process-local singleton; intended for tests and controlled teardown."""
    global _ENGINE
    _ENGINE = None
