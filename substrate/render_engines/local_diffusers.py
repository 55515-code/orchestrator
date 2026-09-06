"""Local diffusers engine implementations for the render router."""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any, cast

from .base import (
    RenderEngine,
    RenderFailed,
    RenderRequest,
    RenderResult,
    RenderUnavailable,
    apply_memory_strategy,
    detect_gpu,
    ensure_scratch_env,
    resize_for_engine,
    unavailable,
    write_images,
)


class LocalDiffusersEngine(RenderEngine):
    """Concrete base shared by all local diffusers engines."""

    model_id: str = ""
    default_steps: int = 30
    default_guidance: float = 7.5
    memory_strategy_default: str = "model_cpu_offload"
    model_size_gb: float = 5.0
    pipeline_cls_dotted: str = "diffusers:StableDiffusionPipeline"
    needs_safetensors: bool = False
    variant: str | None = None
    supports_negative_prompt: bool = True
    extra_pipeline_kwargs: dict[str, Any] = {}

    def _load_pipeline(self) -> Any:
        module_path, _, attribute = self.pipeline_cls_dotted.partition(":")
        if not module_path or not attribute:
            raise unavailable(self.spec.id, f"bad pipeline_cls_dotted '{self.pipeline_cls_dotted}'")
        try:
            module = importlib.import_module(module_path)
            pipe_cls = getattr(module, attribute)
        except (ImportError, AttributeError) as exc:
            raise unavailable(self.spec.id, f"cannot import pipeline {self.pipeline_cls_dotted}: {exc}") from exc

        import torch

        kwargs: dict[str, Any] = {
            "torch_dtype": torch.float16,
            "use_safetensors": self.needs_safetensors,
            **self.extra_pipeline_kwargs,
        }
        if self.variant:
            kwargs["variant"] = self.variant

        return pipe_cls.from_pretrained(self.spec.model_id, **kwargs)

    def _call_pipe(
        self,
        pipe: Any,
        request: RenderRequest,
        generator: Any,
        source_image: Any,
        steps: int,
        guidance: float,
    ) -> list[Any]:
        raise NotImplementedError

    def render(self, request: RenderRequest) -> RenderResult:
        ensure_scratch_env(Path.cwd())
        gpu = detect_gpu()
        self.require_available(gpu=gpu)

        try:
            import torch
        except ImportError as exc:
            raise unavailable(self.spec.id, f"missing torch: {exc}") from exc

        steps = request.steps or self.default_steps
        guidance = request.guidance if request.guidance is not None else self.default_guidance

        try:
            pipe = self._load_pipeline()
        except RenderUnavailable:
            raise
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: pipeline load failed: {exc}") from exc

        strategy = request.extra.get("memory_strategy") or self.spec.memory_strategy or self.memory_strategy_default
        apply_memory_strategy(pipe, strategy)

        generator = None
        if request.seed is not None:
            generator = cast(Any, torch.Generator)(device="cuda").manual_seed(request.seed)

        source_image = None
        if request.mode in {"image_to_image", "edit", "inpaint", "upscale"} and request.source_image:
            try:
                from PIL import Image
                source_image = Image.open(request.source_image).convert("RGB")
                source_image = resize_for_engine(source_image, self.spec.max_pixels)
            except Exception as exc:
                raise RenderFailed(f"{self.spec.id}: cannot load source image: {exc}") from exc

        t0 = time.monotonic()
        try:
            images = self._call_pipe(pipe, request, generator, source_image, steps, guidance)
        except RenderUnavailable:
            raise
        except RenderFailed:
            raise
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: generation failed: {exc}") from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        try:
            output = request.output or (Path("generated") / "renders" / f"{self.spec.id}_output.png")
            paths = write_images(images, output)
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: write_images failed: {exc}") from exc

        return RenderResult(
            engine_id=self.spec.id,
            model_id=self.spec.model_id,
            status="success",
            images=paths,
            latency_ms=latency_ms,
            cost_usd=self.spec.cost_per_image_usd * request.num_images,
            metadata={"steps": steps, "guidance": guidance, "seed": request.seed, "strategy": strategy},
        )


class Flux2KleinEngine(LocalDiffusersEngine):
    """FLUX.2-klein-4B distilled — 4 steps, guidance 1.0, modern look."""

    model_id = "black-forest-labs/FLUX.2-klein-4B"
    default_steps = 4
    default_guidance = 1.0
    model_size_gb = 4.0
    memory_strategy_default = "model_cpu_offload"
    pipeline_cls_dotted = "diffusers:FluxPipeline"
    supports_negative_prompt = False
    extra_pipeline_kwargs = {"max_sequence_length": 256}

    def _call_pipe(self, pipe, request, generator, source_image, steps, guidance):
        kwargs: dict[str, Any] = {
            "prompt": request.prompt,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "num_images_per_prompt": request.num_images,
            "height": request.height,
            "width": request.width,
        }
        if generator is not None:
            kwargs["generator"] = generator
        if source_image is not None:
            kwargs["image"] = source_image
            kwargs["strength"] = request.extra.get("strength", 0.5)
        if self.supports_negative_prompt and request.negative:
            kwargs["negative_prompt"] = request.negative
        return pipe(**kwargs).images


