#!/usr/bin/env python3
"""QA harness — compare a rendered symbol against the WATER reference.

Metrics (all defined in design/photometry.json):
  - radial annuli luminance profile (0.1..1.0 r)
  - bright fraction (>20 lum), hot fraction (>150 lum), max luminance
  - core color (near-white)
  - luminance centroid

Output: a score (lower = closer to reference) + per-metric deltas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from geometry.elements import ELEMENTS  # noqa: E402
from rendering.photometric import render_symbol  # noqa: E402

REF_PHOTO = ROOT / "design" / "photometry.json"


def luminance(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def annuli(L):
    H, W = L.shape
    ys, xs = np.mgrid[0:H, 0:W]
    tot = L.sum()
    cx = (xs * L).sum() / tot
    cy = (ys * L).sum() / tot
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    rmax = d.max()
    out = {}
    for rn in np.arange(0.1, 1.01, 0.1):
        rn = round(float(rn), 1)
        m = (d / rmax <= rn) & (d / rmax > rn - 0.1)
        out[str(rn)] = float(L[m].mean()) if m.sum() > 100 else 0.0
    return out, (float(cx), float(cy))


def compare(path_or_sym, ref_path=REF_PHOTO, label=""):
    ref = json.loads(ref_path.read_text())
    if isinstance(path_or_sym, str):
        img = Image.open(path_or_sym).convert("RGB")
    else:
        img = render_symbol(path_or_sym)
    L = luminance(np.asarray(img, dtype=np.float32))
    a, cent = annuli(L)

    ref_rings = ref["radial_rings"]
    score = sum(abs(a[k] - ref_rings[k]) / max(ref_rings[k], 1.0)
                for k in ref_rings)
    bright = float((L > 20).mean() * 100)
    hot = float((L > 150).mean() * 100)
    mx = float(L.max())
    ref_bright = ref["bright_frac"]["20"]
    ref_hot = ref["bright_frac"]["90"]
    ref_max = ref["percentiles"]["p100"]

    print(f"== {label or path_or_sym} ==")
    print(f"  score: {score:.3f}")
    print(f"  annuli:  " + "  ".join(f"{k}:{v:5.1f}" for k, v in a.items()))
    print(f"  ref:     " + "  ".join(f"{k}:{ref_rings[k]:5.1f}" for k in ref_rings))
    print(f"  bright>20: {bright:.2f}% (ref {ref_bright:.2f}%)  "
          f">150: {hot:.3f}% (ref {ref_hot:.2f}%)  max: {mx:.1f} (ref {ref_max:.1f})")
    print(f"  centroid: ({cent[0]:.0f},{cent[1]:.0f}) ref "
          f"({ref['lum_centroid']['x']:.0f},{ref['lum_centroid']['y']:.0f})")
    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("element", nargs="?", default="water")
    ap.add_argument("--image", help="compare an existing image instead")
    args = ap.parse_args()
    if args.image:
        compare(args.image, label=args.image)
    else:
        sym = ELEMENTS[args.element]()
        compare(sym, label=f"render:{args.element}")


if __name__ == "__main__":
    main()
