#!/usr/bin/env python3
"""Measure a clean 1D line+glow profile from the horizon dashes."""
from pathlib import Path
import json

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "reference" / "water-master.png"
OUT = ROOT / "design" / "line-profile.json"

img = Image.open(REF).convert("RGB")
a = np.asarray(img, dtype=np.float32)
lum = (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2])

# horizon dash: left x338-594 y561-564. Take vertical cut at x=450.
cuts = {}
for x in [400, 450, 500, 550]:
    col = lum[540:590, x]
    cuts[str(x)] = [float(v) for v in col]

# Also horizontal cut across the dash at its peak row y=562 (profile along line
# + glow is not useful; skip).

# Bubble: (444,333) 4-10px. Vertical cut at x=444.
cuts["bubble_x444"] = [float(v) for v in lum[320:350, 444]]
cuts["bubble_x452"] = [float(v) for v in lum[330:360, 452]]

# Fish mark: find its actual bright rows near (487,364) — scan a vertical band
band = lum[340:400, 440:540]
rows_with_runs = []
for y in range(340, 400):
    row = lum[y, 440:540]
    bright = row > 15
    if bright.any():
        rows_with_runs.append(y)
print("fish bright rows:", rows_with_runs[:5], "...", rows_with_runs[-5:] if rows_with_runs else "")

OUT.write_text(json.dumps(cuts, indent=2))
for k, v in cuts.items():
    print(k, "->", [round(x, 1) for x in v])
