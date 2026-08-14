from __future__ import annotations

from pathlib import Path

import pytest

from substrate.render_engines.base import (
    QUALITY_TIERS,
    SPEED_TIERS,
    EngineSpec,
    RenderRequest,
    detect_gpu,
    ensure_scratch_env,
    tier_rank,
)

# ---------------------------------------------------------------------------
# Tier helpers
# ---------------------------------------------------------------------------


def test_tier_rank_quality():
    assert tier_rank("low", QUALITY_TIERS) == 0
    assert tier_rank("ultra", QUALITY_TIERS) == 3
    with pytest.raises(ValueError, match="Unknown tier"):
        tier_rank("legendary", QUALITY_TIERS)


def test_tier_rank_speed():
    assert tier_rank("slow", SPEED_TIERS) == 0
    assert tier_rank("realtime", SPEED_TIERS) == 3


# ---------------------------------------------------------------------------
# EngineSpec
# ---------------------------------------------------------------------------


def test_engine_spec_from_mapping_minimal(tmp_path: Path):
    raw = {
        "id": "test_engine",
        "kind": "local_gpu",
        "impl": "substrate.render_engines.local_diffusers:Flux2KleinEngine",
        "model_id": "test/model",
        "capabilities": ["text_to_image"],
        "quality_tier": "high",
        "speed_tier": "fast",
        "cost_per_image_usd": 0.0,
        "memory_strategy": "model_cpu_offload",
        "api_key_env": None,
        "license": "MIT",
        "gated": False,
        "max_pixels": 1024 * 1024,
        "supports_style_refs": False,
        "style_ref_max": 0,
        "requires": ["torch"],
    }
    spec = EngineSpec.from_mapping(raw)
    assert spec.id == "test_engine"
    assert spec.kind == "local_gpu"
    assert spec.cost_per_image_usd == 0.0
    assert spec.enabled is True


def test_engine_spec_requires_id_and_impl():
    with pytest.raises(ValueError, match="requires a non-empty 'id'"):
        EngineSpec.from_mapping({})
    with pytest.raises(ValueError, match="requires an 'impl' dotted path"):
        EngineSpec.from_mapping({"id": "x", "kind": "local_gpu", "impl": "", "model_id": "m", "capabilities": ["text_to_image"], "quality_tier": "high", "speed_tier": "fast", "memory_strategy": "none"})


def test_engine_spec_hosted_requires_api_key_env():
    with pytest.raises(ValueError, match="requires 'api_key_env'"):
        EngineSpec.from_mapping({
            "id": "x", "kind": "hosted_api", "impl": "mod:Cls", "model_id": "m",
            "capabilities": ["text_to_image"], "quality_tier": "high", "speed_tier": "fast",
            "memory_strategy": "none", "api_key_env": None,
        })


# ---------------------------------------------------------------------------
# RenderRequest
# ---------------------------------------------------------------------------


def test_render_request_validates():
    r = RenderRequest(prompt="test")
    r.validate()
    with pytest.raises(ValueError, match="non-empty"):
        RenderRequest(prompt="").validate()
    with pytest.raises(ValueError, match="positive"):
        RenderRequest(prompt="x", width=0, height=1024).validate()
    with pytest.raises(ValueError, match="num_images must be >= 1"):
        RenderRequest(prompt="x", num_images=0).validate()
    with pytest.raises(ValueError, match="requires a source_image"):
        RenderRequest(prompt="x", mode="image_to_image").validate()


def test_render_request_to_dict():
    r = RenderRequest(prompt="a neon city", width=832, height=1216, seed=42)
    d = r.to_dict()
    assert d["prompt"] == "a neon city"
    assert d["width"] == 832
    assert d["height"] == 1216
    assert d["seed"] == 42


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------


def test_detect_gpu_reports_device():
    info = detect_gpu()
    assert "name" in info
    assert "vram_free_mb" in info
    assert "available" in info


# ---------------------------------------------------------------------------
# Scratch env
# ---------------------------------------------------------------------------


def test_ensure_scratch_env_creates_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("TORCH_HOME", raising=False)
    applied = ensure_scratch_env(tmp_path)
    assert "TMPDIR" in applied
    assert (tmp_path / "state" / "render-cache" / "tmp").exists()
    assert (tmp_path / "state" / "render-cache" / "hf" / "hub").exists()
    assert (tmp_path / "state" / "render-cache" / "torch").exists()


# ---------------------------------------------------------------------------
# Hosted engine availability
# ---------------------------------------------------------------------------


