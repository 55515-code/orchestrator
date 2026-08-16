#!/usr/bin/env python3
"""Extract the true lobe geometry from the WATER reference.

The reference is a vesica piscis: two filled almond/teardrop lobes with
bright outlines + faint luminous fill, overlapping in a central lens.
This script thresholds the figure mask, finds connected components, and
traces the outline of each lobe as a polygon, saved to design/lobe-geometry.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "reference" / "water-master.png"
OUT = ROOT / "design" / "lobe-geometry.json"


def luminance(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def trace_outline(mask):
    """Trace the outer boundary of a binary mask using a Moore-neighbor walk.

    Returns list of (x, y) boundary pixels in raster order (y,x).
    """
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return []
    # start at topmost, then leftmost point
    start = (int(xs[np.argmin(ys)]), int(ys[np.argmin(ys)]))
    # Moore neighbor tracing
    dirs = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    contour = []
    # We'll use a simple approach: find boundary pixels (mask pixel with a
    # non-mask 4-neighbor), then order them by angle around the centroid.
    by = np.zeros_like(mask)
    by[1:-1, 1:-1] = (mask[1:-1, 1:-1] & ~(
        mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]))
    by = by & mask
    bys, bxs = np.where(by)
    if len(bxs) == 0:
        return []
    cx, cy = bxs.mean(), bys.mean()
    ang = np.arctan2(bys - cy, bxs - cx)
    order = np.argsort(ang)
    return [(float(bxs[i]), float(bys[i])) for i in order]


def main():
    img = np.asarray(Image.open(REF).convert("RGB"), dtype=np.float32)
    L = luminance(img)
    H, W = L.shape

    # Figure mask: moderately bright material (fills + outlines + lens)
    # Use lum > 14 to capture fill, then clean with a small blur+threshold
    mask = (L > 14).astype(np.uint8)
    # Remove specks: keep only the largest components via BFS flood fill
    lab = np.zeros_like(mask, dtype=np.int32)
    n = 0
    for y in range(H):
        for x in range(W):
            if mask[y, x] and lab[y, x] == 0:
                n += 1
                stack = [(x, y)]
                lab[y, x] = n
                while stack:
                    cx0, cy0 = stack.pop()
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx0 + dx, cy0 + dy
                        if 0 <= nx < W and 0 <= ny < H and mask[ny, nx] and lab[ny, nx] == 0:
                            lab[ny, nx] = n
                            stack.append((nx, ny))
    sizes = [(lab == i).sum() for i in range(1, n + 1)]
    big = [i for i, s in enumerate(sizes, 1) if s > 500]
    keep = np.isin(lab, big)
    mask = keep.astype(np.uint8)
    sizes = [(lab == i).sum() for i in range(1, n + 1)]
    big = [i for i, s in enumerate(sizes, 1) if s > 500]
    keep = np.isin(lab, big)
    mask = keep.astype(np.uint8)

    # Boundary polygon
    poly = trace_outline(mask > 0)
    print(f"mask pixels: {mask.sum()}, components >500px: {len(big)}")
    print(f"outline points: {len(poly)}")

    # Split into left/right lobe by the lens at x=720: actually the figure is
    # one connected vesica — the two lobes share the lens. We trace the outer
    # boundary once; the renderer will use the SAME polygon filled + outlined.

    # Also extract the bright outline mask (lum > 80) for the stroke layer
    outline_mask = (L > 80).astype(np.uint8)
    outline_poly = trace_outline(outline_mask > 0)
    print(f"outline mask pixels: {outline_mask.sum()}, poly points: {len(outline_poly)}")

    # The bright lens band (lum > 150) — where fills overlap
    lens_mask = L > 150
    lens_frac = lens_mask.mean() * 100
    print(f"lens (lum>150) fraction: {lens_frac:.2f}%")

    data = {
        "width": W, "height": H,
        "figure_threshold": 14.0,
        "figure_polygon": poly,
        "outline_threshold": 80.0,
        "outline_polygon": outline_poly,
        "figure_bbox": [int(mask.sum(0).argmax()) if mask.any() else 0],
    }
    # bbox of mask
    ys, xs = np.where(mask)
    data["figure_bbox"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    OUT.write_text(json.dumps(data, indent=1))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
