#!/usr/bin/env python3
"""
ChatGPT-style image modification via Hugging Face InferenceClient.

Usage:
  export HF_TOKEN="hf_***"
  uv run --with huggingface_hub python scripts/chat_image_edit.py \
    --source /home/ahron/Downloads/nephilim_union_by_clownblack_dfnuyx3-414w-2x.jpg \
    --prompt "Modern surreal digital art, same two-fused-face composition, red zipper, indigo visor eye, magenta star crown, teal hair, wavy contour lines, neon gradients, 4k" \
    --model black-forest-labs/FLUX.2-klein-9B --provider fal-ai
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description="HF image-to-image edit")
    p.add_argument("--source", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--model", default="black-forest-labs/FLUX.2-klein-9B")
    p.add_argument("--provider", default="fal-ai", choices=["fal-ai", "replicate", "auto"])
    p.add_argument("--output", default=str(REPO_ROOT / "generated" / "remaster" / "ai_chat_edit.png"))
    args = p.parse_args()

    if not os.environ.get("HF_TOKEN"):
        print("ERROR: HF_TOKEN not set.")
        print("Set with: export HF_TOKEN=\"hf_***\"")
        print("Generate token: https://huggingface.co/settings/tokens/new")
        print("Usage after export:")
        print(f"  uv run --with huggingface_hub python {__file__} --source {args.source} --prompt \"...\"")
        return 2

    try:
        from huggingface_hub import InferenceClient  # noqa: E402
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: uv pip install huggingface_hub")
        return 2

    client = InferenceClient(provider=args.provider, api_key=os.environ["HF_TOKEN"])
    src = Path(args.source)
    try:
        image = client.image_to_image(
            open(src, "rb"),
            prompt=args.prompt,
            model=args.model,
        )
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(out), optimize=True)
        print(f"Saved edited image: {out}")
        return 0
    except Exception as e:
        print(f"ERROR during image edit: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
