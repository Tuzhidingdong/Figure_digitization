from __future__ import annotations

import math
from dataclasses import asdict

from .models import AxisAnchor, AxisCalibration


def fit_linear_axis(axis: str, anchors: list[dict], unit: str | None = None) -> AxisCalibration:
    """Fit value = slope * pixel + intercept using explicit, evidence-backed anchors."""
    if len(anchors) < 2:
        raise ValueError("At least two numeric anchors are required for linear calibration")
    points = [AxisAnchor(float(a["pixel"]), float(a["value"])) for a in anchors]
    xs = [p.pixel for p in points]
    ys = [p.value for p in points]
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom == 0:
        raise ValueError("Calibration anchors have identical pixel coordinates")
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - slope * xbar
    if not math.isfinite(slope) or not math.isfinite(intercept) or slope == 0:
        raise ValueError("Calibration produced a non-finite or zero slope")
    residuals = [slope * x + intercept - y for x, y in zip(xs, ys)]
    rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    return AxisCalibration(axis, unit, slope, intercept, points, rmse)


def map_pixel(calibration: AxisCalibration, pixel: float) -> float:
    return calibration.slope * float(pixel) + calibration.intercept


def calibration_to_dict(calibration: AxisCalibration) -> dict:
    return {
        "axis": calibration.axis, "unit": calibration.unit, "slope": calibration.slope,
        "intercept": calibration.intercept, "anchors": [asdict(a) for a in calibration.anchors],
        "rmse": calibration.rmse, "status": calibration.status,
    }
