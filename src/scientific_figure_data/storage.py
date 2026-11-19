from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .hashing import atomic_write_json, sha256_file, sha256_json
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
 bbox_json TEXT, status TEXT, PRIMARY KEY(paper_id, figure_id, panel_id),
 FOREIGN KEY(paper_id, figure_id) REFERENCES figures(paper_id, figure_id)
);
CREATE TABLE IF NOT EXISTS entities(
 entity_id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, entity_type TEXT,
 domain TEXT, aliases_json TEXT NOT NULL DEFAULT '[]', evidence_json TEXT NOT NULL DEFAULT '[]'
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
 panel_id TEXT NOT NULL, technique TEXT, domain TEXT, label TEXT, x_unit TEXT, y_unit TEXT,
 y_axis_side TEXT NOT NULL, extraction_status TEXT NOT NULL, qc_status TEXT NOT NULL,
 review_state TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_series_paper ON series(paper_id);
CREATE INDEX IF NOT EXISTS idx_series_technique ON series(technique);
CREATE INDEX IF NOT EXISTS idx_series_domain ON series(domain);
CREATE TABLE IF NOT EXISTS series_points(
 series_id TEXT NOT NULL, point_index INTEGER NOT NULL, x_value REAL, x_label TEXT,
 y_value REAL, pixel_x REAL, pixel_y REAL, y_err_low REAL, y_err_high REAL, err_type TEXT,
 PRIMARY KEY(series_id, point_index), FOREIGN KEY(series_id) REFERENCES series(series_id)
);
CREATE TABLE IF NOT EXISTS series_subject_links(
 series_id TEXT NOT NULL, entity_id TEXT NOT NULL, role_in_series TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}', link_status TEXT NOT NULL DEFAULT 'UNASSIGNED',
 PRIMARY KEY(series_id, entity_id, role_in_series)
);
CREATE TABLE IF NOT EXISTS observations(
 observation_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, name TEXT NOT NULL,
 value_json TEXT NOT NULL, source_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs(
 paper_id TEXT PRIMARY KEY, state TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0,
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
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    return con


def point_dict(point) -> dict[str, Any]:
    return asdict(point) if hasattr(point, "__dataclass_fields__") else dict(point)


def write_paper_artifacts(
    output_root: Path,
    snapshot: PaperSnapshot,
    figures: list[dict],
    panels: list[dict],
    series: list[SeriesRecord],
    status: str,
    extra: dict | None = None,
) -> dict:
    paper_root = output_root / "papers" / snapshot.paper_id
    evidence_dir = paper_root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    paper_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "1.0",
        "paper_id": snapshot.paper_id,
        "source_dir": snapshot.source_dir,
        "input_fingerprint": snapshot.input_fingerprint,
        "upstream_version": snapshot.detected_upstream_version,
        "adapter_version": snapshot.adapter_version,
        "created_at": snapshot.created_at,
        "artifacts": [asdict(a) for a in snapshot.artifacts],
        "missing_roles": snapshot.missing_roles,
        "warnings": snapshot.warnings,
        "processing_status": status,
    }
    atomic_write_json(paper_root / "paper_manifest.json", manifest)
    atomic_write_json(paper_root / "figure_inventory.json", {
        "schema_version": "1.0", "paper_id": snapshot.paper_id, "figures": figures
    })
    digitization = {
        "schema_version": "1.0",
        "paper_id": snapshot.paper_id,
        "input_fingerprint": snapshot.input_fingerprint,
        "generated_at": utc_now(),
        "status": status,
        "qc_threshold_status": "PROVISIONAL_UNCALIBRATED",
        "series": [{
            **{k: v for k, v in asdict(s).items() if k != "points"},
            "points_count": len(s.points),
        } for s in series],
        "extra": extra or {},
    }
    atomic_write_json(paper_root / "digitization.json", digitization)

    # A single CSV per panel prevents one-file-per-series/point proliferation.
    grouped: dict[tuple[str, str], list[SeriesRecord]] = {}
    for item in series:
        grouped.setdefault((item.figure_id, item.panel_id), []).append(item)
    csv_paths = []
    for (figure_id, panel_id), panel_series in grouped.items():
        relative_path = Path("series") / f"{figure_id}__{panel_id}" / "panel_series.csv"
        csv_path = paper_root / relative_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["series_id", "point_index", "x_value", "x_label", "y_value",
                             "pixel_x", "pixel_y", "y_err_low", "y_err_high", "err_type"])
            for item in panel_series:
                for point in item.points:
                    writer.writerow([item.series_id, point.point_index,
                                     point.x if isinstance(point.x, (int, float)) else "",
                                     point.x if isinstance(point.x, str) else "",
                                     point.y, point.pixel_x, point.pixel_y,
                                     point.y_err_low, point.y_err_high, point.err_type])
        csv_paths.append(relative_path.as_posix())

    canonical_paths = ["paper_manifest.json", "figure_inventory.json", "digitization.json"] + csv_paths
    hashes = {name: sha256_file(paper_root / name) for name in canonical_paths}
    bundle = {
        "schema_version": "1.0", "bundle_version": "1.0", "paper_id": snapshot.paper_id,
        "generated_at": utc_now(), "input_fingerprint": snapshot.input_fingerprint,
        "algorithm_versions": {"core": "0.1.0"}, "profile_versions": {},
        "status": status, "canonical_artifacts": canonical_paths, "content_hashes": hashes,
        "series_count": len(series), "figure_count": len(figures),
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
        with self.con:
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
                    series: list[SeriesRecord], status: str, artifact_paths: dict | None = None):
        with self.con:
            self.register_paper(snapshot, status, artifact_paths)
            self.con.execute("DELETE FROM series WHERE paper_id=?", (snapshot.paper_id,))
            self.con.execute("DELETE FROM panels WHERE paper_id=?", (snapshot.paper_id,))
            self.con.execute("DELETE FROM figures WHERE paper_id=?", (snapshot.paper_id,))
            for fig in figures:
                figure_id = str(fig["figure_id"])
                self.con.execute("INSERT INTO figures VALUES(?,?,?,?)",
                                 (snapshot.paper_id, figure_id, fig.get("page"), fig.get("caption")))
            for panel in panels:
                self.con.execute("INSERT INTO panels VALUES(?,?,?,?,?)",
                                 (snapshot.paper_id, str(panel["figure_id"]), str(panel["panel_id"]),
                                  json.dumps(panel.get("bbox"), ensure_ascii=False),
                                  panel.get("status", "INVENTORIED")))
            for item in series:
                self._insert_series(item)

    def _insert_series(self, item: SeriesRecord):
        self.con.execute(
            """INSERT INTO series(series_id,paper_id,figure_id,panel_id,technique,domain,label,
               x_unit,y_unit,y_axis_side,extraction_status,qc_status,review_state,metadata_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item.series_id, item.paper_id, item.figure_id, item.panel_id, item.technique,
             item.domain, item.label, item.x_unit, item.y_unit, item.y_axis_side,
             item.extraction_status, item.qc_status, item.review_state,
             json.dumps(item.metadata, ensure_ascii=False)),
        )
        self.con.executemany(
            """INSERT INTO series_points(series_id,point_index,x_value,x_label,y_value,pixel_x,pixel_y,
               y_err_low,y_err_high,err_type) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            [(item.series_id, p.point_index, p.x if isinstance(p.x, (int, float)) else None,
              p.x if isinstance(p.x, str) else None, p.y, p.pixel_x, p.pixel_y,
              p.y_err_low, p.y_err_high, p.err_type) for p in item.points],
        )
        self.con.executemany(
            "INSERT INTO series_subject_links(series_id,entity_id,role_in_series,evidence_json,link_status) VALUES(?,?,?,?,?)",
            [(item.series_id, link.get("entity_id", "UNKNOWN"), link.get("role_in_series", "unknown"),
              json.dumps(link.get("evidence", {}), ensure_ascii=False),
              link.get("status", "UNASSIGNED")) for link in item.subject_links],
        )

    def query_series(self, filters: dict[str, str | None], limit: int = 500) -> list[dict]:
        sql = """SELECT s.*, p.source_dir FROM series s JOIN papers p ON p.paper_id=s.paper_id WHERE 1=1"""
        args: list[Any] = []
        mapping = {"paper_id": "s.paper_id", "technique": "s.technique", "domain": "s.domain",
                   "review_state": "s.review_state", "qc_status": "s.qc_status"}
        for key, column in mapping.items():
            value = filters.get(key)
            if value:
                sql += f" AND {column}=?"
                args.append(value)
        entity = filters.get("entity_id")
        if entity:
            sql += " AND EXISTS (SELECT 1 FROM series_subject_links l WHERE l.series_id=s.series_id AND l.entity_id=?)"
            args.append(entity)
        role = filters.get("series_role")
        if role:
            sql += " AND EXISTS (SELECT 1 FROM series_subject_links l WHERE l.series_id=s.series_id AND l.role_in_series=?)"
            args.append(role)
        sql += " ORDER BY s.paper_id,s.figure_id,s.panel_id,s.series_id LIMIT ?"
        args.append(max(1, min(int(limit), 10000)))
        return [dict(row) for row in self.con.execute(sql, args).fetchall()]

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
            if not (manifest_path.is_file() and digitization_path.is_file() and figures_path.is_file()):
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fig_data = json.loads(figures_path.read_text(encoding="utf-8"))
            # Rebuild only the query-critical scalar index. Point CSVs remain canonical artifacts.
            snapshot = PaperSnapshot(
                paper_id=manifest["paper_id"], source_dir=manifest["source_dir"],
                detected_upstream_version=manifest.get("upstream_version"),
                adapter_version=manifest["adapter_version"], created_at=manifest["created_at"],
                input_fingerprint=manifest["input_fingerprint"],
            )
            with self.con:
                self.con.execute("DELETE FROM series WHERE paper_id=?", (snapshot.paper_id,))
                self.con.execute("DELETE FROM panels WHERE paper_id=?", (snapshot.paper_id,))
                self.con.execute("DELETE FROM figures WHERE paper_id=?", (snapshot.paper_id,))
                self.register_paper(snapshot, manifest.get("processing_status", "UNKNOWN"), {
                    "manifest_path": str(manifest_path), "bundle_path": str(paper_root / "paper_bundle.json")
                })
                for fig in fig_data.get("figures", []):
                    self.con.execute("INSERT INTO figures VALUES(?,?,?,?)",
                                     (snapshot.paper_id, fig.get("figure_id"), fig.get("page"),
                                      fig.get("caption")))
                for series in json.loads(digitization_path.read_text(encoding="utf-8")).get("series", []):
                    self.con.execute(
                        """INSERT OR REPLACE INTO series(series_id,paper_id,figure_id,panel_id,technique,
                           domain,label,x_unit,y_unit,y_axis_side,extraction_status,qc_status,review_state,metadata_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (series["series_id"], snapshot.paper_id, series["figure_id"], series["panel_id"],
                         series.get("technique"), series.get("domain"), series.get("label"),
                         series.get("x_unit"), series.get("y_unit"), series.get("y_axis_side", "UNASSIGNED"),
                         series.get("extraction_status", "NEEDS_REVIEW"), series.get("qc_status", "PROVISIONAL_UNCALIBRATED"),
                         series.get("review_state", "NEEDS_REVIEW"), json.dumps(series.get("metadata", {}))),
                    )
            count += 1
        return {"papers_indexed": count}
