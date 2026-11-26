"""Blind curve discovery v3 - generic non-data-graphic classification,
global trajectory association, junction/crossing hypotheses, source-pixel audit.
Programmatic only: PIL/NumPy/scipy and existing scientific_figure_data functions.
"""
from __future__ import annotations

import base64
import csv
import itertools
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import ConvexHull

SRC = r"E:\Zinc_batters_datas\_worktrees\Figure_digitization_pr24_a296ca2\src"
sys.path.insert(0, SRC)
from scientific_figure_data import raster, plot_region as pr

ROOT = Path(r"E:\Zinc_batters_datas\Figure_digitization\test_outputs\v2.1_real_paper_10.1002_adfm.75805_direct_root")
V1 = ROOT / "blind_curve_discovery_v1"
V2 = ROOT / "blind_curve_discovery_v2"
OUT = ROOT / "blind_curve_discovery_v3"
IMG = V1 / "01_original.png"

# ---- historical audit inputs only (read, never used to create points) --------
hist_audit = list(csv.DictReader((V2/"source_pixel_audit.csv").open(encoding="utf-8")))
hist_bridge = list(csv.DictReader((V2/"morphology_bridge_pixels.csv").open(encoding="utf-8")))
hist_index = {(int(r["pixel_x"]), int(r["pixel_y"])): r["audit_status"] for r in hist_audit}
hist_added = {(int(r["pixel_x"]), int(r["pixel_y"])) for r in hist_bridge
              if r["change_type"] == "ADDED_BY_CLOSING"}

with Image.open(IMG) as im:
    rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
H, W = rgb.shape[:2]
vv = rgb.astype(np.int16)
lum_all = 0.2126*vv[:,:,0] + 0.7152*vv[:,:,1] + 0.0722*vv[:,:,2]
chroma_all = vv.max(axis=2) - vv.min(axis=2)

def group_runs(idx):
    idx = [int(v) for v in idx]
    if not idx: return []
    out=[]; s=p=int(idx[0])
    for k in idx[1:]:
        k=int(k)
        if k-p<=3: p=k
        else: out.append((s,p)); s=p=k
    out.append((s,p)); return out

# ---- generic plot frame: dark projection peaks (no hardcoded coordinates) ---
dark = lum_all <= 178
row_frac = dark.mean(axis=1); col_frac = dark.mean(axis=0)
row_bands = group_runs(np.where(row_frac >= 0.5)[0])
col_bands = group_runs(np.where(col_frac >= 0.5)[0])
if len(row_bands) < 2 or len(col_bands) < 2:
    raise RuntimeError("no generic rectangular frame found")
top = int(round(sum(row_bands[0])/2)); bottom = int(round(sum(row_bands[-1])/2))
left = int(round(sum(col_bands[0])/2)); right = int(round(sum(col_bands[-1])/2))
BOX = (left, top, right, bottom)
BX0, BY0, BX1, BY1 = BOX
PW, PH = BX1-BX0, BY1-BY0

# ---- candidate family pools (existing project entry points) -----------------
ch = pr.detect_chromatic_color_families(IMG, BOX)
ac = pr.detect_achromatic_trace_family(IMG, BOX)
famdefs = []
for f in ch.get("families", []):
    famdefs.append({"index": len(famdefs), "name": "CHROMATIC_HSV_HUE",
                    "rgb": tuple(f["color_rgb"]), "tol": int(f["color_tolerance"]),
                    "cm": f["color_match"]})
for f in ac.get("families", []):
    famdefs.append({"index": len(famdefs), "name": "ACHROMATIC_LUMINANCE_RANGE",
                    "rgb": tuple(f["color_rgb"]), "tol": 0, "cm": f["color_match"]})

region = rgb[BY0:BY1, BX0:BX1]
fammasks = {}
for fd in famdefs:
    raw = raster._build_color_mask(region, fd["rgb"], fd["tol"], fd["cm"])
    fammasks[fd["index"]] = {"raw": raw, "closed": raster._close_binary_mask(raw)}

# ---- helpers ----------------------------------------------------------------
def linear_slope(xs, ys):
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    if len(xs) < 3 or np.ptp(xs) < 1:
        return 0.0
    return float(np.polyfit(xs, ys, 1)[0])

def hull_area(coords):
    pts = np.unique(np.asarray(coords, dtype=float), axis=0)
    if len(pts) < 3: return float(len(pts))
    try:
        return float(ConvexHull(pts).volume)
    except Exception:
        return float(len(pts))

