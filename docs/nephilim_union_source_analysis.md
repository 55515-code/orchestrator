# Source Analysis — *Nephilim Union* (ClownBlack)

**Source file:** `/home/ahron/Downloads/nephilim_union_by_clownblack_dfnuyx3-414w-2x.jpg`
**Method:** Direct visual inspection of the source image (414×585 web thumbnail, JPEG).
All observations below are drawn from the image itself; no prior artifacts carried over.

---

## 1. Content (what is depicted)

- **One composite head made of two faces joined by a vertical red zipper/stitched seam**
  running forehead-to-chin — the literal "union" of two beings.
- **Left face:** dark brown/maroon skin; one realistic eye (white sclera, dark iris,
  defined lid). A lavender-pink hand pinches and **peels its edge like a mask**; a second
  lavender hand cups the jaw from lower left. Fingernails visible; hands read as
  removing/holding the face.
- **Right face:** flat hot-pink mask-like face with minimal features — small dark eye
  slit, small open oval mouth, faint freckle dots.
- **Indigo visor band** (sunglass-like) spanning both faces at eye level; inside it on the
  right, a **second sharp realistic eye** — a third-eye/gaze motif.
- **Crown:** radiating row of sharp magenta/crimson four-pointed star/diamond spikes;
  above it, **teal-green painterly brushstroke hair**.
- **Glitch accents:** iridescent holographic rainbow smears at the right ear/neck and a
  spectral band at the throat.
- **Background:** translucent flowing magenta/violet/purple blob shapes over a pale
  gray-white field; lower third fades to flat gray.
- **Line overlays:** continuous wavy topographic/woodgrain contour lines in blue,
  magenta, and orange rippling across the whole canvas; thin straight diagonal
  orange/red accent lines cutting the composition.
- **Typography:** bottom — "Nephilim" + **mirrored "Union"** ("noin∪") in white geometric
  sans-serif.

## 2. Visual Style

- Psychedelic / visionary surrealism (Alex Grey lineage — the artist's stated favorite).
- Photomanipulation fused with flat vector shapes and continuous line art.
- Wave-distortion / glitch aesthetic; translucent layering; screen-blend color builds.
- Palette: hot magenta/pink dominant, violet/purple, electric indigo-blue, teal-green
  accent, crimson seam, orange/yellow line accents, gray-white ground.
- Lighting: no single source — luminous flat/translucent color fields; highlights bloom
  out of the pink washes.

## 3. Thematic Elements

- **Duality/union:** hybrid being (nephilim = joined natures); two faces, one head.
- **Mask & identity:** faces peeled/held like masks; the visor hides/reveals a third eye.
- **Stitched self:** the zipper seam as forced or sacred joining.
- **Crown/halo:** star-spikes and brushstroke hair as profane-sacred regalia.
- **Mirrored self:** reversed "Union" text — the other half reads backwards.

## 4. Context

- DeviantArt deviation by **clownblack** (user's earlier alias), titled *Nephilim Union*.
- 414 px-wide JPEG web thumbnail → low-res, blocky compression; era tooling: GIMP.
- Artist's current identity: **Electrac Angel**; brand essence "electric, transformative,
  boundary-pushing."

## 5. Modernization Strategy (derived from observation)

Fidelity-first. Text-to-image and AI img2img were tested and **discarded with evidence**:

- **FLUX Kontext** (structure-preserving edit model): HTTP 500 — "kontext model is only
  available on enter.pollinations.ai" (enterprise tier). Unavailable.
- **Free flux + `image` param** (img2img): returned a generic two-portrait anime image
  borrowing only the palette; source composition ignored (probe kept in repo history,
  QC edge-correlation gate would reject). Discarded.

Final pipeline (`scripts/remaster_pipeline.py`), all steps derived from §1–§3:

1. **Edge-masked deblock** at source scale — Gaussian smoothing applied only to flat
   wash regions (edge magnitude < p55), preserving linework, seam, and type.
2. **5× LANCZOS upscale** (828×1104 → 4140×5520).
3. **Vibrance** (undersaturated-pixel-weighted saturation lift, a=0.25).
4. **Gentle S-curve** (contrast 1.06).
5. **Subtle highlight bloom** (15% screen-blend of 24px blur above luma 190).
6. **UnsharpMask** (r=2, 110%, t=2) to crisp the contour linework.

QC gates (all pass on final run):
- luminance NCC vs source ≥ 0.93 → **0.9961**
- palette ΔE (k-means 5, Lab) ≤ 12 → **4.50**
- integrity: decodable PNG 4140×5520 → pass

Outputs: `generated/remaster/nephilim_union_modern_final.png` (primary),
`preview_modern_1024.png`, `report.json`.
