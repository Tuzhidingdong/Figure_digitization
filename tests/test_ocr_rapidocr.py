from __future__ import annotations

import pytest


def test_rapidocr_310_cpu_configuration_uses_public_enum_and_constructs():
    rapidocr = pytest.importorskip("rapidocr")
    from scientific_figure_data.ocr import _build_rapidocr_params

    engine_type = rapidocr.EngineType
    params = _build_rapidocr_params(engine_type)

    for stage in ("Det", "Cls", "Rec"):
        value = params[f"{stage}.engine_type"]
        assert isinstance(value, engine_type)
        assert value is engine_type.ONNXRUNTIME

    # RapidOCR >=3.10.0 lazily loads model weights on first inference.
    # Construction checks the real parameter parser without downloading
    # model files or running OCR in the CI job.
    engine = rapidocr.RapidOCR(params=params)
    assert engine is not None
