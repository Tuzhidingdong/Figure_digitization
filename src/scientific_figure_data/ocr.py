from __future__ import annotations

from pathlib import Path
from typing import Any

_ENGINE = None
_ENGINE_INITIALIZATION_ERROR: str | None = None


class OCREngineInitializationError(RuntimeError):
    """RapidOCR could not initialize in this worker process."""


# Explicit CPU-only, single-threaded inference. RapidOCR currently defaults
# ONNX Runtime thread counts to -1 (auto); that is unsafe when several native
# libraries coexist on a low-resource Windows worker.
_RAPIDOCR_PARAMS = {
    "EngineConfig.onnxruntime.use_cuda": False,
    "EngineConfig.onnxruntime.use_dml": False,
    "EngineConfig.onnxruntime.intra_op_num_threads": 1,
    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
}


def _build_rapidocr_params(engine_type: Any) -> dict[str, Any]:
    """Build parameters using RapidOCR's public EngineType enum contract."""
    params = dict(_RAPIDOCR_PARAMS)
    for stage in ("Det", "Cls", "Rec"):
        params[f"{stage}.engine_type"] = engine_type.ONNXRUNTIME
    return params


def _as_list(value):
    if value is None:
        return []
    converter = getattr(value, "tolist", None)
    return converter() if callable(converter) else list(value)


def run_ocr(image_path: Path) -> list[dict[str, Any]]:
    """Run optional CPU OCR with a process-local lazily initialized engine.

    OCR is deterministic/local preprocessing, not an LLM call. The engine is
    constructed once per paper worker and reused across selected figures.
    Initialization failures are cached for this worker so every later panel
    receives a concise diagnostic without repeatedly constructing the engine.
    """
    global _ENGINE, _ENGINE_INITIALIZATION_ERROR
    try:
        from rapidocr import EngineType, RapidOCR
    except ImportError as exc:
        from .errors import OptionalDependencyError
        raise OptionalDependencyError("OCR requires the optional extra: pip install '.[ocr]'") from exc

    if _ENGINE_INITIALIZATION_ERROR is not None:
        raise OCREngineInitializationError(
            "RapidOCR initialization previously failed: "
            f"{_ENGINE_INITIALIZATION_ERROR}"
        )

    if _ENGINE is None:
        try:
            _ENGINE = RapidOCR(params=_build_rapidocr_params(EngineType))
        except Exception as exc:
            _ENGINE_INITIALIZATION_ERROR = f"{type(exc).__name__}: {exc}"
            raise OCREngineInitializationError(
                f"RapidOCR initialization failed: {_ENGINE_INITIALIZATION_ERROR}"
            ) from exc

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
    """Clear the process-local singleton and initialization failure state."""
    global _ENGINE, _ENGINE_INITIALIZATION_ERROR
    _ENGINE = None
    _ENGINE_INITIALIZATION_ERROR = None
