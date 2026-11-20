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
    original = float(value)
    if not math.isfinite(original):
        raise ValueError("Dimensional conversion requires a finite numeric value")
    if source_unit == target_unit:
        return original
    try:
        factor = UNIT_FACTORS[(source_unit, target_unit)]
    except KeyError as exc:
        raise ValueError(f"No approved deterministic conversion: {source_unit} -> {target_unit}") from exc
    converted = original * factor
    if not math.isfinite(converted):
        raise ValueError("Dimensional conversion produced a non-finite value")
    return converted


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
        "conversion": {"scale_factor": factor, "offset_v": offset},
        "conditions": {key: details[key] for key in required[:6]},
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


def aop_metric_warning(metric_a: str | None, metric_b: str | None) -> str | None:
    """Keep AOP concentration, efficiency, kinetics and mineralization metrics distinct."""
    distinct = {
        "parent_concentration", "removal_efficiency", "rate_constant",
        "toc", "cod", "mineralization",
    }
    if not metric_a or not metric_b:
        return "AOP_METRIC_UNRESOLVED"
    left = metric_a.strip().casefold()
    right = metric_b.strip().casefold()
    if left in distinct and right in distinct and left != right:
        return "AOP_METRICS_ARE_NOT_INTERCHANGEABLE"
    if left != right:
        return "AOP_METRIC_COMPARABILITY_NOT_ESTABLISHED"
    return None


def domain_semantic_warnings(
    domain: str | None, metadata: dict, technique: str | None = None,
) -> list[str]:
    """Validate only explicit per-series semantics; never infer missing scientific fields."""
    semantics = metadata.get("measurement_semantics")
    if not isinstance(semantics, dict):
        semantics = {}
    metric = (
        semantics.get("metric") or semantics.get("measurement_metric")
        or metadata.get("metric") or metadata.get("measurement_metric")
    )
    comparison_target = (
        semantics.get("comparison_target_metric")
        or metadata.get("comparison_target_metric")
    )
    normalized_domain = str(domain or "").strip().casefold()
    warnings: list[str] = []

    if normalized_domain in {"aop", "advanced_oxidation", "advanced oxidation"}:
        if not metric:
            warnings.append("AOP_METRIC_UNRESOLVED")
        elif comparison_target:
            warning = aop_metric_warning(str(metric), str(comparison_target))
            if warning:
                warnings.append(warning)

    elif normalized_domain in {"pfas", "pfoa"}:
        if not metric:
            warnings.append("PFAS_METRIC_UNRESOLVED")
        elif comparison_target:
            warning = pfas_metric_warning(str(metric), str(comparison_target))
            if warning:
                warnings.append(warning)

    elif normalized_domain in {"battery", "energy_storage"}:
        metric_text = str(metric or "").strip().casefold()
        technique_text = str(technique or "").strip().upper()
        capacity_metric = any(token in metric_text for token in ("capacity", "specific_capacity"))
        capacity_technique = technique_text in {
            "GCD", "GITT", "CHARGE_DISCHARGE", "BATTERY_PERFORMANCE",
        }
        if not metric_text and capacity_technique:
            warnings.append("BATTERY_MEASUREMENT_METRIC_UNRESOLVED")
        elif capacity_metric:
            required = (
                "capacity_basis", "cell_scope", "current_density_basis", "cycling_protocol",
            )
            for key in required:
                value = semantics.get(key, metadata.get(key))
                if value in (None, ""):
                    warnings.append(f"BATTERY_BASIS_UNRESOLVED:{key}")
        comparison_basis = semantics.get("comparison_basis")
        if isinstance(comparison_basis, dict):
            comparable, mismatches = comparable_battery_records(semantics, comparison_basis)
            if not comparable:
                category = (
                    "BATTERY_COMPARABILITY_UNRESOLVED"
                    if any(item.endswith(":UNRESOLVED") for item in mismatches)
                    else "BATTERY_COMPARABILITY_MISMATCH"
                )
                warnings.append(category + ":" + ",".join(mismatches))
    return warnings


def preserve_censored_value(raw_value: str) -> dict:
    """Preserve censored scalar values without converting them to numeric zero.

    Explicit numeric LOD/LOQ limits are retained when written next to the
    comparator. The original source string is always kept verbatim.
    """
    import re

    if not isinstance(raw_value, str):
        return {"raw": raw_value, "numeric_value": None, "status": "UNPARSED_RAW_VALUE"}

    normalized = raw_value.replace("≤", "<=").replace("≥", ">=")
    comparator = r"(?P<comparator><=|>=|<|>)"
    number = r"(?P<limit_value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    limit = re.fullmatch(
        rf"\s*{comparator}\s*(?P<limit_type>LOD|LOQ)"
        rf"(?:\s*(?:=|:)\s*{number}\s*(?P<unit>.*))?\s*",
        normalized, re.I,
    )
    if limit:
        value = limit.group("limit_value")
        return {
            "raw": raw_value,
            "comparator": limit.group("comparator"),
            "limit_type": limit.group("limit_type").upper(),
            "limit_value": float(value) if value is not None else None,
            "unit": (limit.group("unit") or "").strip() or None,
            "numeric_value": None,
            "status": "CENSORED_VALUE",
        }

    numeric_limit = re.fullmatch(
        rf"\s*{comparator}\s*{number}\s*(?P<unit>.*)\s*",
        normalized,
    )
    if numeric_limit:
        return {
            "raw": raw_value,
            "comparator": numeric_limit.group("comparator"),
            "limit_value": float(numeric_limit.group("limit_value")),
            "unit": (numeric_limit.group("unit") or "").strip() or None,
            "numeric_value": None,
            "status": "CENSORED_VALUE",
        }

    return {"raw": raw_value, "numeric_value": None, "status": "UNPARSED_RAW_VALUE"}

def standardize_measurement_value(value: float, original_unit: str | None,
                                  target_unit: str | None) -> dict:
    """Return original and optional standardized values without guessing conversions."""
    original_value = float(value)
    result = {
        "original_value": original_value,
        "original_unit": original_unit,
        "standardized_value": None,
        "standardized_unit": target_unit,
        "standardization_status": "NOT_REQUESTED" if not target_unit else "UNRESOLVED",
        "method_id": None,
        "evidence_id": None,
    }
    if not target_unit:
        return result
    if not math.isfinite(original_value):
        result["standardization_status"] = "UNRESOLVED_NON_FINITE_VALUE"
        return result
    if not original_unit:
        result["standardization_status"] = "UNRESOLVED_MISSING_ORIGINAL_UNIT"
        return result
    try:
        standardized = convert_dimensionally(original_value, original_unit, target_unit)
    except ValueError:
        result["standardization_status"] = "UNRESOLVED_UNSUPPORTED_CONVERSION"
        return result
    result.update({
        "standardized_value": standardized,
        "standardization_status": "DETERMINISTIC_DIMENSIONAL_CONVERSION",
        "method_id": "DIMENSIONAL_FACTOR_TABLE_V1",
        "evidence_id": f"unit-factor:{original_unit}->{target_unit}",
    })
    return result
