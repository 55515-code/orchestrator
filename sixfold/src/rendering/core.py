#!/usr/bin/env python3
"""SIXFOLD rendering core — primitives, colors, sampling helpers.

Reusable engine implementing the WATER visual grammar:
hairline geometry + narrow luminous core + extremely soft atmospheric spill.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------- colors

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def color_ramp(stops, t):
    """stops: list of (position, rgb). Linear interpolation."""
    if t <= stops[0][0]:
        return stops[0][1]
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if t <= p1:
            return lerp(c0, c1, (t - p0) / (p1 - p0) if p1 > p0 else 0)
    return stops[-1][1]


# ---------------------------------------------------------------- primitives

@dataclass
class Path:
    points: list  # list of (x, y) in canvas coords
    width: float = 2.0
    color: tuple = (130, 221, 248)
    glow: float = 9.0          # glow radius px
    glow_strength: float = 1.0
    glow_color: tuple | None = None   # deep glow hue; None → derived
    loop: bool = False
    fade_ends: bool = False    # AIR: extremities dissolve into darkness
    name: str = ""


@dataclass
class Mark:
    cx: float
    cy: float
    kind: str = "fish"         # fish, spark, ember, seed, leaf, root, beetle,
                               # bird, feather, prism, aperture, point,
                               # ambiguity, ripple, bubble
    scale: float = 1.0
    color: tuple = (200, 230, 255)
    rot: float = 0.0           # radians
    params: dict = field(default_factory=dict)


@dataclass
class Symbol:
    name: str
    paths: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    fills: list = field(default_factory=list)  # (points, color, alpha) closed
                                               # luminous regions
    width: int = 1448
    height: int = 1086
    background: tuple = (0, 0, 0)
    atmosphere: tuple | None = (5, 10, 20)   # deep atmosphere hue or None
    atmosphere_peak: float = 70.0    # peak luminance of atmosphere field
    atmosphere_sigma: float = 320.0  # gaussian sigma px (at scale 1.0)
    horizon: float | None = None      # y position (canvas coords) or None
    horizon_color: tuple = (90, 160, 200)
    horizon_glow: float = 6.0
    reflections: list = field(default_factory=list)  # (y, length, alpha)
    lens_band: tuple | None = None   # (x0, x1, y, height, lum) bright cross
                                     # horizon band (measured: 493..963, y=540)
    lens_strip: tuple | None = None  # (x, y0, y1, width, lum) vertical lens
    glow_stack: list = field(default_factory=lambda: [
        (3.0, 0.55), (9.0, 0.35), (22.0, 0.18), (48.0, 0.09),
        (100.0, 0.05), (180.0, 0.02)])
    core_boost: float = 0.55        # mix of path colors toward white
    tone_gamma: float = 1.0         # tone curve exponent
    tone_cap: float = 250.0         # highlight roll-off ceiling

    def canvas_center(self):
        return self.width / 2, self.height / 2


# ---------------------------------------------------------------- sampling helpers

def catmull_rom(pts, samples=200, loop=False):
    """Smooth polyline through control points. Returns dense polyline."""
    n = len(pts)
    if n < 3:
        return list(pts)
    out = []
    if loop:
        ext = pts + pts[:3]
    else:
        ext = [(2 * pts[0][0] - pts[1][0], 2 * pts[0][1] - pts[1][1])] + list(pts) + \
              [(2 * pts[-1][0] - pts[-2][0], 2 * pts[-1][1] - pts[-2][1])]
    per_seg = max(8, samples // (n - 1))
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i:i + 4]
        for t in np.linspace(0, 1, per_seg + 1)[:-1]:
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    if not loop:
        out.append(ext[-2])
    return out


def resample(poly, n=600):
    """Evenly resample a polyline by arc length."""
    if len(poly) < 2:
        return list(poly)
    segs = [math.dist(poly[i], poly[i + 1]) for i in range(len(poly) - 1)]
    total = sum(segs)
    if total <= 0:
        return list(poly)
    out = [poly[0]]
    acc = 0.0
    i = 0
    for k in range(1, n):
        goal = total * k / n
        while i < len(segs) - 1 and acc + segs[i] < goal:
            acc += segs[i]
            i += 1
        if i >= len(segs):
            break
        rem = goal - acc
        t = rem / segs[i] if segs[i] > 0 else 0
        out.append((poly[i][0] + (poly[i + 1][0] - poly[i][0]) * t,
                    poly[i][1] + (poly[i + 1][1] - poly[i][1]) * t))
    out.append(poly[-1])
    return out


def path_point(poly, t):
    """Point at normalized arc-length t along a polyline."""
    i = t * (len(poly) - 1)
    i0 = min(int(i), len(poly) - 2)
    f = i - i0
    p0, p1 = poly[i0], poly[i0 + 1]
    return (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)


def path_tangent(poly, t):
    i = t * (len(poly) - 1)
    i0 = min(int(i), len(poly) - 2)
    p0, p1 = poly[i0], poly[i0 + 1]
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    return (dx / L, dy / L)


def offset_poly(poly, offset):
    """Offset a polyline perpendicular to its local tangent."""
    out = []
    for k, (x, y) in enumerate(poly):
        if k == 0:
            tx, ty = path_tangent(poly, 0)
        elif k == len(poly) - 1:
            tx, ty = path_tangent(poly, 0.9999)
        else:
            tx, ty = path_tangent(poly, k / (len(poly) - 1))
        out.append((x - ty * offset, y + tx * offset))
    return out


def rotate_pts(pts, center, ang):
    c = math.cos(ang)
    s = math.sin(ang)
    cx, cy = center
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
            for x, y in pts]
