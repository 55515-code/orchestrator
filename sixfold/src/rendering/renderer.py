#!/usr/bin/env python3
"""SIXFOLD raster renderer — dark-field master, transparent variant, SVG export.

Rendering recipe (shared by all six symbols):
  1. near-black field + faint atmosphere wash
  2. multi-pass soft glow layer (radial falloff)
  3. hairline core layer (screen-blended, sharp)
  4. horizon/reflections + micro-marks composited additively
  5. subtle core bloom — glow supports, never is, the drawing
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import Path, Mark, Symbol
from .marks import MARK_DRAWERS


def render_symbol(sym: Symbol, scale: float = 1.0) -> Image.Image:
    """Render a Symbol to a dark-field raster at sym.width*scale."""
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale

    img = Image.new("RGB", (W, H), sym.background)
    # faint atmosphere wash (radial vignette toward black)
    if sym.atmosphere and sym.atmosphere != sym.background:
        at = Image.new("RGB", (W, H), sym.atmosphere)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        for i in range(60, 0, -4):
            a = int(255 * (i / 60) ** 2.2 * 0.5)
            md.ellipse([-W * 0.25 - i * 4, -H * 0.25 - i * 4,
                        W * 1.25 + i * 4, H * 1.25 + i * 4], outline=a)
        img = Image.composite(img, at, mask)

    # ---------------- glow layer
    glow_layer = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for p in sym.paths:
        if p.glow <= 0 or p.glow_strength <= 0:
            continue
        pts = [(x * S, y * S) for x, y in p.points]
        col = tuple(int(c * p.glow_strength) for c in p.color)
        passes = [(p.glow * 3.0, 14), (p.glow * 1.6, 26), (p.glow * 0.8, 40)]
        for radius, alpha in passes:
            if p.loop:
                gd.line(pts + [pts[0]], fill=col, width=max(1, int(radius * S)),
                        joint="curve")
            else:
                gd.line(pts, fill=col, width=max(1, int(radius * S)), joint="curve")

    # ---------------- core line layer
    core_layer = Image.new("RGB", (W, H), (0, 0, 0))
    cd = ImageDraw.Draw(core_layer)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        w = max(1, int(p.width * S))
        if p.fade_ends:
            for k in range(len(pts) - 1):
                t = k / max(1, len(pts) - 2)
                fade = math.sin(min(max(t, 0.0), 1.0) * math.pi) ** 1.2
                if fade < 0.05:
                    continue
                col = tuple(int(c * fade) for c in p.color)
                cd.line([pts[k], pts[k + 1]], fill=col, width=w)
        else:
            if p.loop:
                cd.line(pts + [pts[0]], fill=p.color, width=w, joint="curve")
            else:
                cd.line(pts, fill=p.color, width=w, joint="curve")

    # ---------------- horizon + reflections layer
    horizon_layer = Image.new("RGB", (W, H), (0, 0, 0))
    hd = ImageDraw.Draw(horizon_layer)
    if sym.horizon is not None:
        y = sym.horizon * S
        hd.line([0, y, W, y], fill=sym.horizon_color, width=max(1, int(1.2 * S)))
        hd.line([0, y, W, y],
                fill=tuple(int(c * 0.5) for c in sym.horizon_color),
                width=max(1, int(sym.horizon_glow * S)))
    for (ry, rlen, alpha) in sym.reflections:
        y = ry * S
        L = rlen * S
        cx = W / 2
        col = tuple(int(c * alpha) for c in sym.horizon_color)
        hd.line([cx - L / 2, y, cx + L / 2, y], fill=col, width=max(1, int(1.0 * S)))

    # ---------------- micro marks layer
    mark_layer = Image.new("RGB", (W, H), (0, 0, 0))
    md = ImageDraw.Draw(mark_layer)
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer is None:
            continue
        drawer(md, m.cx * S, m.cy * S, m.scale * S, m.color, m.rot)

    # ---------------- composite
    base = Image.new("RGB", (W, H), sym.background)
    base = Image.composite(horizon_layer, base,
                           Image.eval(horizon_layer.convert("L"), lambda v: v))
    base = Image.composite(mark_layer, base,
                           Image.eval(mark_layer.convert("L"), lambda v: v))

    # additive glow (screen blend)
    glow_blur = glow_layer.filter(ImageFilter.GaussianBlur(max(1.0, 1.2 * S)))
    arr_g = np.asarray(glow_blur, dtype=np.float32) / 255.0
    arr_b = np.asarray(base, dtype=np.float32) / 255.0
    arr = 1 - (1 - arr_g) * (1 - arr_b)
    base = Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8))

    # sharp core on top
    core_on = Image.composite(core_layer, base,
                              Image.eval(core_layer.convert("L"), lambda v: v))
    # small bloom on core only
    core_bloom = core_layer.filter(ImageFilter.GaussianBlur(max(0.6, 0.7 * S)))
    arr_cb = np.asarray(core_bloom, dtype=np.float32) / 255.0 * 0.35
    arr_b2 = np.asarray(core_on, dtype=np.float32) / 255.0
    arr2 = 1 - (1 - arr_cb) * (1 - arr_b2)
    final = Image.fromarray(np.clip(arr2 * 255, 0, 255).astype(np.uint8))
    return final


def render_transparent(sym: Symbol, scale: float = 1.0) -> Image.Image:
    """Transparent-background variant: symbol on alpha, no dark field."""
    W = int(sym.width * scale)
    H = int(sym.height * scale)
    S = scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    line_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line_layer)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        col = p.color + (255,)
        w = max(1, int(p.width * S))
        if p.loop:
            ld.line(pts + [pts[0]], fill=col, width=w, joint="curve")
        else:
            ld.line(pts, fill=col, width=w, joint="curve")

    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for p in sym.paths:
        pts = [(x * S, y * S) for x, y in p.points]
        col = p.color + (120,)
        if p.loop:
            gd.line(pts + [pts[0]], fill=col,
                    width=max(1, int(p.glow * 2.2 * S)), joint="curve")
        else:
            gd.line(pts, fill=col, width=max(1, int(p.glow * 2.2 * S)), joint="curve")

    mark_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    md = ImageDraw.Draw(mark_layer)
    for m in sym.marks:
        drawer = MARK_DRAWERS.get(m.kind)
        if drawer:
            drawer(md, m.cx * S, m.cy * S, m.scale * S, m.color + (255,), m.rot)

    glow_blur = glow_layer.filter(ImageFilter.GaussianBlur(max(1.0, 1.2 * S)))
    img = Image.alpha_composite(img, glow_blur)
    img = Image.alpha_composite(img, line_layer)
    img = Image.alpha_composite(img, mark_layer)
    return img


# ---------------------------------------------------------------- SVG export

def svg_export(sym: Symbol, path: Path):
    """Editable vector master export (lines + marks as paths)."""
    W, H = sym.width, sym.height

    def esc(v):
        return "%.1f" % v

    def pts_str(pts, loop=False):
        body = " ".join(f"{esc(x)},{esc(y)}" for x, y in pts)
        if loop and pts:
            body += f" {esc(pts[0][0])},{esc(pts[0][1])}"
        return body

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
        d = f'M {"L ".join(pts_str(p.points).split(" "))}' if False else None
        # build path data manually: M x,y L x,y ...
        data = "M " + " L ".join(f"{esc(x)},{esc(y)}" for x, y in p.points)
        if p.loop:
            data += " Z"
        col = "#%02x%02x%02x" % tuple(int(v) for v in p.color)
        parts.append(
            f'  <path d="{data}" fill="none" stroke="{col}" '
            f'stroke-width="{esc(p.width)}" stroke-linejoin="round" '
            f'stroke-linecap="round" filter="url(#glow)"/>')
    # marks: simplified as small circles/lines per kind via generic glyph
    for m in sym.marks:
        col = "#%02x%02x%02x" % tuple(int(v) for v in m.color)
        r = esc(2.2 * m.scale)
        parts.append(
            f'  <circle cx="{esc(m.cx)}" cy="{esc(m.cy)}" r="{r}" fill="{col}"/>')
    parts.append("</svg>")
    path.write_text("\n".join(parts))
