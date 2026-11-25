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
    entity_kind: str = "SAMPLE"
    resolution_status: str = "UNRESOLVED"


@dataclass
class SubjectEntityAlias:
    subject_entity_id: str
    alias: str
    alias_type: str
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



def assert_acyclic_process_graph(edges) -> None:
    """Reject cycles in explicit process-to-process dependency edges."""
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if isinstance(edge, dict):
            parent = str(edge.get("parent_process_id") or "")
            child = str(edge.get("child_process_id") or "")
        else:
            try:
                parent, child = (str(edge[0]), str(edge[1]))
            except (TypeError, IndexError) as exc:
                raise ValueError("Process DAG edges must contain parent and child IDs") from exc
        if not parent or not child:
            raise ValueError("Process DAG edge IDs must be non-empty")
        adjacency.setdefault(parent, set()).add(child)
        adjacency.setdefault(child, set())

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str):
        if node in visiting:
            raise ValueError(f"Synthesis process graph contains a cycle at {node!r}")
        if node in visited:
            return
        visiting.add(node)
        for child in sorted(adjacency.get(node, ())):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(adjacency):
        visit(node)
