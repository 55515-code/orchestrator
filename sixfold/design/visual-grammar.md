# SIXFOLD — Visual Grammar

Canonical source: `reference/water-master.png` (Symbol I: WATER).
Measurements: `measurements.json` (computed). Perception: `reference-analysis.md` (vision model).

## The Genome (inherited by every symbol)

1. **Darkness** — near-black field (`#000`–`#050a14`), background dominates.
2. **Single luminous trajectory** — one continuous principal line, uniform width, no joints.
3. **Extreme negative space** — symbol occupies a small fraction of canvas; measured: ~78% of pixels below even the faintest atmosphere.
4. **Micro-scale life/symbol** — one or two tiny glyph-sized creatures/objects embedded IN the path, not on it.
5. **Balanced geometry** — centered composition; rotational/diagonal counterbalance instead of literal mirror symmetry.
6. **Quiet atmosphere** — self-emissive glow, radial falloff, no external light source, no lens flares.
7. **Elemental motion** — static image that implies continuous flow/behavior.
8. **Line character** — hairline core (measured ≈2 px at 1448×1086), precise but organic, clean orthogonal self-crossing, no taper, no bevel, no bloom excess. Glow supports, never is, the drawing.

## Measured Constraints (1448×1086 reference)

| Property | Value |
|---|---|
| Canvas aspect | 1.333 (4:3) |
| Core bbox | 1113 × 394 px → width ≈ 77% canvas, height ≈ 36% |
| Glow bbox | 1352 × 395 px |
| Center | (0.503, 0.484) — essentially dead center, slightly above |
| Line weight | 2.75 px mean / 2.0 px median core |
| Glow radius | ≈9 px |
| Negative space | 78.4% |
| Horizon | y = 0.502 (through the crossing) |
| Dominant core color | (130, 221, 248) — luminous cyan |
| Background | (0,0,0) |
| Symmetry | 0.28 IoU — far from bilateral; diagonal counterbalance |
| Micro components | ~28 small marks (fish, bubbles, ripples), mass ≈ 28% of core mass — but visually they read as "a few tiny things" |

## Composition Rules

- Symbol centered; vertical center ≈ canvas midpoint; horizon through crossing.
- Primary line extends ~77% of canvas width; margins roughly equal.
- Micro-objects: 2 fish + 6 bubbles + 3 reflection bands. Scale: fish ≈ 8–9× line width.
- Glow: radial falloff to ~20% at borders; slight chromatic dispersion at halo edges.
- Deliberate asymmetry: fish at upper-left / lower-right (diagonal tension), subtle non-uniform blur.

## The Mutation Table (how each element differs)

| Element | Geometry gene | Micro-narrative | Atmosphere mutation | Color |
|---|---|---|---|---|
| I WATER | ∞ crossing at center, horizon through it | 2 fish on diagonal lobes | soft aquatic radial glow | cyan (130,221,248) |
| II FIRE | vertically biased double-spiral/folded loop, climbing | 2 sparks / ember crossing | hot core, tight falloff, ember dust | deep ember → orange → near-white core |
| III EARTH | heavy strata/orbit path with compression | seed / root bifurcation / beetle | denser, gravitational, low glow | mineral green + ochre |
| IV AIR | interrupted-continuity circulation, thinnest line | bird/seed/feather on trajectory | thinnest, softest glow, nearly vanishing | silver-blue → pale violet |
| V LIGHT | converging/emerging geometry, single luminous focus | prism/aperture/eye points | darkness as active component, hard-edged focus | warm white → restrained gold |
| VI CHAOS | near-symmetric path with ONE impossible transition | ambiguous eye/insect/seed/fish/star | one surgical chromatic fracture | ultraviolet/magenta + single RGB split |

## Rules That Never Bend

- No typography, no borders, no signatures, no runes, no texture fills.
- Max ~2–6 secondary marks per symbol.
- One dominant color family.
- One principal continuous geometric gesture.
- Thumbnail-recognizable; full-res reveals tiny discoveries.
- Fewer marks after every refinement pass — never more.
- The five new symbols derive from the grammar, not by copying the ∞ glyph and swapping fish.
