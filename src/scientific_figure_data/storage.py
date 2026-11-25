from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .hashing import atomic_write_json, sha256_file
from .models import PaperSnapshot, SeriesRecord, utc_now

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS papers(
 paper_id TEXT PRIMARY KEY, source_dir TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
 status TEXT NOT NULL, manifest_path TEXT, bundle_path TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS figures(
 paper_id TEXT NOT NULL, figure_id TEXT NOT NULL, source_page INTEGER, caption TEXT,
 PRIMARY KEY(paper_id, figure_id), FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
);
CREATE TABLE IF NOT EXISTS panels(
 paper_id TEXT NOT NULL, figure_id TEXT NOT NULL, panel_id TEXT NOT NULL,
 bbox_json TEXT, status TEXT, PRIMARY KEY(paper_id, figure_id, panel_id)
);
CREATE TABLE IF NOT EXISTS entities(
 entity_id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, entity_type TEXT,
 domain TEXT, aliases_json TEXT NOT NULL DEFAULT '[]', evidence_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS entity_aliases(
 entity_id TEXT NOT NULL, alias TEXT NOT NULL, alias_norm TEXT NOT NULL,
 PRIMARY KEY(entity_id,alias_norm)
);
CREATE INDEX IF NOT EXISTS idx_entity_alias_norm ON entity_aliases(alias_norm);
CREATE TABLE IF NOT EXISTS entity_relationships(
 parent_entity_id TEXT NOT NULL, child_entity_id TEXT NOT NULL, relationship TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(parent_entity_id,child_entity_id,relationship)
);
CREATE TABLE IF NOT EXISTS subject_entities(
 subject_entity_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, entity_kind TEXT NOT NULL,
 canonical_name TEXT NOT NULL, aliases_json TEXT NOT NULL DEFAULT '[]',
 resolution_status TEXT NOT NULL, composition_json TEXT, preparation_variant_json TEXT,
 evidence_json TEXT NOT NULL DEFAULT '[]',
 FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_subject_entities_paper ON subject_entities(paper_id);
CREATE TABLE IF NOT EXISTS subject_entity_aliases(
 subject_entity_id TEXT NOT NULL, alias TEXT NOT NULL, alias_norm TEXT NOT NULL,
 alias_type TEXT NOT NULL DEFAULT 'EXACT', evidence_json TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY(subject_entity_id,alias_norm),
 FOREIGN KEY(subject_entity_id) REFERENCES subject_entities(subject_entity_id)
);
CREATE INDEX IF NOT EXISTS idx_subject_alias_norm ON subject_entity_aliases(alias_norm);
CREATE TABLE IF NOT EXISTS synthesis_processes(
 process_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, method_text TEXT NOT NULL,
 process_type TEXT, input_materials_json TEXT NOT NULL DEFAULT '[]',
 condition_ids_json TEXT NOT NULL DEFAULT '[]', evidence_json TEXT NOT NULL DEFAULT '[]',
 process_status TEXT NOT NULL,
 FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
);
CREATE TABLE IF NOT EXISTS sample_process_steps(
 sample_id TEXT NOT NULL, process_id TEXT NOT NULL, step_order INTEGER NOT NULL,
 step_role TEXT NOT NULL, evidence_id TEXT NOT NULL, scope_status TEXT NOT NULL,
 PRIMARY KEY(sample_id,process_id,step_order),
 FOREIGN KEY(sample_id) REFERENCES subject_entities(subject_entity_id),
 FOREIGN KEY(process_id) REFERENCES synthesis_processes(process_id)
);
CREATE TABLE IF NOT EXISTS series_measurement_links(
 series_id TEXT NOT NULL, measurement_id TEXT, measurement_role TEXT NOT NULL,
 link_status TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY(series_id,measurement_id,measurement_role)
);
CREATE TABLE IF NOT EXISTS evidence_items(
 evidence_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, source_type TEXT NOT NULL,
 source_path TEXT, source_sha256 TEXT, location_json TEXT NOT NULL DEFAULT '{}',
 snippet TEXT NOT NULL DEFAULT '', parser_version TEXT, confidence_json TEXT NOT NULL DEFAULT '{}',
 FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
);
CREATE TABLE IF NOT EXISTS cross_validation_results(
 result_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, series_id TEXT NOT NULL,
 status TEXT NOT NULL, checks_json TEXT NOT NULL DEFAULT '[]',
 unresolved_fields_json TEXT NOT NULL DEFAULT '[]',
 FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
);
CREATE TABLE IF NOT EXISTS conditions(
 condition_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, measurement_id TEXT,
 name TEXT NOT NULL, value_json TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS measurements(
 measurement_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, figure_id TEXT,
 technique TEXT, domain TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS series(
 series_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, figure_id TEXT NOT NULL,
 panel_id TEXT NOT NULL, measurement_id TEXT, technique TEXT, domain TEXT, label TEXT, x_unit TEXT, y_unit TEXT,
 y_axis_side TEXT NOT NULL, extraction_status TEXT NOT NULL, qc_status TEXT NOT NULL,
 review_state TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
 scale_type TEXT NOT NULL DEFAULT 'UNKNOWN', baseline_comparable INTEGER,
 offset_value REAL, normalization_provenance_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_paper ON series(paper_id);
CREATE INDEX IF NOT EXISTS idx_series_technique ON series(technique);
CREATE INDEX IF NOT EXISTS idx_series_domain ON series(domain);
CREATE TABLE IF NOT EXISTS series_points(
 series_id TEXT NOT NULL, point_index INTEGER NOT NULL, x_value REAL, x_label TEXT,
 y_value REAL, pixel_x REAL, pixel_y REAL, y_err_low REAL, y_err_high REAL, err_type TEXT,
 PRIMARY KEY(series_id, point_index)
);
CREATE TABLE IF NOT EXISTS series_subject_links(
 series_id TEXT NOT NULL, entity_id TEXT NOT NULL, role_in_series TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}', link_status TEXT NOT NULL DEFAULT 'UNASSIGNED',
 identity_scope TEXT NOT NULL DEFAULT 'PAPER', subject_role TEXT NOT NULL DEFAULT 'UNKNOWN',
 PRIMARY KEY(series_id, entity_id, role_in_series)
);
CREATE TABLE IF NOT EXISTS observations(
 observation_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, name TEXT NOT NULL,
 value_json TEXT NOT NULL, source_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs(
 paper_id TEXT PRIMARY KEY, state TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0,
 worker_id TEXT, worker_pid INTEGER, started_at TEXT, input_fingerprint TEXT,
 lease_expires_at REAL, heartbeat_at REAL, current_stage TEXT, last_error TEXT,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_events(
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, paper_id TEXT NOT NULL, event_type TEXT NOT NULL,
 created_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews(
 review_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, series_id TEXT, patch_id TEXT,
 reviewer TEXT, reviewed_at TEXT NOT NULL, original_hash TEXT NOT NULL,
 revised_hash TEXT NOT NULL, decision TEXT NOT NULL, patch_path TEXT
);
CREATE TABLE IF NOT EXISTS applied_patches(
 patch_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, applied_at TEXT NOT NULL,
 original_hash TEXT NOT NULL, revised_hash TEXT NOT NULL
);
"""


def connect_catalog(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    journal_mode = str(con.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
    if journal_mode != "wal":
        con.close()
        raise RuntimeError(f"SQLite WAL mode unavailable (reported {journal_mode!r})")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.executescript(SCHEMA)
    # Additive schema migration for catalogs created by earlier development snapshots.
    series_columns = {row[1] for row in con.execute("PRAGMA table_info(series)").fetchall()}
    if "measurement_id" not in series_columns:
        con.execute("ALTER TABLE series ADD COLUMN measurement_id TEXT")
    for name, declaration in (
        ("scale_type", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
        ("baseline_comparable", "INTEGER"),
        ("offset_value", "REAL"),
        ("normalization_provenance_json", "TEXT"),
    ):
        if name not in series_columns:
            con.execute(f"ALTER TABLE series ADD COLUMN {name} {declaration}")
    condition_columns = {row[1] for row in con.execute("PRAGMA table_info(conditions)").fetchall()}
    for name, declaration in (
        ("condition_scope", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
        ("scope_entity_id", "TEXT"),
        ("value_kind", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
        ("operator", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
        ("numeric_values_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("text_values_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("unit_raw", "TEXT"),
        ("unit_canonical", "TEXT"),
        ("uncertainty_json", "TEXT"),
        ("normalization_basis", "TEXT"),
        ("parse_status", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
    ):
        if name not in condition_columns:
            con.execute(f"ALTER TABLE conditions ADD COLUMN {name} {declaration}")
    measurement_columns = {row[1] for row in con.execute("PRAGMA table_info(measurements)").fetchall()}
    for name, declaration in (
        ("measurement_role", "TEXT"),
        ("subject_roles_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("condition_ids_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("evidence_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("scope_status", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
    ):
        if name not in measurement_columns:
            con.execute(f"ALTER TABLE measurements ADD COLUMN {name} {declaration}")
    subject_link_columns = {row[1] for row in con.execute("PRAGMA table_info(series_subject_links)").fetchall()}
    if "subject_role" not in subject_link_columns:
        con.execute("ALTER TABLE series_subject_links ADD COLUMN subject_role TEXT NOT NULL DEFAULT 'UNKNOWN'")
    job_columns = {row[1] for row in con.execute("PRAGMA table_info(jobs)").fetchall()}
    for name, declaration in (
        ("worker_id", "TEXT"),
        ("worker_pid", "INTEGER"),
        ("started_at", "TEXT"),
        ("input_fingerprint", "TEXT"),
    ):
        if name not in job_columns:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
    link_columns = {row[1] for row in con.execute("PRAGMA table_info(series_subject_links)").fetchall()}
    if "identity_scope" not in link_columns:
        con.execute(
            "ALTER TABLE series_subject_links ADD COLUMN identity_scope TEXT NOT NULL DEFAULT 'PAPER'"
        )
    # Migrate entity aliases for catalogs created before the exact-alias index existed.
    import unicodedata
    for entity in con.execute(
        "SELECT entity_id,canonical_name,aliases_json FROM entities"
    ).fetchall():
        try:
            aliases = json.loads(entity["aliases_json"] or "[]")
        except (TypeError, ValueError):
            aliases = []
        names = {str(entity["canonical_name"] or "")}
        if isinstance(aliases, list):
            names.update(str(alias) for alias in aliases if alias)
        con.executemany(
            "INSERT OR IGNORE INTO entity_aliases(entity_id,alias,alias_norm) VALUES(?,?,?)",
            [(entity["entity_id"], alias,
              unicodedata.normalize("NFKC", alias).casefold())
             for alias in names if alias],
        )
    return con


def write_paper_artifacts(
    output_root: Path, snapshot: PaperSnapshot, figures: list[dict], panels: list[dict],
    series: list[SeriesRecord], status: str, extra: dict | None = None,
    semantic_artifacts: dict | None = None,
) -> dict:
    paper_root = output_root / "papers" / snapshot.paper_id
    (paper_root / "evidence").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0", "paper_id": snapshot.paper_id,
        "source_dir": snapshot.source_dir, "input_fingerprint": snapshot.input_fingerprint,
        "upstream_version": snapshot.detected_upstream_version, "adapter_version": snapshot.adapter_version,
        "created_at": snapshot.created_at, "artifacts": [asdict(a) for a in snapshot.artifacts],
        "missing_roles": snapshot.missing_roles, "warnings": snapshot.warnings,
        "processing_status": status,
    }
    atomic_write_json(paper_root / "paper_manifest.json", manifest)
    atomic_write_json(paper_root / "figure_inventory.json", {
        "schema_version": "1.0", "paper_id": snapshot.paper_id, "figures": figures
    })
    atomic_write_json(paper_root / "panel_layout.json", {
        "schema_version": "1.0", "paper_id": snapshot.paper_id, "panels": panels
    })
    extra = extra or {}
    digitization = {
        "schema_version": "1.0", "algorithm_version": extra.get("algorithm_version", "0.2.0"),
        "paper_id": snapshot.paper_id, "input_fingerprint": snapshot.input_fingerprint,
        "stage_fingerprint": extra.get("stage_fingerprint"),
        "context_index_fingerprint": extra.get("context_index_fingerprint"),
        "generated_at": utc_now(), "status": status,
        "qc_threshold_status": extra.get("qc_threshold_status", "PROVISIONAL_UNCALIBRATED"),
        "series": [{**{k: v for k, v in asdict(s).items() if k != "points"},
                    "points_count": len(s.points) or int(s.metadata.get("points_count", 0))} for s in series],
        "extra": extra,
    }
    atomic_write_json(paper_root / "digitization.json", digitization)

    semantic_artifacts = semantic_artifacts or {}
    semantic_paths = []
    if semantic_artifacts:
        caption_path = paper_root / "caption_semantics.json"
        registry_path = paper_root / "sample_registry.json"
        process_path = paper_root / "synthesis_processes.json"
        experiment_path = paper_root / "experiments.json"
        cross_validation_path = paper_root / "cross_validation.json"
        atomic_write_json(caption_path, {
            "schema_version": "2.1", "paper_id": snapshot.paper_id,
            "figures": semantic_artifacts.get("caption_semantics", []),
        })
        atomic_write_json(registry_path, {
            "schema_version": "2.1", "paper_id": snapshot.paper_id,
            **semantic_artifacts.get("sample_registry", {}),
            "series_subject_links": semantic_artifacts.get("series_subject_links", []),
        })
        all_conditions = semantic_artifacts.get("conditions", [])
        atomic_write_json(process_path, {
            "schema_version": "2.1", "paper_id": snapshot.paper_id,
            "processes": semantic_artifacts.get("synthesis_processes", []),
            "sample_process_steps": semantic_artifacts.get("sample_registry", {}).get(
                "sample_process_steps", []
            ),
            "conditions": [
                item for item in all_conditions if item.get("condition_scope") == "SYNTHESIS"
            ],
        })
        atomic_write_json(experiment_path, {
            "schema_version": "2.1", "paper_id": snapshot.paper_id,
            "measurements": semantic_artifacts.get("measurements", []),
            "series_measurement_links": semantic_artifacts.get("series_measurement_links", []),
            "conditions": [
                item for item in all_conditions if item.get("condition_scope") == "EXPERIMENT"
            ],
        })
        atomic_write_json(cross_validation_path, {
            "schema_version": "2.1", "paper_id": snapshot.paper_id,
            **semantic_artifacts.get("cross_validation", {}),
        })
        semantic_paths = [
            path.name for path in (
                caption_path, registry_path, process_path, experiment_path, cross_validation_path
            )
        ]

    # Point batches are streamed to panel CSVs during extraction. Do not rewrite or
    # accumulate them here; this function handles compact paper-level metadata.
    csv_paths = [p.relative_to(paper_root).as_posix()
                 for p in (paper_root / "series").glob("**/panel_series.csv")] if (paper_root / "series").exists() else []
    evidence_paths = [
        path.relative_to(paper_root).as_posix()
        for path in (paper_root / "evidence").glob("**/*")
        if path.is_file()
    ]
    context_paths = [
        path.relative_to(paper_root).as_posix()
        for path in (paper_root / "context").glob("**/*")
        if path.is_file()
    ] if (paper_root / "context").exists() else []
    canonical_paths = list(dict.fromkeys(
        ["paper_manifest.json", "figure_inventory.json", "panel_layout.json", "digitization.json"]
        + semantic_paths + csv_paths + evidence_paths + context_paths
    ))
    hashes = {name: sha256_file(paper_root / name) for name in canonical_paths}
    bundle = {
        "schema_version": "1.0", "bundle_version": "1.0", "paper_id": snapshot.paper_id,
        "generated_at": utc_now(), "input_fingerprint": snapshot.input_fingerprint,
        "stage_fingerprint": extra.get("stage_fingerprint"),
        "context_index_fingerprint": extra.get("context_index_fingerprint"),
        "algorithm_versions": {"core": "0.1.0"}, "profile_versions": {},
        "status": status, "canonical_artifacts": canonical_paths, "content_hashes": hashes,
        "semantic_schema_version": "2.1" if semantic_paths else None,
        "series_count": len(series), "figure_count": len(figures), "panel_count": len(panels),
    }
    atomic_write_json(paper_root / "paper_bundle.json", bundle)
    return {"paper_root": str(paper_root), "bundle": bundle, "csv_paths": csv_paths}


class Catalog:
    """SQLite index with a single writer owned by the parent scheduler/CLI."""

    def __init__(self, path: Path):
        self.path = path
        self.con = connect_catalog(path)

    def close(self):
        self.con.close()

    def register_paper(self, snapshot: PaperSnapshot, status: str, artifact_paths: dict | None = None):
        paths = artifact_paths or {}
        self.con.execute(
            """INSERT INTO papers(paper_id,source_dir,input_fingerprint,status,manifest_path,bundle_path,updated_at)
               VALUES(?,?,?,?,?,?,?) ON CONFLICT(paper_id) DO UPDATE SET
               source_dir=excluded.source_dir,input_fingerprint=excluded.input_fingerprint,
               status=excluded.status,manifest_path=excluded.manifest_path,
               bundle_path=excluded.bundle_path,updated_at=excluded.updated_at""",
            (snapshot.paper_id, snapshot.source_dir, snapshot.input_fingerprint, status,
             paths.get("manifest_path"), paths.get("bundle_path"), utc_now()),
        )

    def index_paper(self, snapshot: PaperSnapshot, figures: list[dict], panels: list[dict],
                    series: list[SeriesRecord], status: str, artifact_paths: dict | None = None,
                    paper_root: Path | None = None, batch_size: int = 1000):
        mismatched = [item.series_id for item in series if item.paper_id != snapshot.paper_id]
        if mismatched:
            raise ValueError(
                f"Series paper_id must match snapshot paper_id {snapshot.paper_id!r}: {mismatched[:10]}"
            )
        with self.con:
            self.register_paper(snapshot, status, artifact_paths)
            self.con.execute(
                "DELETE FROM series_points WHERE series_id IN (SELECT series_id FROM series WHERE paper_id=?)",
                (snapshot.paper_id,),
            )
            self.con.execute(
                "DELETE FROM series_subject_links WHERE series_id IN (SELECT series_id FROM series WHERE paper_id=?)",
                (snapshot.paper_id,),
            )
            self.con.execute("DELETE FROM series WHERE paper_id=?", (snapshot.paper_id,))
            self.con.execute("DELETE FROM conditions WHERE paper_id=?", (snapshot.paper_id,))
            self.con.execute("DELETE FROM measurements WHERE paper_id=?", (snapshot.paper_id,))
            self.con.execute("DELETE FROM panels WHERE paper_id=?", (snapshot.paper_id,))
            self.con.execute("DELETE FROM figures WHERE paper_id=?", (snapshot.paper_id,))
            for fig in figures:
                self.con.execute("INSERT INTO figures VALUES(?,?,?,?)",
                                 (snapshot.paper_id, str(fig["figure_id"]), fig.get("page"), fig.get("caption")))
            for panel in panels:
                self.con.execute("INSERT INTO panels VALUES(?,?,?,?,?)",
                                 (snapshot.paper_id, str(panel["figure_id"]), str(panel["panel_id"]),
                                  json.dumps(panel.get("bbox"), ensure_ascii=False),
                                  panel.get("status", "INVENTORIED")))
            for item in series:
                self._insert_series(item)
            if paper_root:
                self._index_panel_csv_points(paper_root, series, batch_size)

    def _index_panel_csv_points(self, paper_root: Path, series: list[SeriesRecord] | set[str],
                                batch_size: int = 1000):
        known = series if isinstance(series, set) else {item.series_id for item in series}
        for csv_path in (paper_root / "series").glob("**/panel_series.csv"):
            batch = []
            with csv_path.open("r", newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    sid = row.get("series_id")
                    if sid not in known:
                        continue
                    batch.append((
                        sid, int(row["point_index"]),
                        float(row["x_value"]) if row.get("x_value") else None,
                        row.get("x_label") or None,
                        float(row["y_value"]) if row.get("y_value") else None,
                        float(row["pixel_x"]) if row.get("pixel_x") else None,
                        float(row["pixel_y"]) if row.get("pixel_y") else None,
                        float(row["y_err_low"]) if row.get("y_err_low") else None,
                        float(row["y_err_high"]) if row.get("y_err_high") else None,
                        row.get("err_type") or "UNKNOWN",
                    ))
                    if len(batch) >= max(1, batch_size):
                        self.con.executemany("INSERT INTO series_points VALUES(?,?,?,?,?,?,?,?,?,?)", batch)
                        batch.clear()
            if batch:
                self.con.executemany("INSERT INTO series_points VALUES(?,?,?,?,?,?,?,?,?,?)", batch)

    def _insert_series(self, item: SeriesRecord):
        from .models import namespaced_id

        local_measurement_id = str(item.measurement_id or f"measurement:{item.series_id}")
        measurement_id = namespaced_id(item.paper_id, local_measurement_id)
        self.con.execute(
            """INSERT INTO series(series_id,paper_id,figure_id,panel_id,measurement_id,technique,domain,label,
               x_unit,y_unit,y_axis_side,extraction_status,qc_status,review_state,metadata_json,
               scale_type,baseline_comparable,offset_value,normalization_provenance_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item.series_id, item.paper_id, item.figure_id, item.panel_id,
             measurement_id, item.technique,
             item.domain, item.label, item.x_unit, item.y_unit, item.y_axis_side,
             item.extraction_status, item.qc_status, item.review_state,
             json.dumps(item.metadata, ensure_ascii=False), item.scale_type,
             None if item.baseline_comparable is None else int(item.baseline_comparable),
             item.offset_value,
             json.dumps(item.normalization_provenance, ensure_ascii=False)
             if item.normalization_provenance is not None else None),
        )
        self.con.execute(
            "INSERT OR REPLACE INTO measurements(measurement_id,paper_id,figure_id,technique,domain,metadata_json) VALUES(?,?,?,?,?,?)",
            (measurement_id, item.paper_id, item.figure_id, item.technique, item.domain,
             json.dumps({"series_id": item.series_id}, ensure_ascii=False)),
        )
        if item.points:
            self.con.executemany(
                """INSERT INTO series_points(series_id,point_index,x_value,x_label,y_value,pixel_x,pixel_y,
                   y_err_low,y_err_high,err_type) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [(item.series_id, p.point_index, p.x if isinstance(p.x, (int, float)) else None,
                  p.x if isinstance(p.x, str) else None, p.y, p.pixel_x, p.pixel_y,
                  p.y_err_low, p.y_err_high, p.err_type) for p in item.points],
            )
        for link in item.subject_links:
            source_entity_id = str(link.get("entity_id") or "").strip()
            identity_scope = str(link.get("identity_scope") or "PAPER").upper()
            if not source_entity_id or source_entity_id == "UNKNOWN":
                continue
            if identity_scope == "GLOBAL":
                entity_id = source_entity_id
            else:
                identity_scope = "PAPER"
                entity_id = namespaced_id(item.paper_id, source_entity_id)
            canonical = str(link.get("canonical_name") or link.get("entity_name") or entity_id)
            link_evidence = dict(link.get("evidence") or {})
            if link.get("source_entity_id"):
                link_evidence.setdefault("source_entity_id", link.get("source_entity_id"))
            link_evidence.setdefault("identity_scope", identity_scope)
            existing = self.con.execute(
                "SELECT canonical_name,entity_type FROM entities WHERE entity_id=?",
                (entity_id,),
            ).fetchone()
            if existing and (
                str(existing["canonical_name"]) != canonical
                or (existing["entity_type"] or None) != (link.get("entity_type") or None)
            ):
                raise ValueError(
                    f"Entity identity conflict for {entity_id!r}: existing canonical/type "
                    f"does not match incoming {canonical!r}/{link.get('entity_type')!r}"
                )
            self.con.execute(
                """INSERT INTO entities(entity_id,canonical_name,entity_type,domain,aliases_json,evidence_json)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(entity_id) DO NOTHING""",
                (entity_id, canonical, link.get("entity_type"), item.domain,
                 json.dumps(link.get("aliases", []), ensure_ascii=False),
                 json.dumps(link_evidence, ensure_ascii=False)),
            )
            self.con.execute(
                """INSERT OR REPLACE INTO series_subject_links
                   (series_id,entity_id,role_in_series,evidence_json,link_status,identity_scope,subject_role)
                   VALUES(?,?,?,?,?,?,?)""",
                (item.series_id, entity_id, link.get("role_in_series", "unknown"),
                 json.dumps(link_evidence, ensure_ascii=False),
                 link.get("status", "UNASSIGNED"), identity_scope,
                 link.get("subject_role", link.get("role_in_series", "UNKNOWN"))),
            )
            import unicodedata
            aliases = {canonical, *(str(alias) for alias in link.get("aliases", []) if alias)}
            self.con.executemany(
                "INSERT OR IGNORE INTO entity_aliases(entity_id,alias,alias_norm) VALUES(?,?,?)",
                [(entity_id, alias, unicodedata.normalize("NFKC", alias).casefold())
                 for alias in aliases],
            )
        for relationship in item.metadata.get("entity_relationships", []):
            if not all(relationship.get(key) for key in ("parent_entity_id", "child_entity_id", "relationship")):
                continue
            self.con.execute(
                "INSERT OR REPLACE INTO entity_relationships VALUES(?,?,?,?)",
                (
                    (relationship["parent_entity_id"] if relationship.get("identity_scope") == "GLOBAL"
                     else namespaced_id(item.paper_id, relationship["parent_entity_id"])),
                    (relationship["child_entity_id"] if relationship.get("identity_scope") == "GLOBAL"
                     else namespaced_id(item.paper_id, relationship["child_entity_id"])),
                    relationship["relationship"], json.dumps(relationship.get("evidence", {}), ensure_ascii=False)
                ),
            )
        for index, condition in enumerate(item.conditions):
            local_condition_id = str(condition.get("condition_id") or f"{item.series_id}:condition:{index}")
            condition_id = namespaced_id(item.paper_id, local_condition_id)
            value = condition.get("value") if isinstance(condition.get("value"), dict) else {}
            self.con.execute(
                """INSERT OR REPLACE INTO conditions(
                   condition_id,paper_id,measurement_id,name,value_json,evidence_json,
                   condition_scope,scope_entity_id,value_kind,operator,numeric_values_json,
                   text_values_json,unit_raw,unit_canonical,uncertainty_json,
                   normalization_basis,parse_status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (condition_id, item.paper_id,
                 measurement_id if condition.get("condition_scope") == "EXPERIMENT" else None,
                 str(condition.get("raw_text") or condition.get("name", "unknown")),
                 json.dumps(value, ensure_ascii=False),
                 json.dumps(condition.get("evidence", {}), ensure_ascii=False),
                 condition.get("condition_scope", "UNRESOLVED"),
                 condition.get("scope_entity_id"), value.get("value_kind", "UNKNOWN"),
                 value.get("operator", "UNKNOWN"),
                 json.dumps(value.get("numeric_values", []), ensure_ascii=False),
                 json.dumps(value.get("text_values", []), ensure_ascii=False),
                 value.get("unit_raw"), value.get("unit_canonical"),
                 json.dumps(value.get("uncertainty"), ensure_ascii=False),
                 value.get("normalization_basis"), value.get("parse_status", "UNRESOLVED")),
            )

    def _query_sql(self, filters: dict[str, str | None], limit: int | None = None) -> tuple[str, list[Any]]:
        sql = "SELECT s.*, p.source_dir, p.input_fingerprint FROM series s JOIN papers p ON p.paper_id=s.paper_id WHERE 1=1"
        args: list[Any] = []
        mapping = {"paper_id": "s.paper_id", "technique": "s.technique", "domain": "s.domain",
                   "review_state": "s.review_state", "qc_status": "s.qc_status"}
        for key, column in mapping.items():
            value = filters.get(key)
            if value:
                sql += f" AND {column}=?"
                args.append(value)
        entity_id = filters.get("entity_id")
        entity_name = filters.get("entity")
        if entity_id:
            sql += " AND EXISTS (SELECT 1 FROM series_subject_links l WHERE l.series_id=s.series_id AND l.entity_id=?)"
            args.append(entity_id)
        elif entity_name:
            import unicodedata
            normalized_entity = unicodedata.normalize("NFKC", entity_name.strip()).casefold()
            sql += """ AND EXISTS (
                      SELECT 1 FROM series_subject_links l
                      JOIN entity_aliases a ON a.entity_id=l.entity_id
                      WHERE l.series_id=s.series_id AND a.alias_norm=?
                      )"""
            args.append(normalized_entity)
        analyte = filters.get("analyte")
        if analyte:
            import unicodedata
            normalized_analyte = unicodedata.normalize("NFKC", analyte.strip()).casefold()
            sql += """ AND EXISTS (SELECT 1 FROM series_subject_links l
                      JOIN entities e ON e.entity_id=l.entity_id
                      JOIN entity_aliases a ON a.entity_id=e.entity_id
                      WHERE l.series_id=s.series_id AND
                      (lower(e.entity_type)='analyte' OR lower(l.role_in_series)='target_analyte')
                      AND a.alias_norm=?)"""
            args.append(normalized_analyte)
        role = filters.get("series_role")
        if role:
            sql += " AND EXISTS (SELECT 1 FROM series_subject_links l WHERE l.series_id=s.series_id AND l.role_in_series=?)"
            args.append(role)
        condition = filters.get("condition")
        if condition:
            sql += """ AND EXISTS (SELECT 1 FROM conditions c
                      WHERE c.measurement_id=s.measurement_id
                      AND (lower(c.name) LIKE ? OR lower(c.value_json) LIKE ?))"""
            needle = f"%{condition.casefold()}%"
            args.extend((needle, needle))
        sql += " ORDER BY s.paper_id,s.figure_id,s.panel_id,s.series_id"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(max(1, min(int(limit), 10000)))
        return sql, args

    def iter_query_series(self, filters: dict[str, str | None], batch_size: int = 500):
        sql, args = self._query_sql(filters, limit=None)
        cursor = self.con.execute(sql, args)
        while True:
            batch = cursor.fetchmany(max(1, batch_size))
            if not batch:
                break
            for row in batch:
                yield dict(row)

    def query_series(self, filters: dict[str, str | None], limit: int = 500) -> list[dict]:
        sql, args = self._query_sql(filters, limit=limit)
        return [dict(row) for row in self.con.execute(sql, args).fetchall()]


    def series_associations(self, series_id: str) -> dict:
        entity_rows = self.con.execute(
            """SELECT e.entity_id,e.canonical_name,e.entity_type,e.domain,e.aliases_json,
                      l.role_in_series,l.link_status,l.identity_scope,l.evidence_json
               FROM series_subject_links l LEFT JOIN entities e ON e.entity_id=l.entity_id
               WHERE l.series_id=? ORDER BY l.role_in_series,e.canonical_name""",
            (series_id,),
        ).fetchall()
        condition_rows = self.con.execute(
            """SELECT c.condition_id,c.name,c.value_json,c.evidence_json
               FROM conditions c JOIN series s ON s.measurement_id=c.measurement_id
               WHERE s.series_id=? ORDER BY c.name""",
            (series_id,),
        ).fetchall()
        return {
            "subject_links": [dict(row) for row in entity_rows],
            "conditions": [dict(row) for row in condition_rows],
        }

    def list_reviews(self, limit: int = 1000) -> list[dict]:
        return [dict(row) for row in self.con.execute(
            "SELECT * FROM series WHERE review_state!='REVIEWED_ACCEPTED' ORDER BY paper_id LIMIT ?",
            (max(1, min(limit, 10000)),),
        ).fetchall()]

    def rebuild_from_artifacts(self, output_root: Path) -> dict:
        count = 0
        for paper_root in sorted((output_root / "papers").glob("*")):
            manifest_path = paper_root / "paper_manifest.json"
            digitization_path = paper_root / "digitization.json"
            figures_path = paper_root / "figure_inventory.json"
            panels_path = paper_root / "panel_layout.json"
            if not (manifest_path.is_file() and digitization_path.is_file() and figures_path.is_file()):
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fig_data = json.loads(figures_path.read_text(encoding="utf-8"))
            panel_data = json.loads(panels_path.read_text(encoding="utf-8")) if panels_path.exists() else {"panels": []}
            digitization = json.loads(digitization_path.read_text(encoding="utf-8"))
            snapshot = PaperSnapshot(
                paper_id=manifest["paper_id"], source_dir=manifest["source_dir"],
                detected_upstream_version=manifest.get("upstream_version"),
                adapter_version=manifest["adapter_version"], created_at=manifest["created_at"],
                input_fingerprint=manifest["input_fingerprint"],
            )
            series_by_id = {s["series_id"]: s for s in digitization.get("series", [])}
            with self.con:
                self.con.execute("DELETE FROM series_subject_links WHERE series_id IN (SELECT series_id FROM series WHERE paper_id=?)",
                                 (snapshot.paper_id,))
                self.con.execute("DELETE FROM series_points WHERE series_id IN (SELECT series_id FROM series WHERE paper_id=?)",
                                 (snapshot.paper_id,))
                self.con.execute("DELETE FROM series WHERE paper_id=?", (snapshot.paper_id,))
                self.con.execute("DELETE FROM panels WHERE paper_id=?", (snapshot.paper_id,))
                self.con.execute("DELETE FROM figures WHERE paper_id=?", (snapshot.paper_id,))
                self.register_paper(snapshot, manifest.get("processing_status", "UNKNOWN"), {
                    "manifest_path": str(manifest_path), "bundle_path": str(paper_root / "paper_bundle.json")
                })
                for fig in fig_data.get("figures", []):
                    self.con.execute("INSERT INTO figures VALUES(?,?,?,?)",
                                     (snapshot.paper_id, fig.get("figure_id"), fig.get("page"), fig.get("caption")))
                for panel in panel_data.get("panels", []):
                    self.con.execute("INSERT INTO panels VALUES(?,?,?,?,?)",
                                     (snapshot.paper_id, panel.get("figure_id"), panel.get("panel_id"),
                                      json.dumps(panel.get("bbox")), panel.get("status", "INVENTORIED")))
                self.con.execute("DELETE FROM conditions WHERE paper_id=?", (snapshot.paper_id,))
                self.con.execute("DELETE FROM measurements WHERE paper_id=?", (snapshot.paper_id,))
                for item in digitization.get("series", []):
                    series_record = SeriesRecord(
                        series_id=item["series_id"], paper_id=snapshot.paper_id,
                        figure_id=item["figure_id"], panel_id=item["panel_id"],
                        technique=item.get("technique"), domain=item.get("domain"),
                        label=item.get("label"), x_label=item.get("x_label"), y_label=item.get("y_label"),
                        x_unit=item.get("x_unit"), y_unit=item.get("y_unit"),
                        measurement_id=item.get("measurement_id") or f"measurement:{item['series_id']}",
                        y_axis_side=item.get("y_axis_side", "UNASSIGNED"),
                        extraction_method=item.get("extraction_method", "UNRESOLVED"),
                        extraction_status=item.get("extraction_status", "NEEDS_REVIEW"),
                        qc_status=item.get("qc_status", "PROVISIONAL_UNCALIBRATED"),
                        review_state=item.get("review_state", "NEEDS_REVIEW"),
                        subject_links=item.get("subject_links", []),
                        conditions=item.get("conditions", []),
                        evidence=item.get("evidence", []), metadata=item.get("metadata", {}),
                    )
                    self._insert_series(series_record)
                self._index_panel_csv_points(paper_root, set(series_by_id))
            count += 1
        return {"papers_indexed": count}


def append_panel_series_csv(paper_root: Path, figure_id: str, panel_id: str,
                            series: list[SeriesRecord]) -> Path | None:
    """Persist point batches, including explicit candidate values for unresolved dual Y axes."""
    panel_series = [item for item in series if item.points]
    if not panel_series:
        return None
    path = paper_root / "series" / f"{figure_id}__{panel_id}" / "panel_series.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "series_id", "point_index", "path_segment_index", "x_value", "x_label", "y_value",
        "pixel_x", "pixel_y", "y_err_low", "y_err_high", "err_type",
        "y_axis_side", "y_left_candidate", "y_right_candidate", "y_mapping_status",
    ]

    # Upgrade pre-existing panel CSVs in place before appending rows with the
    # extended dual-axis schema. Existing values are retained; the new
    # candidate columns stay blank for historical rows that cannot be
    # reconstructed from their old pixel provenance.
    if path.is_file():
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            previous_fields = list(reader.fieldnames or [])
            previous_rows = list(reader)
        if previous_fields != fieldnames:
            # Preserve any forward-compatible columns already present while
            # adding the current schema's dual-axis candidate fields.
            fieldnames = list(dict.fromkeys(previous_fields + fieldnames))
            temporary = path.with_name(f".{path.name}.tmp")
            with temporary.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in previous_rows:
                    writer.writerow({name: row.get(name, "") for name in fieldnames})
            temporary.replace(path)

    exists = path.is_file()
    with path.open("a" if exists else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for item in panel_series:
            item.metadata["points_count"] = len(item.points)
            calibrations = item.metadata.get("y_axis_calibrations")
            calibrations = calibrations if isinstance(calibrations, dict) else {}
            left_calibration = calibrations.get("LEFT")
            right_calibration = calibrations.get("RIGHT")
            if item.y_axis_side == "LEFT":
                right_calibration = None
            elif item.y_axis_side == "RIGHT":
                left_calibration = None
            assignment = item.metadata.get("series_axis_assignment")
            if not isinstance(assignment, dict):
                trace_specification = item.metadata.get("trace_specification")
                if not isinstance(trace_specification, dict):
                    trace_specification = {}
                assignment = trace_specification.get("series_axis_assignment", {})
            mapping_status = (
                assignment.get("status", "UNRESOLVED")
                if isinstance(assignment, dict) else "UNRESOLVED"
            )

            def candidate_value(calibration: Any, pixel_y: float | None):
                if not isinstance(calibration, dict) or pixel_y is None:
                    return ""
                slope = calibration.get("slope")
                intercept = calibration.get("intercept")
                if not isinstance(slope, (int, float)) or not isinstance(intercept, (int, float)):
                    return ""
                return float(slope) * float(pixel_y) + float(intercept)

            raster_qc = item.metadata.get("raster_qc", {})
            path_segments = (
                raster_qc.get("path_segments", [])
                if isinstance(raster_qc, dict) else []
            )
            segment_by_point = {}
            for segment in path_segments if isinstance(path_segments, list) else []:
                if not isinstance(segment, dict):
                    continue
                try:
                    segment_index = int(segment["segment_index"])
                    segment_start = int(segment["start_point_index"])
                    segment_end = int(segment["end_point_index"])
                except (KeyError, TypeError, ValueError):
                    continue
                for point_index in range(segment_start, segment_end + 1):
                    segment_by_point[point_index] = segment_index

            for point in item.points:
                writer.writerow({
                    "series_id": item.series_id,
                    "point_index": point.point_index,
                    "path_segment_index": segment_by_point.get(point.point_index, 0),
                    "x_value": point.x if isinstance(point.x, (int, float)) else "",
                    "x_label": point.x if isinstance(point.x, str) else "",
                    "y_value": point.y if point.y is not None else "",
                    "pixel_x": point.pixel_x if point.pixel_x is not None else "",
                    "pixel_y": point.pixel_y if point.pixel_y is not None else "",
                    "y_err_low": point.y_err_low if point.y_err_low is not None else "",
                    "y_err_high": point.y_err_high if point.y_err_high is not None else "",
                    "err_type": point.err_type,
                    "y_axis_side": item.y_axis_side,
                    "y_left_candidate": candidate_value(left_calibration, point.pixel_y),
                    "y_right_candidate": candidate_value(right_calibration, point.pixel_y),
                    "y_mapping_status": mapping_status,
                })
    return path
