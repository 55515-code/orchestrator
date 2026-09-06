"""Shared contract for the render orchestration router.

This module defines the request/result/spec dataclasses, the abstract engine
interface, and the environment helpers that every render engine (local GPU or
hosted API) depends on. It is deliberately dependency-light: torch, diffusers,
transformers and PIL are optional heavy dependencies and are only imported
lazily inside functions, so importing this module never requires a GPU.

Failure convention (matches ``substrate/providers.py`` and
``substrate/reliability.py::classify_failure``): unavailability is signalled by
raising :class:`RenderUnavailable` (a ``RuntimeError``) whose message follows
``"<name> temporarily unavailable: <reason>"``, which ``classify_failure``
treats as *transient* and therefore retryable / failover-able. Deterministic
render errors raise :class:`RenderFailed`, and malformed input raises
``ValueError`` (which ``classify_failure`` treats as *terminal*).
"""

from __future__ import annotations

import abc
import importlib
import importlib.util
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import _utils

__all__ = [
    "CAPABILITIES",
    "KINDS",
    "MEMORY_STRATEGIES",
    "QUALITY_TIERS",
    "SPEED_TIERS",
    "EngineSpec",
    "RenderEngine",
    "RenderFailed",
    "RenderRequest",
    "RenderResult",
    "RenderUnavailable",
    "apply_memory_strategy",
    "detect_gpu",
    "ensure_scratch_env",
    "load_engine",
    "resize_for_engine",
    "scratch_root",
    "select_memory_strategy",
    "tier_rank",
    "write_images",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUALITY_TIERS: tuple[str, ...] = ("low", "medium", "high", "ultra")
SPEED_TIERS: tuple[str, ...] = ("slow", "medium", "fast", "realtime")

CAPABILITIES: frozenset[str] = frozenset(
    {
        "text_to_image",
        "image_to_image",
        "edit",
        "inpaint",
        "style_reference",
        "upscale",
    }
)

KINDS: frozenset[str] = frozenset({"local_gpu", "hosted_api"})

MEMORY_STRATEGIES: frozenset[str] = frozenset(
    {"cuda", "model_cpu_offload", "sequential_cpu_offload", "none"}
)

RENDER_MODES: frozenset[str] = frozenset(
    {
        "text_to_image",
        "image_to_image",
        "edit",
        "inpaint",
        "upscale",
    }
)

_SCRATCH_SUBDIR = Path("state") / "render-cache"
_GPU_QUERY_TIMEOUT_SECONDS = 5


def tier_rank(tier: str, tiers: tuple[str, ...]) -> int:
    """Return the numeric rank of *tier* inside the ordered *tiers* tuple.

    Higher is better. Raises ``ValueError`` for unknown tiers so misconfigured
    catalogs fail loudly rather than silently sorting last.
    """
    normalized = (tier or "").strip().lower()
    if normalized not in tiers:
        raise ValueError(f"Unknown tier '{tier}'. Expected one of: {', '.join(tiers)}.")
    return tiers.index(normalized)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RenderUnavailable(RuntimeError):
    """An engine cannot run right now (missing dep, missing key, no GPU).

    Messages must contain the substring ``"temporarily unavailable"`` so that
    :func:`substrate.reliability.classify_failure` classifies them as transient
    and the router is allowed to fail over to the next engine.
    """


class RenderFailed(RuntimeError):
    """An engine was available but the render itself failed."""


def unavailable(name: str, reason: str) -> RenderUnavailable:
    """Build a :class:`RenderUnavailable` with the substrate-wide message shape."""
    return RenderUnavailable(f"{name} temporarily unavailable: {reason}")


def _unavailable_reason(name: str, reason: str) -> str:
    return f"{name} temporarily unavailable: {reason}"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RenderRequest:
    """A single render job, independent of which engine executes it."""

    prompt: str
    negative: str = ""
    width: int = 1024
    height: int = 1024
    steps: int | None = None
    guidance: float | None = None
    seed: int | None = None
    num_images: int = 1
    mode: str = "text_to_image"
    source_image: Path | None = None
    style_refs: list[Path] = field(default_factory=list)
    output: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate intrinsic request consistency.

        Engine-relative limits (max pixels, style-reference caps, cost ceilings)
        are the router's responsibility; this method only rejects requests that
        are wrong regardless of engine.
        """
        if not self.prompt or not self.prompt.strip():
            raise ValueError("RenderRequest.prompt must be a non-empty string.")
        if self.mode not in RENDER_MODES:
            raise ValueError(
                f"RenderRequest.mode '{self.mode}' is not supported. "
                f"Expected one of: {', '.join(sorted(RENDER_MODES))}."
            )
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"RenderRequest dimensions must be positive (got {self.width}x{self.height})."
            )
        if self.num_images < 1:
            raise ValueError("RenderRequest.num_images must be >= 1.")
        if self.steps is not None and self.steps < 1:
            raise ValueError("RenderRequest.steps must be >= 1 when provided.")
        if self.guidance is not None and self.guidance < 0:
            raise ValueError("RenderRequest.guidance must be >= 0 when provided.")
        if self.mode in {"image_to_image", "edit", "inpaint", "upscale"} and self.source_image is None:
            raise ValueError(
                f"RenderRequest.mode '{self.mode}' requires a source_image."
            )
        for ref in self.style_refs:
            if not isinstance(ref, Path):
                raise ValueError("RenderRequest.style_refs must contain Path entries.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation (``Path`` values become strings)."""
        return {
            "prompt": self.prompt,
            "negative": self.negative,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "guidance": self.guidance,
            "seed": self.seed,
            "num_images": self.num_images,
            "mode": self.mode,
            "source_image": str(self.source_image) if self.source_image else None,
            "style_refs": [str(ref) for ref in self.style_refs],
            "output": str(self.output) if self.output else None,
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class RenderResult:
    """The outcome of one render attempt by one engine."""

    engine_id: str
    model_id: str
    status: str
    images: list[Path] = field(default_factory=list)
    latency_ms: int = 0
    cost_usd: float = 0.0
    quality_score: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe primitives for CLI output and DB persistence."""
        return {
            "engine_id": self.engine_id,
            "model_id": self.model_id,
            "status": self.status,
            "images": [str(image) for image in self.images],
            "latency_ms": int(self.latency_ms),
            "cost_usd": float(self.cost_usd),
            "quality_score": (
                float(self.quality_score) if self.quality_score is not None else None
            ),
            "error": self.error,
            "metadata": _json_safe(self.metadata),
        }

    @classmethod
    def failure(
        cls,
        *,
        engine_id: str,
        model_id: str,
        error: str,
        latency_ms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> RenderResult:
        """Convenience constructor for a failed attempt."""
        return cls(
            engine_id=engine_id,
            model_id=model_id,
            status="failed",
            latency_ms=latency_ms,
            error=error,
            metadata=metadata or {},
        )


@dataclass(slots=True)
class EngineSpec:
    """Declarative description of one engine, loaded from ``render_profiles.yaml``."""

    id: str
    name: str
    kind: str
    impl: str
    model_id: str
    capabilities: list[str]
    quality_tier: str
    speed_tier: str
    cost_per_image_usd: float
    memory_strategy: str
    api_key_env: str | None
    license: str
    gated: bool
    max_pixels: int
    supports_style_refs: bool
    style_ref_max: int
    requires: list[str]
    enabled: bool = True
    notes: str = ""

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> EngineSpec:
        """Normalize and validate one ``engines:`` entry into an EngineSpec."""
        if not isinstance(raw, dict):
            raise ValueError("Engine entry must be a mapping.")

        engine_id = str(raw.get("id") or "").strip()
        if not engine_id:
            raise ValueError("Engine entry requires a non-empty 'id'.")

        kind = str(raw.get("kind") or "").strip()
        if kind not in KINDS:
            raise ValueError(
                f"Engine '{engine_id}' has invalid kind '{kind}'. "
                f"Expected one of: {', '.join(sorted(KINDS))}."
            )

        impl = str(raw.get("impl") or "").strip()
        if not impl:
            raise ValueError(f"Engine '{engine_id}' requires an 'impl' dotted path.")
        if ":" not in impl:
            raise ValueError(
                f"Engine '{engine_id}' impl '{impl}' must use "
                "'package.module:ClassName' form."
            )

        capabilities = [
            str(item).strip()
            for item in _utils.ensure_list(
                raw.get("capabilities"), f"engine '{engine_id}' capabilities"
            )
        ]
        if not capabilities:
            raise ValueError(f"Engine '{engine_id}' must declare at least one capability.")
        unknown = sorted(set(capabilities) - CAPABILITIES)
        if unknown:
            raise ValueError(
                f"Engine '{engine_id}' declares unknown capabilities: {', '.join(unknown)}."
            )

        quality_tier = str(raw.get("quality_tier") or "medium").strip().lower()
        tier_rank(quality_tier, QUALITY_TIERS)
        speed_tier = str(raw.get("speed_tier") or "medium").strip().lower()
        tier_rank(speed_tier, SPEED_TIERS)

        memory_strategy = str(raw.get("memory_strategy") or "none").strip()
        if memory_strategy not in MEMORY_STRATEGIES:
            raise ValueError(
                f"Engine '{engine_id}' has invalid memory_strategy '{memory_strategy}'. "
                f"Expected one of: {', '.join(sorted(MEMORY_STRATEGIES))}."
            )

        requires = [
            str(item).strip()
            for item in _utils.ensure_list(
                raw.get("requires"), f"engine '{engine_id}' requires"
            )
        ]

        api_key_env_raw = raw.get("api_key_env")
        api_key_env = str(api_key_env_raw).strip() if api_key_env_raw else None
        if kind == "hosted_api" and not api_key_env:
            raise ValueError(
                f"Engine '{engine_id}' is a hosted_api engine and requires 'api_key_env'."
            )

        try:
            cost_per_image_usd = float(raw.get("cost_per_image_usd", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Engine '{engine_id}' cost_per_image_usd must be numeric."
            ) from exc
        if cost_per_image_usd < 0:
            raise ValueError(f"Engine '{engine_id}' cost_per_image_usd must be >= 0.")

        try:
            max_pixels = int(raw.get("max_pixels", 1024 * 1024))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Engine '{engine_id}' max_pixels must be an integer.") from exc
        if max_pixels <= 0:
            raise ValueError(f"Engine '{engine_id}' max_pixels must be > 0.")

        try:
            style_ref_max = int(raw.get("style_ref_max", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Engine '{engine_id}' style_ref_max must be an integer."
            ) from exc
        if style_ref_max < 0:
            raise ValueError(f"Engine '{engine_id}' style_ref_max must be >= 0.")

        supports_style_refs = bool(raw.get("supports_style_refs", style_ref_max > 0))
        if supports_style_refs and style_ref_max < 1:
            raise ValueError(
                f"Engine '{engine_id}' supports_style_refs is true but style_ref_max is 0."
            )

        return cls(
            id=engine_id,
            name=str(raw.get("name") or engine_id),
            kind=kind,
            impl=impl,
            model_id=str(raw.get("model_id") or ""),
            capabilities=capabilities,
            quality_tier=quality_tier,
            speed_tier=speed_tier,
            cost_per_image_usd=cost_per_image_usd,
            memory_strategy=memory_strategy,
            api_key_env=api_key_env,
            license=str(raw.get("license") or "unknown"),
            gated=bool(raw.get("gated", False)),
            max_pixels=max_pixels,
            supports_style_refs=supports_style_refs,
            style_ref_max=style_ref_max,
            requires=requires,
            enabled=bool(raw.get("enabled", True)),
            notes=str(raw.get("notes") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the spec."""
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "impl": self.impl,
            "model_id": self.model_id,
            "capabilities": list(self.capabilities),
            "quality_tier": self.quality_tier,
            "speed_tier": self.speed_tier,
            "cost_per_image_usd": float(self.cost_per_image_usd),
            "memory_strategy": self.memory_strategy,
            "api_key_env": self.api_key_env,
            "license": self.license,
            "gated": self.gated,
            "max_pixels": int(self.max_pixels),
            "supports_style_refs": self.supports_style_refs,
            "style_ref_max": int(self.style_ref_max),
            "requires": list(self.requires),
            "enabled": self.enabled,
            "notes": self.notes,
        }

    def supports(self, capability: str) -> bool:
        """Return whether this engine declares *capability*."""
        return capability in self.capabilities


# ---------------------------------------------------------------------------
# Engine interface
# ---------------------------------------------------------------------------


class RenderEngine(abc.ABC):
    """Abstract base class every render engine implements."""

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec

    @abc.abstractmethod
    def render(self, request: RenderRequest) -> RenderResult:
        """Execute *request* and return a :class:`RenderResult`."""

    def availability(self, *, gpu: dict[str, Any] | None = None) -> tuple[bool, str]:
        """Report whether this engine can run right now.

        Returns ``(True, "")`` when available, otherwise ``(False, reason)``
        where *reason* follows the substrate's
        ``"<name> temporarily unavailable: <reason>"`` convention.
        """
        spec = self.spec
        name = spec.id

        if not spec.enabled:
            return False, _unavailable_reason(name, "engine disabled in render_profiles.yaml")

        if spec.kind == "hosted_api":
            env_name = spec.api_key_env or ""
            if not env_name:
                return False, _unavailable_reason(name, "no api_key_env configured")
            if not (os.environ.get(env_name) or "").strip():
                return False, _unavailable_reason(name, f"set {env_name}")
            return True, ""

        if spec.kind == "local_gpu":
            missing = [
                module
                for module in spec.requires
                if importlib.util.find_spec(module) is None
            ]
            if missing:
                return False, _unavailable_reason(
                    name, f"missing python modules: {', '.join(missing)}"
                )
            probe = gpu if gpu is not None else detect_gpu()
            if not probe.get("available"):
                return False, _unavailable_reason(name, "no usable CUDA device detected")
            return True, ""

        return False, _unavailable_reason(name, f"unsupported engine kind '{spec.kind}'")

    def require_available(self, *, gpu: dict[str, Any] | None = None) -> None:
        """Raise :class:`RenderUnavailable` if :meth:`availability` says no."""
        ok, reason = self.availability(gpu=gpu)
        if not ok:
            raise RenderUnavailable(reason)


def load_engine(spec: EngineSpec) -> RenderEngine:
    """Resolve ``spec.impl`` and instantiate the engine class it names."""
    module_path, _, attribute = spec.impl.partition(":")
    if not module_path or not attribute:
        raise ValueError(
            f"Engine '{spec.id}' impl '{spec.impl}' must use 'package.module:ClassName' form."
        )
    try:
        module = importlib.import_module(module_path)
        candidate = getattr(module, attribute)
    except ImportError as exc:
        raise unavailable(spec.id, f"cannot import {module_path}: {exc}") from exc
    except AttributeError as exc:
        raise unavailable(
            spec.id, f"{module_path} has no attribute '{attribute}'"
        ) from exc

    if not (isinstance(candidate, type) and issubclass(candidate, RenderEngine)):
        raise ValueError(
            f"Engine '{spec.id}' impl '{spec.impl}' is not a RenderEngine subclass."
        )
    return candidate(spec)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def scratch_root(root: Path) -> Path:
    """Return the render scratch directory for repository *root*."""
    return Path(root) / _SCRATCH_SUBDIR


def _is_tmpfs_path(value: str) -> bool:
    """Return True when *value* lives under the (full) ``/tmp`` tmpfs."""
    try:
        resolved = Path(value).expanduser()
    except (OSError, ValueError):
        return True
    parts = resolved.parts
    return bool(parts) and parts[0] == "/" and len(parts) > 1 and parts[1] == "tmp"


def _keep_existing(name: str) -> bool:
    """Return True when the pre-existing env var is already a safe non-/tmp path."""
    existing = (os.environ.get(name) or "").strip()
    if not existing:
        return False
    if _is_tmpfs_path(existing):
        return False
    parent = Path(existing).expanduser().parent
    return parent.exists() or Path(existing).expanduser().exists()


def ensure_scratch_env(root: Path) -> dict[str, str]:
    """Point all model/temp caches at ``<root>/state/render-cache`` instead of ``/tmp``.

    ``/tmp`` on this host is a 32 GB tmpfs that runs 100% full, so torch temp
    files and Hugging Face downloads must never land there. Pre-existing
    settings that already point somewhere other than ``/tmp`` are respected.

    Returns:
        The mapping of environment variables this call actually applied.
    """
    base = scratch_root(root)
    tmp_dir = base / "tmp"
    hf_dir = base / "hf"
    torch_dir = base / "torch"
    for directory in (tmp_dir, hf_dir, hf_dir / "hub", torch_dir):
        directory.mkdir(parents=True, exist_ok=True)

    desired: dict[str, str] = {
        "TMPDIR": str(tmp_dir),
        "TEMP": str(tmp_dir),
        "TMP": str(tmp_dir),
        "HF_HOME": str(hf_dir),
        "HF_HUB_CACHE": str(hf_dir / "hub"),
        "TORCH_HOME": str(torch_dir),
        "XDG_CACHE_HOME": str(base),
    }

    applied: dict[str, str] = {}
    for name, value in desired.items():
        if _keep_existing(name):
            continue
        os.environ[name] = value
        applied[name] = value
    return applied


def detect_gpu() -> dict[str, Any]:
    """Probe the local GPU without ever raising.

    Tries ``torch.cuda`` first (lazy import), then falls back to
    ``nvidia-smi``. Returns ``available: False`` and ``source: "none"`` when
    nothing usable is found.
    """
    probe = _detect_gpu_torch()
    if probe is not None:
        return probe
    probe = _detect_gpu_nvidia_smi()
    if probe is not None:
        return probe
    return {
        "available": False,
        "name": "",
        "vram_total_mb": 0,
        "vram_free_mb": 0,
        "compute_capability": None,
        "source": "none",
    }


def _detect_gpu_torch() -> dict[str, Any] | None:
    try:
        import torch
    except Exception:  # noqa: BLE001  - ImportError or broken CUDA init
        return None
    try:
        cuda = getattr(torch, "cuda", None)
        if cuda is None or not cuda.is_available():
            return None
        index = cuda.current_device()
        properties = cuda.get_device_properties(index)
        free_bytes, total_bytes = cuda.mem_get_info(index)
        return {
            "available": True,
            "name": str(properties.name),
            "vram_total_mb": int(total_bytes // (1024 * 1024)),
            "vram_free_mb": int(free_bytes // (1024 * 1024)),
            "compute_capability": f"{properties.major}.{properties.minor}",
            "source": "torch",
        }
    except Exception:  # noqa: BLE001  - never let hardware probing break a render
        return None


def _detect_gpu_nvidia_smi() -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GPU_QUERY_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001  - FileNotFoundError, TimeoutExpired, OSError
        return None
    if completed.returncode != 0:
        return None
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        return None
    fields = [field_value.strip() for field_value in line[0].split(",")]
    if len(fields) < 3:
        return None
    try:
        total_mb = int(float(fields[1]))
        free_mb = int(float(fields[2]))
    except ValueError:
        return None
    compute_capability = fields[3] if len(fields) > 3 and fields[3] else None
    if compute_capability in {"[N/A]", "[Not Supported]"}:
        compute_capability = None
    return {
        "available": True,
        "name": fields[0],
        "vram_total_mb": total_mb,
        "vram_free_mb": free_mb,
        "compute_capability": compute_capability,
        "source": "nvidia-smi",
    }


def select_memory_strategy(vram_free_mb: int, model_gb: float) -> str:
    """Pick a diffusers memory strategy for *model_gb* given free VRAM.

    Full-resident CUDA needs headroom for activations (1.35x the weights);
    below that, whole-component offload; below 0.75x, submodule offload.
    """
    if model_gb <= 0:
        raise ValueError("model_gb must be > 0")
    model_mb = model_gb * 1024
    if vram_free_mb > model_mb * 1.35:
        return "cuda"
    if vram_free_mb > model_mb * 0.75:
        return "model_cpu_offload"
    return "sequential_cpu_offload"


def apply_memory_strategy(pipe: Any, strategy: str) -> None:
    """Apply *strategy* plus the always-on VAE memory savers to a diffusers pipe.

    All calls are guarded with ``hasattr``/``getattr`` so the same code works
    across diffusers versions and across pipelines that lack a VAE.
    """
    if strategy not in MEMORY_STRATEGIES:
        raise ValueError(
            f"Unknown memory strategy '{strategy}'. "
            f"Expected one of: {', '.join(sorted(MEMORY_STRATEGIES))}."
        )

    if strategy == "cuda":
        mover = getattr(pipe, "to", None)
        if callable(mover):
            mover("cuda")
    elif strategy == "model_cpu_offload":
        enable = getattr(pipe, "enable_model_cpu_offload", None)
        if callable(enable):
            enable()
    elif strategy == "sequential_cpu_offload":
        enable = getattr(pipe, "enable_sequential_cpu_offload", None)
        if callable(enable):
            enable()

    for saver in ("enable_vae_slicing", "enable_vae_tiling"):
        enable = getattr(pipe, saver, None)
        if callable(enable):
            try:
                enable()
            except Exception:  # noqa: BLE001  - optional optimization only
                continue


def write_images(images: list[Any], output: Path) -> list[Path]:
    """Persist PIL images to disk, mirroring the legacy render scripts.

    A single image is written to *output* verbatim; multiple images are written
    as ``<stem>_<index><suffix>`` beside it.
    """
    if not images:
        raise ValueError("write_images requires at least one image.")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for index, image in enumerate(images):
        if len(images) == 1:
            path = target
        else:
            path = target.parent / f"{target.stem}_{index}{target.suffix}"
        saver = getattr(image, "save", None)
        if not callable(saver):
            raise ValueError(
                f"write_images entry {index} has no save() method: {type(image)!r}"
            )
        saver(str(path))
        written.append(path)
    return written


def resize_for_engine(image: Any, max_pixels: int, multiple_of: int = 16) -> Any:
    """Downscale *image* so ``w*h <= max_pixels``, snapping dims to *multiple_of*.

    Aspect ratio is preserved. Images already within budget are still snapped
    to the required multiple, because diffusers rejects off-grid dimensions.
    """
    if max_pixels <= 0:
        raise ValueError("max_pixels must be > 0")
    if multiple_of < 1:
        raise ValueError("multiple_of must be >= 1")

    try:
        from PIL import Image as PILImage
    except ImportError as exc:
        raise unavailable("pillow", f"install pillow: {exc}") from exc

    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError(f"Image has invalid size {width}x{height}.")

    scale = 1.0
    if width * height > max_pixels:
        scale = (max_pixels / float(width * height)) ** 0.5

    target_width = _snap_down(int(width * scale), multiple_of)
    target_height = _snap_down(int(height * scale), multiple_of)

    # Snapping up can push the area back over budget; step down until it fits.
    while target_width * target_height > max_pixels and (
        target_width > multiple_of or target_height > multiple_of
    ):
        if target_width >= target_height and target_width > multiple_of:
            target_width -= multiple_of
        elif target_height > multiple_of:
            target_height -= multiple_of
        else:
            break

    if (target_width, target_height) == (width, height):
        return image
    resample = getattr(PILImage, "Resampling", PILImage).LANCZOS
    return image.resize((target_width, target_height), resample)


def _snap_down(value: int, multiple_of: int) -> int:
    snapped = (value // multiple_of) * multiple_of
    return max(multiple_of, snapped)


def _json_safe(payload: Any) -> Any:
    """Recursively convert Paths (and Path-valued containers) to strings."""
    if isinstance(payload, Path):
        return str(payload)
    if isinstance(payload, dict):
        return {str(key): _json_safe(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple, set)):
        return [_json_safe(item) for item in payload]
    return payload
