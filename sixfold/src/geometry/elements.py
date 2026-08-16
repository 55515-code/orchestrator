#!/usr/bin/env python3
"""SIXFOLD symbol definitions.

Each element is a parametric description built from the shared grammar
(one line, one field, one force, one tiny living/symbolic interruption).
"""
from __future__ import annotations

import math

from rendering.core import Path, Mark, Symbol, catmull_rom, hex_to_rgb, \
    path_point, path_tangent, resample

# Canvas (matches reference)
W, H = 1448, 1086


def _place(poly, t, off_px):
    """Point offset from the path at normalized t."""
    p = path_point(poly, t)
    tx, ty = path_tangent(poly, t)
    return (p[0] - ty * off_px, p[1] + tx * off_px)


# ================================================================ I — WATER
# Geometry measured from the reference:
#   two tall teardrop lobes (outer tips pointed), lens-shaped crossing,
#   horizon as TWO DASHES beneath each lobe (not a full line),
#   two fish ~90px long on upper-left / lower-right,
#   small bubbles, two reflection dashes under each lobe.

def _teardrop(center, tip_x, r=195.0, n=70):
    """Teardrop loop: circular lobe with a pointed outer tip.
    Path: crossing → around top → tip → around bottom → crossing."""
    lcx, lcy = center
    tip_pt = (tip_x, lcy)

    def tip_blend(pts):
        """Pull arc points near angle 0 (tip side) toward the pointed tip."""
        out = []
        for x, y, ang in pts:
            closeness = max(0.0, 1 - abs(ang) / (math.pi / 5))
            if closeness > 0:
                bx = x + (tip_pt[0] - x) * closeness ** 1.6
                by = y + (tip_pt[1] - y) * closeness ** 1.6
                out.append((bx, by))
            else:
                out.append((x, y))
        return out

    # top arc: angle 90° → -90° via 0° (tip at 0°)
    top = []
    for k in range(n + 1):
        t = k / n
        ang = math.pi / 2 - t * math.pi
        top.append((lcx + math.cos(ang) * r, lcy - math.sin(ang) * r, ang))
    top = tip_blend(top)

    # bottom arc: -90° → 90° via 0°
    bot = []
    for k in range(n + 1):
        t = k / n
        ang = -math.pi / 2 + t * math.pi
        bot.append((lcx + math.cos(ang) * r, lcy - math.sin(ang) * r, ang))
    bot = tip_blend(bot)

    return top + bot[1:]