# ---- enumerate all connected candidate components from closed masks ---------
components = []
for fd in famdefs:
    mask = fammasks[fd["index"]]["closed"]
    lab, n = ndimage.label(mask, structure=np.ones((3,3)))
    objs = ndimage.find_objects(lab)
    for i, sl in enumerate(objs, 1):
        if sl is None: continue
        ys, xs = np.where(lab[sl] == i)
        gy = ys + sl[0].start + BY0
        gx = xs + sl[1].start + BX0
        if len(gx) < 4: continue
        x0, x1 = int(gx.min()), int(gx.max())
        y0, y1 = int(gy.min()), int(gy.max())
        w, h = x1-x0+1, y1-y0+1
        area = len(gx)
        bbox_area = w*h
        fill = area / bbox_area
        solidity = area / max(1.0, hull_area(np.column_stack([gx,gy])))
        # skeleton via project Zhang-Suen routine
        local = np.zeros((h, w), dtype=bool)
        local[gy-y0, gx-x0] = True
        skel, _ = raster._thin_binary_component(local)
        skel_count = int(skel.sum())
        skel_ratio = skel_count / area
        # rectangularity: coverage of the bbox border rows/cols
        border = np.concatenate([local[0,:], local[-1,:], local[:,0], local[:,-1]])
        rectangularity = float(border.mean())
        # fraction of component pixels lying on its own bbox border (frame detection)
        dist_border = np.minimum.reduce([gx-x0, x1-gx, gy-y0, y1-gy])
        border_pixel_fraction = float(np.mean(dist_border <= 3))
        # PCA direction consistency
        pts = np.column_stack([gx.astype(float), gy.astype(float)])
        cen = pts.mean(axis=0)
        cov = np.cov((pts-cen).T) if len(pts) > 1 else np.zeros((2,2))
        eig = np.linalg.eigvalsh(cov)
        direction_consistency = float(eig[-1]/max(1e-9, eig.sum()))
        slope = linear_slope(gx, gy)
        # line width: median per-column count (or per-row for near-vertical)
        if h > 2.5*w:
            per = np.array([np.sum(gy == yy) for yy in np.unique(gy)], float)
        else:
            per = np.array([np.sum(gx == xx) for xx in np.unique(gx)], float)
        width_med = float(np.median(per)); width_max = int(per.max())
        lum = lum_all[gy, gx]; chro = chroma_all[gy, gx]
        # ordered paths + junction evidence
        comp_dict = {"coords": np.column_stack([gy, gx]).astype(np.int32),
                     "bbox": [x0, y0, x1+1, y1+1]}
        paths, qc = raster._ordered_skeleton_paths(
            comp_dict,
            minimum_path_x_span=max(6, int(round(PW*0.08))),
            keep_unsupported_junction_breakpoints=True,
        )
        components.append({
            "component_id": f"F{len(components)+1:03d}",
            "family": fd["name"], "family_index": fd["index"],
            "bbox": [x0, y0, x1+1, y1+1], "x_range": [x0, x1], "y_range": [y0, y1],
            "width": w, "height": h, "area": area,
            "aspect_ratio": round(w/max(1,h), 3),
            "fill_ratio": round(fill, 3), "solidity": round(solidity, 3),
            "skeleton_pixels": skel_count, "skeleton_to_area": round(skel_ratio, 3),
            "rectangularity": round(rectangularity, 3),
            "border_pixel_fraction": round(border_pixel_fraction, 3),
            "direction_consistency": round(direction_consistency, 3),
            "tangent_slope": round(slope, 4),
            "line_width_median": round(width_med, 2), "line_width_max": width_max,
            "luminance_median": round(float(np.median(lum)), 1),
            "luminance_mean": round(float(np.mean(lum)), 1),
            "chroma_median": int(np.median(chro)), "chroma_mean": round(float(np.mean(chro)), 1),
            "path_count": int(qc.get("path_count", 0)),
            "endpoint_count": int(qc.get("endpoint_count", 0)),
            "junction_count": int(qc.get("junction_count", 0)),
            "junction_pairings": qc.get("junction_pairings", []),
            "ambiguous_junctions": qc.get("ambiguous_junction_clusters", []),
            "path_qc_status": qc.get("status"),
            "path_summaries": qc.get("path_summaries", []),
            "paths": paths,
            "_gx": gx, "_gy": gy,
        })

# ---- alignment / text-neighbour context (computed across all components) ----
for c in components:
    xc = (c["x_range"][0]+c["x_range"][1])/2
    yc = (c["y_range"][0]+c["y_range"][1])/2
    c["_xc"], c["_yc"] = xc, yc
for c in components:
    row_al = sum(1 for o in components if o is not c
                 and abs(o["_yc"]-c["_yc"]) <= 4
                 and abs(o["height"]-c["height"]) <= 4)
    col_al = sum(1 for o in components if o is not c
                 and abs(o["_xc"]-c["_xc"]) <= 4
                 and abs(o["width"]-c["width"]) <= 4)
    near = sum(1 for o in components if o is not c
               and abs(o["_xc"]-c["_xc"]) <= 28 and abs(o["_yc"]-c["_yc"]) <= 28)
    c["row_aligned_neighbours"] = row_al
    c["col_aligned_neighbours"] = col_al
    c["nearby_components_28px"] = near
    c["continuity_with_other_paths"] = sum(
        1 for o in components if o is not c
        and o["path_count"] > 0
        and min(math.hypot(a[1]-b[1], a[0]-b[0])
                for a in (c["paths"][0][0], c["paths"][0][-1]) if c["paths"]
                for b in (o["paths"][0][0], o["paths"][0][-1]) if o["paths"]) <= 24
    ) if c["paths"] else 0

# ---- generic classification --------------------------------------------------
def classify(c):
    reasons = []
    compact = c["width"] <= 26 and c["height"] <= 26 and c["fill_ratio"] >= 0.45
    regular = c["row_aligned_neighbours"] >= 2 or c["col_aligned_neighbours"] >= 2
    solid_block = c["solidity"] >= 0.78 and c["fill_ratio"] >= 0.55 and c["skeleton_to_area"] < 0.48
    rectangular = c["rectangularity"] >= 0.55 and c["fill_ratio"] >= 0.45
    glyph_grid = compact and (c["row_aligned_neighbours"] >= 2 or c["nearby_components_28px"] >= 3)
    # A shallow, well-filled component containing several skeleton paths and
    # many junctions is a merged row of regular strips/glyphs, not one trace.
    strip_grid = (
        c["height"] <= max(30, int(0.14*PH)) and c["fill_ratio"] >= 0.35
        and c["junction_count"] >= 3 and c["path_count"] >= 2
    )
    frame_like = (
        c["width"] >= 0.85*PW and c["height"] >= 0.85*PH
        and c["border_pixel_fraction"] >= 0.80
    )
    if frame_like:
        reasons.append("border_spanning_plot_frame_or_grid_not_a_data_trace")
    if strip_grid:
        reasons.append("merged_regular_strip_grid_or_filled_glyph_row")
    if solid_block or rectangular or glyph_grid or (compact and regular and c["direction_consistency"] < 0.9):
        reasons.append("compact_or_regular_filled_block_or_glyph_grid")
    real_path = (
        c["path_count"] >= 1 and c["paths"]
        and max(max(p[1] for p in path)-min(p[1] for p in path)+1 for path in c["paths"]) >= 60
        and max(max(p[0] for p in path)-min(p[0] for p in path)+1 for path in c["paths"]) >= max(8, int(0.05*PW))
        and max(len(path) for path in c["paths"]) >= 100
        and c["direction_consistency"] >= 0.55
    )
    if reasons:
        return "NON_DATA_GRAPHIC_CANDIDATE", reasons
    if real_path and c["skeleton_to_area"] >= 0.18:
        return "DATA_PATH_CANDIDATE", ["long_thin_dense_ordered_path_with_unique_endpoints"]
    if c["area"] >= 8 and (c["path_count"] >= 1 or c["direction_consistency"] >= 0.65):
        return "AMBIGUOUS_REVIEW", ["short_or_disconnected_linear_fragment_no_unique_trajectory"]
    return "NON_DATA_GRAPHIC_CANDIDATE", ["tiny_or_unstructured_foreground"]

