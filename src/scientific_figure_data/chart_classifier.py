from __future__ import annotations

import re
import unicodedata


TECHNIQUE_RULES = (
    ("CV", ("cyclic voltammetry", "cyclic voltammogram", "current density", "potential", "scan rate")),
    ("EIS", ("electrochemical impedance", "nyquist", "z''", "z′′", "z'' vs", "imaginary impedance")),
    ("XRD", ("2theta", "2 theta", "2θ", "diffraction angle", "x-ray diffraction")),
    ("Raman", ("raman shift", "raman spectra", "cm-1", "cm⁻¹")),
    ("FTIR", ("ftir", "infrared spectra", "wavenumber")),
    ("XPS", ("binding energy", "xps", "photoelectron")),
    ("GCD", ("charge-discharge", "charge/discharge", "galvanostatic", "discharge time")),
    ("GITT", ("gitt", "intermittent titration")),
)

SPECTRAL_TECHNIQUES = {"XRD", "Raman", "FTIR", "XPS"}
NON_MONOTONIC_TECHNIQUES = {"CV", "EIS"}


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("−", "-").replace("–", "-").replace("′", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def classify_chart_family(
    technique: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    caption: str | None = None,
    native_text: str | None = None,
) -> dict:
    """Deterministic conservative chart-family preclassification; no LLM or inference by values."""
    explicit = (technique or "").strip()
    x_text = _normalize(x_label)
    y_text = _normalize(y_label)
    context = " ".join(_normalize(value) for value in (caption, native_text, x_label, y_label) if value)
    if explicit:
        normalized_technique = explicit.upper()
        if normalized_technique in NON_MONOTONIC_TECHNIQUES:
            return {
                "technique": normalized_technique,
                "chart_family": "NON_MONOTONIC_CURVE",
                "status": "CLASSIFIED_FROM_UPSTREAM_METADATA",
                "confidence": 1.0,
                "evidence": [{"source": "upstream_technique", "value": explicit}],
            }
        if normalized_technique in SPECTRAL_TECHNIQUES:
            return {
                "technique": normalized_technique,
                "chart_family": "SPECTRUM",
                "y_signal_mode": "SERIES_RELATIVE_SIGNAL",
                "status": "CLASSIFIED_FROM_UPSTREAM_METADATA",
                "confidence": 1.0,
                "evidence": [{"source": "upstream_technique", "value": explicit}],
            }
        if normalized_technique in {"GCD", "GITT"}:
            return {
                "technique": normalized_technique,
                "chart_family": "TIME_SERIES",
                "status": "CLASSIFIED_FROM_UPSTREAM_METADATA",
                "confidence": 1.0,
                "evidence": [{"source": "upstream_technique", "value": explicit}],
            }

    matches = []
    for candidate, terms in TECHNIQUE_RULES:
        hit_terms = [term for term in terms if _normalize(term) in context]
        if hit_terms:
            matches.append((candidate, hit_terms))
    unique = {candidate for candidate, _ in matches}
    if len(unique) == 1:
        candidate = next(iter(unique))
        evidence = [{"source": "caption_or_axis_text", "term": term}
                    for tech, terms in matches if tech == candidate for term in terms]
        if candidate in NON_MONOTONIC_TECHNIQUES:
            family = "NON_MONOTONIC_CURVE"
        elif candidate in SPECTRAL_TECHNIQUES:
            family = "SPECTRUM"
        else:
            family = "TIME_SERIES"
        return {
            "technique": candidate,
            "chart_family": family,
            "y_signal_mode": "SERIES_RELATIVE_SIGNAL" if candidate in SPECTRAL_TECHNIQUES else None,
            "status": "PROVISIONAL_TEXT_CLASSIFICATION",
            "confidence": 0.85,
            "evidence": evidence,
        }

    if any(token in x_text for token in ("time", "min", "hour", " h", " s")) and any(
        token in y_text for token in ("concentration", "c/c0", "c0", "removal", "fluoride", "f-")
    ):
        return {
            "technique": None,
            "chart_family": "TIME_SERIES",
            "status": "PROVISIONAL_AXIS_SEMANTIC_CLASSIFICATION",
            "confidence": 0.72,
            "evidence": [{"source": "axis_semantics", "x_label": x_label, "y_label": y_label}],
        }

    return {
        "technique": None,
        "chart_family": "UNCLASSIFIED",
        "status": "NEEDS_REVIEW",
        "confidence": None,
        "evidence": [],
    }
