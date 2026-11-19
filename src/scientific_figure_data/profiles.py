from __future__ import annotations

from pathlib import Path
from typing import Any

PROFILE_ROOT = Path(__file__).resolve().parents[2] / "configs" / "profiles"


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load domain profiles; install the base package.") from exc
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Profile configuration must be a mapping: {path}")
    return value


def _merge(parent: dict, child: dict) -> dict:
    result = dict(parent)
    for key, value in child.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        elif isinstance(value, list) and isinstance(result.get(key), list):
            result[key] = [*result[key], *[v for v in value if v not in result[key]]]
        else:
            result[key] = value
    return result


def load_profile(name: str, profile_root: Path | None = None, _seen: set[str] | None = None) -> dict:
    root = profile_root or PROFILE_ROOT
    key = name.lower()
    seen = _seen or set()
    if key in seen:
        raise ValueError(f"Profile inheritance cycle: {' -> '.join([*seen, key])}")
    directory = root / key
    metadata = _read_yaml(directory / "profile.yaml")
    if not metadata:
        raise KeyError(f"Unknown profile: {name}")
    seen = {*seen, key}
    combined: dict[str, Any] = {}
    for parent in metadata.get("inherits", []):
        combined = _merge(combined, load_profile(str(parent), root, seen))
    techniques = _read_yaml(directory / "techniques.yaml")
    analytes = _read_yaml(directory / "analytes.yaml")
    combined = _merge(combined, metadata)
    combined = _merge(combined, techniques)
    if analytes:
        combined = _merge(combined, analytes)
    combined["profile_name"] = key
    combined["profile_root"] = str(directory)
    return combined
