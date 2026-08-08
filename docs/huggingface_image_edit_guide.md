# Hugging Face Image-to-Image — Tooling Awareness

The substrate is aware of HF image-to-image services for ChatGPT-style image editing.

## Two paths

### 1. Remote: HF InferenceClient (requires `HF_TOKEN`)

```python
from huggingface_hub import InferenceClient
client = InferenceClient(provider="fal-ai", api_key=os.environ["HF_TOKEN"])
edited = client.image_to_image(
    open("src.jpg","rb"),
    prompt="Turn the cat into a tiger.",
    model="black-forest-labs/FLUX.2-klein-9B",
)
```

Providers: `fal-ai` (fastest), `replicate`, `auto`.

### 2. Local: `diffusers` pipeline (no token needed, uses GPU)

```python
from diffusers import StableDiffusionInstructPix2PixPipeline
import torch
pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(
    "timbrooks/instruct-pix2pix",
    torch_dtype=torch.float16, safety_checker=None, requires_safety_checker=False,
).to("cuda")
result = pipe(prompt="...", image=src, image_guidance_scale=2.0).images[0]
```

`instruct-pix2pix` is purpose-built for natural-language image editing — the same UX as
ChatGPT's "upload an image + describe the edit."

## CLI wrappers in this repo

| Script | Path |
|---|---|
| Remote HF edit | `scripts/chat_image_edit.py` |
| Local diffusers edit | `scripts/chat_image_edit_local.py` |

Both accept `--source`, `--prompt`, `--output`.

## Authentication

```
export HF_TOKEN="hf_****"   # https://huggingface.co/settings/tokens/new
```

Without the token, the remote script reports the exact command to run after setting it.

## References
- https://huggingface.co/docs/inference-providers/tasks/image-to-image
- https://huggingface.co/docs/inference-providers/guides/image-editor
- https://huggingface.co/timbrooks/instruct-pix2pix
