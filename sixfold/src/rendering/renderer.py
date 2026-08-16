#!/usr/bin/env python3
"""SIXFOLD raster renderer v2 — dark-field master, transparent variant, SVG export.

Rendering recipe (derived from photometric autopsy of the WATER reference,
design/photometry.json):

  1. pure-black field
  2. radial atmosphere field: gaussian falloff centered on the figure
     (ref: peak ~70 lum at center, sigma ~0.34*rmax, deep saturated color,
     corners ~0)
  3. glow stack: N gaussian passes over the figure layer, each drawn as a
     wide stroke of the deep glow color, blurred to (sigma, lum_peak),
     screen-blended (ref: sigma ~5/15/35 px at ~100/40/25 lum)
  4. sharp core layer: near-white boosted path colors + marks at their own
     (dimmer) colors (ref: lobes near-white 215,255,255; fish mid-cyan;
     bubbles deep-cyan)
  5. soft tone roll-off capping luminance at ~250 (ref max = 250.1)
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import Path, Mark, Symbol, lerp
from .marks import MARK_DRAWERS

WHITE = (255, 255, 255)


def _lerp_c(c, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c, WHITE))


def _atmosphere_layer(W, H, color, center, peak_lum, sigma):
    """Radial gaussian atmosphere field. Returns RGB image."""
    cx, cy = center
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    v = peak_lum * np.exp(-0.5 * (d / sigma) ** 2)
    v = np.clip(v, 0, 255).astype(np.float32)
    r = v * (color[0] / 255.0)
    g = v * (color[1] / 255.0)
    b = v * (color[2] / 255.0)
    out = np.stack([r, g, b], axis=-1)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _draw_figure_layer(draw, sym, S, color_fn, width_fn=None):
    """Draw all paths+marks onto a draw surface using a color/width function."""
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        col = color_fn(p)
        w = max(1, int((width_fn(p) if width_fn else p.width) * S))
        if p.loop:
            draw.line(pts + [pts[0]], fill=col, width=w, joint="curve")
        else:
            draw.line(pts, fill=col, width=w, joint="curve")
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer is None:
            continue
        drawer(draw, m.cx * S, m.cy * S, m.scale * S, color_fn(m, mark=True),
               m.rot)


def _draw_fills(draw, sym, S, color_fn):
    """Draw luminous translucent regions (the reference's filled lobes)."""
    for pts, color, alpha in sym.fills:
        poly = [(x * S, y * S) for x, y in pts]
        col = color_fn(color) if callable(color_fn) else color
        if len(poly) >= 3:
            draw.polygon(poly, fill=col + (int(255 * alpha),))


def _glow_source(sym, S, scale_w=4.0):
    """Deep-color figure layer (fills + thick strokes) used as blur input."""
    W, H = int(sym.width * S), int(sym.height * S)
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    # fills first (luminous regions)
    for pts, color, alpha in getattr(sym, "fills", []) or []:
        poly = [(x * S, y * S) for x, y in pts]
        if len(poly) >= 3:
            d.polygon(poly, fill=tuple(int(c * alpha) for c in color))
    for p in sym.paths:
        gcol = p.glow_color or p.color
        pts = [(x * S, y * S) for x, y in p.points]
        w = max(2, int(p.glow * scale_w * S * 0.5))
        if p.loop:
            d.line(pts + [pts[0]], fill=gcol, width=w, joint="curve")
        else:
            d.line(pts, fill=gcol, width=w, joint="curve")
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer is None:
            continue
        drawer(d, m.cx * S, m.cy * S, m.scale * S * 2.0,
               tuple(int(c * 0.7) for c in m.color), m.rot)
    return layer


def _screen(a, b):
    return 1 - (1 - a) * (1 - b)


def render_symbol(sym: Symbol, scale: float = 1.0) -> Image.Image:
    """Render a Symbol to a dark-field raster at sym.width*scale."""
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale

    # ---------------- 1. background + atmosphere field
    img = Image.new("RGB", (W, H), sym.background)
    if sym.atmosphere is not None:
        cx, cy = sym.canvas_center()
        at = _atmosphere_layer(W, H, sym.atmosphere, (cx, cy),
                               sym.atmosphere_peak, sym.atmosphere_sigma * S)
        arr = 1 - (1 - np.asarray(at, dtype=np.float32) / 255.0) * \
            (1 - np.asarray(img, dtype=np.float32) / 255.0)
        img = Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8))

    # ---------------- 2. glow stack (screen-blended gaussian passes)
    source = _glow_source(sym, S)
    base_arr = np.asarray(img, dtype=np.float32) / 255.0
    for sigma_px, lum_peak in sym.glow_stack:
        if lum_peak <= 0:
            continue
        blur = source.filter(ImageFilter.GaussianBlur(max(0.5, sigma_px * S)))
        b_arr = np.asarray(blur, dtype=np.float32) / 255.0
        # normalize the blurred deep color to the pass peak luminance
        lum = (0.2126 * b_arr[..., 0] + 0.7152 * b_arr[..., 1] +
               0.0722 * b_arr[..., 2])
        scale_f = (lum_peak / 255.0) / (lum.max() + 1e-6)
        b_arr = np.clip(b_arr * scale_f, 0, 1)
        base_arr = _screen(base_arr, b_arr)
    img = Image.fromarray(np.clip(base_arr * 255, 0, 255).astype(np.uint8))

    # ---------------- 2b. bright lens cross (horizon band + vertical strip)
    if getattr(sym, "lens_band", None) is not None or getattr(sym, "lens_strip", None) is not None:
        cross = Image.new("RGB", (W, H), (0, 0, 0))
        xd = ImageDraw.Draw(cross)
        if sym.lens_band is not None:
            x0, x1, y, h, lum = sym.lens_band
            xd.rectangle([x0 * S, (y - h / 2) * S, x1 * S, (y + h / 2) * S],
                         fill=(int(lum * 0.75), int(lum * 0.95), int(lum)))
        if sym.lens_strip is not None:
            x, y0, y1, w, lum = sym.lens_strip
            xd.rectangle([(x - w / 2) * S, y0 * S, (x + w / 2) * S, y1 * S],
                         fill=(int(lum * 0.75), int(lum * 0.95), int(lum)))
        c1 = cross.filter(ImageFilter.GaussianBlur(max(0.5, 5 * S)))
        c2 = cross.filter(ImageFilter.GaussianBlur(max(1.0, 14 * S)))
        for bl in (c1, c2):
            b_arr = np.asarray(bl, dtype=np.float32) / 255.0
            base_arr = _screen(base_arr, b_arr)
        # sharp core of the cross
        c_arr = np.asarray(cross, dtype=np.float32) / 255.0 * 0.9
        base_arr = _screen(base_arr, c_arr)
        img = Image.fromarray(np.clip(base_arr * 255, 0, 255).astype(np.uint8))
        base_arr = np.asarray(img, dtype=np.float32) / 255.0

    # ---------------- 3. sharp core layer
    core_layer = Image.new("RGB", (W, H), (0, 0, 0))
    cd = ImageDraw.Draw(core_layer)

    def core_color(p, mark=False):
        if mark:
            return p.color
        return _lerp_c(p.color, sym.core_boost)

    # fills also get a soft luminous presence in the core layer (the fill
    # luminance mostly comes from the glow stack; here we add a subtle layer)
    for pts, color, alpha in getattr(sym, "fills", []) or []:
        poly = [(x * S, y * S) for x, y in pts]
        if len(poly) >= 3:
            cd.polygon(poly, fill=tuple(int(c * min(1.0, alpha * 1.8))
                                        for c in color))
    _draw_figure_layer(cd, sym, S, core_color)
    core_arr = np.asarray(core_layer, dtype=np.float32) / 255.0
    base_arr = np.asarray(img, dtype=np.float32) / 255.0
    base_arr = _screen(base_arr, core_arr)

    # ---------------- 4. tone roll-off (soft cap ~250, slight mid lift)
    x = np.clip(base_arr * 255.0, 0, 255)
    y = 255.0 * (x / 255.0) ** sym.tone_gamma
    y = np.minimum(y, sym.tone_cap)
    final = Image.fromarray(np.clip(y, 0, 255).astype(np.uint8))
    return final