def test_hosted_engine_missing_key_is_retryable(monkeypatch: pytest.MonkeyPatch):
    from substrate.render_engines.hosted import OpenAIGPTImageEngine
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = EngineSpec.from_mapping({
        "id": "openai_test", "kind": "hosted_api",
        "impl": "substrate.render_engines.hosted:OpenAIGPTImageEngine",
        "model_id": "gpt-image-2", "capabilities": ["text_to_image"],
        "quality_tier": "ultra", "speed_tier": "fast",
        "cost_per_image_usd": 0.211, "memory_strategy": "none",
        "api_key_env": "OPENAI_API_KEY", "license": "test", "gated": False,
        "max_pixels": 1572864, "supports_style_refs": True, "style_ref_max": 10,
        "requires": [],
    })
    engine = OpenAIGPTImageEngine(spec)
    ok, reason = engine.availability()
    assert ok is False
    assert "temporarily unavailable" in reason


def test_hosted_engine_present_key_is_available(monkeypatch: pytest.MonkeyPatch):
    from substrate.render_engines.hosted import OpenAIGPTImageEngine
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    spec = EngineSpec.from_mapping({
        "id": "openai_test", "kind": "hosted_api",
        "impl": "substrate.render_engines.hosted:OpenAIGPTImageEngine",
        "model_id": "gpt-image-2", "capabilities": ["text_to_image"],
        "quality_tier": "ultra", "speed_tier": "fast",
        "cost_per_image_usd": 0.211, "memory_strategy": "none",
        "api_key_env": "OPENAI_API_KEY", "license": "test", "gated": False,
        "max_pixels": 1572864, "supports_style_refs": True, "style_ref_max": 10,
        "requires": [],
    })
    engine = OpenAIGPTImageEngine(spec)
    ok, _reason = engine.availability()
    assert ok is True


# ---------------------------------------------------------------------------
# Local engine availability (no GPU / missing deps)
# ---------------------------------------------------------------------------


def test_local_engine_missing_deps_is_retryable(monkeypatch: pytest.MonkeyPatch):
    from substrate.render_engines.local_diffusers import Flux2KleinEngine
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    spec = EngineSpec.from_mapping({
        "id": "local_test", "kind": "local_gpu",
        "impl": "substrate.render_engines.local_diffusers:Flux2KleinEngine",
        "model_id": "black-forest-labs/FLUX.2-klein-4B",
        "capabilities": ["text_to_image"], "quality_tier": "high", "speed_tier": "fast",
        "cost_per_image_usd": 0.0, "memory_strategy": "model_cpu_offload",
        "api_key_env": None, "license": "Apache-2.0", "gated": False,
        "max_pixels": 4194304, "supports_style_refs": False, "style_ref_max": 0,
        "requires": ["torch", "diffusers"],
    })
    engine = Flux2KleinEngine(spec)
    ok, reason = engine.availability()
    assert ok is False
    assert "temporarily unavailable" in reason


# ---------------------------------------------------------------------------
# Catalog and selection
# ---------------------------------------------------------------------------


def test_render_catalog_loads_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from substrate.registry import SubstrateRuntime
    from substrate.render import render_catalog_payload

    monkeypatch.chdir(tmp_path)
    (tmp_path / "render_profiles.yaml").write_text(_MINIMAL_YAML)
    rt = SubstrateRuntime(root=tmp_path)
    cat = render_catalog_payload(rt)
    assert cat["version"] == 1
    assert len(cat["engines"]) >= 1
    assert cat["defaults"]["optimize_for"] == "quality"


_MINIMAL_YAML = """
version: 1
defaults:
  optimize_for: quality
  allow_hosted: false
  max_cost_usd: 0.50
  fallback_order: [local_flux2_klein]
  local_first: true
  quality_gate: 0.0
engines:
  - id: local_flux2_klein
    name: FLUX.2 Klein 4B (local)
    kind: local_gpu
    impl: substrate.render_engines.local_diffusers:Flux2KleinEngine
    model_id: black-forest-labs/FLUX.2-klein-4B
    capabilities: [text_to_image]
    quality_tier: high
    speed_tier: fast
    cost_per_image_usd: 0.0
    memory_strategy: model_cpu_offload
    api_key_env: null
    license: Apache-2.0
    gated: false
    max_pixels: 4194304
    supports_style_refs: false
    style_ref_max: 0
    requires: [torch, diffusers, transformers, accelerate]
    enabled: true
    notes: test
"""
