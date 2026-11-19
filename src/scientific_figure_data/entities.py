from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubjectEntity:
    entity_id: str
    canonical_name: str
    entity_type: str
    domain: str | None = None
    aliases: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


def link_series_to_subject(
    series_id: str, entity: SubjectEntity | None, role_in_series: str,
    evidence: dict[str, Any] | None, *, exact_match: bool,
) -> dict:
    """Create an evidence-backed link; ambiguous aliases are never promoted automatically."""
    if entity is None or not exact_match or not evidence:
        return {
            "series_id": series_id, "entity_id": "UNKNOWN", "role_in_series": role_in_series,
            "status": "UNASSIGNED", "evidence": evidence or {},
        }
    return {
        "series_id": series_id, "entity_id": entity.entity_id,
        "canonical_name": entity.canonical_name, "entity_type": entity.entity_type,
        "domain": entity.domain, "aliases": entity.aliases, "role_in_series": role_in_series,
        "status": "ASSIGNED_WITH_EVIDENCE", "evidence": evidence,
    }