class ZImageTurboEngine(LocalDiffusersEngine):
    """Tongyi-MAI Z-Image-Turbo — 8 steps, guidance 0.0, photoreal."""

    model_id = "Tongyi-MAI/Z-Image-Turbo"
    default_steps = 8
    default_guidance = 0.0
    model_size_gb = 6.0
    memory_strategy_default = "model_cpu_offload"
    pipeline_cls_dotted = "diffusers:AutoPipelineForText2Image"
    extra_pipeline_kwargs = {"trust_remote_code": True}
    supports_negative_prompt = True

    def _call_pipe(self, pipe, request, generator, source_image, steps, guidance):
        kwargs: dict[str, Any] = {
            "prompt": request.prompt,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "num_images_per_prompt": request.num_images,
            "height": request.height,
            "width": request.width,
        }
        if generator is not None:
            kwargs["generator"] = generator
        if source_image is not None:
            kwargs["image"] = source_image
            kwargs["strength"] = request.extra.get("strength", 0.5)
        if request.negative:
            kwargs["negative_prompt"] = request.negative
        return pipe(**kwargs).images


class NoobAIXLEngine(LocalDiffusersEngine):
    """Illustrious/NoobAI-XL v-pred — neon/cyberpunk SDXL finetune."""

    model_id = "Illustrious/NoobAI-XL-v-pred"
    default_steps = 28
    default_guidance = 4.0
    model_size_gb = 6.5
    memory_strategy_default = "model_cpu_offload"
    pipeline_cls_dotted = "diffusers:StableDiffusionXLPipeline"
    needs_safetensors = True
    variant = "fp16"
    supports_negative_prompt = True

    def _call_pipe(self, pipe, request, generator, source_image, steps, guidance):
        kwargs: dict[str, Any] = {
            "prompt": request.prompt,
            "negative_prompt": request.negative,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "num_images_per_prompt": request.num_images,
            "height": request.height,
            "width": request.width,
        }
        if generator is not None:
            kwargs["generator"] = generator
        if source_image is not None:
            kwargs["image"] = source_image
            kwargs["strength"] = request.extra.get("strength", 0.5)
        return pipe(**kwargs).images


class SDXLEngine(LocalDiffusersEngine):
    """SDXL Base 1.0 — legacy fallback."""

    model_id = "stabilityai/stable-diffusion-xl-base-1.0"
    default_steps = 30
    default_guidance = 7.5
    model_size_gb = 6.5
    memory_strategy_default = "model_cpu_offload"
    pipeline_cls_dotted = "diffusers:StableDiffusionXLPipeline"
    needs_safetensors = True
    variant = "fp16"
    supports_negative_prompt = True

    def _call_pipe(self, pipe, request, generator, source_image, steps, guidance):
        kwargs: dict[str, Any] = {
            "prompt": request.prompt,
            "negative_prompt": request.negative,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "num_images_per_prompt": request.num_images,
            "height": request.height,
            "width": request.width,
        }
        if generator is not None:
            kwargs["generator"] = generator
        if source_image is not None:
            kwargs["image"] = source_image
            kwargs["strength"] = request.extra.get("strength", 0.5)
        return pipe(**kwargs).images


class Flux1DevGGUFEngine(LocalDiffusersEngine):
    """FLUX.1-dev via NF4/GGUF quant — non-commercial, adapter ecosystem."""

    model_id = "city96/FLUX.1-dev-gguf"
    default_steps = 20
    default_guidance = 3.5
    model_size_gb = 6.8
    memory_strategy_default = "model_cpu_offload"
    pipeline_cls_dotted = "diffusers:FluxPipeline"
    supports_negative_prompt = False
    extra_pipeline_kwargs = {"max_sequence_length": 512}

    def _load_pipeline(self):
        import torch
        from diffusers import FluxPipeline, FluxTransformer2DModel

        nf4 = None
        try:
            from diffusers import BitsAndBytesConfig as DBnB
            from transformers import BitsAndBytesConfig as TBnB
            from transformers import T5EncoderModel
            nf4 = {"load_in_4bit": True, "bnb_4bit_quant_type": "nf4", "bnb_4bit_compute_dtype": torch.bfloat16}
            tr = FluxTransformer2DModel.from_pretrained(
                "black-forest-labs/FLUX.1-dev",
                subfolder="transformer",
                quantization_config=DBnB(**nf4),
                torch_dtype=torch.bfloat16,
            )
            te2 = T5EncoderModel.from_pretrained(
                "black-forest-labs/FLUX.1-dev",
                subfolder="text_encoder_2",
                quantization_config=TBnB(**nf4),
                torch_dtype=torch.bfloat16,
            )
            return FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-dev",
                transformer=tr,
                text_encoder_2=te2,
                torch_dtype=torch.bfloat16,
            )
        except Exception:
            pass

        try:
            return FluxPipeline.from_pretrained(
                self.spec.model_id,
                torch_dtype=torch.float16,
            )
        except Exception as exc:
            raise unavailable(self.spec.id, f"FLUX.1-dev GGUF load failed: {exc}") from exc

    def _call_pipe(self, pipe, request, generator, source_image, steps, guidance):
        kwargs: dict[str, Any] = {
            "prompt": request.prompt,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "num_images_per_prompt": request.num_images,
            "height": request.height,
            "width": request.width,
        }
        if generator is not None:
            kwargs["generator"] = generator
        if source_image is not None:
            kwargs["image"] = source_image
            kwargs["strength"] = request.extra.get("strength", 0.5)
        return pipe(**kwargs).images
