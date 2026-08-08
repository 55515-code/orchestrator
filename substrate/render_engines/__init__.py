"""Render engine package: shared contract plus local/hosted engine implementations."""

from __future__ import annotations

from .base import (
    CAPABILITIES,
    KINDS,
    MEMORY_STRATEGIES,
    QUALITY_TIERS,
    SPEED_TIERS,
    EngineSpec,
    RenderEngine,
    RenderFailed,
    RenderRequest,
    RenderResult,
    RenderUnavailable,
    apply_memory_strategy,
    detect_gpu,
    ensure_scratch_env,
    load_engine,
    resize_for_engine,
    scratch_root,
    select_memory_strategy,
    tier_rank,
    write_images,
)

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
