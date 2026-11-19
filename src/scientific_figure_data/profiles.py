from __future__ import annotations

from pathlib import Path

PROFILE_DEFAULTS = {
    "battery": {
        "domain": "battery",
        "techniques": ["XRD", "Raman", "FTIR", "XPS", "CV", "GCD", "EIS", "GITT"],
        "distinct_metrics": ["gravimetric_capacity", "areal_capacity", "volumetric_capacity",
                             "positive_electrode_capacity", "negative_electrode_capacity",
                             "full_cell_capacity", "half_cell_capacity"],
    },
    "aop": {
        "domain": "aop",
        "techniques": ["degradation_kinetics", "C/C0_time", "TOC", "COD", "radical_quenching"],
        "distinct_metrics": ["parent_concentration", "removal_efficiency", "rate_constant",
                             "TOC", "COD", "mineralization"],
    },
    "pfas": {
        "domain": "pfas",
        "techniques": ["parent_compound_time", "fluoride_release", "fluorine_balance", "LC-MS/MS"],
        "distinct_metrics": ["parent_removal", "defluorination", "mineralization",
                             "fluoride_release", "total_fluorine", "organic_fluorine"],
    },
}


def load_profile(name: str, profile_root: Path | None = None) -> dict:
    key = name.lower()
    if key not in PROFILE_DEFAULTS:
        raise KeyError(f"Unknown profile: {name}")
    return dict(PROFILE_DEFAULTS[key])
