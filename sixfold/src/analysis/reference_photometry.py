#!/usr/bin/env python3
"""Deep photometric autopsy of the WATER master reference.

Goal: derive an exact rendering recipe (glow sigma/strength stack,
atmosphere profile, core color, tone curve) so the pipeline can reproduce
the reference's *light behavior*, not just its geometry.

Outputs a JSON with measured parameters consumed by the renderer.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "reference" / "water-master.png"
OUT = ROOT / "design" / "photometry.json"


def luminance(a: np.ndarray) -> np.ndarray:
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def main() -> int:
    img = Image.open(REF).convert("RGB")
    a = np.asarray(img, dtype=np.float32)
    H, W = a.shape[:2]
    lum = luminance(a)
    res: dict = {"width": W, "height": H}

    # ---- 1. global histogram shape (log-spaced)
    hist, edges = np.histogram(lum, bins=64, range=(0, 256))
    res["histogram"] = [int(v) for v in hist]
    res["hist_edges"] = [float(e) for e in edges]

    # ---- 2. percentile ladder
    pcts = [50, 90, 95, 99, 99.5, 99.9, 100]
    res["percentiles"] = {f"p{p}": float(np.percentile(lum, p)) for p in pcts}

    # ---- 3. bright-pixel population vs threshold
    res["bright_frac"] = {}
    for t in [8, 12, 16, 20, 30, 40, 60, 90, 120]:
        res["bright_frac"][str(t)] = float((lum > t).mean() * 100)

    # ---- 4. atmosphere floor: luminance at the frame corners and edges
    margin = 40
    corners = np.concatenate([
        lum[:margin, :margin].ravel(), lum[:margin, -margin:].ravel(),
        lum[-margin:, :margin].ravel(), lum[-margin:, -margin:].ravel(),
    ])
    res["corner_lum"] = {
        "mean": float(corners.mean()), "p50": float(np.percentile(corners, 50)),
        "p95": float(np.percentile(corners, 95)),
    }

    # ---- 5. radial falloff from figure centroid (bright-weighted)
    w = lum - lum.min()
    if w.max() > 0:
        cy = float((np.arange(H)[:, None] * w).sum() / w.sum())
        cx = float((np.arange(W)[None, :] * w).sum() / w.sum())
    else:
        cx, cy = W / 2, H / 2
    res["lum_centroid"] = {"x": cx, "y": cy}

    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    # sample luminance in radial annuli (normalized radius)
    rmax = dist.max()
    rings = {}
    for rn in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        mask = (dist / rmax <= rn) & (dist / rmax > rn - 0.1)
        if mask.sum() > 100:
            rings[str(rn)] = float(lum[mask].mean())
    res["radial_rings"] = rings
    res["radial_rmax"] = float(rmax)

    # ---- 6. brightest core color (near-white region)
    core_mask = lum > np.percentile(lum, 99.9)
    if core_mask.sum() > 0:
        res["core_color"] = [float(a[core_mask][:, 0].mean()),
                             float(a[core_mask][:, 1].mean()),
                             float(a[core_mask][:, 2].mean())]
        res["core_color_p95"] = [
            float(np.percentile(a[core_mask][:, i], 95)) for i in range(3)]

    # ---- 7. glow color at mid levels (30-90 lum)
    glow_mask = (lum > 30) & (lum < 90)
    if glow_mask.sum() > 0:
        res["glow_color"] = [float(a[glow_mask][:, 0].mean()),
                             float(a[glow_mask][:, 1].mean()),
                             float(a[glow_mask][:, 2].mean())]

    # ---- 8. atmosphere color at low levels (8-30)
    atm_mask = (lum >= 8) & (lum < 30)
    if atm_mask.sum() > 0:
        res["atmosphere_color"] = [float(a[atm_mask][:, 0].mean()),
                                   float(a[atm_mask][:, 1].mean()),
                                   float(a[atm_mask][:, 2].mean())]

    # ---- 9. line profile: perpendicular cut across the left lobe arm
    # find a long bright run at y≈540 (lobe region), measure intensity profile
    row = lum[540]
    runs = []
    in_run = False
    for i, v in enumerate(row):
        if v > 20 and not in_run:
            start = i; in_run = True
        elif v <= 20 and in_run:
            runs.append((start, i - start)); in_run = False
    if in_run:
        runs.append((start, len(row) - start))
    runs.sort(key=lambda r: -r[1])
    res["runs_y540"] = [(int(s), int(l)) for s, l in runs[:6]]

    # full-width at half max on the widest bright run
    if runs:
        s0, l0 = runs[0]
        prof = lum[540, s0:s0 + l0]
        pk = prof.max()
        half = pk / 2
        above = np.where(prof >= half)[0]
        if len(above) >= 2:
            fwhm = above[-1] - above[0]
            res["fwhm_widest_run"] = int(fwhm)
            # gaussian sigma estimate from FWHM
            res["fwhm_sigma_est"] = float(fwhm / 2.3548)

    # ---- 10. estimate glow stack: fit gaussian to a clean isolated line
    # use a horizontal profile across the *fish* mark region (isolated)
    # fish at (487,364) area — scan rows around y=364 for bright runs
    for probe_y in [364, 368, 372]:
        row = lum[probe_y]
        runs2 = []
        in_run = False
        for i, v in enumerate(row):
            if v > 15 and not in_run:
                start = i; in_run = True
            elif v <= 15 and in_run:
                runs2.append((start, i - start)); in_run = False
        if in_run:
            runs2.append((start, len(row) - start))
        runs2.sort(key=lambda r: -r[1])
        if runs2 and runs2[0][1] > 3 and runs2[0][1] < 60:
            s0, l0 = runs2[0]
            prof = lum[probe_y, s0:s0 + l0]
            pk = prof.max()
            half = pk / 2
            above = np.where(prof >= half)[0]
            if len(above) >= 2:
                fwhm = above[-1] - above[0]
                res[f"isolated_line_y{probe_y}"] = {
                    "run": [int(s0), int(l0)], "peak": float(pk),
                    "fwhm": int(fwhm),
                    "sigma_est": float(fwhm / 2.3548),
                    "profile": [float(v) for v in prof[:: max(1, l0 // 24)]],
                }

    # ---- 11. falloff exponent: log-log slope of radial rings
    radii = np.array([float(r) for r in res["radial_rings"].keys()])
    vals = np.array(list(res["radial_rings"].values()))
    valid = (vals > 1) & (radii > 0.1)
    if valid.sum() >= 3:
        logr = np.log(radii[valid])
        logv = np.log(vals[valid] - vals[valid].min() + 1e-6)
        slope = np.polyfit(logr, logv, 1)[0]
        res["falloff_exponent"] = float(slope)

    OUT.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
