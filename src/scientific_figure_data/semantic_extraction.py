from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from .models import namespaced_id

UNIT_CANONICAL = {
    "°c": "degC", "℃": "degC", "k": "K",
    "mv s−1": "mV/s", "mv/s": "mV/s", "a g−1": "A/g",
    "ma cm−2": "mA/cm2", "ml min−1": "mL/min",
    "h": "h", "hr": "h", "hour": "h", "hours": "h",
    "min": "min", "minute": "min", "minutes": "min",
    "s": "s", "sec": "s", "second": "s", "seconds": "s",
    "v": "V", "mv": "mV", "a": "A", "ma": "mA",
    "m": "mol/L", "mol/l": "mol/L", "mm": "mmol/L",
    "mmol/l": "mmol/L", "um": "umol/L", "μm": "umol/L",
    "mg/l": "mg/L", "mg l−1": "mg/L", "mg l-1": "mg/L",
    "g/l": "g/L", "g l−1": "g/L", "g l-1": "g/L",
    "hz": "Hz", "khz": "kHz", "mhz": "MHz",
    "%": "%", "wt.%": "wt.%", "rpm": "rpm",
}
UNIT_PATTERN = (
    r"°C|℃|K|mV[ \t]*s(?:[ \t]*-[ \t]*1|−1)?|mV/s|A[ \t]*g(?:[ \t]*-[ \t]*1|−1)?|"
    r"mA[ \t]*cm(?:[ \t]*-[ \t]*2|−2)?|mg[ \t]*L(?:[ \t]*-[ \t]*1|−1)?|mg/L|g/L|"
    r"mmol/L|mol/L|mM|uM|μM|µM|M|kHz|MHz|Hz|mV|V|mA|A|h|hr|hours?|"
    r"min|minutes?|s|sec|seconds?|wt[.]%|%|rpm|bar|MPa|mL[ \t]*min(?:[ \t]*-[ \t]*1|−1)?"
)
NUMBER = r"[+-]?(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)(?:[eE][+-]?[0-9]+)?"
LIST_QUANTITY_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<expr>{NUMBER}(?:[ \t]*,[ \t]*{NUMBER}){{2,}}[ \t]*(?:{UNIT_PATTERN}))",
    re.IGNORECASE,
)
QUANTITY_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<expr>(?:<=|>=|<|>|≤|≥|~|≈|about[ \t]+)?[ \t]*{NUMBER}"
    rf"(?:[ \t]*(?:–|—|-|to)[ \t]*{NUMBER})?"
    rf"(?:[ \t]*(?:±|[+]/-)[ \t]*{NUMBER})?"
    rf"[ \t]*(?:{UNIT_PATTERN}))",
    re.IGNORECASE,
)
PANEL_MARKER_RE = re.compile(r"[(][ \t]*([a-z])[ \t]*[)]", re.IGNORECASE)
SAMPLE_MENTION_RE = re.compile(
    r"[ \t]*\b(?:sample|specimen|electrode|catalyst|material)[-_ ]+"
    r"([A-Za-z0-9][A-Za-z0-9_.@+/-]{0,40})\b",
    re.IGNORECASE,
)
TECHNIQUES = {
    "CV": r"\bcyclic voltammetr(?:y|ic)|\bCV\b",
    "GCD": r"\bgalvanostatic charge.?discharge|\bGCD\b",
    "EIS": r"\belectrochemical impedance|\bEIS\b",
    "GITT": r"\bGITT\b|\bgalvanostatic intermittent titration",
    "XRD": r"\bX.?ray diffraction|\bXRD\b",
    "Raman": r"\bRaman\b",
    "FTIR": r"\bFT.?IR\b|\binfrared spectroscopy",
    "XPS": r"\bXPS\b|\bX.?ray photoelectron",
    "SEM": r"\bSEM\b|\bscanning electron microscopy",
    "TEM": r"\bTEM\b|\btransmission electron microscopy",
    "UV_VIS": r"\bUV.?Vis\b|\bultraviolet.?visible",
    "LSV": r"\bLSV\b|\blinear sweep voltammetr",
    "CA": r"\bchronoamperometr",
    "TGA": r"\bTGA\b|\bthermogravimetric",
}
SYNTHESIS_HINTS = (
    "synthes", "hydrothermal", "solvothermal", "precursor", "calcination",
    "calcined", "anneal", "pyrolysis", "mixed", "stirred", "dried", "washed",
    "heat-treated", "heating rate", "furnace", "preparation", "prepared by",
)
EXPERIMENT_HINTS = (
    "scan rate", "current density", "electrolyte", "potential window", "voltage window",
    "frequency", "cycle", "measured", "measurement", "tested", "experiment",
    "reaction", "irradiation", "flow rate", "working electrode", "counter electrode",
    "reference electrode", "galvanostatic", "voltammetry", "impedance",
)
GENERIC_SERIES_LABELS = {
    "", "series", "series 1", "series 2", "unknown", "unassigned", "curve",
    "curve 1", "curve 2", "data", "data 1",
}


