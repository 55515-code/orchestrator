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
    B = hex_to_rgb("6BC4EA")       # bubbles (measured bright ~107,199,230)
    G = hex_to_rgb("023161")       # deep glow hue (measured glow 2,49,97 → darker)
    A = hex_to_rgb("12315C")       # atmosphere hue (measured 0.3,17.6,38.8 → scaled)

    # ---- measured vesica geometry (design/vesica-geometry.json) ----
    # The reference is built from FOUR SPLINE ARCS traced from the pixel
    # data + a horizon line:
    #   horizon: y=545, x=143..1311 (bright line)
    #   left_top arc:    spline from tip region up over the top to x=660
    #   left_bottom arc: spline from x=660 under the bottom back to tip
    #   right_top arc:   spline from x=880 over the top to tip
    #   right_bottom arc:spline from tip under the bottom to x=880
    #   lens side: top apex (740,523) → bottom apex (740,562)
    import json
    from pathlib import Path as FsPath
    geo = json.loads(FsPath(__file__).resolve().parents[2].joinpath(
        "design", "vesica-geometry.json").read_text())

    TIPL = geo["tips"]["left"]
    TIPR = geo["tips"]["right"]
    TA = geo["lens"]["top_apex"]
    BA = geo["lens"]["bottom_apex"]
    SP = geo["splines"]

    # Build each lobe as TWO paths (the reference has no bright stroke on
    # the lens side between the apexes — the lens is dark, crossed only by
    # the horizon):
    #   top:    tip → left_top spline → diagonal → top apex (740,523)
    #   bottom: bottom apex (740,562) → diagonal → left_bottom spline → tip
    l_top_pts = [tuple(p) for p in SP["left_top"]]
    l_bot_pts = [tuple(p) for p in SP["left_bottom"]][::-1]
    l_top_path = [tuple(TIPL)] + l_top_pts + [tuple(TA)]
    l_bot_path = [tuple(BA)] + l_bot_pts + [tuple(TIPL)]
    l_top_path = resample(l_top_path, 300)
    l_bot_path = resample(l_bot_path, 300)

    r_top_pts = [tuple(p) for p in SP["right_top"]]
    r_bot_pts = [tuple(p) for p in SP["right_bottom"]][::-1]
    r_top_path = [tuple(TA)] + r_top_pts + [tuple(TIPR)]
    r_bot_path = [tuple(TIPR)] + r_bot_pts + [tuple(BA)]
    r_top_path = resample(r_top_path, 300)
    r_bot_path = resample(r_bot_path, 300)

    paths = [
        Path(l_top_path, width=2.2, color=C, glow=9.0, glow_strength=0.95,
             glow_color=G, name="lobe-left-top"),
        Path(l_bot_path, width=2.2, color=C, glow=9.0, glow_strength=0.95,
             glow_color=G, name="lobe-left-bottom"),
        Path(r_top_path, width=2.2, color=C, glow=9.0, glow_strength=0.95,
             glow_color=G, name="lobe-right-top"),
        Path(r_bot_path, width=2.2, color=C, glow=9.0, glow_strength=0.95,
             glow_color=G, name="lobe-right-bottom"),
    ]

    # fish: measured bbox upper-left (442,347)-(533,382) → center (487,364)
    #              lower-right (953,686)-(1040,722) → center (996,704)
    fl = Mark(487, 364, kind="fish", scale=9.0, color=D, rot=0.0)
    fr = Mark(996, 704, kind="fish", scale=9.0, color=D, rot=0.0)

    # bubbles: small bright rings trailing the fish (measured: ring at
    # (445,334) r≈4.4px peak 235; second at (452,341))
    bubbles = [
        Mark(445, 334, kind="bubble", scale=2.6, color=B),
        Mark(454, 341, kind="bubble", scale=1.8, color=B),
        Mark(1052, 689, kind="bubble", scale=2.2, color=B),
        Mark(1069, 700, kind="bubble", scale=2.6, color=B),
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
        fills=[],
        lens_band=(493, 963, 540, 30, 150),   # measured bright horizon band
        lens_strip=(740, 480, 620, 16, 110),  # measured lens hot vertical
        width=W, height=H,
        background=(0, 0, 0),
        atmosphere=A,
        atmosphere_peak=22.0,
        atmosphere_sigma=340.0,
        glow_stack=[(3.0, 0.5), (9.0, 0.3), (22.0, 0.15), (48.0, 0.06)],
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