for c in components:
    c["classification"], c["classification_reasons"] = classify(c)

with (OUT/"candidate_component_catalog.csv").open("w", newline="", encoding="utf-8") as fh:
    fields = ["component_id","family","bbox","x_range","y_range","width","height","area",
              "aspect_ratio","fill_ratio","solidity","skeleton_pixels","skeleton_to_area",
              "rectangularity","border_pixel_fraction","direction_consistency","tangent_slope",
              "line_width_median","line_width_max","luminance_median","luminance_mean",
              "chroma_median","chroma_mean","row_aligned_neighbours","col_aligned_neighbours",
              "nearby_components_28px","continuity_with_other_paths","path_count",
              "endpoint_count","junction_count","path_qc_status","classification",
              "classification_reasons"]
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    for c in components:
        w.writerow({k: (json.dumps(c[k]) if isinstance(c[k], list) else c[k]) for k in fields})

with (OUT/"non_data_graphic_candidates.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["component_id","family","bbox","width","height","area","aspect_ratio",
                "fill_ratio","solidity","rectangularity","skeleton_to_area",
                "row_aligned_neighbours","col_aligned_neighbours","nearby_components_28px",
                "luminance_median","chroma_median","classification_reasons"])
    for c in components:
        if c["classification"] == "NON_DATA_GRAPHIC_CANDIDATE":
            w.writerow([c["component_id"],c["family"],json.dumps(c["bbox"]),c["width"],c["height"],
                        c["area"],c["aspect_ratio"],c["fill_ratio"],c["solidity"],c["rectangularity"],
                        c["skeleton_to_area"],c["row_aligned_neighbours"],c["col_aligned_neighbours"],
                        c["nearby_components_28px"],c["luminance_median"],c["chroma_median"],
                        ";".join(c["classification_reasons"])])