def water():
    C = hex_to_rgb("82DDF8")       # luminous cyan core (measured ~117,212,244)
    D = hex_to_rgb("5BB8E2")       # dimmer cyan (fish/horizon ~92,188,226)
    B = hex_to_rgb("1E8FC8")       # bubbles
    G = hex_to_rgb("023161")       # deep glow hue (measured glow 2,49,97 → darker)
    A = hex_to_rgb("12315C")       # atmosphere hue (measured 0.3,17.6,38.8 → scaled)

    # ---- measured vesica geometry (design/lobe-geometry.json) ----
    # two filled ellipses, inner edges meeting at x=720 (the lens)
    import json
    from pathlib import Path as FsPath
    geo = json.loads(FsPath(__file__).resolve().parents[2].joinpath(
        "design", "lobe-geometry.json").read_text())
    L = geo["left_ellipse"]
    R = geo["right_ellipse"]
    lcx, lcy, lrx, lry = L["cx"], L["cy"], L["rx"], L["ry"]
    rcx, rcy, rrx, rry = R["cx"], R["cy"], R["rx"], R["ry"]

    def ellipse_poly(cx, cy, rx, ry, n=120):
        return [(cx + rx * math.cos(a), cy + ry * math.sin(a))
                for a in [2 * math.pi * k / n for k in range(n)]]

    left_poly = ellipse_poly(lcx, lcy, lrx, lry)
    right_poly = ellipse_poly(rcx, rcy, rrx, rry)

    # fill: translucent luminous cyan, alpha stronger toward the lens
    fills = [
        (left_poly, (20, 90, 160), 0.28),
        (right_poly, (20, 90, 160), 0.28),
    ]

    # inset outline strokes: bright arcs along each ellipse, ~15-30px inside
    # top arc: angle 90°→-90° (via 0°), bottom arc: -90°→90°
    def arc(cx, cy, rx, ry, a0, a1, n=80, inset=22):
        return [(cx + (rx - inset) * math.cos(a), cy + (ry - inset) * math.sin(a))
                for a in np_linspace(a0, a1, n)]

    import numpy as np
    def np_linspace(a0, a1, n):
        return list(np.linspace(a0, a1, n))

    # left lobe: top arc from left tip (π) to inner top (0), bottom arc from
    # inner bottom (0... actually 2π) back to left tip (π)
    # ellipse angles: 0 = right, π/2 = down (image y+)
    # left lobe tip is at angle π (left side), inner edge at angle 0 (right side)
    l_top = arc(lcx, lcy, lrx, lry, math.pi, 0, n=70, inset=24)
    l_bot = arc(lcx, lcy, lrx, lry, math.tau, math.pi, n=70, inset=24)
    l_top.reverse()  # keep continuity
    l_path = l_top + l_bot[1:]

    # right lobe: tip at angle 0 (right side), inner edge at angle π (left)
    r_top = arc(rcx, rcy, rrx, rry, math.pi, 0, n=70, inset=24)
    r_bot = arc(rcx, rcy, rrx, rry, math.tau, math.pi, n=70, inset=24)
    r_top.reverse()
    r_path = r_top + r_bot[1:]

    paths = [
        Path(l_path, width=2.2, color=C, glow=9.0, glow_strength=0.95,
             glow_color=G, name="lobe-left"),
        Path(r_path, width=2.2, color=C, glow=9.0, glow_strength=0.95,
             glow_color=G, name="lobe-right"),
    ]

    # fish: measured bbox upper-left (442,347)-(533,382) → center (487,364)
    #              lower-right (953,686)-(1040,722) → center (996,704)
    fl = Mark(487, 364, kind="fish", scale=9.0, color=D, rot=-0.42)
    fr = Mark(996, 704, kind="fish", scale=9.0, color=D, rot=-2.72)

    # bubbles: small clusters trailing the fish
    bubbles = [
        Mark(444, 333, kind="bubble", scale=2.0, color=B),
        Mark(452, 341, kind="bubble", scale=1.4, color=B),
        Mark(1052, 689, kind="bubble", scale=1.5, color=B),
        Mark(1069, 700, kind="bubble", scale=2.1, color=B),
    ]

    # horizon: two dashes under each lobe + reflection dashes below
    horizon_marks = [
        Mark(466, 563, kind="ripple", scale=9.0, color=D, rot=0),
        Mark(1000, 563, kind="ripple", scale=10.5, color=D, rot=0),
        Mark(466, 584, kind="ripple", scale=3.2, color=B, rot=0),
        Mark(993, 583, kind="ripple", scale=3.2, color=B, rot=0),
    ]

    return Symbol(
        name="water",
        paths=paths,
        marks=[fl, fr] + bubbles + horizon_marks,
        fills=fills,
        lens_band=(493, 963, 540, 30, 150),   # measured bright horizon band
        lens_strip=(740, 480, 620, 16, 110),  # measured lens hot vertical
        width=W, height=H,
        background=(0, 0, 0),
        atmosphere=A,
        atmosphere_peak=70.0,
        atmosphere_sigma=330.0,
        glow_stack=[(3.0, 0.55), (9.0, 0.35), (22.0, 0.18), (48.0, 0.09)],
        core_boost=0.85,
        tone_gamma=1.0,
        tone_cap=250.0,
        horizon=None,
    )


