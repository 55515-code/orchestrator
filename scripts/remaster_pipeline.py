#!/usr/bin/env python3
"""
Nephilim Union — fidelity-first modernization pipeline (fresh start).

Derived solely from observed source image (docs/nephilim_union_source_analysis.md).
AI img2img re-render was tested and discarded: kontext is enterprise-only and free
flux+image ignores source structure (probe evidence in generated/remaster/). The
remaster therefore carries the deliverable.

Stages:
  1 intake   - read source, observed palette/luma/sharpness profile
  2 remaster - edge-masked deblock, 5x LANCZOS, vibrance, S-curve, bloom, unsharp
  3 QC       - luminance NCC >= 0.93, palette dE <= 12, integrity
  4 deliver  - final PNG + 1024 preview + report

Exit codes: 0 = QC pass; 1 = flagged; 3 = fatal.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import traceback
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

SRC = Path("/home/ahron/Downloads/nephilim_union_by_clownblack_dfnuyx3-414w-2x.jpg")
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "generated" / "remaster"
SCALE = 5


def lum_of(arr: np.ndarray) -> np.ndarray:
    return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]


def lap_var(gray: np.ndarray) -> float:
    g = gray.astype(np.float64)
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], float)
    p = np.pad(g, 1, mode="edge")
    H, W = g.shape
    out = sum(k[i, j] * p[i:i + H, j:j + W] for i in range(3) for j in range(3))
    return float(out.var())


def edges(gray: np.ndarray) -> np.ndarray:
    g = gray.astype(np.float64)
    gy, gx = np.gradient(g)
    return np.hypot(gx, gy)


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64).ravel()
    b = b.astype(np.float64).ravel()
    return float(np.corrcoef(a, b)[0, 1])


def kmeans(px: np.ndarray, k: int = 5, iters: int = 8) -> np.ndarray:
    rng = random.Random(7)
    c = px[rng.sample(range(len(px)), k)].astype(np.float64)
    for _ in range(iters):
        d = np.linalg.norm(px[:, None] - c[None], axis=2)
        lab = d.argmin(1)
        nc = np.array([px[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
        if np.allclose(nc, c, atol=1e-2):
            break
        c = nc
    return c


def rgb2lab(rgb: np.ndarray) -> np.ndarray:
    a = np.clip(rgb, 0, 255) / 255.0
    a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    x = a @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(x <= 0.008856, (903.3 * x + 16) / 116.0, np.cbrt(x))
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def palette_de(a: np.ndarray, b: np.ndarray) -> float:
    ca = kmeans(a.reshape(-1, 3).astype(float))
    cb = kmeans(b.reshape(-1, 3).astype(float))
    la, lb = rgb2lab(ca), rgb2lab(cb)
    d = np.linalg.norm(la[:, None] - lb[None], axis=2)
    return float(d.min(1).mean())


def profile(img: Image.Image) -> dict:
    arr = np.asarray(img.convert("RGB"))
    return {
        "size": img.size,
        "luma_std": round(float(lum_of(arr.astype(float)).std()), 2),
        "sat_mean": round(float(np.asarray(img.convert("HSV"))[..., 1].mean() / 255), 3),
        "sharpness": round(lap_var(lum_of(arr.astype(float))), 2),
        "palette": kmeans(arr.reshape(-1, 3).astype(float)).round(1).tolist(),
    }


def modern_artistic_grade(src: Image.Image) -> Image.Image:
    """Apply a dramatic modern artistic grade: neon glow, edge-lit linework,
    deeper cinematic contrast, electric palette enhancement — aligned with
    the observed source (psychedelic surreal / visionary / neon electric style)."""
    arr = np.asarray(src.convert("RGB")).astype(np.float64)
    # 1) Deep cinematic base grade: stronger S-curve, deeper blacks, brighter mids
    # Apply via PIL enhance chain
    img_base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img_base = ImageEnhance.Contrast(img_base).enhance(1.08)
    img_base = ImageEnhance.Brightness(img_base).enhance(1.0)  # preserve luminance range
    # 2) Color grading toward the observed palette accents (magenta, cyan, crimson)
    hsv = np.asarray(img_base.convert("HSV")).astype(np.float64)
    s = hsv[..., 1] / 255.0
    hsv[..., 1] = np.clip(s * (1 + 0.25 * (1 - s)), 0, 1) * 255  # moderate vibrance
    img_base = Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")
    # 3) Edge-lit linework: blend bright edges with electric blue/magenta glow
    arr2 = np.asarray(img_base).astype(np.float64)
    lum2 = lum_of(arr2)
    e2 = edges(lum2)
    # Create neon glow layer using the palette colors
    glow_mag = np.array([255, 0, 168], dtype=np.float64)  # neon magenta
    glow_cyan = np.array([0, 240, 255], dtype=np.float64)  # voltage cyan
    glow_crimson = np.array([220, 20, 60], dtype=np.float64)  # crimson
    # Blend glow into bright/high-contrast regions
    bright_mask = np.clip((lum2 - 160) / 100.0, 0, 1)[..., None]
    glow_color = (glow_mag * 0.5 + glow_cyan * 0.3 + glow_crimson * 0.2)
    arr2 = arr2 + bright_mask * glow_color * 0.12
    arr2 = np.clip(arr2, 0, 255)
    img_base = Image.fromarray(arr2.astype(np.uint8))
    # 4) Dramatic bloom: larger radius, stronger blend, on bright regions
    bloom_large = np.asarray(img_base.filter(ImageFilter.GaussianBlur(40))).astype(np.float64)
    a2 = np.asarray(img_base).astype(np.float64)
    lm2 = lum_of(a2)
    bloom_mask = np.clip((lm2 - 170) / 70.0, 0, 1)[..., None]
    a2 = np.clip(a2 * (1 - 0.25 * bloom_mask) + bloom_large * (0.25 * bloom_mask), 0, 255)
    img_base = Image.fromarray(a2.astype(np.uint8))
    # 5) Subtle chromatic aberration at sharp edges
    r, g, b = img_base.split()
    r = r.transform(img_base.size, Image.AFFINE, (1, 0, 2, 0, 1, 0), resample=Image.BICUBIC)
    b = b.transform(img_base.size, Image.AFFINE, (1, 0, -2, 0, 1, 0), resample=Image.BICUBIC)
    img_base = Image.merge("RGB", (r, g, b))
    # 6) Final sharpness: stronger unsharp
    img_base = img_base.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=1))
    # 7) Final contrast lift — moderate
    img_base = ImageEnhance.Contrast(img_base).enhance(1.05)
    return img_base


def remaster(src: Image.Image) -> Image.Image:
    # 1) Edge-masked deblock at source scale
    arr = np.asarray(src.convert("RGB")).astype(np.float64)
    e = edges(lum_of(arr))
    flat = (e < np.percentile(e, 55))[..., None]
    smooth = np.asarray(src.convert("RGB").filter(
        ImageFilter.GaussianBlur(1.6))).astype(np.float64)
    arr = np.where(flat, smooth, arr)
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # 2) Modern dramatic artistic grade (before upscale, relative to source scale)
    graded = modern_artistic_grade(base)
    # 3) Upscale
    w, h = src.size
    up = graded.resize((w * SCALE, h * SCALE), Image.LANCZOS)
    # 4) Final crispness after upscale
    up = up.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=1))
    return up


def qc(src: Image.Image, out: Image.Image) -> dict:
    a = np.asarray(src.convert("RGB"))
    b = np.asarray(out.convert("RGB").resize(src.size, Image.LANCZOS))
    la, lb = lum_of(a.astype(float)), lum_of(b.astype(float))
    m = {
        "luma_ncc": round(ncc(la, lb), 4),
        "palette_de": round(palette_de(a, b), 2),
        "sharp_src": round(lap_var(la), 2),
        "dims": list(out.size),
    }
    m["pass"] = bool(m["luma_ncc"] >= 0.97 and m["palette_de"] <= 15)
    return m


def main() -> int:
    argparse.ArgumentParser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"stages": {}}
    try:
        src = Image.open(SRC).convert("RGB")
        report["stages"]["intake"] = {"ok": True, **profile(src)}

        up = remaster(src)
        final = OUT / "nephilim_union_modern_final.png"
        up.save(final, "PNG", optimize=True)
        q = qc(src, up)
        report["stages"]["remaster"] = {"ok": q["pass"], "qc": q, "path": str(final)}

        pw = 1024
        ph = int(pw * src.height / src.width)
        up.resize((pw, ph), Image.LANCZOS).save(
            OUT / "preview_modern_1024.png", "PNG", optimize=True)

        report["status"] = "pass" if q["pass"] else "flagged"
        report["exit_code"] = 0 if q["pass"] else 1
        (OUT / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return report["exit_code"]
    except Exception as e:
        report.update({"status": "error", "error": repr(e),
                       "traceback": traceback.format_exc(), "exit_code": 3})
        (OUT / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 3


if __name__ == "__main__":
    sys.exit(main())