def stable_id(namespace: str, value: str) -> str:
    digest = hashlib.sha256(f"{namespace}\0{value}".encode("utf-8")).hexdigest()[:16]
    return f"{namespace}_{digest}"


def normalize_alias(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


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


def parse_condition_value(raw_text: str) -> ConditionValue:
    raw = " ".join(str(raw_text).strip().split())
    result = ConditionValue(raw_text=raw)
    if not raw:
        return result
    unit_match = re.search(rf"({UNIT_PATTERN})[ \t]*$", raw, re.IGNORECASE)
    if unit_match:
        result.unit_raw = unit_match.group(1)
        result.unit_canonical = UNIT_CANONICAL.get(result.unit_raw.casefold())
        numeric_text = raw[:unit_match.start()].strip()
    else:
        numeric_text = raw
    comparator = re.match(r"^(<=|>=|<|>|≤|≥|~|≈|about[ \t]+)", numeric_text, re.IGNORECASE)
    if comparator:
        token = comparator.group(1).strip().casefold()
        result.operator = {
            "<": "LT", "<=": "LTE", "≤": "LTE", ">": "GT", ">=": "GTE",
            "≥": "GTE", "~": "APPROX", "≈": "APPROX", "about": "APPROX",
        }.get(token, "UNKNOWN")
        numeric_text = numeric_text[comparator.end():].strip()
    uncertainty = re.fullmatch(rf"({NUMBER})[ \t]*(?:±|[+]/-)[ \t]*({NUMBER})", numeric_text)
    if uncertainty:
        result.value_kind = "QUANTITY"
        result.operator = "EQ" if result.operator == "UNKNOWN" else result.operator
        result.numeric_values = [float(uncertainty.group(1))]
        result.uncertainty = {"value": float(uncertainty.group(2)), "unit_raw": result.unit_raw}
        result.parse_status = "PARSED"
        return result
    range_match = re.fullmatch(rf"({NUMBER})[ \t]*(?:–|—|-|to)[ \t]*({NUMBER})", numeric_text, re.IGNORECASE)
    if range_match:
        result.value_kind = "QUANTITY"
        result.operator = "RANGE" if result.operator == "UNKNOWN" else result.operator
        result.numeric_values = [float(range_match.group(1)), float(range_match.group(2))]
        result.parse_status = "PARSED"
        return result
    list_text = numeric_text.replace(" and ", ",")
    if "," in list_text:
        tokens = [part.strip() for part in list_text.split(",") if part.strip()]
        if len(tokens) > 1 and all(re.fullmatch(NUMBER, part) for part in tokens):
            result.value_kind = "LIST"
            result.operator = "LIST"
            result.numeric_values = [float(part) for part in tokens]
            result.parse_status = "PARSED"
            return result
    if re.fullmatch(NUMBER, numeric_text):
        result.value_kind = "QUANTITY"
        result.operator = "EQ" if result.operator == "UNKNOWN" else result.operator
        result.numeric_values = [float(numeric_text)]
        result.parse_status = "PARSED"
        return result
    if not result.unit_raw and not comparator:
        result.value_kind = "TEXT"
        result.operator = "EQ"
        result.text_values = [raw]
        result.parse_status = "TEXT_PRESERVED"
    return result


def extract_quantity_expressions(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    matches = list(LIST_QUANTITY_RE.finditer(text)) + list(QUANTITY_RE.finditer(text))
    matches.sort(key=lambda match: (match.start("expr"), -(match.end("expr") - match.start("expr"))))
    seen: set[tuple[int, int]] = set()
    for match in matches:
        span = match.span("expr")
        if any(not (span[1] <= old_start or span[0] >= old_end) for old_start, old_end in seen):
            continue
        seen.add(span)
        parsed = parse_condition_value(match.group("expr"))
        if parsed.parse_status == "PARSED":
            found.append({
                "start": span[0], "end": span[1], "raw_text": match.group("expr"),
                "value": asdict(parsed),
            })
    return sorted(found, key=lambda item: item["start"])


def segment_caption(caption: str | None) -> list[dict[str, Any]]:
    raw = str(caption or "").strip()
    if not raw:
        return []
    matches = list(PANEL_MARKER_RE.finditer(raw))
    if not matches:
        return [{"segment_id": "figure_shared", "scope": "FIGURE_SHARED",
                 "panel_id": None, "raw_text": raw, "start": 0, "end": len(raw)}]
    segments = []
    first = matches[0]
    if raw[:first.start()].strip():
        segments.append({
            "segment_id": "figure_shared", "scope": "FIGURE_SHARED",
            "panel_id": None, "raw_text": raw[:first.start()].strip(),
            "start": 0, "end": first.start(),
        })
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        panel_id = match.group(1).lower()
        segments.append({
            "segment_id": f"panel_{panel_id}", "scope": "PANEL",
            "panel_id": panel_id, "raw_text": raw[match.end():end].strip(),
            "start": match.start(), "end": end,
        })
    return segments


def _scope_for_statement(text: str) -> str:
    lowered = text.casefold()
    synthesis = any(term in lowered for term in SYNTHESIS_HINTS)
    experiment = any(term in lowered for term in EXPERIMENT_HINTS)
    if synthesis and not experiment:
        return "SYNTHESIS"
    if experiment and not synthesis:
        return "EXPERIMENT"
    return "UNRESOLVED"


def _techniques(text: str) -> list[str]:
    found = []
    for name, pattern in TECHNIQUES.items():
        if re.search(pattern, text, re.IGNORECASE):
            found.append(name)
    return found


def _evidence_id(paper_id: str, source_path: str, line_number: int, snippet: str) -> str:
    return stable_id("evidence", f"{paper_id}|{source_path}|{line_number}|{snippet}")


def build_semantic_pass1(
    paper_id: str, figures: list[dict], context_index: Any,
) -> dict[str, Any]:
    """Build provisional text-first caption/sample candidates before image interpretation."""
    captions: list[dict[str, Any]] = []
    text_candidates: dict[str, dict[str, Any]] = {}
    sample_rows = context_index.search("sample_alias", "", limit=5000)

    def add_candidate(name: str, evidence: dict[str, Any], source_kind: str):
        cleaned = " ".join(str(name).strip().split())
        key = normalize_alias(cleaned)
        if not key or len(key) < 2:
            return
        record = text_candidates.setdefault(key, {
            "subject_entity_id": stable_id("subject", f"{paper_id}|{key}"),
            "canonical_name": cleaned, "aliases": [], "entity_kind": "SAMPLE",
            "resolution_status": "PROVISIONAL_TEXT_CANDIDATE", "evidence": [],
            "source_kinds": [],
        })
        if cleaned not in record["aliases"]:
            record["aliases"].append(cleaned)
        if evidence and evidence not in record["evidence"]:
            record["evidence"].append(evidence)
        if source_kind not in record["source_kinds"]:
            record["source_kinds"].append(source_kind)

    for row in sample_rows:
        evidence = {
            "evidence_id": _evidence_id(
                paper_id, row.get("source_path", ""),
                int(row.get("line_number", 0)), row.get("snippet", ""),
            ),
            "source_type": "EXTRACTED_TEXT", "source_path": row.get("source_path"),
            "line_number": row.get("line_number"), "snippet": row.get("snippet"),
        }
        add_candidate(row.get("value", ""), evidence, "TEXT")
    for figure in figures:
        caption = str(figure.get("caption") or "")
        segments = segment_caption(caption)
        captions.append({
            "figure_id": figure.get("figure_id"), "raw_text": caption,
            "segments": segments, "parser_version": "caption-segmenter-0.1.0",
            "parse_status": "PARSED" if caption else "MISSING",
        })
        for segment in segments:
            for match in SAMPLE_MENTION_RE.finditer(segment["raw_text"]):
                name = match.group(0)
                evidence = {
                    "evidence_id": _evidence_id(
                        paper_id, f"caption:{figure.get('figure_id')}",
                        int(segment.get("start", 0)) + match.start(), match.group(0),
                    ),
                    "source_type": "CAPTION", "figure_id": figure.get("figure_id"),
                    "panel_id": segment.get("panel_id"), "snippet": match.group(0),
                }
                add_candidate(name, evidence, "CAPTION")
    return {
        "captions": captions,
        "text_candidates": text_candidates,
        "registry_pass1": list(text_candidates.values()),
    }


def build_semantic_package(
    paper_id: str,
    input_fingerprint: str,
    figures: list[dict],
    panels: list[dict],
    series_records: list[Any],
    context_index: Any,
    pass1_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Complete the single visual enrichment pass over a provisional text-first registry."""
    pass1_state = pass1_state or build_semantic_pass1(paper_id, figures, context_index)
    captions = pass1_state["captions"]
    text_candidates = pass1_state["text_candidates"]
    registry_pass1 = pass1_state["registry_pass1"]

    # One visual enrichment pass. OCR text and series labels remain candidates, not facts.
    visual_candidates = []
    seen_visual = set()
    for record in series_records:
        metadata = getattr(record, "metadata", {})
        raw_candidates = metadata.get("visual_legend_candidates", []) if isinstance(metadata, dict) else []
        for item in (raw_candidates if isinstance(raw_candidates, list) else []):
            if not isinstance(item, dict):
                continue
            label = " ".join(str(item.get("label") or "").split())
            key = normalize_alias(label)
            if not key or key in GENERIC_SERIES_LABELS:
                continue
            visual_key = (key, item.get("figure_id"), item.get("panel_id"))
            if visual_key in seen_visual:
                continue
            seen_visual.add(visual_key)
            visual_candidates.append({
                "series_id": None,
                "figure_id": item.get("figure_id") or getattr(record, "figure_id", None),
                "panel_id": item.get("panel_id") or getattr(record, "panel_id", None),
                "label": label,
                "evidence_type": item.get("source_type", "OCR_TEXT_CANDIDATE"),
                "evidence_id": item.get("evidence_id"),
                "polygon": item.get("polygon"),
                "confidence": item.get("confidence"),
            })
        label = str(getattr(record, "label", None) or "").strip()
        if normalize_alias(label) in GENERIC_SERIES_LABELS:
            continue
        visual_key = (normalize_alias(label), getattr(record, "figure_id", None),
                      getattr(record, "panel_id", None))
        if visual_key not in seen_visual:
            seen_visual.add(visual_key)
            visual_candidates.append({
                "series_id": getattr(record, "series_id", None),
                "figure_id": getattr(record, "figure_id", None),
                "panel_id": getattr(record, "panel_id", None),
                "label": label, "evidence_type": "SERIES_LABEL",
                "evidence_id": None, "polygon": None, "confidence": None,
            })
    pass2_new_names = []
    for candidate in visual_candidates:
        key = normalize_alias(candidate["label"])
        evidence = {
            "evidence_id": candidate.get("evidence_id") or stable_id(
                "visual_evidence",
                f"{paper_id}|{candidate.get('figure_id')}|{candidate.get('panel_id')}|{candidate['label']}",
            ),
            "source_type": candidate.get("evidence_type", "VISUAL_CANDIDATE"),
            "figure_id": candidate.get("figure_id"),
            "panel_id": candidate.get("panel_id"),
            "snippet": candidate["label"],
            "polygon": candidate.get("polygon"),
            "confidence": candidate.get("confidence"),
        }
        if key in text_candidates:
            entity = text_candidates[key]
            if evidence not in entity["evidence"]:
                entity["evidence"].append(evidence)
            if "VISUAL_CORROBORATION" not in entity["source_kinds"]:
                entity["source_kinds"].append("VISUAL_CORROBORATION")
            continue
        text_candidates[key] = {
            "subject_entity_id": stable_id("subject", f"{paper_id}|{key}"),
            "canonical_name": candidate["label"], "aliases": [candidate["label"]],
            "entity_kind": "SAMPLE", "resolution_status": "UNRESOLVED_IMAGE_ONLY",
            "evidence": [evidence], "source_kinds": ["VISUAL"],
        }
        pass2_new_names.append(candidate["label"])
    registry_pass2 = list(text_candidates.values())

    # Targeted backfill only queries the prebuilt statement index for Pass-2 names.
    targeted_backfill = []
    for name in pass2_new_names:
        for row in context_index.search("statement", name, limit=500):
            targeted_backfill.append({
                "sample_name": name, "source_path": row.get("source_path"),
                "line_number": row.get("line_number"), "snippet": row.get("snippet"),
                "evidence_id": _evidence_id(
                    paper_id, row.get("source_path", ""),
                    int(row.get("line_number", 0)), row.get("snippet", ""),
                ),
            })

    # Caption-derived measurement candidates are figure-scoped, not copied to every series.
    measurements: dict[str, dict[str, Any]] = {}
    for figure in figures:
        caption = str(figure.get("caption") or "")
        for technique in _techniques(caption):
            evidence_id = _evidence_id(
                paper_id, f"caption:{figure.get('figure_id')}", 0, caption,
            )
            measurement_id = stable_id(
                "measurement", f"{paper_id}|{figure.get('figure_id')}|{technique}",
            )
            measurements[measurement_id] = {
                "measurement_id": measurement_id, "paper_id": paper_id,
                "figure_id": figure.get("figure_id"), "technique": technique,
                "scope_status": "CAPTION_CANDIDATE", "evidence_ids": [evidence_id],
                "condition_ids": [],
            }

    # Build source-backed process and atomic condition candidates.
    synthesis_processes: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    sample_steps: list[dict[str, Any]] = []
    for key, entity in text_candidates.items():
        aliases = entity["aliases"]
        matching_rows = []
        for alias in aliases:
            matching_rows.extend(context_index.search("statement", alias, limit=500))
        unique_rows = {
            (row.get("source_path"), row.get("line_number"), row.get("snippet")): row
            for row in matching_rows
        }
        ordered_rows = sorted(
            unique_rows.values(),
            key=lambda row: (str(row.get("source_path")), int(row.get("line_number", 0))),
        )
        step_order = 0
        for row in ordered_rows:
            snippet = str(row.get("snippet") or "")
            scope = _scope_for_statement(snippet)
            evidence_id = _evidence_id(
                paper_id, row.get("source_path", ""),
                int(row.get("line_number", 0)), snippet,
            )
            techniques = _techniques(snippet)
            for technique in techniques:
                figure_candidates = [
                    item for item in measurements.values()
                    if item.get("technique") == technique and item.get("figure_id")
                ]
                if len(figure_candidates) == 1:
                    measurement_id = figure_candidates[0]["measurement_id"]
                    if evidence_id not in figure_candidates[0]["evidence_ids"]:
                        figure_candidates[0]["evidence_ids"].append(evidence_id)
                else:
                    measurement_id = stable_id(
                        "measurement",
                        f"{paper_id}|{technique}|{row.get('source_path')}|{row.get('line_number')}",
                    )
                    measurements.setdefault(measurement_id, {
                        "measurement_id": measurement_id, "paper_id": paper_id,
                        "figure_id": None, "technique": technique,
                        "scope_status": "TEXT_CANDIDATE",
                        "evidence_ids": [evidence_id], "condition_ids": [],
                    })
            process_id = None
            if scope == "SYNTHESIS":
                process_id = stable_id("process", f"{paper_id}|{evidence_id}")
                step_order += 1
                synthesis_processes.append({
                    "process_id": process_id, "paper_id": paper_id,
                    "method_text": snippet, "evidence_ids": [evidence_id],
                    "process_status": "CANDIDATE", "condition_ids": [],
                })
                sample_steps.append({
                    "sample_id": entity["subject_entity_id"], "process_id": process_id,
                    "step_order": step_order, "step_role": "UNRESOLVED",
                    "evidence_id": evidence_id, "scope_status": "SOURCE_BACKED_CANDIDATE",
                })
            if scope in {"SYNTHESIS", "EXPERIMENT"}:
                statement_measurements = [
                    item for item in measurements.values()
                    if item.get("technique") in techniques
                    and item.get("technique") is not None
                ]
                scope_entity_id = (
                    process_id if scope == "SYNTHESIS"
                    else statement_measurements[0]["measurement_id"]
                    if len(statement_measurements) == 1 else None
                )
                for quantity in extract_quantity_expressions(snippet):
                    condition_id = stable_id(
                        "condition", f"{paper_id}|{scope}|{evidence_id}|{quantity['start']}|{quantity['raw_text']}"
                    )
                    conditions.append({
                        "condition_id": condition_id, "paper_id": paper_id,
                        "condition_scope": scope, "scope_entity_id": scope_entity_id,
                        "scope_status": "LINKED" if scope_entity_id else "UNRESOLVED_TARGET",
                        "raw_text": quantity["raw_text"], "value": quantity["value"],
                        "evidence_ids": [evidence_id], "parse_status": quantity["value"]["parse_status"],
                    })
                    if scope == "SYNTHESIS" and process_id:
                        process_record = next(
                            (item for item in synthesis_processes if item["process_id"] == process_id),
                            None,
                        )
                        if process_record is not None:
                            process_record["condition_ids"].append(condition_id)
                    elif scope == "EXPERIMENT" and scope_entity_id:
                        measurement_record = measurements.get(scope_entity_id)
                        if measurement_record is not None:
                            measurement_record["condition_ids"].append(condition_id)

    # Caption and series association uses exact normalized aliases only.
    aliases_to_entity = {}
    for key, entity in text_candidates.items():
        for alias in entity["aliases"]:
            aliases_to_entity[normalize_alias(alias)] = entity
    series_subject_links = []
    series_measurement_links = []
    cross_validation = []
    for record in series_records:
        label = str(getattr(record, "label", None) or "").strip()
        entity = aliases_to_entity.get(normalize_alias(label)) if label else None
        if entity:
            link = {
                "series_id": record.series_id, "subject_entity_id": entity["subject_entity_id"],
                "subject_role": "UNKNOWN", "link_status": "MATCHED_EXACT_ALIAS",
                "evidence_ids": [item.get("evidence_id") for item in entity["evidence"]],
            }
        elif label and normalize_alias(label) not in GENERIC_SERIES_LABELS:
            candidate = text_candidates.get(normalize_alias(label))
            link = {
                "series_id": record.series_id,
                "subject_entity_id": candidate["subject_entity_id"] if candidate else None,
                "subject_role": "UNKNOWN", "link_status": "UNRESOLVED_IMAGE_ONLY",
                "evidence_ids": [item.get("evidence_id") for item in candidate["evidence"]] if candidate else [],
            }
        else:
            link = {
                "series_id": record.series_id, "subject_entity_id": None,
                "subject_role": "UNKNOWN", "link_status": "UNASSIGNED",
                "evidence_ids": [],
            }
        series_subject_links.append(link)
        technique = str(getattr(record, "technique", None) or "").upper()
        matching_measurements = [
            item for item in measurements.values()
            if technique and str(item.get("technique", "")).upper() == technique
            and item.get("figure_id") in (None, record.figure_id)
        ]
        if len(matching_measurements) == 1:
            series_measurement_links.append({
                "series_id": record.series_id,
                "measurement_id": matching_measurements[0]["measurement_id"],
                "measurement_role": "MEASUREMENT_RESULT",
                "link_status": "CANDIDATE_TECHNIQUE_MATCH",
                "evidence_ids": matching_measurements[0]["evidence_ids"],
            })
        else:
            series_measurement_links.append({
                "series_id": record.series_id, "measurement_id": None,
                "measurement_role": "UNKNOWN", "link_status": "UNRESOLVED",
                "evidence_ids": [],
            })
        figure_caption = next(
            (str(item.get("caption") or "") for item in figures
             if item.get("figure_id") == record.figure_id),
            "",
        )
        caption_techniques = _techniques(figure_caption)
        technique_conflict = bool(
            technique and caption_techniques and technique not in caption_techniques
        )
        checks = [{
            "check": "SERIES_LABEL_TO_SAMPLE_ALIAS",
            "status": link["link_status"],
            "evidence_ids": link["evidence_ids"],
        }]
        if technique and caption_techniques:
            checks.append({
                "check": "SERIES_TECHNIQUE_TO_CAPTION",
                "status": "CONFLICT" if technique_conflict else "CONSISTENT",
                "series_technique": technique,
                "caption_techniques": caption_techniques,
            })
        cross_validation.append({
            "series_id": record.series_id,
            "status": "CONFLICT" if technique_conflict else
            "CONSISTENT_WITH_AVAILABLE_EVIDENCE"
            if link["link_status"] == "MATCHED_EXACT_ALIAS"
            else "UNRESOLVED",
            "checks": checks,
            "unresolved_fields": (
                ["technique"] if technique_conflict else
                [] if link["link_status"] == "MATCHED_EXACT_ALIAS"
                else ["subject_entity_id"]
            ),
        })

    # Deduplicate shared process/condition nodes while preserving multiple sample-step links.
    synthesis_processes = list({
        item["process_id"]: item for item in synthesis_processes
    }.values())
    conditions = list({
        item["condition_id"]: item for item in conditions
    }.values())
    sample_steps = list({
        (item["sample_id"], item["process_id"], item["step_order"]): item
        for item in sample_steps
    }.values())

    # A pass-2 fingerprint is recorded once; this function has no recursive retry path.
    pass2_fingerprint = hashlib.sha256(json.dumps({
        "input_fingerprint": input_fingerprint,
        "visual_candidates": visual_candidates,
        "registry_pass1_ids": [item["subject_entity_id"] for item in registry_pass1],
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    for record in series_records:
        subject = next((item for item in series_subject_links if item["series_id"] == record.series_id), None)
        if subject:
            record.subject_links = [{
                "entity_id": subject.get("subject_entity_id") or "UNKNOWN",
                "canonical_name": next((
                    item["canonical_name"] for item in registry_pass2
                    if item["subject_entity_id"] == subject.get("subject_entity_id")
                ), None),
                "entity_type": "SAMPLE", "role_in_series": subject["subject_role"],
                "subject_role": subject["subject_role"],
                "status": (
                    "ASSIGNED_WITH_EVIDENCE"
                    if subject["link_status"] == "MATCHED_EXACT_ALIAS" else "UNASSIGNED"
                ),
                "semantic_link_status": subject["link_status"],
                "evidence": {"evidence_ids": subject["evidence_ids"]},
            }]
        measurement_link = next(
            (item for item in series_measurement_links
             if item["series_id"] == record.series_id and item.get("measurement_id")),
            None,
        )
        if measurement_link:
            record.measurement_id = namespaced_id(
                record.paper_id, measurement_link["measurement_id"],
            )
        related_ids = {
            subject.get("subject_entity_id") if subject else None,
            measurement_link.get("measurement_id") if measurement_link else None,
        }
        record.conditions = [
            item for item in conditions
            if item.get("scope_entity_id") in related_ids
        ]
        record.metadata["semantic_pass2_fingerprint"] = pass2_fingerprint
        record.metadata["semantic_subject_link_status"] = subject["link_status"] if subject else "UNASSIGNED"
        explicit_scale = str(
            record.metadata.get("scale_type")
            or record.metadata.get("y_axis_scale_type")
            or ""
        ).upper()
        offset_value = (
            record.metadata.get("offset_value")
            if record.metadata.get("offset_value") is not None
            else record.metadata.get("vertical_offset")
            if record.metadata.get("vertical_offset") is not None
            else record.metadata.get("stacked_offset")
        )
        if explicit_scale in {
            "ABSOLUTE", "NORMALIZED", "ARBITRARY_RELATIVE",
            "ARBITRARY_OFFSET_STACKED", "UNKNOWN",
        }:
            scale_type = explicit_scale
        elif offset_value is not None:
            scale_type = "ARBITRARY_OFFSET_STACKED"
        elif record.metadata.get("normalization_provenance"):
            scale_type = "NORMALIZED"
        else:
            scale_type = "UNKNOWN"
        record.scale_type = scale_type
        record.baseline_comparable = (
            False if scale_type == "ARBITRARY_OFFSET_STACKED" else None
        )
        record.offset_value = float(offset_value) if offset_value is not None else None
        provenance = record.metadata.get("normalization_provenance")
        record.normalization_provenance = provenance if isinstance(provenance, dict) else None
        record.metadata["scale_type"] = record.scale_type
        record.metadata["baseline_comparable"] = record.baseline_comparable

    return {
        "schema_version": "2.1", "paper_id": paper_id,
        "caption_semantics": captions,
        "sample_registry": {
            "pass1_status": "PROVISIONAL",
            "pass2_status": "COMPLETED_ONCE",
            "pass2_fingerprint": pass2_fingerprint,
            "pass2_new_visual_names": pass2_new_names,
            "subjects": registry_pass2,
            "sample_process_steps": sample_steps,
        },
        "synthesis_processes": synthesis_processes,
        "conditions": conditions,
        "measurements": list(measurements.values()),
        "series_subject_links": series_subject_links,
        "series_measurement_links": series_measurement_links,
        "targeted_condition_backfill": targeted_backfill,
        "cross_validation": {
            "status": "COMPLETED_WITH_UNRESOLVED" if any(
                item["status"] in {"UNRESOLVED", "CONFLICT"} for item in cross_validation
            ) else "CONSISTENT_WITH_AVAILABLE_EVIDENCE",
            "results": cross_validation,
        },
    }
