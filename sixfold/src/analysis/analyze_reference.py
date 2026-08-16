#!/usr/bin/env python3
"""Stage A — Reference analysis for SIXFOLD.

Computes structural measurements of the WATER master:
- canvas proportions, symbol bbox, center, line weight
- dominant color, luminance distribution, negative space %
- glow radius, horizon position, micro-symbol scale, symmetry

Outputs sixfold/design/measurements.json
"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[3]
REF = ROOT / "sixfold/reference/water-master.png"
OUT = ROOT / "sixfold/design/measurements.json"


def luminance(arr):
    r, g, b = arr[..., 0].astype(np.float32), arr[..., 1].astype(np.float32), arr[..., 2].astype(np.float32)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def main():
    im = Image.open(REF).convert("RGB")
    w, h = im.size
    arr = np.asarray(im).astype(np.float32)
    lum = luminance(arr)

    # --- brightness thresholds (relative to global max) ---
    global_max = lum.max()
    if global_max < 1:
        global_max = 1

    # Line core: > 60% of max luminance
    core = lum > 0.6 * global_max
    # Symbol (with glow): > 12% of max
    glow = lum > 0.12 * global_max
    # Faint atmosphere: > 3% of max
    atmos = lum > 0.03 * global_max

    def bbox(mask):
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return None
        return {
            "x0": int(xs.min()), "y0": int(ys.min()),
            "x1": int(xs.max()), "y1": int(ys.max()),
            "w": int(xs.max() - xs.min() + 1),
            "h": int(ys.max() - ys.min() + 1),
            "cx": float((xs.min() + xs.max()) / 2),
            "cy": float((ys.min() + ys.max()) / 2),
        }

    core_bb, glow_bb, atmos_bb = bbox(core), bbox(glow), bbox(atmos)

    # --- negative space: fraction of pixels below faint atmosphere ---
    neg_space = 1.0 - atmos.mean()

    # --- line weight: mean thickness of core mask via distance transform ---
    from scipy import ndimage  # optional; fallback to erosion estimate
    try:
        dist = ndimage.distance_transform_edt(core)
        line_weight = float(2 * dist[core].mean())
        line_weight_median = float(2 * np.median(dist[core]))
    except ImportError:
        line_weight = line_weight_median = None

    # --- dominant color: mean color of core pixels ---
    core_colors = arr[core]
    core_mean = core_colors.mean(axis=0) if len(core_colors) else np.zeros(3)
    glow_colors = arr[glow]
    glow_mean = glow_colors.mean(axis=0) if len(glow_colors) else np.zeros(3)

    # --- background color (darkest mode) ---
    dark = lum < np.percentile(lum, 5)
    bg_mean = arr[dark].mean(axis=0) if dark.sum() else np.zeros(3)

    # --- horizon detection: row with strong horizontal line signature ---
    # A horizon = long horizontal run of elevated luminance within the symbol band.
    row_scores = np.zeros(h)
    glow_rows = glow.sum(axis=1)
    for y in range(h):
        row = lum[y]
        runs = 0
        in_run = False
        for x in range(w):
            if row[x] > 0.25 * global_max:
                if not in_run:
                    runs += 1
                in_run = True
            else:
                in_run = False
        row_scores[y] = runs
    # horizon = row with fewest runs but substantial glow, inside symbol bbox
    if glow_bb:
        y0, y1 = glow_bb["y0"], glow_bb["y1"]
        band = range(y0, y1)
        candidates = [y for y in band if glow_rows[y] > 0.02 * w]
        if candidates:
            horizon_y = min(candidates, key=lambda y: (row_scores[y], -glow_rows[y]))
        else:
            horizon_y = None
    else:
        horizon_y = None

    # --- symmetry: flip core mask horizontally about its center, measure IoU ---
    sym_iou = None
    if core_bb:
        sub = core[core_bb["y0"]:core_bb["y1"] + 1, core_bb["x0"]:core_bb["x1"] + 1]
        flipped = sub[:, ::-1]
        inter = np.logical_and(sub, flipped).sum()
        union = np.logical_or(sub, flipped).sum()
        sym_iou = float(inter / max(1, union))

    # --- micro-symbol scale: connected components of core that are small ---
    # (fish are thin, small components vs the main loop)
    try:
        lbl, n = ndimage.label(core)
        sizes = ndimage.sum(core, lbl, range(1, n + 1))
        comps = sorted(sizes, reverse=True)
        main_comp = comps[0] if comps else 0
        small_comps = [c for c in comps if c > 0 and c < main_comp * 0.15]
        micro_count = len(small_comps)
        micro_frac = float(sum(small_comps) / max(1, main_comp))
    except Exception:
        micro_count, micro_frac = None, None

    # --- glow radius: mean distance from core to glow boundary ---
    glow_radius = None
    if glow_bb and line_weight:
        try:
            d_core = ndimage.distance_transform_edt(~core)
            edge = glow & ~core
            if edge.sum():
                glow_radius = float(d_core[edge].mean())
        except Exception:
            pass

    # --- quantiles of luminance (for atmosphere characterization) ---
    lum_flat = lum.flatten()
    q = {f"q{int(p*100)}": float(np.percentile(lum_flat, p * 100)) for p in (0.01, 0.05, 0.5, 0.9, 0.99)}

    result = {
        "canvas": {"width": w, "height": h, "aspect": round(w / h, 4)},
        "line_core_threshold": 0.6,
        "glow_threshold": 0.12,
        "atmos_threshold": 0.03,
        "symbol_bbox_core": core_bb,
        "symbol_bbox_glow": glow_bb,
        "symbol_bbox_atmos": atmos_bb,
        "negative_space_pct": round(neg_space * 100, 2),
        "line_weight_px": round(line_weight, 2) if line_weight else None,
        "line_weight_median_px": round(line_weight_median, 2) if line_weight_median else None,
        "dominant_core_color": [round(float(x), 1) for x in core_mean],
        "dominant_glow_color": [round(float(x), 1) for x in glow_mean],
        "background_color": [round(float(x), 1) for x in bg_mean],
        "global_max_luminance": float(global_max),
        "horizon_y": horizon_y,
        "horizon_relative": round(horizon_y / h, 4) if horizon_y else None,
        "center": {"cx": core_bb["cx"] / w if core_bb else None,
                   "cy": core_bb["cy"] / h if core_bb else None},
        "symmetry_iou": round(sym_iou, 4) if sym_iou else None,
        "micro_component_count": micro_count,
        "micro_mass_fraction": round(micro_frac, 5) if micro_frac else None,
        "glow_radius_px": round(glow_radius, 2) if glow_radius else None,
        "luminance_quantiles": q,
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