# ================================================================ II — FIRE
# Rise, ignition, recurrence.
# Geometry: a single continuous folded-flame loop — enters low, climbs through
# a waist crossing, opens into a taller loop that folds back on itself and
# terminates in a near-white hot point. Vertically biased infinity derivative.
# Micro-narrative: two sparks riding the trajectory, one ember crossing the path.
# Color: deep ember → orange → narrow near-white hot core.

def fire():
    cx, cy = W / 2, H / 2
    EMBER = hex_to_rgb("D84A12")      # deep ember
    ORANGE = hex_to_rgb("FF7A1A")
    HOT = hex_to_rgb("FFE8C0")        # near-white core

    # ---- parametric folded flame ----
    # One continuous curve, parameterized from bottom (t=0) to top (t=1).
    # Bottom: rises from a point, curves left, crosses at the waist,
    # opens into the main flame loop, folds at the top into a hot tip.
    def folded_flame():
        pts = []
        n = 500
        for k in range(n):
            t = k / (n - 1)
            # base → waist (t 0→0.45): climb from bottom center-left
            if t < 0.45:
                u = t / 0.45
                x = cx - 60 - 300 * math.sin(u * math.pi * 0.5) * (1 - u * 0.4)
                y = cy + 330 - 260 * u
            # waist crossing (t 0.45→0.55): the fold — path crosses itself
            elif t < 0.55:
                u = (t - 0.45) / 0.10
                x = cx - 60 + 120 * u
                y = cy + 70 - 40 * u
            # main loop (t 0.55→0.95): opens wide, rises, folds inward
            else:
                u = (t - 0.55) / 0.40
                ang = u * math.tau * 1.0 - math.pi / 2
                rx = 360 + 60 * u
                ry = 150 + 110 * u
                x = cx + 60 + math.cos(ang) * rx * 0.55
                y = cy - 40 - math.sin(ang) * ry + 60 * (1 - u)
            pts.append((x, y))
        # hot tip: the loop's top folds into a sharp point (t 0.95→1)
        top = pts[-1]
        tip = (cx + 60, cy - 320)
        for k in range(60):
            u = k / 59
            x = top[0] + (tip[0] - top[0]) * u
            y = top[1] + (tip[1] - top[1]) * u
            pts.append((x, y))
        return pts

    core_path = resample(folded_flame(), 700)

    # color ramp along path: ember → orange → hot
    def seg(t0, t1, color, width, glow):
        sub = [p for k, p in enumerate(core_path)
               if t0 <= k / (len(core_path) - 1) <= t1]
        if not sub:
            return None
        return Path(sub, width=width, color=color, glow=glow, name="flame")

    paths = [
        seg(0.00, 0.50, EMBER, 2.6, 10.0),
        seg(0.46, 0.80, ORANGE, 2.1, 9.0),
        seg(0.76, 1.00, HOT, 1.5, 8.0),
    ]
    paths = [p for p in paths if p]

    # sparks on the trajectory + ember crossing near the waist
    s1 = _place(core_path, 0.30, 14)
    s2 = _place(core_path, 0.88, 14)
    ex, ey = _place(core_path, 0.52, -18)

    marks = [
        Mark(*s1, kind="spark", scale=0.8, color=ORANGE, rot=0.7),
        Mark(*s2, kind="spark", scale=0.9, color=HOT, rot=-0.4),
        Mark(ex, ey, kind="ember", scale=0.9, color=ORANGE, rot=0.0),
    ]

    return Symbol(
        name="fire",
        paths=paths,
        marks=marks,
        width=W, height=H,
        background=(0, 0, 0),
        atmosphere=(28, 8, 2),          # faint ember warmth
        atmosphere_peak=60.0,
        atmosphere_sigma=300.0,
        glow_stack=[(3.0, 0.55), (9.0, 0.35), (22.0, 0.18), (48.0, 0.09)],
        core_boost=0.80,
        tone_gamma=1.0,
        tone_cap=250.0,
        horizon=None,
    )


# ================================================================ registry

ELEMENTS = {
    "water": water,
    "fire": fire,
}
