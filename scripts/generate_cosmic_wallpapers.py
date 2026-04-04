#!/usr/bin/env python3

import argparse
import random
import re
import subprocess
from pathlib import Path


THEME_ROOT = Path.home() / ".config" / "cosmic"
DEFAULT_OUTPUT = Path.home() / "codespace" / "generated" / "cosmic-wallpapers"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_rgb(path: Path, group: str | None = None, fallback=(0.0, 0.0, 0.0)):
    text = path.read_text(encoding="utf-8")
    if group:
        match = re.search(
            rf"{re.escape(group)}:\s*\(\s*red:\s*([-\d.]+),\s*green:\s*([-\d.]+),\s*blue:\s*([-\d.]+)",
            text,
            flags=re.S,
        )
    else:
        match = re.search(
            r"red:\s*([-\d.]+),\s*green:\s*([-\d.]+),\s*blue:\s*([-\d.]+)",
            text,
            flags=re.S,
        )
    if not match:
        return fallback
    return tuple(clamp01(float(match.group(i))) for i in range(1, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{round(clamp01(channel) * 255):02x}" for channel in rgb)


def rgb_to_rgba(rgb, alpha):
    return f"rgba({round(rgb[0] * 255)}, {round(rgb[1] * 255)}, {round(rgb[2] * 255)}, {alpha:.4f})"


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def brighten(rgb, amount):
    return mix(rgb, (1.0, 1.0, 1.0), amount)


def darken(rgb, amount):
    return mix(rgb, (0.0, 0.0, 0.0), amount)


def parse_current_mode():
    candidates = [Path.home() / ".local" / "bin" / "wlr-randr", Path("/usr/bin/wlr-randr")]
    for candidate in candidates:
        if candidate.exists():
            result = subprocess.run(
                [str(candidate)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                continue
            match = re.search(r"^\s+(\d+)x(\d+) px, .*?\(preferred, current\)", result.stdout, flags=re.M)
            if not match:
                match = re.search(r"^\s+(\d+)x(\d+) px, .*?\(current\)", result.stdout, flags=re.M)
            if match:
                return int(match.group(1)), int(match.group(2))
    return 1920, 1200


def load_palette():
    dark = THEME_ROOT / "com.system76.CosmicTheme.Dark"
    dark_builder = THEME_ROOT / "com.system76.CosmicTheme.Dark.Builder"
    palette = {
        "bg": parse_rgb(dark_builder / "v1" / "bg_color"),
        "accent": parse_rgb(dark_builder / "v1" / "accent"),
        "neutral_tint": parse_rgb(dark_builder / "v1" / "neutral_tint", fallback=(0.0, 1.0, 0.3)),
        "text_tint": parse_rgb(dark_builder / "v1" / "text_tint", fallback=(0.0, 1.0, 0.8)),
        "success": parse_rgb(dark / "v1" / "success", group="base", fallback=(0.57, 0.81, 0.61)),
        "warning": parse_rgb(dark / "v1" / "warning", group="base", fallback=(0.97, 0.88, 0.38)),
        "button": parse_rgb(dark / "v1" / "button", group="hover", fallback=(0.0, 0.47, 0.13)),
        "surface": parse_rgb(dark / "v1" / "primary", group="component", fallback=(0.02, 0.02, 0.02)),
        "surface_border": parse_rgb(dark / "v1" / "button", group="border", fallback=(0.0, 0.89, 0.26)),
        "mint": parse_rgb(dark / "v1" / "background", group="on", fallback=(0.0, 0.74, 0.59)),
    }
    return palette


def star_elements(width, height, seed, palette, variant):
    rng = random.Random(seed)
    stars = []
    dense_regions = {
        "event-horizon": (0.72 * width, 0.24 * height, 0.32 * width, 0.22 * height),
        "orbital-bloom": (0.78 * width, 0.52 * height, 0.24 * width, 0.34 * height),
        "aurora-veil": (0.22 * width, 0.22 * height, 0.45 * width, 0.24 * height),
    }
    cluster = dense_regions[variant]
    for _ in range(320):
        x = rng.random() * width
        y = rng.random() * height
        radius = 0.55 + rng.random() * 1.8
        opacity = 0.08 + rng.random() * 0.5
        if rng.random() < 0.24:
            x = min(width, max(0, rng.gauss(cluster[0], cluster[2])))
            y = min(height, max(0, rng.gauss(cluster[1], cluster[3])))
            radius = 0.75 + rng.random() * 2.8
            opacity = 0.22 + rng.random() * 0.6
        color = palette["warning"] if rng.random() < 0.06 else brighten(palette["text_tint"], rng.random() * 0.25)
        stars.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}" '
            f'fill="{rgb_to_rgba(color, opacity)}" '
            f'filter="url(#soft-glow-{variant})" opacity="{min(1.0, opacity + 0.1):.3f}" />'
        )
        if rng.random() < 0.065:
            flare = 12 + rng.random() * 28
            flare_opacity = 0.08 + rng.random() * 0.18
            stars.append(
                f'<g opacity="{flare_opacity:.3f}">'
                f'<line x1="{x - flare:.1f}" y1="{y:.1f}" x2="{x + flare:.1f}" y2="{y:.1f}" '
                f'stroke="{rgb_to_rgba(brighten(palette["text_tint"], 0.35), 0.9)}" stroke-width="1.2" />'
                f'<line x1="{x:.1f}" y1="{y - flare * 0.75:.1f}" x2="{x:.1f}" y2="{y + flare * 0.75:.1f}" '
                f'stroke="{rgb_to_rgba(brighten(palette["success"], 0.35), 0.8)}" stroke-width="1.1" />'
                f'</g>'
            )
    return "\n".join(stars)


def make_masks(width, height, variant):
    if variant == "event-horizon":
        return f"""
<mask id="nebula-mask-a-{variant}">
  <rect width="100%" height="100%" fill="black" />
  <ellipse cx="{0.78 * width:.1f}" cy="{0.34 * height:.1f}" rx="{0.26 * width:.1f}" ry="{0.19 * height:.1f}" fill="url(#mask-core-a-{variant})" />
  <ellipse cx="{0.56 * width:.1f}" cy="{0.22 * height:.1f}" rx="{0.20 * width:.1f}" ry="{0.14 * height:.1f}" fill="url(#mask-core-b-{variant})" />
</mask>
<mask id="nebula-mask-b-{variant}">
  <rect width="100%" height="100%" fill="black" />
  <ellipse cx="{0.32 * width:.1f}" cy="{0.62 * height:.1f}" rx="{0.24 * width:.1f}" ry="{0.17 * height:.1f}" fill="url(#mask-core-c-{variant})" />
</mask>
"""
    if variant == "orbital-bloom":
        return f"""
<mask id="nebula-mask-a-{variant}">
  <rect width="100%" height="100%" fill="black" />
  <ellipse cx="{0.78 * width:.1f}" cy="{0.56 * height:.1f}" rx="{0.28 * width:.1f}" ry="{0.22 * height:.1f}" fill="url(#mask-core-a-{variant})" />
  <ellipse cx="{0.66 * width:.1f}" cy="{0.76 * height:.1f}" rx="{0.18 * width:.1f}" ry="{0.18 * height:.1f}" fill="url(#mask-core-b-{variant})" />
</mask>
<mask id="nebula-mask-b-{variant}">
  <rect width="100%" height="100%" fill="black" />
  <ellipse cx="{0.28 * width:.1f}" cy="{0.18 * height:.1f}" rx="{0.24 * width:.1f}" ry="{0.12 * height:.1f}" fill="url(#mask-core-c-{variant})" />
</mask>
"""
    return f"""
<mask id="nebula-mask-a-{variant}">
  <rect width="100%" height="100%" fill="black" />
  <ellipse cx="{0.32 * width:.1f}" cy="{0.28 * height:.1f}" rx="{0.34 * width:.1f}" ry="{0.15 * height:.1f}" fill="url(#mask-core-a-{variant})" />
  <ellipse cx="{0.64 * width:.1f}" cy="{0.46 * height:.1f}" rx="{0.24 * width:.1f}" ry="{0.17 * height:.1f}" fill="url(#mask-core-b-{variant})" />
</mask>
<mask id="nebula-mask-b-{variant}">
  <rect width="100%" height="100%" fill="black" />
  <ellipse cx="{0.74 * width:.1f}" cy="{0.18 * height:.1f}" rx="{0.18 * width:.1f}" ry="{0.12 * height:.1f}" fill="url(#mask-core-c-{variant})" />
</mask>
"""


def gradients_and_filters(width, height, palette, variant, seed):
    deep_bg = darken(palette["bg"], 0.12)
    emerald = palette["surface_border"]
    mint = palette["mint"]
    acid = palette["neutral_tint"]
    cyan = palette["text_tint"]
    gold = palette["warning"]
    dim_emerald = darken(mix(palette["accent"], emerald, 0.65), 0.25)
    blur_heavy = height / 65
    blur_mid = height / 110
    return f"""
<defs>
  <radialGradient id="bg-radial-{variant}" cx="24%" cy="18%" r="92%">
    <stop offset="0%" stop-color="{rgb_to_hex(darken(mix(dim_emerald, mint, 0.08), 0.82))}" />
    <stop offset="40%" stop-color="{rgb_to_hex(darken(deep_bg, 0.08))}" />
    <stop offset="100%" stop-color="{rgb_to_hex(darken(palette["bg"], 0.0))}" />
  </radialGradient>
  <linearGradient id="nebula-grad-a-{variant}" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="{rgb_to_rgba(darken(dim_emerald, 0.2), 0.0)}" />
    <stop offset="24%" stop-color="{rgb_to_rgba(dim_emerald, 0.58)}" />
    <stop offset="55%" stop-color="{rgb_to_rgba(mix(emerald, mint, 0.45), 0.85)}" />
    <stop offset="100%" stop-color="{rgb_to_rgba(brighten(cyan, 0.12), 0.0)}" />
  </linearGradient>
  <linearGradient id="nebula-grad-b-{variant}" x1="100%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%" stop-color="{rgb_to_rgba(darken(acid, 0.18), 0.0)}" />
    <stop offset="35%" stop-color="{rgb_to_rgba(mix(acid, emerald, 0.4), 0.58)}" />
    <stop offset="70%" stop-color="{rgb_to_rgba(brighten(mint, 0.12), 0.46)}" />
    <stop offset="100%" stop-color="{rgb_to_rgba(brighten(gold, 0.08), 0.0)}" />
  </linearGradient>
  <linearGradient id="ribbon-grad-a-{variant}" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="{rgb_to_rgba(dim_emerald, 0.0)}" />
    <stop offset="30%" stop-color="{rgb_to_rgba(mix(emerald, acid, 0.3), 0.48)}" />
    <stop offset="58%" stop-color="{rgb_to_rgba(brighten(cyan, 0.08), 0.88)}" />
    <stop offset="100%" stop-color="{rgb_to_rgba(brighten(mint, 0.2), 0.0)}" />
  </linearGradient>
  <linearGradient id="ribbon-grad-b-{variant}" x1="0%" y1="100%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="{rgb_to_rgba(darken(emerald, 0.08), 0.0)}" />
    <stop offset="44%" stop-color="{rgb_to_rgba(brighten(acid, 0.1), 0.52)}" />
    <stop offset="72%" stop-color="{rgb_to_rgba(brighten(cyan, 0.18), 0.76)}" />
    <stop offset="100%" stop-color="{rgb_to_rgba(brighten(gold, 0.14), 0.0)}" />
  </linearGradient>
  <radialGradient id="planet-core-{variant}" cx="42%" cy="38%" r="76%">
    <stop offset="0%" stop-color="{rgb_to_hex(darken(mix(palette["surface"], dim_emerald, 0.08), 0.2))}" />
    <stop offset="62%" stop-color="{rgb_to_hex(darken(palette["surface"], 0.58))}" />
    <stop offset="100%" stop-color="{rgb_to_hex(darken(palette["bg"], 0.0))}" />
  </radialGradient>
  <linearGradient id="atmo-grad-{variant}" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="{rgb_to_rgba(brighten(cyan, 0.28), 0.92)}" />
    <stop offset="36%" stop-color="{rgb_to_rgba(brighten(emerald, 0.16), 0.74)}" />
    <stop offset="74%" stop-color="{rgb_to_rgba(brighten(gold, 0.08), 0.26)}" />
    <stop offset="100%" stop-color="{rgb_to_rgba(brighten(mint, 0.12), 0.0)}" />
  </linearGradient>
  <radialGradient id="mask-core-a-{variant}">
    <stop offset="0%" stop-color="white" stop-opacity="1" />
    <stop offset="72%" stop-color="white" stop-opacity="0.78" />
    <stop offset="100%" stop-color="white" stop-opacity="0" />
  </radialGradient>
  <radialGradient id="mask-core-b-{variant}">
    <stop offset="0%" stop-color="white" stop-opacity="0.95" />
    <stop offset="76%" stop-color="white" stop-opacity="0.62" />
    <stop offset="100%" stop-color="white" stop-opacity="0" />
  </radialGradient>
  <radialGradient id="mask-core-c-{variant}">
    <stop offset="0%" stop-color="white" stop-opacity="0.88" />
    <stop offset="84%" stop-color="white" stop-opacity="0.42" />
    <stop offset="100%" stop-color="white" stop-opacity="0" />
  </radialGradient>
  <filter id="nebula-warp-a-{variant}" x="-30%" y="-30%" width="160%" height="160%">
    <feTurbulence type="fractalNoise" baseFrequency="0.0012 0.0026" numOctaves="4" seed="{seed + 7}" result="noise" />
    <feDisplacementMap in="SourceGraphic" in2="noise" scale="{height * 0.095:.1f}" xChannelSelector="R" yChannelSelector="G" />
    <feGaussianBlur stdDeviation="{blur_heavy:.1f}" />
  </filter>
  <filter id="nebula-warp-b-{variant}" x="-30%" y="-30%" width="160%" height="160%">
    <feTurbulence type="turbulence" baseFrequency="0.0028 0.0062" numOctaves="3" seed="{seed + 31}" result="noise" />
    <feDisplacementMap in="SourceGraphic" in2="noise" scale="{height * 0.052:.1f}" xChannelSelector="G" yChannelSelector="B" />
    <feGaussianBlur stdDeviation="{blur_mid:.1f}" />
  </filter>
  <filter id="ribbon-glow-{variant}" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="{height / 52:.1f}" result="blur" />
    <feMerge>
      <feMergeNode in="blur" />
      <feMergeNode in="SourceGraphic" />
    </feMerge>
  </filter>
  <filter id="soft-glow-{variant}" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="{height / 240:.1f}" result="blur" />
    <feMerge>
      <feMergeNode in="blur" />
      <feMergeNode in="SourceGraphic" />
    </feMerge>
  </filter>
  <filter id="star-bloom-{variant}" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="{height / 140:.1f}" result="glow" />
    <feMerge>
      <feMergeNode in="glow" />
      <feMergeNode in="SourceGraphic" />
    </feMerge>
  </filter>
  <filter id="grain-{variant}" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="{seed + 101}" result="noise" />
    <feColorMatrix in="noise" type="saturate" values="0" />
    <feComponentTransfer>
      <feFuncA type="table" tableValues="0 0.03" />
    </feComponentTransfer>
  </filter>
  {make_masks(width, height, variant)}
</defs>
"""


def event_horizon(width, height, palette):
    planet_x = -0.12 * width
    planet_y = 1.10 * height
    planet_r = 0.54 * height
    return f"""
<rect width="100%" height="100%" fill="url(#bg-radial-event-horizon)" />
<rect width="100%" height="100%" fill="{rgb_to_rgba(palette["bg"], 0.72)}" />
<rect width="100%" height="100%" fill="url(#nebula-grad-a-event-horizon)" mask="url(#nebula-mask-a-event-horizon)" filter="url(#nebula-warp-a-event-horizon)" opacity="0.95" />
<rect width="100%" height="100%" fill="url(#nebula-grad-b-event-horizon)" mask="url(#nebula-mask-b-event-horizon)" filter="url(#nebula-warp-b-event-horizon)" opacity="0.58" />
<g filter="url(#ribbon-glow-event-horizon)">
  <path d="M {-0.08 * width:.1f} {0.78 * height:.1f} C {0.20 * width:.1f} {0.56 * height:.1f}, {0.46 * width:.1f} {0.42 * height:.1f}, {0.76 * width:.1f} {0.48 * height:.1f} S {1.06 * width:.1f} {0.70 * height:.1f}, {1.10 * width:.1f} {0.40 * height:.1f}" fill="none" stroke="url(#ribbon-grad-a-event-horizon)" stroke-width="{0.12 * height:.1f}" stroke-linecap="round" opacity="0.44" />
  <path d="M {-0.06 * width:.1f} {0.84 * height:.1f} C {0.12 * width:.1f} {0.62 * height:.1f}, {0.36 * width:.1f} {0.44 * height:.1f}, {0.62 * width:.1f} {0.45 * height:.1f} S {0.90 * width:.1f} {0.58 * height:.1f}, {1.02 * width:.1f} {0.34 * height:.1f}" fill="none" stroke="url(#ribbon-grad-b-event-horizon)" stroke-width="{0.052 * height:.1f}" stroke-linecap="round" opacity="0.82" />
</g>
<g opacity="0.32">
  <ellipse cx="{0.88 * width:.1f}" cy="{0.26 * height:.1f}" rx="{0.22 * width:.1f}" ry="{0.11 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["text_tint"], 0.2), 0.6)}" stroke-width="{height / 500:.2f}" />
  <ellipse cx="{0.88 * width:.1f}" cy="{0.26 * height:.1f}" rx="{0.27 * width:.1f}" ry="{0.14 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["surface_border"], 0.1), 0.4)}" stroke-width="{height / 740:.2f}" />
</g>
<g opacity="0.98">
  <circle cx="{planet_x:.1f}" cy="{planet_y:.1f}" r="{planet_r:.1f}" fill="url(#planet-core-event-horizon)" />
  <circle cx="{planet_x:.1f}" cy="{planet_y:.1f}" r="{planet_r * 1.006:.1f}" fill="none" stroke="url(#atmo-grad-event-horizon)" stroke-width="{height / 52:.1f}" filter="url(#soft-glow-event-horizon)" opacity="0.86" />
  <circle cx="{planet_x + planet_r * 0.16:.1f}" cy="{planet_y - planet_r * 0.21:.1f}" r="{planet_r * 0.90:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["mint"], 0.2), 0.16)}" stroke-width="{height / 300:.1f}" opacity="0.34" />
</g>
"""


def orbital_bloom(width, height, palette):
    moon_x = 0.84 * width
    moon_y = 0.64 * height
    moon_r = 0.18 * height
    return f"""
<rect width="100%" height="100%" fill="url(#bg-radial-orbital-bloom)" />
<rect width="100%" height="100%" fill="{rgb_to_rgba(palette["bg"], 0.64)}" />
<rect width="100%" height="100%" fill="url(#nebula-grad-a-orbital-bloom)" mask="url(#nebula-mask-a-orbital-bloom)" filter="url(#nebula-warp-a-orbital-bloom)" opacity="0.92" />
<rect width="100%" height="100%" fill="url(#nebula-grad-b-orbital-bloom)" mask="url(#nebula-mask-b-orbital-bloom)" filter="url(#nebula-warp-b-orbital-bloom)" opacity="0.46" />
<g filter="url(#ribbon-glow-orbital-bloom)">
  <path d="M {0.32 * width:.1f} {-0.10 * height:.1f} C {0.52 * width:.1f} {0.20 * height:.1f}, {0.72 * width:.1f} {0.36 * height:.1f}, {0.88 * width:.1f} {0.54 * height:.1f} S {1.06 * width:.1f} {0.96 * height:.1f}, {0.88 * width:.1f} {1.08 * height:.1f}" fill="none" stroke="url(#ribbon-grad-a-orbital-bloom)" stroke-width="{0.10 * height:.1f}" stroke-linecap="round" opacity="0.40" />
  <path d="M {0.28 * width:.1f} {-0.06 * height:.1f} C {0.52 * width:.1f} {0.16 * height:.1f}, {0.74 * width:.1f} {0.34 * height:.1f}, {0.90 * width:.1f} {0.52 * height:.1f} S {1.04 * width:.1f} {0.88 * height:.1f}, {0.94 * width:.1f} {1.04 * height:.1f}" fill="none" stroke="url(#ribbon-grad-b-orbital-bloom)" stroke-width="{0.040 * height:.1f}" stroke-linecap="round" opacity="0.82" />
</g>
<g opacity="0.58" filter="url(#soft-glow-orbital-bloom)">
  <ellipse cx="{0.86 * width:.1f}" cy="{0.64 * height:.1f}" rx="{0.28 * width:.1f}" ry="{0.17 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["text_tint"], 0.15), 0.55)}" stroke-width="{height / 420:.1f}" />
  <ellipse cx="{0.86 * width:.1f}" cy="{0.64 * height:.1f}" rx="{0.37 * width:.1f}" ry="{0.22 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["surface_border"], 0.14), 0.34)}" stroke-width="{height / 680:.1f}" />
</g>
<g opacity="0.96">
  <circle cx="{moon_x:.1f}" cy="{moon_y:.1f}" r="{moon_r:.1f}" fill="url(#planet-core-orbital-bloom)" />
  <circle cx="{moon_x:.1f}" cy="{moon_y:.1f}" r="{moon_r * 1.014:.1f}" fill="none" stroke="url(#atmo-grad-orbital-bloom)" stroke-width="{height / 82:.1f}" filter="url(#star-bloom-orbital-bloom)" opacity="0.88" />
</g>
"""


def aurora_veil(width, height, palette):
    return f"""
<rect width="100%" height="100%" fill="url(#bg-radial-aurora-veil)" />
<rect width="100%" height="100%" fill="{rgb_to_rgba(palette["bg"], 0.70)}" />
<rect width="100%" height="100%" fill="url(#nebula-grad-a-aurora-veil)" mask="url(#nebula-mask-a-aurora-veil)" filter="url(#nebula-warp-a-aurora-veil)" opacity="0.98" />
<rect width="100%" height="100%" fill="url(#nebula-grad-b-aurora-veil)" mask="url(#nebula-mask-b-aurora-veil)" filter="url(#nebula-warp-b-aurora-veil)" opacity="0.50" />
<g filter="url(#ribbon-glow-aurora-veil)">
  <path d="M {-0.10 * width:.1f} {0.72 * height:.1f} C {0.14 * width:.1f} {0.48 * height:.1f}, {0.32 * width:.1f} {0.26 * height:.1f}, {0.54 * width:.1f} {0.24 * height:.1f} S {0.88 * width:.1f} {0.52 * height:.1f}, {1.08 * width:.1f} {0.36 * height:.1f}" fill="none" stroke="url(#ribbon-grad-a-aurora-veil)" stroke-width="{0.14 * height:.1f}" stroke-linecap="round" opacity="0.42" />
  <path d="M {-0.08 * width:.1f} {0.80 * height:.1f} C {0.16 * width:.1f} {0.54 * height:.1f}, {0.36 * width:.1f} {0.34 * height:.1f}, {0.58 * width:.1f} {0.34 * height:.1f} S {0.86 * width:.1f} {0.58 * height:.1f}, {1.04 * width:.1f} {0.44 * height:.1f}" fill="none" stroke="url(#ribbon-grad-b-aurora-veil)" stroke-width="{0.050 * height:.1f}" stroke-linecap="round" opacity="0.84" />
  <path d="M {0.06 * width:.1f} {1.02 * height:.1f} C {0.18 * width:.1f} {0.76 * height:.1f}, {0.30 * width:.1f} {0.62 * height:.1f}, {0.42 * width:.1f} {0.60 * height:.1f} S {0.76 * width:.1f} {0.86 * height:.1f}, {0.98 * width:.1f} {0.82 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["warning"], 0.08), 0.14)}" stroke-width="{0.024 * height:.1f}" stroke-linecap="round" opacity="0.42" />
</g>
<g opacity="0.28">
  <ellipse cx="{0.18 * width:.1f}" cy="{0.18 * height:.1f}" rx="{0.22 * width:.1f}" ry="{0.09 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["text_tint"], 0.18), 0.52)}" stroke-width="{height / 520:.2f}" />
  <ellipse cx="{0.18 * width:.1f}" cy="{0.18 * height:.1f}" rx="{0.29 * width:.1f}" ry="{0.12 * height:.1f}" fill="none" stroke="{rgb_to_rgba(brighten(palette["surface_border"], 0.08), 0.30)}" stroke-width="{height / 760:.2f}" />
</g>
"""


VARIANT_BUILDERS = {
    "event-horizon": event_horizon,
    "orbital-bloom": orbital_bloom,
    "aurora-veil": aurora_veil,
}


def build_svg(width, height, palette, variant, seed):
    defs = gradients_and_filters(width, height, palette, variant, seed)
    body = VARIANT_BUILDERS[variant](width, height, palette)
    stars = star_elements(width, height, seed + 211, palette, variant)
    grain = f'<rect width="100%" height="100%" fill="white" filter="url(#grain-{variant})" opacity="0.20" />'
    vignette_color = rgb_to_rgba((0.0, 0.0, 0.0), 0.72)
    vignette = (
        f'<radialGradient id="vignette-{variant}" cx="50%" cy="48%" r="78%">'
        f'<stop offset="58%" stop-color="{rgb_to_rgba((0, 0, 0), 0.0)}" />'
        f'<stop offset="100%" stop-color="{vignette_color}" /></radialGradient>'
        f'<rect width="100%" height="100%" fill="url(#vignette-{variant})" />'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
{defs}
{body}
<g filter="url(#star-bloom-{variant})">
{stars}
</g>
{grain}
{vignette}
</svg>
"""


def rasterize(svg_path: Path, png_path: Path, jpg_path: Path):
    subprocess.run(["magick", str(svg_path), str(png_path)], check=True)
    subprocess.run(
        [
            "magick",
            str(png_path),
            "-sampling-factor",
            "4:4:4",
            "-quality",
            "96",
            str(jpg_path),
        ],
        check=True,
    )


def make_contact_sheet(previews, output):
    subprocess.run(
        [
            "magick",
            *[str(path) for path in previews],
            "-set",
            "label",
            "%t",
            "-background",
            "#000000",
            "-fill",
            "#d8f8ea",
            "-pointsize",
            "28",
            "-label",
            "%t",
            "-resize",
            "1200x750",
            "+append",
            str(output),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate wallpapers from the local COSMIC dark palette.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260323)
    args = parser.parse_args()

    display_width, display_height = parse_current_mode()
    master_width = display_width * 2
    master_height = display_height * 2
    palette = load_palette()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    preview_paths = []

    for index, variant in enumerate(VARIANT_BUILDERS):
        variant_seed = args.seed + index * 97
        svg = build_svg(master_width, master_height, palette, variant, variant_seed)
        stem = f"{variant}-{master_width}x{master_height}"
        svg_path = args.output_dir / f"{stem}.svg"
        png_path = args.output_dir / f"{stem}.png"
        jpg_path = args.output_dir / f"{stem}.jpg"
        preview_path = args.output_dir / f"{stem}-preview.png"
        native_path = args.output_dir / f"{variant}-{display_width}x{display_height}.png"
        svg_path.write_text(svg, encoding="utf-8")
        rasterize(svg_path, png_path, jpg_path)
        subprocess.run(["magick", str(png_path), "-resize", "1600x1000", str(preview_path)], check=True)
        subprocess.run(["magick", str(png_path), "-resize", f"{display_width}x{display_height}", str(native_path)], check=True)
        preview_paths.append(preview_path)

    contact_sheet = args.output_dir / "contact-sheet.png"
    make_contact_sheet(preview_paths, contact_sheet)

    palette_report = args.output_dir / "palette.txt"
    palette_report.write_text(
        "\n".join(f"{key}: {rgb_to_hex(value)}" for key, value in palette.items()) + "\n",
        encoding="utf-8",
    )

    print(f"display={display_width}x{display_height}")
    print(f"master={master_width}x{master_height}")
    print(f"output_dir={args.output_dir}")
    print(f"contact_sheet={contact_sheet}")


if __name__ == "__main__":
    main()
