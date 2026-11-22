"""Merge Skill pipeline classifications with labelled visual triage for all images."""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
ROOT = Path(r"E:\Zinc_batters_datas\chem-literacy\runs\preprocessed\10.1002_adfm.75805")

# Manual visual judgments from contact sheets. Key = basename. Value = (category, evidence, digitizable)
VISUAL = {
    "MAIN_MAIN_FIG_P3_01.png": ("mixed_non_curve", "schematic + SEM/TEM/HRTEM + EDX maps; no numeric plot frame for whole image", "NO"),
    "MAIN_MAIN_FIG_P4_02.png": ("mixed_curve_and_microscopy", "panel a CE cycling curves; b optical photos; c bar comparison (P1 unsupported)", "PANEL_ONLY"),
    "MAIN_MAIN_FIG_P5_03.png": ("mixed_microscopy_and_curves", "a-d SEM; e LSV, f Tafel, g Nyquist, h bar, i XRD, j histogram are sub-panels", "PANEL_ONLY"),
    "MAIN_MAIN_FIG_P7_04.png": ("multi_panel_curves", "a LSV, b Nyquist, c DRT, d H2-vs-time, f PDOS; e is Gibbs schematic", "PANEL_ONLY"),
    "MAIN_MAIN_FIG_P7_05.png": ("multi_panel_curves", "a CV, b rate, d/e cycling plots; c schematic; f scatter comparison", "PANEL_ONLY"),
    "MAIN_MAIN_FIG_P8_06.png": ("invalid_asset", "1549x89 header/text strip; caption is body prose; no plot frame", "NO"),
    "image1.png": ("mixed_structure_and_bar", "schematic + grouped bar chart (P1 unsupported)", "NO"),
    "image10.png": ("spectrum_curve", "Intensity vs 2theta XRD pattern with numeric ticks", "UNLINKED"),
    "image11.png": ("curve_composite", "multi-panel voltage profiles / CE; no unique upstream figure association", "UNLINKED"),
    "image12.png": ("bar_chart", "CE bar charts; P1 bar support not production", "NO"),
    "image13.png": ("curve_composite", "CE curve and CV-like plot; unlinked", "UNLINKED"),
    "image14.png": ("spectrum_composite", "XRD patterns a-d; unlinked", "UNLINKED"),
    "image15.png": ("curve_composite", "CV, Tafel, schematic and histogram composite; unlinked", "UNLINKED"),
    "image16.jpeg": ("curve", "single LSV curve with Potential (V vs SHE) / Current axes", "UNLINKED"),
    "image17.png": ("spectrum_composite", "XRD/XPS pattern panels; unlinked", "UNLINKED"),
    "image18.png": ("structure_model", "atomic structure model", "NO"),
    "image19.png": ("structure_model", "atomic structure model series", "NO"),
    "image2.png": ("schematic_and_photo", "surface schematic and photographs", "NO"),
    "image20.png": ("curve_composite", "LSV / Tafel / Nyquist panels; unlinked", "UNLINKED"),
    "image21.png": ("curve_composite", "chronoamperometry curves; unlinked", "UNLINKED"),
    "image22.png": ("structure_model", "atomic structure model", "NO"),
    "image23.jpeg": ("curve", "Capacitance vs Potential (V vs SCE) curve; unlinked", "UNLINKED"),
    "image24.png": ("microscopy", "SEM + EDS element maps", "NO"),
    "image25.jpeg": ("spectrum_curve", "XRD Intensity vs 2theta; unlinked", "UNLINKED"),
    "image26.png": ("curve_composite", "CV curves 1st-4th cycles; unlinked", "UNLINKED"),
    "image27.jpeg": ("curve", "capacity/coulombic efficiency vs cycle number; unlinked", "UNLINKED"),
    "image28.png": ("curve_composite", "electrochemical profiles; unlinked", "UNLINKED"),
    "image3.png": ("microscopy", "SEM image", "NO"),
    "image4.png": ("microscopy", "AFM images", "NO"),
    "image5.png": ("microscopy", "TEM images", "NO"),
    "image6.png": ("simulation_map", "simulation field maps", "NO"),
    "image7.png": ("spectrum_composite", "XPS spectra composite", "UNLINKED"),
    "image8.jpeg": ("spectrum_curve", "Zn 2p XPS spectrum", "UNLINKED"),
    "image9.png": ("spectrum_composite", "XPS / adsorption spectra composite", "UNLINKED"),
}


def main() -> None:
    with (OUT / "inventory.csv").open(encoding="utf-8") as handle:
        inventory = list(csv.DictReader(handle))
    pipe = {}
    with (OUT / "classification_results.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pipe[row["figure_id"]] = row
    fields = [
        "file", "figure_id", "width", "height", "classification_source", "category",
        "skill_chart_family", "skill_status", "confidence", "skill_evidence",
        "visual_evidence", "entered_digitization", "reason",
    ]
    rows = []
    for item in inventory:
        if not item["width"]:
            continue
        rel = item["relative_path"]
        name = Path(rel).name
        p = pipe.get(item["figure_id"], {})
        cat, evidence, entered = VISUAL.get(name, ("unknown", "no visual judgment recorded", "NO"))
        rows.append(
            {
                "file": rel,
                "figure_id": item["figure_id"] or "",
                "width": item["width"],
                "height": item["height"],
                "classification_source": "SKILL_PIPELINE+MANUAL_VISUAL" if p else "MANUAL_VISUAL_ONLY",
                "category": cat,
                "skill_chart_family": p.get("chart_family", ""),
                "skill_status": p.get("classification_status", ""),
                "confidence": p.get("confidence", ""),
                "skill_evidence": p.get("evidence", ""),
                "visual_evidence": evidence,
                "entered_digitization": entered,
                "reason": p.get("reason", "") or (
                    "No unique upstream figure_id / no local axis evidence; Skill did not process SI assets"
                    if "SI" in rel else ""
                ),
            }
        )
    with (OUT / "classification_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