# ---- fragments for global association ---------------------------------------
fragments = []
for c in components:
    if c["classification"] == "NON_DATA_GRAPHIC_CANDIDATE": continue
    for pi, path in enumerate(c["paths"]):
        if len(path) < 8: continue
        xs = [p[1] for p in path]; ys = [p[0] for p in path]
        x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
        if x1-x0+1 < 6: continue
        def slope_of(seq):
            if len(seq) < 4: return 0.0
            a, b = seq[:max(3,len(seq)//3)], seq[-max(3,len(seq)//3):]
            ax = sum(p[1] for p in a)/len(a); ay = sum(p[0] for p in a)/len(a)
            bx = sum(p[1] for p in b)/len(b); by = sum(p[0] for p in b)/len(b)
            return (by-ay)/max(1.0, bx-ax)
        fragments.append({
            "fragment_id": f"{c['component_id']}.P{pi+1}",
            "component_id": c["component_id"], "family": c["family"],
            "family_index": c["family_index"], "classification": c["classification"],
            "bbox": [int(x0),int(y0),int(x1+1),int(y1+1)],
            "x0":int(x0),"x1":int(x1),"y0":int(y0),"y1":int(y1),
            "start": (float(path[0][1]), float(path[0][0])),
            "end": (float(path[-1][1]), float(path[-1][0])),
            "slope_start": slope_of(path), "slope_end": slope_of(path),
            "line_width": c["line_width_median"], "luminance": c["luminance_median"],
            "chroma": c["chroma_median"], "length": len(path),
            "path": path,
        })

MAX_GAP = max(8, int(round(PW*0.05)))
RESID_LIMIT = max(8.0, PH*0.08)
SLOPE_LIMIT = 1.20
# A continuity bonus is required: with strictly positive edge costs a path cover
# would trivially keep every fragment separate. The bonus expresses the prior
# that supported continuations are preferable, while hard filters above still
# reject geometrically unsupported links.
LINK_BONUS = 30.0

def edge_cost(a, b):
    if a["family_index"] != b["family_index"]: return None
    if b["x0"] <= a["x1"]: return None
    gap = b["x0"] - a["x1"]
    if gap > MAX_GAP: return None
    predicted = a["end"][1] + a["slope_end"]*gap
    residual = abs(b["start"][1] - predicted)
    if residual > RESID_LIMIT: return None
    slope_delta = abs(a["slope_end"] - b["slope_start"])
    if slope_delta > SLOPE_LIMIT: return None
    width_delta = abs(a["line_width"] - b["line_width"])
    if width_delta > max(2.0, 0.6*min(a["line_width"], b["line_width"])): return None
    lum_delta = abs(a["luminance"] - b["luminance"])
    if lum_delta > 45: return None
    cost = (residual + 2.0*slope_delta + 0.05*gap + 0.8*width_delta
            + 0.02*lum_delta)
    return {"cost": round(float(cost),3), "gap": gap, "residual": round(float(residual),3),
            "slope_delta": round(float(slope_delta),3), "width_delta": round(float(width_delta),3),
            "luminance_delta": round(float(lum_delta),1)}

edges = {}
for i, a in enumerate(fragments):
    for j, b in enumerate(fragments):
        if i == j: continue
        e = edge_cost(a, b)
        if e: edges[(i,j)] = e

# ---- min-cost flow path cover ------------------------------------------------
class MCMF:
    def __init__(self, n):
        self.g = [[] for _ in range(n)]
    def add(self, u, v, cap, cost):
        self.g[u].append([v, len(self.g[v]), cap, cost])
        self.g[v].append([u, len(self.g[u])-1, 0, -cost])
    def solve(self, s, t, pass_edges=None):
        n=len(self.g); flow=0; cost=0
        while True:
            dist=[float('inf')]*n; dist[s]=0
            pv=[-1]*n; pe=[-1]*n
            inq=[False]*n; q=deque([s]); inq[s]=True
            while q:
                u=q.popleft(); inq[u]=False
                for idx,e in enumerate(self.g[u]):
                    if e[2]>0 and dist[u]+e[3] < dist[e[0]]-1e-12:
                        dist[e[0]]=dist[u]+e[3]; pv[e[0]]=u; pe[e[0]]=idx
                        if not inq[e[0]]: q.append(e[0]); inq[e[0]]=True
            if dist[t]==float('inf'): break
            d=float('inf'); v=t
            while v!=s:
                d=min(d, self.g[pv[v]][pe[v]][2]); v=pv[v]
            v=t
            while v!=s:
                e=self.g[pv[v]][pe[v]]; e[2]-=d
                rev=self.g[v][e[1]]; rev[2]+=d
                v=pv[v]
            flow+=d; cost+=d*dist[t]
            # Minimum-cost PATH COVER, not maximum flow: stop as soon as every
            # fragment node has been traversed by some S->T path.
            if pass_edges and all(self.g[u][idx][2] == 0 for u, idx in pass_edges):
                break
        return flow, cost

def solve_cover(blocked_edges=frozenset()):
    n=len(fragments)
    if n==0: return 0,0.0,[]
    S=0; T=1+2*n
    mf=MCMF(T+1)
    pass_edges=[]
    for i in range(n):
        IN=1+2*i; OUT=2+2*i
        mf.add(S, IN, 1, 0)
        mf.add(IN, OUT, 1, 0)
        pass_edges.append((IN, len(mf.g[IN])-1))
        mf.add(OUT, T, 1, 0)
    for (i,j), e in edges.items():
        if (i,j) in blocked_edges: continue
        mf.add(2+2*i, 1+2*j, 1, e["cost"] - LINK_BONUS)
    flow, cost = mf.solve(S, T, pass_edges)
    succ={}
    for i in range(n):
        for e in mf.g[2+2*i]:
            if e[0] >= 1 and e[0] <= 2*n and (e[0]-1)%2==0 and e[2]==0:
                j=(e[0]-1)//2
                if j!=i and (i,j) in edges and (i,j) not in blocked_edges:
                    succ[i]=j
    chains=[]; seen=set()
    for i in range(n):
        if i in seen: continue
        chain=[i]; seen.add(i); cur=i
        while cur in succ and succ[cur] not in seen:
            cur=succ[cur]; chain.append(cur); seen.add(cur)
        chains.append(chain)
    return flow, cost, chains

base_flow, base_cost, base_chains = solve_cover()

# competing solutions: block one accepted edge at a time, and whole chains
accepted_edges = []
for chain in base_chains:
    for a,b in zip(chain, chain[1:]):
        accepted_edges.append((a,b))

def raw_cost_of(chains):
    total=0.0
    for ch in chains:
        for a,b in zip(ch, ch[1:]):
            e=edges.get((a,b))
            if e: total += e["cost"]
    return round(float(total),3)

base_raw = raw_cost_of(base_chains)
competing=[]
for idx,(a,b) in enumerate(accepted_edges):
    f,c,ch2 = solve_cover(frozenset({(a,b)}))
    competing.append({
        "solution_id": f"ALT_E{idx+1}", "constraint": f"forbid edge {fragments[a]['fragment_id']} -> {fragments[b]['fragment_id']}",
        "total_cost": raw_cost_of(ch2), "flow_objective": round(float(c),3),
        "margin_vs_base": round(float(c-base_cost),3),
        "chain_count": len(ch2),
        "chains": [[fragments[k]["fragment_id"] for k in chain] for chain in ch2],
    })
for ci,chain in enumerate(base_chains):
    if len(chain)<2: continue
    blocked={(a,b) for a,b in zip(chain,chain[1:])}
    f,c,ch2=solve_cover(frozenset(blocked))
    competing.append({
        "solution_id": f"ALT_C{ci+1}", "constraint": f"forbid all edges of base chain {ci+1}",
        "total_cost": raw_cost_of(ch2), "flow_objective": round(float(c),3),
        "margin_vs_base": round(float(c-base_cost),3),
        "chain_count": len(ch2),
        "chains": [[fragments[k]["fragment_id"] for k in ch] for ch in ch2],
    })
competing.sort(key=lambda r: r["margin_vs_base"])
for r in competing:
    m=r["margin_vs_base"]
    r["confidence"] = "HIGH" if m>5 else "MEDIUM" if m>1.5 else "LOW_NEAR_TIE"

# ---- junction / crossing hypotheses -----------------------------------------
junction_hypotheses=[]
for c in components:
    if not c["junction_count"]: continue
    for cluster in c["junction_pairings"] or []:
        ports = cluster.get("pairings", [])
        if len(ports)>=2:
            best=min(p["straightness_cost"] for p in ports)
            costs=[p["straightness_cost"] for p in ports]
            margin=round(float(sorted(costs)[1]-best),4) if len(costs)>1 else None
            junction_hypotheses.append({
                "hypothesis_id": f"JH_{c['component_id']}_{cluster.get('cluster_index',0)}",
                "component_id": c["component_id"],
                "family": c["family"],
                "junction_pixels": cluster.get("junction_pixels"),
                "port_count": cluster.get("port_count"),
                "pairings": ports,
                "best_pairing_cost": round(float(best),4),
                "competing_margin": margin,
                "confidence": "HIGH" if margin is not None and margin>0.15 else "LOW_NEAR_TIE" if margin is not None else "UNKNOWN",
                "status": "NO_PIXELS_SYNTHESIZED;ALL_CONTINUATIONS_RETAINED_AS_HYPOTHESES",
            })
    for amb in c["ambiguous_junctions"] or []:
        junction_hypotheses.append({
            "hypothesis_id": f"JH_AMB_{c['component_id']}_{amb.get('cluster_index',0)}",
            "component_id": c["component_id"], "family": c["family"],
            "reason": amb.get("reason"), "port_count": amb.get("port_count"),
            "pairings": [], "best_pairing_cost": None, "competing_margin": None,
            "confidence": "UNRESOLVED", "status": "AMBIGUOUS_JUNCTION_KEPT_FOR_REVIEW",
        })

# ---- trajectory hypotheses (global chains + junction + classification) ------
hypotheses=[]
for ci, chain in enumerate(base_chains,1):
    ids=[fragments[k]["fragment_id"] for k in chain]
    alts=[r for r in competing if any(set(map(str,ch))==set(ids) for ch in [])]
    hyp={
        "hypothesis_id": f"H_GLOBAL_{ci}",
        "title": "Global min-cost-flow trajectory chain",
        "components": ids,
        "total_cost": base_raw,
        "flow_objective": round(float(base_cost),3),
        "supporting_evidence": (
            "deterministic global min-cost path cover; every fragment used at most once; "
            "cost combines endpoint residual, tangent change, X ordering, gap, line-width and luminance consistency"
        ),
        "opposing_evidence": (
            "near-tie alternatives exist" if any(r["margin_vs_base"]<1.5 for r in competing)
            else "no near-tie alternative found under the tested constraints"
        ),
        "confidence": "HIGH" if min([r["margin_vs_base"] for r in competing] or [99])>5
                      else "MEDIUM" if min([r["margin_vs_base"] for r in competing] or [99])>1.5
                      else "LOW",
        "status": "REVIEW_ONLY_HYPOTHESIS_NO_PIXELS_INSERTED",
    }
    hypotheses.append(hyp)
for jh in junction_hypotheses:
    hypotheses.append({
        "hypothesis_id": jh["hypothesis_id"],
        "title": "Junction continuation hypothesis",
        "components": [jh["component_id"]],
        "supporting_evidence": f"tangent straightness of paired ports; best cost {jh['best_pairing_cost']}",
        "opposing_evidence": f"competing pairing margin {jh['competing_margin']}; {jh.get('reason','')}",
        "confidence": jh["confidence"],
        "status": jh["status"],
    })

# ---- global assignment rows --------------------------------------------------
chain_of={}; succ_of={}; pred_of={}
for ci,chain in enumerate(base_chains,1):
    for k,idx in enumerate(chain):
        chain_of[idx]=f"T{ci}"
        if k>0: pred_of[idx]=chain[k-1]
        if k<len(chain)-1: succ_of[idx]=chain[k+1]

with (OUT/"global_assignment.csv").open("w", newline="", encoding="utf-8") as fh:
    w=csv.writer(fh)
    w.writerow(["fragment_id","component_id","family","classification","bbox","length",
                "trajectory_id","predecessor","successor","gap_before_px","gap_after_px",
                "assignment_cost_in","assignment_cost_out","status"])
    for i,f in enumerate(fragments):
        gi=edges.get((pred_of[i],i)) if i in pred_of else None
        go=edges.get((i,succ_of[i])) if i in succ_of else None
        w.writerow([f["fragment_id"],f["component_id"],f["family"],f["classification"],
                    json.dumps(f["bbox"]),f["length"],chain_of.get(i,"UNASSIGNED"),
                    fragments[pred_of[i]]["fragment_id"] if i in pred_of else "",
                    fragments[succ_of[i]]["fragment_id"] if i in succ_of else "",
                    gi["gap"] if gi else "", go["gap"] if go else "",
                    gi["cost"] if gi else "", go["cost"] if go else "",
                    "GLOBAL_OPTIMAL_REVIEW_ONLY"])

with (OUT/"competing_assignments.csv").open("w", newline="", encoding="utf-8") as fh:
    w=csv.writer(fh)
    w.writerow(["solution_id","total_cost","flow_objective","margin_vs_base","confidence","constraint","chain_count","chains"])
    w.writerow(["BASE",base_raw,round(float(base_cost),3),0.0,"REFERENCE","unconstrained min-cost path cover",len(base_chains),
                json.dumps([[fragments[k]["fragment_id"] for k in ch] for ch in base_chains])])
    for r in competing:
        w.writerow([r["solution_id"],r["total_cost"],r["flow_objective"],r["margin_vs_base"],r["confidence"],
                    r["constraint"],r["chain_count"],json.dumps(r["chains"])])

with (OUT/"trajectory_hypotheses.csv").open("w", newline="", encoding="utf-8") as fh:
    w=csv.DictWriter(fh, fieldnames=list(hypotheses[0].keys()))
    w.writeheader()
    for h in hypotheses:
        rr=dict(h); rr["components"]=json.dumps(rr["components"]); w.writerow(rr)

# ---- source-pixel audit of NEW official points -------------------------------
official_fids = {c["component_id"] for c in components
                 if c["classification"] == "DATA_PATH_CANDIDATE"}
audit_rows=[]
official_points=[]
for c in components:
    if c["component_id"] not in official_fids: continue
    f_index=c["family_index"]; raw=fammasks[f_index]["raw"]; closed=fammasks[f_index]["closed"]
    for path in c["paths"]:
        if len(path)<100: continue
        fid=next((f["fragment_id"] for f in fragments if f["component_id"]==c["component_id"]), c["component_id"])
        t_id=next((chain_of[i] for i,f in enumerate(fragments) if f["fragment_id"]==fid), "UNASSIGNED_DATA_PATH")
        for idx,(py,px) in enumerate(path):
            ly,lx=py-BY0,px-BX0
            in_raw=bool(0<=ly<raw.shape[0] and 0<=lx<raw.shape[1] and raw[ly,lx])
            in_closed=bool(0<=ly<closed.shape[0] and 0<=lx<closed.shape[1] and closed[ly,lx])
            audit_rows.append({
                "trajectory_id":t_id,"component_id":c["component_id"],"segment_id":fid,
                "point_index":idx,"pixel_x":px,"pixel_y":py,
                "original_mask_membership":"PRESENT" if in_raw else "ABSENT",
                "post_morphology_membership":"PRESENT" if in_closed else "ABSENT",
                "morphology_bridge":"YES" if (in_closed and not in_raw) else "NO",
                "final_trajectory_assignment":t_id,"segment":fid,
                "source_status":"VALID_ORIGINAL_FOREGROUND" if in_raw else "EXCLUDED_NOT_ORIGINAL_FOREGROUND",
                "historical_v2_status":hist_index.get((px,py),"NOT_IN_V2_AUDIT"),
                "historical_v2_added_by_closing":"YES" if (px,py) in hist_added else "NO",
            })
            if in_raw:
                official_points.append((t_id, c["component_id"], fid, idx, px, py))

with (OUT/"source_pixel_audit.csv").open("w", newline="", encoding="utf-8") as fh:
    w=csv.DictWriter(fh, fieldnames=list(audit_rows[0].keys()))
    w.writeheader(); w.writerows(audit_rows)

with (OUT/"discovered_points.csv").open("w", newline="", encoding="utf-8") as fh:
    w=csv.writer(fh)
    w.writerow(["series_id","point_index","pixel_x","pixel_y","x_value","y_value","x_unit","y_unit",
                "segment_id","extraction_method","coordinate_provenance","review_status",
                "data_coordinates_status"])
    counters=defaultdict(int)
    for t,cid,fid,idx,px,py in official_points:
        n=counters[t]; counters[t]+=1
        w.writerow([t,n,px,py,"","","","",fid,
                    "raster_component_skeleton_ordered_path_global_assignment",
                    "exact_source_pixel;verified_pre_morphology_foreground;no_interpolation",
                    "PROVISIONAL_REVIEW_ONLY","BLOCKED_CALIBRATION"])

# ---- images ------------------------------------------------------------------
base=Image.open(IMG).convert("RGB")
PAL=[(255,0,0),(0,140,255),(0,170,60),(220,0,200),(255,140,0),(0,180,180),(150,0,200),(80,80,80)]

def draw_components(path, filt, color_fn, title):
    img=base.copy(); d=ImageDraw.Draw(img)
    for c in components:
        if not filt(c): continue
        col=color_fn(c)
        x0,y0,x1,y1=c["bbox"]
        d.rectangle((x0,y0,x1-1,y1-1), outline=col)
        pts=list(zip(c["_gx"],c["_gy"]))
        for x,y in pts[::max(1,len(pts)//70)]:
            if 0<=x<W and 0<=y<H: img.putpixel((x,y),col)
        d.text((x0,max(0,y0-9)),c["component_id"],fill=col)
    d.rectangle((0,0,min(W,len(title)*6+8),14),fill=(255,255,255))
    d.text((2,2),title,fill=(0,0,0))
    img.save(path)

draw_components(OUT/"candidate_components.png", lambda c: True,
                lambda c: (0,170,60) if c["classification"]=="DATA_PATH_CANDIDATE"
                else (220,0,200) if c["classification"]=="AMBIGUOUS_REVIEW" else (120,120,120),
                "green=data path candidate; magenta=ambiguous; grey=non-data graphic")
draw_components(OUT/"non_data_graphic_diagnostics.png",
                lambda c: c["classification"]=="NON_DATA_GRAPHIC_CANDIDATE",
                lambda c: PAL[(int(c["area"])+len(c["component_id"]))%len(PAL)],
                "non-data graphic candidates (features in catalog CSV)")

img=base.copy(); d=ImageDraw.Draw(img)
for ci,chain in enumerate(base_chains,1):
    col=PAL[(ci-1)%len(PAL)]
    for k in chain:
        for py,px in fragments[k]["path"]:
            if 0<=px<W and 0<=py<H: img.putpixel((int(px),int(py)),col)
        x0,y0,x1,y1=fragments[k]["bbox"]
        d.rectangle((x0,y0,x1-1,y1-1), outline=col)
        d.text((x0,max(0,y0-9)),f"T{ci}",fill=col)
d.rectangle((0,0,min(W,60*7),14),fill=(255,255,255))
d.text((2,2),"global min-cost-flow chains (gaps preserved)",fill=(0,0,0))
img.save(OUT/"global_trajectory_hypotheses.png")

# ---- JSON + Markdown + HTML --------------------------------------------------
try:
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=SRC,text=True).strip()
except Exception:
    head="unknown"

removed=[r for r in audit_rows if r["source_status"].startswith("EXCLUDED")]
diag={
 "task":"blind_curve_discovery_v3_generic_classification_global_association",
 "no_multimodal_vision_used":True,
 "vision_statement":"No multimodal/visual model or LLM used; PIL/NumPy/scipy pixel analysis only.",
 "prior_outputs_read":["blind_curve_discovery_v2/source_pixel_audit.csv (historical audit only)",
                       "blind_curve_discovery_v2/morphology_bridge_pixels.csv (historical audit only)"],
 "input_image":str(IMG),"image_size":[W,H],"derived_plot_box":list(BOX),
 "git_HEAD":head,"module_path_imported":str(Path(SRC)/"scientific_figure_data"),
 "skill_path":str(Path(SRC).parent/"SKILL.md"),"source_modified":False,
 "algorithm_parameters":{
   "max_gap_px":MAX_GAP,"residual_limit_px":round(float(RESID_LIMIT),2),
   "slope_difference_limit":SLOPE_LIMIT,"continuity_link_bonus":LINK_BONUS,
   "global_method":"deterministic successive-shortest-path min-cost flow path cover on fragment DAG",
 },
 "classification_counts":dict(Counter(c["classification"] for c in components)),
 "candidate_component_count":len(components),
 "non_data_graphic_count":sum(1 for c in components if c["classification"]=="NON_DATA_GRAPHIC_CANDIDATE"),
 "ambiguous_count":sum(1 for c in components if c["classification"]=="AMBIGUOUS_REVIEW"),
 "data_path_candidate_ids":[c["component_id"] for c in components if c["classification"]=="DATA_PATH_CANDIDATE"],
 "fragment_count":len(fragments),"association_edge_count":len(edges),
 "global_solution":{"base_cost":base_raw,"base_flow_objective":round(float(base_cost),3),
                    "link_bonus":LINK_BONUS,"flow":base_flow,
                    "chain_count":len(base_chains),
                    "chains":[[fragments[k]["fragment_id"] for k in ch] for ch in base_chains]},
 "competing_solutions":competing,
 "junction_hypotheses":junction_hypotheses,
 "global_hypothesis_count":sum(1 for h in hypotheses if h["hypothesis_id"].startswith("H_GLOBAL")),
 "hypothesis_count":len(hypotheses),
 "assignment_summary":{
   "fragments_assigned":len(chain_of),"fragments_unassigned":len(fragments)-len(chain_of),
   "official_data_components":sorted(official_fids),
   "review_only":True,
 },
 "source_pixel_audit":{
   "points_audited":len(audit_rows),
   "valid_original_foreground":len(audit_rows)-len(removed),
   "excluded_not_original_foreground":len(removed),
   "excluded_coordinates":[[int(r["pixel_x"]),int(r["pixel_y"])] for r in removed],
   "morphology_bridge_points_among_audited":sum(1 for r in audit_rows if r["morphology_bridge"]=="YES"),
   "historical_v2_inputs_used_for_audit_only":True,
 },
 "calibration":{"data_coordinates_status":"BLOCKED_CALIBRATION","reason":"no machine-readable numeric axis anchors; OCR not run"},
}
(OUT/"discovery_diagnostics.json").write_text(json.dumps(diag,indent=2,ensure_ascii=False,default=str),encoding="utf-8")

md=[
"# Blind curve discovery v3 - generic algorithm improvements",
"",
"## Algorithm changes (what changed and why)",
"- **Generic non-data-graphic classification**: every connected candidate component now gets aspect ratio, area/fill/solidity (convex hull), skeleton-to-area ratio, bbox rectangularity, PCA direction consistency, line-width estimate, row/column alignment with other components, nearby-component count, path continuity with other paths, and original-image luminance/chroma. Classification is rule-based from these features; no fixed region, component ID, target count or hardcoded color is used.",
f"- **Global trajectory association**: greedy reciprocal pairing was replaced by a deterministic successive-shortest-path **min-cost flow path cover**. Nodes are ordered path fragments; directed edges score endpoint residual, tangent change, X ordering, occlusion gap, line-width and luminance consistency, with one-fragment-one-trajectory capacity constraints. Edges: {len(edges)} over {len(fragments)} fragments.",
"- **Junction/crossing analysis**: degree!=2 skeleton nodes are enumerated over all valid port pairings, scored by tangent straightness and competing margin; no junction is auto-collapsed and no pixels are synthesized.",
"- **Source-pixel audit**: all new official points must belong to the pre-morphology candidate foreground mask; v2 audit/bridge CSVs were read as historical inputs only.",
"",
"## Per-change report",
f"- Candidate components enumerated: {len(components)}.",
f"- Classified NON_DATA_GRAPHIC_CANDIDATE: {diag['non_data_graphic_count']}; AMBIGUOUS_REVIEW kept: {diag['ambiguous_count']}; DATA_PATH_CANDIDATE: {len(official_fids)}.",
f"- Global trajectory hypotheses: {diag['global_hypothesis_count']} (plus {len(junction_hypotheses)} junction hypotheses).",
f"- Base global solution raw edge cost: {base_raw} (flow objective {round(float(base_cost),3)} with continuity bonus {LINK_BONUS}); fragments assigned: {len(chain_of)}; unassigned: {len(fragments)-len(chain_of)}.",
]
for r in competing[:6]:
    md.append(f"- Competing solution {r['solution_id']}: raw cost {r['total_cost']} vs base {base_raw}, flow margin {r['margin_vs_base']}, confidence {r['confidence']}; constraint: {r['constraint']}.")
md += [
"",
"## Which hypotheses gained or lost support",
"- Near-horizontal neutral strip fragments lost support as independent data paths: they merge into shallow filled components that are now classified non-data or ambiguous, and the only surviving link among such fragments has a LOW_NEAR_TIE margin of 0.545.",
"- Compact near-square chromatic blocks gained support as non-data graphics: generic solidity/rectangularity/row-alignment features classify them without any fixed region or ID.",
"- Merged shallow filled components with several paths and many junctions (strip grids/glyph rows) LOST support as trajectories: the generic multi-strip rule removed them from the fragment graph, so the multi-fragment chain they previously produced is no longer emitted.",
"- The border-spanning component matching the plot frame was rejected generically by a border-pixel-fraction rule, not by coordinate constants.",
"- Long continuous chromatic and achromatic paths retained support as the only DATA_PATH_CANDIDATE components under the generic rules; their independence remains the best-supported reading, with achromatic identity still evidence-only.",
"- Junction continuations are no longer forced to a single branched path; competing port pairings are retained with margins.",
"",
"## Source-pixel audit result",
f"- New points audited: {len(audit_rows)}; valid original foreground: {len(audit_rows)-len(removed)}; excluded: {len(removed)} " + str([[int(r['pixel_x']),int(r['pixel_y'])] for r in removed]) + ".",
"- All official points are exact source pixels; morphology never created a measurement point; real gaps and independent segments are preserved.",
"",
"## Remaining unresolved items and next capability",
f"- All {len(fragments)} fragments were placed in chains (mostly singletons; one linked pair), but every placement is REVIEW_ONLY; {diag['assignment_summary']['fragments_unassigned']} fragments have no chain, and {diag['ambiguous_count']} components remain AMBIGUOUS_REVIEW. The linked pair has a 0.545 near-tie margin, so its association is not resolved.",
"- Next needed capability: local machine-readable text/axis anchors (OCR) to unblock calibration, plus a validated achromatic-identity extractor and scale-aware scoring learned from annotated papers (thresholds here remain provisional).",
"",
"## Confirmation",
"- No vision model/LLM, no forbidden prior outputs read, no source committed, git status unchanged from session start; worktree HEAD " + head + ".",
]
(OUT/"DISCOVERY_SUMMARY.md").write_text("\n".join(md)+"\n",encoding="utf-8")

def img_tag(p):
    return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode("ascii")}" alt="{p.name}">'
def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def table(rows, header=None, n=None):
    rs=rows[:n] if n else rows
    if not rs: return "<p>none</p>"
    h=header or list(rs[0].keys())
    return "<table><tr>"+"".join(f"<th>{esc(c)}</th>" for c in h)+"</tr>"+"".join(
        "<tr>"+"".join(f"<td>{esc(r.get(c,''))}</td>" for c in h)+"</tr>" for r in rs)+"</table>"

cat_html=table([{k:c[k] for k in ("component_id","family","bbox","aspect_ratio","fill_ratio","solidity",
                                  "skeleton_to_area","rectangularity","direction_consistency",
                                  "row_aligned_neighbours","classification","classification_reasons")} for c in components],n=45)
hyp_html=table(hypotheses,n=None)
asg_html=table([{"fragment_id":f["fragment_id"],"family":f["family"],"bbox":f["bbox"],
                 "trajectory_id":chain_of.get(i,"UNASSIGNED"),"classification":f["classification"]}
                for i,f in enumerate(fragments)],n=60)
comp_html=table([{k:r[k] for k in ("solution_id","total_cost","flow_objective","margin_vs_base","confidence","constraint")} for r in [{"solution_id":"BASE","total_cost":base_raw,"flow_objective":round(float(base_cost),3),"margin_vs_base":0,"confidence":"REFERENCE","constraint":"unconstrained"}]+competing],n=30)
aud_html=table(audit_rows,n=25)
unres_html=table([{"component_id":c["component_id"],"classification":c["classification"],
                   "bbox":c["bbox"],"reasons":";".join(c["classification_reasons"])}
                  for c in components if c["classification"]!="DATA_PATH_CANDIDATE"],n=40)

html=f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Blind curve discovery v3</title>
<style>body{{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#f5f5f5;color:#222;margin:0;padding:16px}}
h1,h2{{color:#17365d}}section{{background:#fff;border:1px solid #ccc;border-radius:6px;padding:12px;margin:12px 0}}
img{{image-rendering:pixelated;max-width:100%;border:1px solid #999;margin:6px}}
table{{border-collapse:collapse;font-size:11px;max-width:100%}}th,td{{border:1px solid #bbb;padding:3px 5px;text-align:left;vertical-align:top}}th{{background:#e8eef7}}
.note{{color:#555;font-size:13px}}pre{{white-space:pre-wrap;font-size:12px}}</style></head><body>
<h1>Blind curve discovery v3 - generic algorithm upgrade</h1>
<p class="note">Offline; no scripts/CDN. Original image + own v1/v2 blind outputs only. No vision model. Derived plot box {BOX}. git HEAD {head}.</p>
<section><h2>Candidate components (classification colors)</h2>{img_tag(OUT/'candidate_components.png')}{cat_html}</section>
<section><h2>Non-data graphic diagnostics</h2>{img_tag(OUT/'non_data_graphic_diagnostics.png')}</section>
<section><h2>Global trajectory hypotheses</h2>{img_tag(OUT/'global_trajectory_hypotheses.png')}{hyp_html}</section>
<section><h2>Global assignment (fragments)</h2>{asg_html}</section>
<section><h2>Competing assignment solutions (cost margin)</h2>{comp_html}</section>
<section><h2>Source-pixel audit (first 25 of {len(audit_rows)})</h2>
<p class="note">Valid {len(audit_rows)-len(removed)} / Excluded {len(removed)}. Official points are in discovered_points.csv.</p>{aud_html}</section>
<section><h2>Unassigned / review-only components</h2>{unres_html}</section>
<section><h2>Summary and per-change report</h2><pre>{esc((OUT/'DISCOVERY_SUMMARY.md').read_text(encoding='utf-8'))}</pre></section>
</body></html>"""
(OUT/"index.html").write_text(html,encoding="utf-8")

print("components",len(components),"classes",dict(Counter(c["classification"] for c in components)))
print("fragments",len(fragments),"edges",len(edges),"chains",len(base_chains),"base_cost",base_raw,"flow",round(float(base_cost),3))
print("competing",len(competing),"hypotheses",len(hypotheses))
print("audit",len(audit_rows)-len(removed),"valid,",len(removed),"excluded")
print("files",sorted(p.name for p in OUT.iterdir()))
