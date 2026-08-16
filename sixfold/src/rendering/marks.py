#!/usr/bin/env python3
"""Micro-mark drawing functions for SIXFOLD.

Each mark is a tiny glyph-scale object that lives ON a symbol's trajectory.
All marks are intentionally minimal — they should read as glyphs, not illustrations.
"""
import math
import numpy as np
from PIL import ImageDraw


def _rotate(pts, center, ang):
    c, s = math.cos(ang), math.sin(ang)
    cx, cy = center
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
            for x, y in pts]


# ---------------------------------------------------------------- individual marks

def _fish(draw, cx, cy, scale, color, rot):
    """Tiny fish glyph: body + tail fin + eye. ~8-9× line width long."""
    L = 9.0 * scale
    half = L / 2
    body_h = L * 0.32
    # body polygon
    top = [(cx + half * 0.75, cy - body_h * 0.9),
           (cx - half * 0.55, cy - body_h * 0.55),
           (cx - half, cy - body_h * 0.15),
           (cx - half, cy + body_h * 0.15),
           (cx - half * 0.55, cy + body_h * 0.55),
           (cx + half * 0.75, cy + body_h * 0.9)]
    draw.polygon(_rotate(top, (cx, cy), rot), fill=color)
    # tail fin
    fin = [(cx - half * 0.9, cy - body_h * 0.1),
           (cx - half * 1.35, cy - body_h * 0.55),
           (cx - half * 1.3, cy + body_h * 0.55),
           (cx - half * 0.9, cy + body_h * 0.1)]
    draw.polygon(_rotate(fin, (cx, cy), rot), fill=color)
    # eye
    eye = _rotate([(cx + half * 0.25, cy)], (cx, cy), rot)[0]
    r = 0.7 * scale
    draw.ellipse([eye[0] - r, eye[1] - r, eye[0] + r, eye[1] + r], fill=(0, 0, 0))


def _spark(draw, cx, cy, scale, color, rot):
    """4-point star spark."""
    r = 3.0 * scale
    pts = []
    for i in range(8):
        ang = rot + i * math.pi / 4
        rad = r if i % 2 == 0 else r * 0.35
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    draw.polygon(pts, fill=color)


def _ember(draw, cx, cy, scale, color, rot):
    """Small teardrop ember with hot core."""
    r = 2.2 * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    rc = r * 0.35
    draw.ellipse([cx - rc, cy - rc, cx + rc, cy + rc], fill=(255, 245, 230))


def _seed(draw, cx, cy, scale, color, rot):
    """Seed: small ellipse with a radicle line."""
    r = 3.0 * scale
    pts = []
    for i in range(24):
        ang = rot + i * math.tau / 24
        pts.append((cx + math.cos(ang) * r * 1.5, cy + math.sin(ang) * r * 0.8))
    draw.polygon(pts, fill=color)
    # radicle
    x0 = cx - math.cos(rot) * r * 1.4
    y0 = cy - math.sin(rot) * r * 0.7
    x1 = cx - math.cos(rot) * r * 2.6
    y1 = cy - math.sin(rot) * r * 1.3
    draw.line([x0, y0, x1, y1], fill=(0, 0, 0), width=max(1, int(scale)))


def _leaf(draw, cx, cy, scale, color, rot):
    """Two small leaves from a point (sprout)."""
    L = 7.0 * scale
    for side in (-1, 1):
        ang = rot + side * 0.55
        tip = (cx + math.cos(ang) * L, cy + math.sin(ang) * L)
        perp = (math.cos(ang + math.pi / 2) * L * 0.3,
                math.sin(ang + math.pi / 2) * L * 0.3)
        mid = ((cx + tip[0]) / 2, (cy + tip[1]) / 2)
        pts = [(cx, cy), (mid[0] + perp[0], mid[1] + perp[1]), tip]
        draw.polygon(pts, fill=color)


def _root(draw, cx, cy, scale, color, rot):
    """Root bifurcation: stem splitting in two."""
    L = 7.0 * scale
    x0 = cx - math.cos(rot) * L * 0.4
    y0 = cy - math.sin(rot) * L * 0.4
    x1 = cx + math.cos(rot) * L * 0.7
    y1 = cy + math.sin(rot) * L * 0.7
    draw.line([x0, y0, x1, y1], fill=color, width=max(1, int(1.4 * scale)))
    for side in (-1, 1):
        ang = rot + side * 0.7
        tx = x1 + math.cos(ang) * L * 0.7
        ty = y1 + math.sin(ang) * L * 0.7
        draw.line([x1, y1, tx, ty], fill=color, width=max(1, int(scale)))


def _beetle(draw, cx, cy, scale, color, rot):
    """Tiny glyph beetle: oval body + head + 3 legs each side."""
    r = 3.2 * scale
    pts = []
    for i in range(20):
        ang = rot + i * math.tau / 20
        pts.append((cx + math.cos(ang) * r * 1.15, cy + math.sin(ang) * r * 0.75))
    draw.polygon(pts, fill=color)
    # head
    hx = cx + math.cos(rot) * r * 1.35
    hy = cy + math.sin(rot) * r * 0.6
    hr = r * 0.45
    draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=color)
    # legs
    for side in (-1, 1):
        for f in (0.25, 0.55, 0.85):
            px = cx + (f - 0.5) * 2 * r * 0.9
            py = cy + side * r * 1.1
            draw.line([px, cy + side * r * 0.5, px, py], fill=color,
                      width=max(1, int(scale)))


