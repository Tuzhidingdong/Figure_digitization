from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_REVIEW = "COMPLETED_WITH_REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED_PERMANENT = "FAILED_PERMANENT"


class ReviewState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEWED_ACCEPTED = "REVIEWED_ACCEPTED"
    PATCH_CONFLICT_STALE_BASE = "PATCH_CONFLICT_STALE_BASE"


@dataclass(slots=True)
class InputArtifact:
    path: str
    role: str
    size_bytes: int
    mtime_ns: int
    sha256: str


@dataclass(slots=True)
class PaperSnapshot:
    paper_id: str
    source_dir: str
    detected_upstream_version: str | None
    adapter_version: str
    created_at: str
    artifacts: list[InputArtifact] = field(default_factory=list)
    missing_roles: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_fingerprint: str = ""
    external_sources: list[dict[str, Any]] = field(default_factory=list)
    # Runtime-only, hash-verified source path. Never serialize absolute local paths.
    resolved_main_pdf: Path | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("resolved_main_pdf", None)
        return payload


@dataclass(slots=True)
class AxisAnchor:
    pixel: float
    value: float


@dataclass(slots=True)
class AxisCalibration:
    axis: str
    unit: str | None
    slope: float
    intercept: float
    anchors: list[AxisAnchor]
    rmse: float
    status: str = "CALIBRATED_NUMERIC"


@dataclass(slots=True)
class SeriesPoint:
    point_index: int
    x: float | str | None
    y: float | None
    pixel_x: float | None = None
    pixel_y: float | None = None
    y_err_low: float | None = None
    y_err_high: float | None = None
    err_type: str = "UNKNOWN"


@dataclass(slots=True)
class SeriesRecord:
    series_id: str
    paper_id: str
    figure_id: str
    panel_id: str
    technique: str | None
    domain: str | None
    label: str | None
    x_label: str | None
    y_label: str | None
    x_unit: str | None
    y_unit: str | None
    measurement_id: str | None = None
    y_axis_side: str = "UNASSIGNED"
    extraction_method: str = "UNRESOLVED"
    extraction_status: str = "NEEDS_REVIEW"
    qc_status: str = "PROVISIONAL_UNCALIBRATED"
    review_state: str = ReviewState.NEEDS_REVIEW.value
    points: list[SeriesPoint] = field(default_factory=list)
    subject_links: list[dict[str, Any]] = field(default_factory=list)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    scale_type: str = "UNKNOWN"
    baseline_comparable: bool | None = None
    offset_value: float | None = None
    normalization_provenance: dict[str, Any] | None = None


@dataclass(slots=True)
class ConditionValue:
    raw_text: str
    value_kind: str = "UNKNOWN"
    operator: str = "UNKNOWN"
    numeric_values: list[float] = field(default_factory=list)
    text_values: list[str] = field(default_factory=list)
    unit_raw: str | None = None
    unit_canonical: str | None = None
    uncertainty: dict[str, Any] | None = None
    normalization_basis: str | None = None
    parse_status: str = "UNRESOLVED"


@dataclass(slots=True)
class Condition:
    condition_id: str
    name: str
    value: Any
    unit: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    condition_scope: str = "UNRESOLVED"
    scope_entity_id: str | None = None
    value_structured: ConditionValue | None = None


@dataclass(slots=True)
class Measurement:
    measurement_id: str
    paper_id: str
    technique: str | None
    domain: str | None
    condition_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    subject_roles: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SynthesisProcess:
    process_id: str
    paper_id: str
    method_text: str
    process_status: str
    condition_ids: list[str] = field(default_factory=list)
    input_materials: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SampleProcessStep:
    sample_id: str
    process_id: str
    step_order: int
    step_role: str
    evidence_id: str
    scope_status: str


@dataclass(slots=True)
class SeriesSubjectLink:
    series_id: str
    subject_entity_id: str | None
    subject_role: str
    link_status: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SeriesMeasurementLink:
    series_id: str
    measurement_id: str | None
    measurement_role: str
    link_status: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceItem:
    evidence_id: str
    source_type: str
    source_path: str | None
    snippet: str
    source_sha256: str | None = None
    page_number: int | None = None
    figure_id: str | None = None
    panel_id: str | None = None
    line_number: int | None = None
    parser_version: str | None = None


@dataclass(slots=True)
class CrossValidationResult:
    series_id: str
    status: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EntityRelationship:
    parent_entity_id: str
    child_entity_id: str
    relationship: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DataObservation:
    observation_id: str
    paper_id: str
    name: str
    raw_value: Any
    unit: str | None = None
    source: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FigureRecord:
    figure_id: str
    paper_id: str
    source_page: int | None
    caption: str | None
    panels: list[dict[str, Any]] = field(default_factory=list)
    shared_legends: list[dict[str, Any]] = field(default_factory=list)


def safe_id(value: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return cleaned[:120] or "unnamed"


def namespaced_id(namespace: str, value: str, max_length: int = 120) -> str:
    """Create a stable globally scoped identifier without silent normalization collisions."""
    import re
    from .hashing import sha256_json

    if max_length < 20:
        raise ValueError("max_length must be at least 20")
    value_text = str(value)
    existing_prefix = f"{namespace}__"
    if value_text.startswith(existing_prefix) and len(value_text) <= max_length:
        return value_text
    raw = f"{namespace}__{value_text}"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip()).strip("-.") or "unnamed"
    if cleaned == raw and len(cleaned) <= max_length:
        return cleaned
    digest = sha256_json(raw)[:12]
    return f"{cleaned[:max_length - 13]}_{digest}"
