from __future__ import annotations

import math

UNIT_FACTORS = {
    ("s", "min"): 1 / 60, ("min", "s"): 60,
    ("min", "h"): 1 / 60, ("h", "min"): 60,
    ("s", "h"): 1 / 3600, ("h", "s"): 3600,
    ("mg/L", "g/L"): 1 / 1000, ("g/L", "mg/L"): 1000,
    ("uM", "mM"): 1 / 1000, ("mM", "uM"): 1000,
}


def convert_dimensionally(value: float, source_unit: str, target_unit: str) -> float:
    if source_unit == target_unit:
        return float(value)
    try:
        factor = UNIT_FACTORS[(source_unit, target_unit)]
    except KeyError as exc:
        raise ValueError(f"No approved deterministic conversion: {source_unit} -> {target_unit}") from exc
    return float(value) * factor


def resolve_reference_scale(value: float, target_scale: str, details: dict) -> dict:
    """Apply only an explicitly documented conversion; never infer offsets from labels."""
    required = ("reference_electrode", "filling_solution", "filling_concentration",
                "temperature_k", "electrolyte", "pH", "formula_id", "formula_evidence_id",
                "scale_factor", "offset_v")
    missing = [key for key in required if details.get(key) in (None, "")]
    if missing:
        return {"value": None, "status": "REFERENCE_CONVERSION_UNRESOLVED",
                "missing_conditions": missing, "original_value": float(value)}
    factor = float(details["scale_factor"])
    offset = float(details["offset_v"])
    original = float(value)
    if not math.isfinite(original) or not math.isfinite(factor) or not math.isfinite(offset):
        raise ValueError("Reference conversion value, scale_factor and offset_v must be finite")
    if factor == 0:
        raise ValueError("Reference conversion scale_factor cannot be zero")
    converted = original * factor + offset
    if not math.isfinite(converted):
        raise ValueError("Reference conversion produced a non-finite value")
    return {
        "value": converted,
        "status": "CONVERTED_WITH_EXPLICIT_EVIDENCE",
        "target_scale": target_scale,
        "formula_id": details["formula_id"],
        "formula_evidence_id": details["formula_evidence_id"],
        "conditions": {key: details[key] for key in required[:5]},
    }


def comparable_battery_records(a: dict, b: dict) -> tuple[bool, list[str]]:
    """Return comparable only when every required basis is explicit and equal."""
    keys = ("capacity_basis", "cell_scope", "current_density_basis", "cycling_protocol")
    mismatches = []
    for key in keys:
        value_a = a.get(key)
        value_b = b.get(key)
        if value_a in (None, "") or value_b in (None, ""):
            mismatches.append(f"{key}:UNRESOLVED")
        elif str(value_a).strip().casefold() != str(value_b).strip().casefold():
            mismatches.append(key)
    return not mismatches, mismatches


def pfas_metric_warning(metric_a: str | None, metric_b: str | None) -> str | None:
    distinct = {"parent_removal", "defluorination", "mineralization", "fluoride_release",
                "total_fluorine", "organic_fluorine"}
    if not metric_a or not metric_b:
        return "PFAS_METRIC_UNRESOLVED"
    left = metric_a.strip().casefold()
    right = metric_b.strip().casefold()
    if left in distinct and right in distinct and left != right:
        return "PFAS_METRICS_ARE_NOT_INTERCHANGEABLE"
    if left != right:
        return "PFAS_METRIC_COMPARABILITY_NOT_ESTABLISHED"
    return None


def preserve_censored_value(raw_value: str) -> dict:
    import re
    censored = re.fullmatch(r"\s*(<|<=|>|>=)\s*(LOD|LOQ)\s*", raw_value, re.I)
    if censored:
        return {"raw": raw_value, "comparator": censored.group(1),
                "limit_type": censored.group(2).upper(), "numeric_value": None,
                "status": "CENSORED_VALUE"}
    match = re.fullmatch(r"\s*(<=|>=|<|>)\s*([0-9]*\.?[0-9]+)\s*(.*)", raw_value)
    if match:
        return {"raw": raw_value, "comparator": match.group(1),
                "limit_value": float(match.group(2)), "unit": match.group(3).strip(),
                "numeric_value": None, "status": "CENSORED_VALUE"}
    return {"raw": raw_value, "status": "UNPARSED_RAW_VALUE"}
