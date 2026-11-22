"""Build manifest.json for the synchronized real-image evidence bundle."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = []
    for path in sorted(BASE.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({
                "path": path.relative_to(BASE).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Synchronize existing real-image digitization evidence to GitHub for downstream development. No pipeline was re-run; no source code or Skill was modified.",
        "repository": "Tuzhidingdong/Figure_digitization",
        "requested_base_branch": "feat/p2-multipanel-detection-worker-cleanup",
        "actual_base_branch": "fix/p2-multipanel-detection-worker-cleanup",
        "base_head": "b039b29a21b412da311e321d1087ebc42ffb2c93",
        "sync_branch": "sync/real-image-evidence-2026-11-22",
        "image_sha256": {
            "P8_06_upstream": "581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549",
            "P8_06_cli_input": "581d8e7c36d1b6ceae4f49cb866670fa06478bb9ac13d252ade1d2c9696bf549",
            "P3_02_upstream": "9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e",
            "P3_02_cli_input": "9d52d73df2c49604d7179e241154f0bb6b269bb822bc7708e005aa43f35a2f7e",
        },
        "cases": {
            "P8_06": {
                "paper": "10.1002_adma.202404834",
                "image": "extracted_figures/MAIN/MAIN_MAIN_FIG_P8_06.png",
                "run_head": "4bb386c48bb54fe9cde31ff542f96516e58f201f",
                "algorithm_version": "0.4.0",
                "result": "FAILED / NEEDS_REVIEW: 1 panel, 1 series, 0 points; dominant detected plot was a single-axis voltage panel; no dual-Y or geometry output.",
            },
            "P3_02": {
                "paper": "10.1002_adma.202001469",
                "image": "extracted_figures/MAIN/MAIN_MAIN_FIG_P3_02.png",
                "run_head": "4bb386c48bb54fe9cde31ff542f96516e58f201f",
                "algorithm_version": "0.4.0",
                "result": "STALLED then FAILED / NEEDS_REVIEW: paper artifacts written but corpus finalization never completed; 1 panel, 1 series, 0 points, PLOT_REGION_UNRESOLVED.",
            },
        },
        "controls": [
            "manual_single_panel_validation_25_points (controlled manual input, 25 points, not automatic)",
            "P7_05_PR19_multicolor_dualY (failed automatic multicolor/dual-Y case)",
            "P7_05_PR18_ocrfix (failed automatic case, OCR working)",
            "P7_05_PR17_ocr_init_failure (failed OCR initialization)",
            "adfm_75805_fullpaper_PR16 (whole-paper failed case, includes bad P8_06 strip)",
            "P7_05_PR16_single_figure (single-image failed case)",
            "root_cause_audit_PR16 (source-level root cause report)",
        ],
        "code_state": {
            "uncommitted_source_changes": "none detected in tracked src/ across all local worktrees",
            "unpushed_commits": "none detected",
            "note": "Original project main worktree has a modified STATUS.md and untracked .agents/, __pycache__/, test_outputs/ from earlier testing; these are not source changes and were not synchronized as code.",
        },
        "large_file_policy": "No file in this bundle exceeds 1 MB; Git LFS was not required.",
        "file_count": len(files),
        "files": files,
    }
    (BASE / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest files={len(files)}")


if __name__ == "__main__":
    main()
