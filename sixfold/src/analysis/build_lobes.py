#!/usr/bin/env python3
"""Fit canonical lobe geometry as ellipses (measured from reference).

Measured anatomy of WATER reference:
  - figure = union of two filled ellipses (vesica piscis), inner edges
    meeting at x≈720 (the lens)
  - left  ellipse: center ≈ (497, 525.5), rx ≈ 223, ry ≈ 199.5
  - right ellipse: center ≈ (951, 525.5), rx ≈ 231, ry ≈ 199.5
  - bright inset outline strokes along each ellipse (~15-30px inside edge)
  - bright lens where ellipses overlap (y≈530-570)
  - horizon dashes + fish + bubbles on top

Output: design/lobe-geometry.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "reference" / "water-master.png"
OUT = ROOT / "design" / "lobe-geometry.json"


def luminance(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def ellipse_pts(cx, cy, rx, ry, n=96):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return [[float(cx + rx * np.cos(a)), float(cy + ry * np.sin(a))]
            for a in t]


def main():
    img = np.asarray(Image.open(REF).convert("RGB"), dtype=np.float32)
    L = luminance(img)
    H, W = L.shape

    # Fit ellipses: search a small parameter grid to maximize IoU vs lum>14
    best = None
    best_iou = -1
    grid = []
    for cx in range(480, 515, 5):
        for rx in range(205, 245, 5):
            for ry in range(180, 215, 5):
                grid.append((cx, rx, ry))
    ref_mask = L > 14
    import itertools
    for cx_l, rx_l, ry_l in grid:
        # right ellipse mirrors: cx_r = 2*720 - cx_l ... actually inner edges
        # meet at 720, so cx_r = 2*720 - cx_l? No: inner edge = cx+rx = 720
        # for the left, and cx-rx = 720 for the right → cx_r = 720 + rx_l.
        cx_r = 720 + rx_l
        m = np.zeros((H, W), dtype=bool)
        yy, xx = np.mgrid[0:H, 0:W]
        d_l = ((xx - cx_l) / rx_l) ** 2 + ((yy - 525.5) / ry_l) ** 2
        d_r = ((xx - cx_r) / rx_l) ** 2 + ((yy - 525.5) / ry_l) ** 2
        m |= (d_l <= 1) | (d_r <= 1)
        inter = (m & ref_mask).sum()
        union = (m | ref_mask).sum()
        iou = inter / union
        if iou > best_iou:
            best_iou = iou
            best = (cx_l, 720 + rx_l, rx_l, ry_l)
    print(f"best IoU: {best_iou:.3f}  left_cx={best[0]} right_cx={best[1]} rx={best[2]} ry={best[3]}")

    cx_l, cx_r, rx, ry = best
    data = {
        "width": W, "height": H,
        "tip_y": 525.5,
        "left_ellipse": {"cx": cx_l, "cy": 525.5, "rx": rx, "ry": ry},
        "right_ellipse": {"cx": cx_r, "cy": 525.5, "rx": rx, "ry": ry},
        "lens_x": 720.0,
        "left_lobe": ellipse_pts(cx_l, 525.5, rx, ry),
        "right_lobe": ellipse_pts(cx_r, 525.5, rx, ry),
    }
    OUT.write_text(json.dumps(data, indent=1))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
