from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


FREE_FIRST_PROVIDER_ORDER = (
    "local",
    "roo-router",
    "ollama",
    "huggingface",
    "gcloud",
    "groq",
    "cerebras",
    "together",
    "openrouter",
    "replicate",
    "anthropic",
    "openai",
    "mock",
)


DEFAULT_PROVIDER_MODELS: dict[str, str] = {
    "mock": "mock-model",
    "local": "roo-router",
    "roo-router": "roo-router",
    "ollama": "llama3.2:latest",
    "huggingface": "meta-llama/Llama-3.1-8B-Instruct",
    "gcloud": "gemini-1.5-flash",
    "groq": "llama3-8b-8192",
    "cerebras": "llama3.1-8b",
    "together": "meta-llama/Llama-3-8b-chat-hf",
    "openrouter": "meta-llama/llama-3.1-8b-instruct",
    "replicate": "meta/llama-2-7b-chat",
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4.1-mini",
}


def models_for_hardware(
    tier: str = "medium",
    base_models: dict[str, str] | None = None,
) -> dict[str, str]:
    base = dict(base_models or DEFAULT_PROVIDER_MODELS)
    if tier == "large":
        base["ollama"] = "llama3.1:70b"
        base["huggingface"] = "meta-llama/Llama-3.1-70B-Instruct"
        base["openrouter"] = "meta-llama/llama-3.1-70b-instruct"
    elif tier == "medium":
        base["ollama"] = "llama3.1:8b"
        base["huggingface"] = "meta-llama/Llama-3.1-8B-Instruct"
        base["openrouter"] = "meta-llama/llama-3.1-8b-instruct"
    else:
        base["ollama"] = "llama3.2:3b"
        base["huggingface"] = "HuggingFaceH4/zephyr-7b-beta"
        base["openrouter"] = "HuggingFaceH4/zephyr-7b-beta"
    return base

FREE_FIRST_PROVIDERS = frozenset(
    provider for provider in FREE_FIRST_PROVIDER_ORDER if provider not in {"anthropic", "openai"}
)
SUPPORTED_PROVIDERS = frozenset(FREE_FIRST_PROVIDER_ORDER)


@dataclass(slots=True)
class ProviderMessage:
    content: str


def provider_diagnostics() -> dict[str, Any]:
    local_base_url = os.getenv("SUBSTRATE_LOCAL_OPENAI_BASE_URL") or os.getenv(
        "ROO_ROUTER_BASE_URL"
    )
    local_ollama_model = os.getenv("SUBSTRATE_LOCAL_OLLAMA_MODEL")
    google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    google_project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
    )
    return {
        "local": {
            "status": (
                "available"
                if (local_base_url or local_ollama_model)
                else "temporarily_unavailable"
            ),
            "configured_via": "openai_compatible_base_url"
            if local_base_url
            else ("ollama_model" if local_ollama_model else None),
        },
        "huggingface": {
            "status": (
                "available"
                if (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN"))
                else "temporarily_unavailable"
            ),
            "configured_via": "HF_TOKEN"
            if os.getenv("HF_TOKEN")
            else ("HUGGINGFACE_API_TOKEN" if os.getenv("HUGGINGFACE_API_TOKEN") else None),
        },
        "gcloud": {
            "status": (
                "available"
                if (google_api_key or google_project)
                else "temporarily_unavailable"
            ),
            "configured_via": "api_key"
            if google_api_key
            else ("project" if google_project else None),
        },
        "supported": sorted(SUPPORTED_PROVIDERS),
        "free_first_order": list(FREE_FIRST_PROVIDER_ORDER),
    }


class GoogleGatewayChatModel:
    def __init__(self, model: str, *, timeout_seconds: int = 120) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    def invoke(self, prompt: str) -> ProviderMessage:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            return self._invoke_gemini_api_key(prompt, api_key=api_key)
        return self._invoke_vertex_with_gcloud(prompt)

    def _invoke_gemini_api_key(self, prompt: str, *, api_key: str) -> ProviderMessage:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={api_key}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        return self._post_generate_content(url, payload, headers={})

    def _invoke_vertex_with_gcloud(self, prompt: str) -> ProviderMessage:
        project = (
            os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GCLOUD_PROJECT")
            or os.getenv("GCP_PROJECT")
        )
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GCLOUD_LOCATION") or "us-central1"
        if not project:
            raise RuntimeError(
                "gcloud provider temporarily unavailable: set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT"
            )
        token = _gcloud_access_token()
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/{self.model}:generateContent"
        )
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        return self._post_generate_content(
            url,
            payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _post_generate_content(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> ProviderMessage:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"gcloud provider temporarily unavailable: HTTP {exc.code}: {body[:500]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"gcloud provider temporarily unavailable: {exc}") from exc

        text = _extract_google_text(data)
        if not text:
            raise RuntimeError("gcloud provider temporarily unavailable: empty model response")
        return ProviderMessage(content=text)


def build_model(provider: str, model: str):
    normalized = provider.strip().lower()
    if normalized == "mock":
        return None
    if normalized in {"local", "roo-router"}:
        return _build_local_router(model)
    if normalized == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)
    if normalized == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=0)
    if normalized == "huggingface":
        api_key = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
        if not api_key:
            raise RuntimeError(
                "huggingface provider temporarily unavailable: set HF_TOKEN or HUGGINGFACE_API_TOKEN"
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=0,
            base_url="https://api-inference.huggingface.co/v1/",
            api_key=api_key,
        )
    if normalized == "gcloud":
        return GoogleGatewayChatModel(model)
    if normalized == "groq":
        return _build_groq(model)
    if normalized == "cerebras":
        return _build_openai_compatible(
            model,
            base_url="https://api.cerebras.ai/v1",
            api_key_env="CEREBRAS_API_KEY",
            provider="cerebras",
        )
    if normalized == "together":
        return _build_together(model)
    if normalized == "openrouter":
        return _build_openai_compatible(
            model,
            base_url="https://api.openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            provider="openrouter",
        )
    if normalized == "replicate":
        raise RuntimeError("replicate provider temporarily unavailable: direct adapter not configured")
    if normalized == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=0)
    raise ValueError(f"Unsupported provider: {provider}")


