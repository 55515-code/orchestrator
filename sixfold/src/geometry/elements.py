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

def water():
    cx, cy = W / 2, H / 2
    C = hex_to_rgb("82DDF8")       # luminous cyan core (measured ~117,212,244)
    D = hex_to_rgb("5BB8E2")       # dimmer cyan (fish/horizon ~92,188,226)
    B = hex_to_rgb("1E8FC8")       # bubbles
    G = hex_to_rgb("2A6FA8")       # glow wash

    # ---- lobes: teardrop = circle arc + pointed tip ----
    # Left lobe: center (485, 545), radius ~195; tip at left (215, 545)
    # Right lobe: center (995, 545), radius ~195; tip at right (1235, 545)
    # Both meet at crossing zone x≈700-755, y≈525-565
    def teardrop(center, tip_x, outer=True):
        """Teardrop loop: circular lobe with a pointed outer tip.
        Path: crossing → around top → tip → around bottom → crossing."""
        r = 195.0
        lcx, lcy = center
        pts = []
        # start at inner crossing edge
        start = (lcx - (r if outer else -r) * 0.0 + (lcx - 20), lcy - 6)
        # We'll build: from crossing, up the inner side, over the top arc,
        # out to the tip, back under the bottom arc, up inner side to crossing
        # inner edge
        n = 60
        # top arc: angle from 90° (top) sweeping to 0° (right/tip side)
        # parametrize: crossing → top → tip
        top_arc = []
        for k in range(n + 1):
            t = k / n
            # angle from -90 (bottom) ... use: start at top going counterclockwise
            ang = math.pi / 2 - t * math.pi  # 90° → -90° (via 0° = right = tip)
            x = lcx + math.cos(ang) * r
            y = lcy - math.sin(ang) * r
            top_arc.append((x, y))
        # tip: pull the 0° point out to the pointed tip
        tip_pt = (tip_x, lcy)
        # blend the arc points near angle 0 toward the tip
        for i, (x, y) in enumerate(top_arc):
            ang = math.pi / 2 - (i / n) * math.pi
            # how close to tip angle (0)?
            closeness = max(0, 1 - abs(ang) / (math.pi / 6))
            if closeness > 0:
                bx = x + (tip_pt[0] - x) * closeness ** 1.5
                by = y + (tip_pt[1] - y) * closeness ** 1.5
                top_arc[i] = (bx, by)
        # bottom arc: from tip back to crossing (angle 0 → 90 via -90)
        bottom_arc = []
        for k in range(n + 1):
            t = k / n
            ang = -math.pi / 2 + t * math.pi  # -90° → 90° (via 0°)
            x = lcx + math.cos(ang) * r
            y = lcy - math.sin(ang) * r
            bottom_arc.append((x, y))
        for i, (x, y) in enumerate(bottom_arc):
            ang = -math.pi / 2 + (i / n) * math.pi
            closeness = max(0, 1 - abs(ang) / (math.pi / 6))
            if closeness > 0:
                bx = x + (tip_pt[0] - x) * closeness ** 1.5
                by = y + (tip_pt[1] - y) * closeness ** 1.5
                bottom_arc[i] = (bx, by)
        # assemble: top_arc goes crossing(top) → tip; bottom_arc tip → crossing(bottom)
        poly = top_arc + bottom_arc[1:]
        return poly

    # Position lobes: crossing at x≈727; left lobe center ~485, right ~995
    left = teardrop((485, 545), 215)
    right = teardrop((995, 545), 1235)

    # Trim the inner ends so the two lobes overlap into a lens crossing:
    # keep everything; renderer draws both, overlap gives the lens.
    left = catmull_rom(left, samples=500)
    right = catmull_rom(right, samples=500)

    paths = [
        Path(left, width=2.2, color=C, glow=9.0, glow_strength=0.95, name="lobe-left"),
        Path(right, width=2.2, color=C, glow=9.0, glow_strength=0.95, name="lobe-right"),
    ]

    # ---- fish on trajectories ----
    # upper-left fish rides the left lobe's top arc, ~90px long
    # measured: bbox (442,347)-(533,382) → center ~(487, 364)
    # lower-right fish: (953,686)-(1040,722) → center ~(996, 704)
    fl = Mark(487, 364, kind="fish", scale=9.0, color=D, rot=-0.35)
    fr = Mark(996, 704, kind="fish", scale=9.0, color=D, rot=-2.75)

    # bubbles: measured b1 (440,330)-(447,337) small cluster above left fish
    #          b2 (1047,687)-(1051,691), (1067,702)-(1077,705) below right fish
    bubbles = [
        Mark(444, 333, kind="bubble", scale=2.0, color=B),
        Mark(452, 341, kind="bubble", scale=1.5, color=B),
        Mark(1052, 689, kind="bubble", scale=1.6, color=B),
        Mark(1069, 700, kind="bubble", scale=2.2, color=B),
    ]

    # ---- horizon: two dashes, one under each lobe ----
    # measured: left dash (338,561)-(594,564); right dash (885,561)-(1116,564)
    # reflections: (431,584)-(502,585) under left, (956,582)-(1030,583) under right
    horizon_marks = [
        Mark(466, 563, kind="ripple", scale=9.0, color=D, rot=0),
        Mark(1000, 563, kind="ripple", scale=10.5, color=D, rot=0),
        # reflection dashes
        Mark(466, 584, kind="ripple", scale=3.2, color=B, rot=0),
        Mark(993, 583, kind="ripple", scale=3.2, color=B, rot=0),
    ]

    return Symbol(
        name="water",
        paths=paths,
        marks=fl, marks2=fr, marks3=bubbles + horizon_marks,
        width=W, height=H,
        background=(0, 0, 0),
        atmosphere=None,
        horizon=None,
    )
