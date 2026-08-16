#!/usr/bin/env python3
"""SIXFOLD photometric WATER model — rebuilt from precise reference anatomy.

Measured structure (design/photometry.json, design/lobe-geometry.json):
  - two overlapping ellipses (vesica piscis), inner edges at x≈720
  - BRIGHT ARC STROKES along the ellipse edges (top arc y≈340 at 223 lum,
    bottom arc y≈660-710 at ~180-200 lum) — drawn with the ellipse geometry
    but inset ~20-30px from the fill edge
  - BRIGHT HORIZON LINE at y≈545 (219-235 lum), spanning x≈250-1230
  - LUMINOUS BAND between the arcs: brightest near the horizon (y 500-580),
    fading to ~8-15 lum at y=350/700 — this is the "field"
  - fish (horizontal ribbon glyphs at (487,364) and (996,704))
  - bubbles (bright rings at (445,334), (454,341), (1052,689), (1069,700))
  - faint radial atmosphere, tone capped at ~250
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import Symbol
from .marks import MARK_DRAWERS

DEFAULTS = dict(
    band_peak=54.0,        # luminous band peak (near horizon)
    band_half=95.0,        # gaussian sigma of the band falloff (y)
    band_gamma=1.2,        # horizontal falloff power (toward tips)
    arc_w=3,               # arc stroke width px
    arc_lum=1.0,           # arc brightness multiplier
    arc_glow=0.3,          # arc halo screen blend strength
    horizon_lum=185.0,     # horizon line peak
    hz_sigma=1.8,          # horizon vertical gaussian sigma
    atm_peak=16.0,
    atm_sigma=360.0,
    glow_stack=((3.0, 0.5), (9.0, 0.3), (22.0, 0.15), (48.0, 0.06)),
    lens_spot=55.0,
    lens_sigma=60.0,
    tip_spot=14.0,
    tip_sigma=34.0,
    hz_glow=((3.0, 0.8), (9.0, 0.1)),
    tone_gamma=0.94,
    tone_cap=250.0,
)

_LENS_X = 720.0
_HORIZON_Y = 545.0


def _load_geometry():
    p = Path(__file__).resolve().parents[2] / "design" / "lobe-geometry.json"
    return json.loads(p.read_text())


def _luminous_band(W, H, params, geo, S=1.0):
    """Luminous band: bright near the horizon, fading up/down and toward
    the tips. Defined inside the vesica (union of the two circle lobes)."""
    yy, xx = np.mgrid[0:H, 0:W]
    band = np.zeros((H, W), dtype=np.float32)
    # vesica lobes: use the spline arcs to define the interior. Simplest
    # robust interior: the union of two circles centered near the splines.
    # From the measurements: left lobe ≈ circle C(457,540) R≈200;
    # right lobe ≈ circle C(1013,541) R≈190.
    circles = [
        (457.0, 540.0, 200.0),
        (1013.0, 541.0, 190.0),
    ]
    for cx, cy, R in circles:
        m = ((xx - cx * S) ** 2 + (yy - cy * S) ** 2) <= (R * S) ** 2
        # vertical falloff from horizon
        v = np.exp(-0.5 * ((yy - _HORIZON_Y * S) / (params["band_half"] * S)) ** 2)
        # horizontal falloff toward the outer tips
        if cx < 700:
            h = np.clip((xx - (cx - R) * S) /
                        ((_LENS_X - (cx - R)) * S), 0, 1)
        else:
            h = np.clip(((cx + R) * S - xx) /
                        (((cx + R) - _LENS_X) * S), 0, 1)
        h = h ** params["band_gamma"]
        band[m] = np.maximum(band[m], params["band_peak"] * v[m] * h[m])
    return band


def _render_symbol(sym, scale, params):
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale
    yy, xx = np.mgrid[0:H, 0:W]
    geo = _load_geometry()

    # ---- 1. luminous band (the vesica fill, DIM — measured ~10-25 lum)
    band = _luminous_band(W, H, params, geo, S)
    col = np.array([30, 120, 200], dtype=np.float32) / 255.0
    img = np.zeros((H, W, 3), dtype=np.float32)
    img[..., 0] = band * col[0]
    img[..., 1] = band * col[1]
    img[..., 2] = band * col[2]

    # ---- 2. atmosphere (broad faint field, 0-20 lum)
    if params["atm_peak"] > 0:
        d = np.sqrt(((xx - 725 * S) / 360) ** 2 + ((yy - 541 * S) / 240) ** 2)
        v = params["atm_peak"] * np.exp(-0.5 * d ** 2)
        img[..., 0] += v * 5 / 255.0
        img[..., 1] += v * 40 / 255.0
        img[..., 2] += v * 90 / 255.0

    # ---- 3. band glow: blur ONLY the band (broad soft field)
    base = np.clip(img, 0, 255)
    gl = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    for sigma, mult in params["glow_stack"]:
        b = gl.filter(ImageFilter.GaussianBlur(sigma * S))
        b_arr = np.asarray(b, dtype=np.float32) / 255.0
        base = 1 - (1 - base / 255.0) * (1 - b_arr * mult)
        base *= 255.0

    # ---- 4. lens spot + tip glows
    if params.get("lens_spot", 0) > 0:
        dl = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        lv = params["lens_spot"] * np.exp(-0.5 * (dl / (params.get("lens_sigma", 60) * S)) ** 2)
        ls = np.stack([lv * 0.8, lv * 0.95, lv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - ls / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    if params.get("lens_glow", 0) > 0:
        dg = np.sqrt((xx - 740 * S) ** 2 + (yy - 545 * S) ** 2)
        gv = params["lens_glow"] * np.exp(-0.5 * (dg / (params.get("lens_glow_sigma", 100) * S)) ** 2)
        gs = np.stack([gv * 0.8, gv * 0.95, gv], axis=-1)
        base = 1 - (1 - base / 255.0) * (1 - gs / 255.0)
        base *= 255.0
    # tip glows: bright convergence points at the vesica tips (measured:
    # the tips are bright ~200 lum points where arcs + horizon meet)
    if params.get("tip_spot", 0) > 0:
        for tx, ty in ((272.0, 545.0), (1150.0, 545.0)):
            dt = np.sqrt((xx - tx * S) ** 2 + (yy - ty * S) ** 2)
            tv = params["tip_spot"] * np.exp(-0.5 * (dt / (params.get("tip_sigma", 28) * S)) ** 2)
            ts = np.stack([tv * 0.8, tv * 0.95, tv], axis=-1)
            base = 1 - (1 - base / 255.0) * (1 - ts / 255.0)
            base *= 255.0

    # ---- 5. horizon band (bright thin gaussian line with soft glow)
    # measured: peak ~238 lum at y=545, gaussian sigma ~4px, bright
    # across x=250..1230 with tips dimmer (~55 lum at x=300)
    hz_v = np.exp(-0.5 * ((yy - _HORIZON_Y * S) / (params["hz_sigma"] * S)) ** 2)
    hz_xmask = (xx >= 143 * S) & (xx <= 1311 * S)
    hz_h = np.clip((xx - 143 * S) / (1311 * S - 143 * S), 0, 1)
    hz_h = np.minimum(hz_h, np.clip((1311 * S - xx) / (1311 * S - 143 * S), 0, 1))
    # horizontal profile: bright center (lens), slightly dimmer tails
    # measured: center (x=720) ~204 mean, tails (x=300/1100) ~93-99,
    # far tips (x=200/1250) ~83-87 — a gentle dome peaking at the lens
    hz_h = 0.70 + 0.30 * np.clip(1 - np.abs(xx - 740 * S) / (600 * S), 0, 1) ** 1.2
    hz_h = np.where(hz_xmask, hz_h, 0.0)
    hz = hz_v * hz_h * params["horizon_lum"]
    hz_img = Image.fromarray(np.clip(
        np.stack([hz * 0.9, hz * 1.0, hz * 1.0], axis=-1), 0, 255).astype(np.uint8))
    # sharp horizon first (bright thin line), then soft glow
    hz_arr = np.asarray(hz_img, dtype=np.float32)
    base = 1 - (1 - base / 255.0) * (1 - hz_arr / 255.0)
    base *= 255.0
    hz_glow = params.get("hz_glow", ((3.0, 0.8), (9.0, 0.4)))
    for sigma, mult in hz_glow:
        b = hz_img.filter(ImageFilter.GaussianBlur(sigma * S))
        b_arr = np.asarray(b, dtype=np.float32) / 255.0 * mult
        base = 1 - (1 - base / 255.0) * (1 - b_arr)
        base *= 255.0
    base = np.clip(base, 0, 255)
    import os
    if os.environ.get("SIXFOLD_DEBUG"):
        print(f"after hz stage center lum: "
              f"{0.2126*base[545,740,0]+0.7152*base[545,740,1]+0.0722*base[545,740,2]:.0f}")

    # ---- 6. arc strokes + marks (core layer, bright & sharp)
    core_img = Image.new("RGB", (W, H), (0, 0, 0))
    cd = ImageDraw.Draw(core_img)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        al = params.get("arc_lum", 1.0)
        cd.line(pts, fill=(int(215 * min(al, 1.2)), 255, 255),
                width=max(1, int(params["arc_w"] * S)), joint="curve")
    # arc glow: tight (the reference arcs have ~2-4px halos)
    arc_glow = core_img.filter(ImageFilter.GaussianBlur(
        max(1.0, params.get("ag_sigma", 2.0) * S)))
    ag_arr = np.asarray(arc_glow, dtype=np.float32) / 255.0 * \
        params.get("arc_glow", 0.3)
    base = 1 - (1 - base / 255.0) * (1 - ag_arr)
    base *= 255.0
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer:
            if m.kind in ("ripple",):
                mc = m.color
            elif m.kind == "bubble":
                mc = tuple(int(c * 1.0) for c in m.color)
            elif m.kind == "fish":
                mc = tuple(int(c * 1.25) for c in m.color)
            else:
                mc = tuple(int(c * 0.65) for c in m.color)
            drawer(cd, m.cx * S, m.cy * S, m.scale * S, mc, m.rot)
    core_arr = np.asarray(core_img, dtype=np.float32)
    base = 1 - (1 - base / 255.0) * (1 - core_arr / 255.0)
    base *= 255.0

    # ---- 7. tone
    x = np.clip(base, 0, 255)
    y = 255.0 * (x / 255.0) ** params["tone_gamma"]
    y = np.minimum(y, params["tone_cap"])
    return Image.fromarray(np.clip(y, 0, 255).astype(np.uint8))


def render_symbol(sym: Symbol, scale: float = 1.0) -> Image.Image:
    return _render_symbol(sym, scale, DEFAULTS)


def render_transparent(sym: Symbol, scale: float = 1.0) -> Image.Image:
    """Transparent-background variant: core + soft glow on alpha."""
    from .marks import MARK_DRAWERS
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale

    line_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line_layer)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        ld.line(pts, fill=(215, 255, 255, 255),
                width=max(1, int(DEFAULTS["arc_w"] * S)), joint="curve")
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer:
            mc = m.color if m.kind in ("bubble", "ripple") else \
                tuple(int(c * 0.65) for c in m.color)
            drawer(ld, m.cx * S, m.cy * S, m.scale * S, mc + (255,), m.rot)

    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        gd.line(pts, fill=(40, 140, 220, 160), width=int(10 * S), joint="curve")

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img = Image.alpha_composite(img, glow_layer.filter(
        ImageFilter.GaussianBlur(max(1.0, 6 * S))))
    img = Image.alpha_composite(img, line_layer)
    return img
