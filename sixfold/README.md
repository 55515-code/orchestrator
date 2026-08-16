# SIXFOLD — Elemental Symbol Series

Autonomous development of a coherent six-element symbolic visual language,
derived from a canonical WATER reference (infinity + horizon + fish + reflection).

## Status: IN PROGRESS

| Element | Geometry | Micro-narrative | Status |
|---|---|---|---|
| I WATER | teardrop ∞ (measured from reference) | 2 fish + bubbles + horizon dashes | v1 rendered, pending critique |
| II FIRE | folded flame loop, climbing | 2 sparks + ember crossing | v1 rendered, pending critique |
| III EARTH | — | — | not started |
| IV AIR | — | — | not started |
| V LIGHT | — | — | not started |
| VI CHAOS | — | — | not started |

## Pipeline (reusable)

1. **Analyze** — `src/analysis/analyze_reference.py` → `design/measurements.json`
   (canvas, bbox, line weight, colors, negative space, symmetry, horizon, micro-scale)
2. **Define** — `src/geometry/elements.py` (parametric symbol definitions)
3. **Render** — `src/rendering/` (core primitives, micro-marks, renderer)
   `scripts/render.py` → dark master PNG + transparent PNG + SVG
4. **Critique** — `src/evaluation/ollama_vision.py` (local qwen3.5:9b vision)
   + `src/evaluation/contact_sheet.py`, `score_parser.py`
5. **Refine** — remove marks; re-render; re-critique

## Key findings from reference analysis

- Canvas 1448×1086 (4:3), symbol core bbox 1113×394 (~77% width, 36% height)
- Line weight ≈2.0–2.75 px; glow radius ≈9 px; negative space ≈78% (atmos threshold)
- **Horizon is two dashes under each lobe, not a full line** (measured 338–594 and 885–1116)
- **Lobes are tall teardrops with pointed outer tips**, crossing in a lens zone
- Fish ≈90 px long (≈9× line width), one upper-left (487,364), one lower-right (996,704)
- Colors: core (117,212,244), fish/horizon (92,188,226), bubbles (30,146,210), pure black bg
- Symmetry 0.28 IoU — diagonal counterbalance, not mirror symmetry

## Docs

- `design/visual-grammar.md` — the genome + mutation table
- `design/reference-analysis.md` — vision-model perception of the reference
- `design/measurements.json` — computed measurements
