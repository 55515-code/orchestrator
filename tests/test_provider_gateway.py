from __future__ import annotations

import pytest

from substrate.providers import (
    DEFAULT_PROVIDER_MODELS,
    FREE_FIRST_PROVIDER_ORDER,
    SUPPORTED_PROVIDERS,
    GoogleGatewayChatModel,
    build_model,
)


def test_free_first_order_keeps_paid_models_late() -> None:
    assert FREE_FIRST_PROVIDER_ORDER.index("gcloud") < FREE_FIRST_PROVIDER_ORDER.index("anthropic")
    assert FREE_FIRST_PROVIDER_ORDER.index("groq") < FREE_FIRST_PROVIDER_ORDER.index("anthropic")
    assert FREE_FIRST_PROVIDER_ORDER.index("anthropic") < FREE_FIRST_PROVIDER_ORDER.index("openai")
    assert FREE_FIRST_PROVIDER_ORDER.index("huggingface") < FREE_FIRST_PROVIDER_ORDER.index("anthropic")
    assert "openai" in SUPPORTED_PROVIDERS
    assert "huggingface" in SUPPORTED_PROVIDERS
    assert DEFAULT_PROVIDER_MODELS["gcloud"].startswith("gemini")
    assert DEFAULT_PROVIDER_MODELS["huggingface"].startswith("meta-llama")


def test_gcloud_gateway_builds_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    model = build_model("gcloud", "gemini-1.5-flash")
    assert isinstance(model, GoogleGatewayChatModel)


def test_huggingface_builds_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("HF_TOKEN", "test-key")
    model = build_model("huggingface", "meta-llama/Llama-3.1-8B-Instruct")
    assert isinstance(model, ChatOpenAI)


def test_huggingface_missing_token_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        build_model("huggingface", "meta-llama/Llama-3.1-8B-Instruct")


def test_local_missing_router_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUBSTRATE_LOCAL_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("ROO_ROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("SUBSTRATE_LOCAL_OLLAMA_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        build_model("local", "roo-router")