def _bird(draw, cx, cy, scale, color, rot):
    """Tiny bird: two-arc wing glyph (seagull mark)."""
    L = 8.0 * scale
    for side, up in ((-1, -1), (1, 1)):
        x0 = cx + side * L * 0.5
        y0 = cy
        x1 = cx + side * L * 0.05
        y1 = cy + up * L * 0.42
        pts = [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) for t in np.linspace(0, 1, 12)]
        draw.line(pts, fill=color, width=max(1, int(1.2 * scale)))
    r = 0.8 * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def _feather(draw, cx, cy, scale, color, rot):
    """Feather: shaft + barbs."""
    L = 8.0 * scale
    x0 = cx - math.cos(rot) * L / 2
    y0 = cy - math.sin(rot) * L / 2
    x1 = cx + math.cos(rot) * L / 2
    y1 = cy + math.sin(rot) * L / 2
    draw.line([x0, y0, x1, y1], fill=color, width=max(1, int(scale)))
    perp = (math.cos(rot + math.pi / 2), math.sin(rot + math.pi / 2))
    for f in (0.2, 0.45, 0.7):
        bx = x0 + (x1 - x0) * f
        by = y0 + (y1 - y0) * f
        wdt = L * 0.4 * (1 - abs(f - 0.5) * 1.2)
        draw.line([bx - perp[0] * wdt, by - perp[1] * wdt,
                   bx + perp[0] * wdt, by + perp[1] * wdt],
                  fill=color, width=max(1, int(0.6 * scale)))


def _prism(draw, cx, cy, scale, color, rot):
    """Tiny prism triangle with a ray line through it."""
    r = 3.5 * scale
    pts = [(cx + math.cos(rot) * r * 1.2, cy + math.sin(rot) * r * 1.2),
           (cx + math.cos(rot + 2.4) * r, cy + math.sin(rot + 2.4) * r),
           (cx + math.cos(rot + 4.2) * r, cy + math.sin(rot + 4.2) * r)]
    draw.polygon(pts, fill=color)
    draw.line([cx - math.cos(rot) * r * 2.2, cy - math.sin(rot) * r * 2.2,
               cx + math.cos(rot) * r * 2.2, cy + math.sin(rot) * r * 2.2],
              fill=color, width=max(1, int(scale)))


def _aperture(draw, cx, cy, scale, color, rot):
    """Aperture: small ring with iris blades."""
    r = 3.5 * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(1, int(scale)))
    rc = r * 0.4
    draw.ellipse([cx - rc, cy - rc, cx + rc, cy + rc], fill=color)
    for i in range(6):
        ang = rot + i * math.tau / 6
        draw.line([cx + math.cos(ang) * r * 0.5, cy + math.sin(ang) * r * 0.5,
                   cx + math.cos(ang) * r, cy + math.sin(ang) * r],
                  fill=color, width=max(1, int(0.5 * scale)))


def _point(draw, cx, cy, scale, color, rot):
    """Photon-like point: dot with tiny cross flare."""
    r = 1.8 * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    f = r * 3
    draw.line([cx - f, cy, cx + f, cy], fill=color, width=max(1, int(0.4 * scale)))
    draw.line([cx, cy - f, cx, cy + f], fill=color, width=max(1, int(0.4 * scale)))


def _ambiguity(draw, cx, cy, scale, color, rot):
    """Chaos mark: reads as eye/insect/seed/fish/star simultaneously.
    Almond outline + radial burst + central dot. Deliberately unresolved.
    """
    r = 3.5 * scale
    pts = []
    for t in np.linspace(0, math.tau, 30):
        x = math.cos(t) * r * 1.6
        y = math.sin(t) * r * 0.85
        if x < 0:
            y *= (1 + x / (r * 1.6)) * 0.55
        px = cx + math.cos(rot) * x - math.sin(rot) * y
        py = cy + math.sin(rot) * x + math.cos(rot) * y
        pts.append((px, py))
    draw.polygon(pts, fill=color)
    # central pupil/seed
    rc = r * 0.4
    draw.ellipse([cx - rc, cy - rc, cx + rc, cy + rc], fill=(0, 0, 0))
    # radial filaments
    for i in range(5):
        ang = rot + i * math.tau / 5 + 0.3
        draw.line([cx + math.cos(ang) * r * 0.8, cy + math.sin(ang) * r * 0.8,
                   cx + math.cos(ang) * r * 1.9, cy + math.sin(ang) * r * 1.9],
                  fill=color, width=max(1, int(0.5 * scale)))


def _ripple(draw, cx, cy, scale, color, rot):
    """Short horizontal ripple stroke."""
    L = 14.0 * scale
    draw.line([cx - L, cy, cx + L, cy], fill=color, width=max(1, int(0.8 * scale)))


def _bubble(draw, cx, cy, scale, color, rot):
    """Tiny bubble ring."""
    r = 1.2 * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=1)


# ---------------------------------------------------------------- registry

MARK_DRAWERS = {
    "fish": _fish, "spark": _spark, "ember": _ember, "seed": _seed,
    "leaf": _leaf, "root": _root, "beetle": _beetle, "bird": _bird,
    "feather": _feather, "prism": _prism, "aperture": _aperture,
    "point": _point, "ambiguity": _ambiguity, "ripple": _ripple,
    "bubble": _bubble,
}