def render_transparent(sym: Symbol, scale: float = 1.0) -> Image.Image:
    """Transparent-background variant: symbol on alpha, no dark field."""
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale

    line_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line_layer)

    def core_color(p, mark=False):
        if mark:
            return p.color
        return _lerp_c(p.color, sym.core_boost)

    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        col = core_color(p) + (255,)
        w = max(1, int(p.width * S))
        if p.loop:
            ld.line(pts + [pts[0]], fill=col, width=w, joint="curve")
        else:
            ld.line(pts, fill=col, width=w, joint="curve")

    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for p in sym.paths:
        gcol = (p.glow_color or p.color) + (140,)
        pts = [(x * S, y * S) for x, y in p.points]
        w = max(2, int(p.glow * 2.2 * S))
        if p.loop:
            gd.line(pts + [pts[0]], fill=gcol, width=w, joint="curve")
        else:
            gd.line(pts, fill=gcol, width=w, joint="curve")

    mark_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    md = ImageDraw.Draw(mark_layer)
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer:
            drawer(md, m.cx * S, m.cy * S, m.scale * S, m.color + (255,), m.rot)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img = Image.alpha_composite(img, glow_layer.filter(
        ImageFilter.GaussianBlur(max(1.0, 1.2 * S))))
    img = Image.alpha_composite(img, line_layer)
    img = Image.alpha_composite(img, mark_layer)
    return img


# ---------------------------------------------------------------- SVG export

def svg_export(sym: Symbol, path: Path):
    """Editable vector master export (lines + marks as paths)."""
    W, H = sym.width, sym.height

    def esc(v):
        return "%.1f" % v

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">',
        f'  <rect width="{W}" height="{H}" fill="black"/>',
        f'  <defs>',
        f'    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">',
        f'      <feGaussianBlur stdDeviation="4" result="b"/>',
        f'      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>',
        f'    </filter>',
        f'  </defs>',
    ]
    for p in sym.paths:
        data = "M " + " L ".join(f"{esc(x)},{esc(y)}" for x, y in p.points)
        if p.loop:
            data += " Z"
        col = "#%02x%02x%02x" % tuple(int(v) for v in p.color)
        parts.append(
            f'  <path d="{data}" fill="none" stroke="{col}" '
            f'stroke-width="{esc(p.width)}" stroke-linejoin="round" '
            f'stroke-linecap="round" filter="url(#glow)"/>')
    for m in sym.marks:
        col = "#%02x%02x%02x" % tuple(int(v) for v in m.color)
        r = esc(2.2 * m.scale)
        parts.append(
            f'  <circle cx="{esc(m.cx)}" cy="{esc(m.cy)}" r="{r}" fill="{col}"/>')
    parts.append("</svg>")
    path.write_text("\n".join(parts))
