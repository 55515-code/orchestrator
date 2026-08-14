#!/usr/bin/env python3
"""
ChatGPT-chat-style image editing — local run via HF diffusers (instruct-pix2pix).

No API token needed: the model runs on the local NVIDIA GPU.

Usage:
  uv run --with torch --with diffusers --with transformers --with accelerate \
    python scripts/chat_image_edit_local.py \
      --source /home/ahron/Downloads/nephilim_union_by_clownblack_dfnuyx3-414w-2x.jpg \
      --prompt "..." \
      --output generated/remaster/ai_local_edit.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description="Local ChatGPT-style image edit (instruct-pix2pix)")
    p.add_argument("--source", required=True, help="input image path")
    p.add_argument("--prompt", required=True, help="natural-language edit instruction")
    p.add_argument("--output", default=str(REPO / "generated" / "remaster" / "ai_local_edit.png"))
    p.add_argument("--image-guidance", type=float, default=2.0,
                   help="higher = keep closer to source structure (default 2.0)")
    p.add_argument("--text-guidance", type=float, default=7.5)
    p.add_argument("--steps", type=int, default=30)
    args = p.parse_args()

    try:
        import torch
        from diffusers import StableDiffusionInstructPix2PixPipeline
        from PIL import Image
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: uv run --with torch --with diffusers --with transformers --with accelerate")
        return 2

    src = Path(args.source)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Loading instruct-pix2pix (first run downloads ~5GB from HF hub)...")
    pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(
        "timbrooks/instruct-pix2pix",
        torch_dtype=torch.float16,
        safety_checker=None,
        requires_safety_checker=False,
    ).to("cuda")
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()

    image = Image.open(src).convert("RGB")
    # instruct-pix2pix expects ~512-1024px input; keep aspect, cap longest side
    longest = max(image.size)
    if longest > 1024:
        scale = 1024 / longest
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)

    print(f"Editing with prompt: {args.prompt!r}")
    result = pipe(
        prompt=args.prompt,
        image=image,
        num_inference_steps=args.steps,
        guidance_scale=args.text_guidance,
        image_guidance_scale=args.image_guidance,
        negative_prompt="blurry, low quality, distorted anatomy",
    ).images[0]
    result.save(str(out))
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