def _build_local_router(model: str):
    base_url = os.getenv("SUBSTRATE_LOCAL_OPENAI_BASE_URL") or os.getenv("ROO_ROUTER_BASE_URL")
    if base_url:
        return _build_openai_compatible(
            model,
            base_url=base_url,
            api_key_env="SUBSTRATE_LOCAL_OPENAI_API_KEY",
            provider="local",
            allow_missing_key=True,
        )
    ollama_model = os.getenv("SUBSTRATE_LOCAL_OLLAMA_MODEL")
    if ollama_model:
        from langchain_ollama import ChatOllama

        return ChatOllama(model=ollama_model, temperature=0)
    raise RuntimeError(
        "local provider temporarily unavailable: set SUBSTRATE_LOCAL_OPENAI_BASE_URL "
        "or SUBSTRATE_LOCAL_OLLAMA_MODEL"
    )


def _build_groq(model: str):
    try:
        from langchain_groq import ChatGroq
    except Exception:  # noqa: BLE001
        return _build_openai_compatible(
            model,
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
            provider="groq",
        )
    return ChatGroq(model=model, temperature=0)


def _build_together(model: str):
    try:
        from langchain_together import ChatTogether
    except Exception:  # noqa: BLE001
        return _build_openai_compatible(
            model,
            base_url="https://api.together.xyz/v1",
            api_key_env="TOGETHER_API_KEY",
            provider="together",
        )
    return ChatTogether(model=model, temperature=0)


def _build_openai_compatible(
    model: str,
    *,
    base_url: str,
    api_key_env: str,
    provider: str,
    allow_missing_key: bool = False,
):
    api_key = os.getenv(api_key_env)
    if not api_key and not allow_missing_key:
        raise RuntimeError(
            f"{provider} provider temporarily unavailable: set {api_key_env}"
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        temperature=0,
        base_url=base_url,
        api_key=api_key or "local",
    )


def _gcloud_access_token() -> str:
    try:
        completed = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gcloud provider temporarily unavailable: {exc}") from exc
    token = completed.stdout.strip()
    if completed.returncode != 0 or not token:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"gcloud provider temporarily unavailable: application default credentials missing. {detail}"
        )
    return token


def _extract_google_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for candidate in data.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunk for chunk in chunks if chunk).strip()
