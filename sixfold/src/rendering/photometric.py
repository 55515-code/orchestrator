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
    band_peak=48.0,        # luminous band peak (near horizon)
    band_half=52.0,        # gaussian sigma of the band falloff (y)
    band_gamma=1.2,        # horizontal falloff power (toward tips)
    arc_w=5,               # arc stroke width px
    arc_lum=1.0,           # arc brightness multiplier
    horizon_lum=160.0,     # horizon line peak
    atm_peak=20.0,
    atm_sigma=340.0,
    glow_stack=((3.0, 0.5), (9.0, 0.3), (22.0, 0.15), (48.0, 0.06)),
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
    the ellipse tips. Defined inside the ellipse union."""
    yy, xx = np.mgrid[0:H, 0:W]
    band = np.zeros((H, W), dtype=np.float32)
    for e in ("left_ellipse", "right_ellipse"):
        E = geo[e]
        m = ((xx - E["cx"] * S) / (E["rx"] * S)) ** 2 + \
            ((yy - E["cy"] * S) / (E["ry"] * S)) ** 2 <= 1
        # vertical falloff from horizon
        v = np.exp(-0.5 * ((yy - _HORIZON_Y * S) / (params["band_half"] * S)) ** 2)
        # horizontal falloff toward the outer tips
        if e == "left_ellipse":
            h = np.clip((xx - (E["cx"] - E["rx"]) * S) /
                        ((_LENS_X - (E["cx"] - E["rx"])) * S), 0, 1)
        else:
            h = np.clip(((E["cx"] + E["rx"]) * S - xx) /
                        (((E["cx"] + E["rx"]) - _LENS_X) * S), 0, 1)
        h = h ** params["band_gamma"]
        band[m] = np.maximum(band[m], params["band_peak"] * v[m] * h[m])
    return band


def _render_symbol(sym, scale, params):
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale
    yy, xx = np.mgrid[0:H, 0:W]
    geo = _load_geometry()

    # ---- 1. luminous band (the field)
    band = _luminous_band(W, H, params, geo, S)
    col = np.array([30, 120, 200], dtype=np.float32) / 255.0
    img = np.zeros((H, W, 3), dtype=np.float32)
    img[..., 0] = band * col[0]
    img[..., 1] = band * col[1]
    img[..., 2] = band * col[2]

    # ---- 2. atmosphere
    if params["atm_peak"] > 0:
        d = np.sqrt((xx - 725 * S) ** 2 + (yy - 541 * S) ** 2)
        v = params["atm_peak"] * np.exp(-0.5 * (d / (params["atm_sigma"] * S)) ** 2)
        img[..., 0] += v * 5 / 255.0
        img[..., 1] += v * 40 / 255.0
        img[..., 2] += v * 90 / 255.0

    # ---- 3. glow stack (softens the band into a field)
    base = np.clip(img, 0, 255)
    gl = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    for sigma, mult in params["glow_stack"]:
        b = gl.filter(ImageFilter.GaussianBlur(sigma * S))
        b_arr = np.asarray(b, dtype=np.float32) / 255.0
        base = 1 - (1 - base / 255.0) * (1 - b_arr * mult)
        base *= 255.0

    # ---- 4. horizon band (bright thin gaussian line with soft glow)
    # measured: peak ~238 lum at y=545, gaussian sigma ~14px, bright
    # across x=250..1230 with tips dimmer (~175 lum)
    hz_v = np.exp(-0.5 * ((yy - _HORIZON_Y * S) / (14 * S)) ** 2)
    hz_xmask = (xx >= 250 * S) & (xx <= 1230 * S)
    hz_h = np.clip((xx - 250 * S) / (1230 * S - 250 * S), 0, 1)
    hz_h = np.minimum(hz_h, np.clip((1230 * S - xx) / (1230 * S - 250 * S), 0, 1))
    hz_h = np.where(hz_xmask, 0.72 + 0.28 * hz_h, 0.0)
    hz = hz_v * hz_h * params["horizon_lum"]
    hz_img = Image.fromarray(np.clip(
        np.stack([hz * 0.75, hz * 0.95, hz], axis=-1), 0, 255).astype(np.uint8))
    for sigma, mult in ((3, 0.8), (9, 0.4)):
        b = hz_img.filter(ImageFilter.GaussianBlur(sigma * S))
        b_arr = np.asarray(b, dtype=np.float32) / 255.0 * mult
        base = 1 - (1 - base / 255.0) * (1 - b_arr)
        base *= 255.0
    base = np.clip(base, 0, 255)

    # ---- 5. arc strokes + marks (core layer)
    core_img = Image.new("RGB", (W, H), (0, 0, 0))
    cd = ImageDraw.Draw(core_img)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        cd.line(pts, fill=(215, 255, 255),
                width=max(1, int(params["arc_w"] * S)), joint="curve")
    # arc glow: blur the core strokes and screen them in softly
    arc_glow = core_img.filter(ImageFilter.GaussianBlur(max(1.0, 4 * S)))
    ag_arr = np.asarray(arc_glow, dtype=np.float32) / 255.0 * \
        params.get("arc_glow", 0.55)
    base = 1 - (1 - base / 255.0) * (1 - ag_arr)
    base *= 255.0
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer:
            # marks are mid-tone glyphs, not hot cores: dim to ~70% so they
            # read as living interruptions, not white-hot elements.
            # bubbles/ripples keep full strength (reference bubbles are
            # bright rings); fish at 80% (reference fish are bright strokes)
            if m.kind in ("bubble", "ripple"):
                mc = m.color
            elif m.kind == "fish":
                mc = tuple(int(c * 1.0) for c in m.color)
            else:
                mc = tuple(int(c * 0.65) for c in m.color)
            drawer(cd, m.cx * S, m.cy * S, m.scale * S, mc, m.rot)
    core_arr = np.asarray(core_img, dtype=np.float32)
    base = 1 - (1 - base / 255.0) * (1 - core_arr / 255.0)
    base *= 255.0

    # ---- 6. tone
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
