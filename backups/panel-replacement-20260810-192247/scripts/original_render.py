#!/usr/bin/env python3
"""
Fully original text-to-image render inspired by Nephilim Union themes,
reimagined in current electric/cyberpunk-gnosis style.

Uses Stable Diffusion 1.5 text-to-image (no source image input).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description="Original text-to-image render")
    p.add_argument("--prompt", required=True, help="text-to-image prompt")
    p.add_argument("--negative", default="blurry, low quality, distorted, deformed, ugly, duplicate, mutation, mutation, bad anatomy, bad proportions, extra limbs, cloned face, disfigured, malformed, mutated, unclear, artistic error, signature, watermark, text, username")
    p.add_argument("--output", default=str(REPO / "generated" / "remaster" / "original_render.png"))
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--guidance", type=float, default=7.5)
    p.add_argument("--width", type=int, default=768)
    p.add_argument("--height", type=int, default=1024)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--num-images", type=int, default=1)
    args = p.parse_args()

    try:
        import torch
        from diffusers import StableDiffusionPipeline
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: uv run --with torch --with diffusers --with transformers --with accelerate")
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Loading Stable Diffusion 1.5 (text-to-image)...")
    pipe = StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
        safety_checker=None,
        requires_safety_checker=False,
    ).to("cuda")
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()

    print(f"Generating with prompt: {args.prompt[:100]}...")
    generator = torch.Generator("cuda").manual_seed(args.seed)
    images = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        width=args.width,
        height=args.height,
        num_images_per_prompt=args.num_images,
        generator=generator,
    ).images
    for i, result in enumerate(images):
        if len(images) == 1:
            out_path = out
        else:
            out_path = out.parent / f"{out.stem}_{i}{out.suffix}"
        result.save(str(out_path))
        print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
