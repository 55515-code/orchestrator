#!/usr/bin/env python3
"""Photometric renderer — builds the WATER look from measured light fields.

The reference (design/photometry.json, design/lobe-geometry.json) is:
  - two filled ellipses (vesica piscis) with a *gradient fill*: bright near
    the lens (inner edge), dim at the outer edges
  - a bright lens where the ellipses overlap
  - inset bright outline strokes (~200+ lum, near-white cyan)
  - horizon dashes + fish + bubbles
  - a faint radial atmosphere that dies by ~0.6 rmax
  - tone capped at ~250, sharp cores ~2-3px

This module renders that model directly with numpy so each layer is
tunable and measurable.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import Symbol
from .marks import MARK_DRAWERS


def _poly_mask(poly, W, H):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.polygon([(p[0], p[1]) for p in poly], fill=255)
    return np.asarray(m) > 0


def _dist_to_edge(mask, W, H):
    """Approx signed distance field: 0 inside near edge, grows outward.
    Uses iterative erosion. Returns float array (0..1 normalized by max)."""
    m = mask.copy()
    dist = np.zeros((H, W), dtype=np.float32)
    from numpy import zeros_like
    for k in range(1, 60):
        er = m.copy()
        er[1:, :] &= m[:-1, :]
        er[:-1, :] &= m[1:, :]
        er[:, 1:] &= m[:, :-1]
        er[:, :-1] &= m[:, 1:]
        changed = m & ~er
        dist[changed] = k
        m = er
        if not m.any():
            break
    # normalize by max so 0..1 (1 = deepest inside)
    mx = dist.max()
    if mx > 0:
        dist = dist / mx
    return dist


def render_photometric(sym: Symbol, scale: float = 1.0,
                       fill_peak: float = 95.0,
                       fill_gamma: float = 1.5,
                       lens_boost: float = 40.0,
                       glow_stack=((6.0, 0.45), (16.0, 0.22), (34.0, 0.10)),
                       atm_peak: float = 22.0,
                       atm_sigma: float = 330.0,
                       atm_color=(5, 40, 90),
                       core_width: float = 3.0,
                       core_color=(215, 255, 255),
                       tone_cap: float = 250.0,
                       tone_gamma: float = 0.92):
    """Render the vesica-piscis light model to a dark-field master."""
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale
    yy, xx = np.mgrid[0:H, 0:W]

    # ---- 1. gradient fill (luminous platform) ----
    fill = np.zeros((H, W), dtype=np.float32)
    overlap = np.zeros((H, W), dtype=np.float32)
    fills = getattr(sym, "fills", []) or []
    for pts, color, alpha in fills:
        poly = [(x * S, y * S) for x, y in pts]
        mask = _poly_mask(poly, W, H)
        # distance to lens (inner edge at x=720): bright near lens
        dx = np.abs(xx - 720.0 * S) / (520.0 * S)
        grad = np.clip(1 - dx, 0, 1) ** fill_gamma
        # also vertical falloff toward top/bottom edges
        # (approximate with ellipse distance via mask erosion)
        fill[mask] += (fill_peak * grad[mask] / max(1, len(fills)))
        overlap += mask.astype(np.float32)
    lens = overlap > 1.0
    fill[lens] += lens_boost
    # normalize fill to peak
    if fill.max() > 0:
        fill = fill / (fill.max() / (fill_peak + lens_boost))

    # ---- 2. atmosphere ----
    atm = np.zeros((H, W), dtype=np.float32)
    if atm_peak > 0:
        cx, cy = sym.canvas_center()
        d = np.sqrt((xx - cx * S) ** 2 + (yy - cy * S) ** 2)
        rmax = np.sqrt((W / 2) ** 2 + (H / 2) ** 2)
        # gaussian that dies by ~0.6 rmax
        atm = atm_peak * np.exp(-0.5 * (d / (atm_sigma * S)) ** 2)

    # ---- 3. combine color fields ----
    # fill provides luminance (fill_peak at lens, ~0 at edges); the color is
    # the deep cyan of the reference glow. Atmosphere adds its own wash.
    img = np.zeros((H, W, 3), dtype=np.float32)
    col = np.array(atm_color, dtype=np.float32) / 255.0
    img[..., 0] = fill * col[0]
    img[..., 1] = fill * col[1]
    img[..., 2] = fill * col[2]
    img += atm[..., None] * np.array(atm_color, dtype=np.float32)[None, None, :] / 255.0

    # ---- 4. glow stack (screen blend of blurred fill) ----
    base = np.clip(img, 0, 255)
    gl = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    for sigma, mult in glow_stack:
        b = gl.filter(ImageFilter.GaussianBlur(sigma * S))
        b_arr = np.asarray(b, dtype=np.float32) / 255.0
        base = 1 - (1 - base / 255.0) * (1 - b_arr * mult)
        base *= 255.0
    base = np.clip(base, 0, 255)

    # ---- 5. core strokes ----
    core_img = Image.new("RGB", (W, H), (0, 0, 0))
    cd = ImageDraw.Draw(core_img)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        w = max(1, int(p.width * S))
        if p.loop:
            cd.line(pts + [pts[0]], fill=core_color, width=w, joint="curve")
        else:
            cd.line(pts, fill=core_color, width=w, joint="curve")
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer:
            drawer(cd, m.cx * S, m.cy * S, m.scale * S, m.color, m.rot)
    core_arr = np.asarray(core_img, dtype=np.float32)
    base = 1 - (1 - base / 255.0) * (1 - core_arr / 255.0)
    base *= 255.0

    # ---- 6. tone curve ----
    x = np.clip(base, 0, 255)
    y = 255.0 * (x / 255.0) ** tone_gamma
    y = np.minimum(y, tone_cap)
    return Image.fromarray(np.clip(y, 0, 255).astype(np.uint8))
