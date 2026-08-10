#!/usr/bin/env python3
"""
Fully original text-to-image render using SDXL for better prompt fidelity and composition.
Runs on RTX A2000 8GB with model CPU offload.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description="Original render via SDXL")
    p.add_argument("--prompt", required=True)
    p.add_argument("--negative", default="blurry, low quality, distorted, watermark, signature, text, deformed, duplicate, ugly, mutation, extra limbs, bad anatomy, cloned face, disfigured, out of frame")
    p.add_argument("--output", default=str(REPO / "generated" / "remaster" / "original_render_xl.png"))
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--guidance", type=float, default=7.5)
    p.add_argument("--width", type=int, default=832)
    p.add_argument("--height", type=int, default=1216)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--num-images", type=int, default=1)
    args = p.parse_args()

    try:
        import torch
        from diffusers import StableDiffusionXLPipeline
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: uv run --with torch --with diffusers --with transformers --with accelerate")
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Loading SDXL base...")
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )
    pipe.enable_model_cpu_offload()
    pipe.enable_vae_slicing()
    pipe.enable_vae_tiling()

    print(f"Generating with prompt: {args.prompt[:120]}...")
    generator = torch.Generator(device="cuda").manual_seed(args.seed)
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
