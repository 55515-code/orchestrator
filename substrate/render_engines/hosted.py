"""Hosted API engine implementations for the render router."""

from __future__ import annotations

import base64
import io
import os
import time
from pathlib import Path
from typing import Any

from .base import (
    RenderEngine,
    RenderFailed,
    RenderRequest,
    RenderResult,
    RenderUnavailable,
    unavailable,
    write_images,
)


class HostedAPIEngine(RenderEngine):
    """Base for all hosted API engines."""

    api_base: str = ""
    _timeout: float = 120

    def _headers(self) -> dict[str, str]:
        return {}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise unavailable(self.spec.id, f"missing httpx: {exc}") from exc

        url = f"{self.api_base.rstrip('/')}/{path.lstrip('/')}"
        headers = {**self._headers(), "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.request(method, url, headers=headers, **kwargs)
            self._check_status(resp)
            return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (429, 503):
                raise RenderUnavailable(f"{self.spec.id} temporarily unavailable: rate limited ({status})") from exc
            if status in (400, 403, 404):
                raise RenderFailed(f"{self.spec.id}: terminal HTTP {status}: {exc.response.text[:200]}") from exc
            raise RenderFailed(f"{self.spec.id}: HTTP {status}: {exc.response.text[:200]}") from exc
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: request failed: {exc}") from exc

    def _check_status(self, resp: Any) -> None:
        if resp.status_code >= 400:
            resp.raise_for_status()

    def _download(self, url: str) -> bytes:
        try:
            import httpx
        except ImportError as exc:
            raise unavailable(self.spec.id, f"missing httpx: {exc}") from exc
        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(url)
                r.raise_for_status()
                return r.content
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: download failed: {exc}") from exc

    def _save(self, images: list[bytes], output: Path) -> list[Path]:
        from PIL import Image as PILImage

        pil_images = []
        for blob in images:
            try:
                pil_images.append(PILImage.open(io.BytesIO(blob)).convert("RGB"))
            except Exception as exc:
                raise RenderFailed(f"{self.spec.id}: invalid image bytes: {exc}") from exc
        return write_images(pil_images, output)

    def _cost(self, request: RenderRequest) -> float:
        return self.spec.cost_per_image_usd * request.num_images

    def _build_payload(self, request: RenderRequest) -> dict[str, Any]:
        raise NotImplementedError

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _parse_response(self, raw: dict[str, Any]) -> list[bytes]:
        raise NotImplementedError

    def render(self, request: RenderRequest) -> RenderResult:
        self.require_available()
        t0 = time.monotonic()
        try:
            payload = self._build_payload(request)
            raw = self._execute(payload)
            images = self._parse_response(raw)
        except RenderUnavailable:
            raise
        except RenderFailed:
            raise
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: render error: {exc}") from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        output = request.output or (Path("generated") / "renders" / f"{self.spec.id}_output.png")
        try:
            paths = self._save(images, output)
        except Exception as exc:
            raise RenderFailed(f"{self.spec.id}: save failed: {exc}") from exc

        return RenderResult(
            engine_id=self.spec.id,
            model_id=self.spec.model_id,
            status="success",
            images=paths,
            latency_ms=latency_ms,
            cost_usd=self._cost(request),
            metadata={"provider_payload": _scrub_payload(payload)},
        )


class OpenAIGPTImageEngine(HostedAPIEngine):
    """OpenAI GPT Image 2 — text-to-image and edits."""

    api_base = "https://api.openai.com/v1"
    _timeout = 180

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.spec.api_key_env or "", "")
        return {"Authorization": f"Bearer {key}"}

    def _build_payload(self, request: RenderRequest) -> dict[str, Any]:
        size = _closest_openai_size(request.width, request.height)
        if request.mode in {"image_to_image", "edit", "inpaint"} and request.source_image:
            return self._build_edit_payload(request, size)
        return {
            "model": self.spec.model_id,
            "prompt": request.prompt,
            "n": request.num_images,
            "size": size,
            "quality": "high",
        }

    def _build_edit_payload(self, request: RenderRequest, size: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.spec.model_id,
            "prompt": request.prompt,
            "n": request.num_images,
            "size": size,
            "quality": "high",
            "input_fidelity": "high",
        }
        if request.source_image:
            payload["image"] = request.source_image
        if request.negative:
            payload["negative_prompt"] = request.negative
        return payload

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "image" in payload:
            return self._execute_edit(payload)
        return self._request("POST", "/images/generations", json=payload)

    def _execute_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise unavailable(self.spec.id, f"missing httpx: {exc}") from exc
        key = os.environ.get(self.spec.api_key_env or "", "")
        headers = {"Authorization": f"Bearer {key}"}
        multipart = getattr(httpx, "MultipartData")()
        fields: dict[str, Any] = {}
        for k, v in payload.items():
            if k == "image" and hasattr(v, "read"):
                fields["image"] = (Path(v.name).name if hasattr(v, "name") else "image.png", v.read(), "image/png")
            else:
                fields[k] = (None, str(v))
        for name, (filename, value, content_type) in fields.items():
            if filename is not None:
                multipart.add_field(name, value, filename=filename, content_type=content_type)
            else:
                multipart.add_field(name, value)
        url = f"{self.api_base}/images/edits"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=headers, files=multipart._fields, data=multipart._data)
        self._check_status(resp)
        return resp.json()

    def _parse_response(self, raw: dict[str, Any]) -> list[bytes]:
        out: list[bytes] = []
        for item in raw.get("data", []):
            if "b64_json" in item:
                out.append(base64.b64decode(item["b64_json"]))
            elif "url" in item:
                out.append(self._download(item["url"]))
        if not out:
            raise RenderFailed(f"{self.spec.id}: no images in response")
        return out


class ReveEngine(HostedAPIEngine):
    """Reve 2.1 — native 4K, style+content reference."""

    api_base = "https://api.reve.com/v1"
    _timeout = 120

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.spec.api_key_env or "", "")
        return {"Authorization": f"Bearer {key}"}

    def _build_payload(self, request: RenderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "size": f"{request.width}x{request.height}",
        }
        if request.mode != "text_to_image" and request.source_image:
            payload["input_image"] = _file_to_base64(request.source_image)
        return payload

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = "/create" if request_mode(payload) == "text_to_image" else "/edit"
        return self._request("POST", endpoint, json=payload)

    def _parse_response(self, raw: dict[str, Any]) -> list[bytes]:
        for key in ("data", "images", "result"):
            if raw.get(key):
                first = raw[key][0]
                if isinstance(first, dict):
                    if "url" in first:
                        return [self._download(first["url"])]
                    if "b64_json" in first:
                        return [base64.b64decode(first["b64_json"])]
        raise RenderFailed(f"{self.spec.id}: unexpected response shape")


class GeminiImageEngine(HostedAPIEngine):
    """Google Gemini 3 Pro Image (Nano Banana Pro)."""

    api_base = "https://generativelanguage.googleapis.com/v1beta"
    _timeout = 120

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _build_payload(self, request: RenderRequest) -> dict[str, Any]:
        contents: list[Any] = []
        for ref in request.style_refs:
            b64 = _file_to_base64(ref)
            contents.append({"inline_data": {"mime_type": "image/png", "data": b64}})
        contents.append({"text": request.prompt})
        return {
            "contents": contents,
            "generationConfig": {
                "response_modalities": ["IMAGE"],
                "imageConfig": {"aspect_ratio": _guess_aspect(request.width, request.height), "imageSize": "2K"},
            },
        }

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = os.environ.get(self.spec.api_key_env or "", "")
        if not key:
            raise RenderUnavailable(f"{self.spec.id} temporarily unavailable: set {self.spec.api_key_env}")
        url = f"/models/{self.spec.model_id}:generateContent?key={key}"
        return self._request("POST", url, json=payload)

    def _parse_response(self, raw: dict[str, Any]) -> list[bytes]:
        out: list[bytes] = []
        for candidate in raw.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inline_data")
                if inline and inline.get("data"):
                    out.append(base64.b64decode(inline["data"]))
        if not out:
            raise RenderFailed(f"{self.spec.id}: no image in response")
        return out


class BFLFlux2Engine(HostedAPIEngine):
    """Black Forest Labs FLUX.2 [max] — async polling, x-key auth."""

    api_base = "https://api.bfl.ai/v1"
    _timeout = 120
    _endpoint = "/flux-2-max"

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.spec.api_key_env or "", "")
        return {"x-key": key, "Content-Type": "application/json"}

    def _build_payload(self, request: RenderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "num_steps": request.steps or 20,
            "guidance": request.guidance if request.guidance is not None else 3.5,
            "samples": request.num_images,
        }
        if request.mode != "text_to_image" and request.source_image:
            payload["input_image"] = _file_to_base64_url(request.source_image)
        if request.negative:
            payload["negative_prompt"] = request.negative
        return payload

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        submit = self._request("POST", self._endpoint, json=payload)
        poll_url = submit.get("polling_url") or submit.get("url")
        if not poll_url:
            raise RenderFailed(f"{self.spec.id}: no polling_url in response")
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            result = self._request("GET", poll_url)
            status = result.get("status", "")
            if status == "Ready":
                return result
            if status in ("Error", "Failed"):
                raise RenderFailed(f"{self.spec.id}: BFL job failed: {result}")
        raise RenderFailed(f"{self.spec.id}: BFL polling timeout")

    def _parse_response(self, raw: dict[str, Any]) -> list[bytes]:
        url = raw.get("result", {}).get("sample")
        if not url:
            raise RenderFailed(f"{self.spec.id}: no sample URL in result")
        return [self._download(url)]


class OpenRouterImageEngine(HostedAPIEngine):
    """OpenRouter image router — one key, multi-model, allow_fallbacks."""

    api_base = "https://openrouter.ai/api/v1"
    _timeout = 120

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.spec.api_key_env or "", "")
        return {"Authorization": f"Bearer {key}"}

    def _build_payload(self, request: RenderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.spec.model_id,
            "prompt": request.prompt,
            "n": request.num_images,
            "aspect_ratio": _guess_aspect(request.width, request.height),
            "resolution": "2K",
        }
        refs = []
        for ref in request.style_refs:
            refs.append(_file_to_base64_url(ref))
        if request.source_image and request.mode != "text_to_image":
            refs.append(_file_to_base64_url(request.source_image))
        if refs:
            payload["input_references"] = refs
        if request.negative:
            payload["negative_prompt"] = request.negative
        return payload

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/images", json=payload)

    def _parse_response(self, raw: dict[str, Any]) -> list[bytes]:
        out: list[bytes] = []
        for item in raw.get("data", []):
            if item.get("b64_json"):
                out.append(base64.b64decode(item["b64_json"]))
        if not out:
            raise RenderFailed(f"{self.spec.id}: no images in response")
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for k in ("image", "input_image"):
        if k in out and hasattr(out[k], "read"):
            out[k] = "<file object>"
    return out


def _closest_openai_size(width: int, height: int) -> str:
    if max(width, height) <= 1024:
        return "1024x1024"
    if width >= height:
        return "1536x1024"
    return "1024x1536"


def _guess_aspect(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio >= 1.7:
        return "16:9"
    if ratio >= 1.3:
        return "4:3"
    if ratio <= 0.6:
        return "9:16"
    if ratio <= 0.8:
        return "3:4"
    return "1:1"


def _file_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _file_to_base64_url(path: Path) -> str:
    blob = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{blob}"


def request_mode(payload: dict[str, Any]) -> str:
    if payload.get("image") or payload.get("input_image"):
        return "edit"
    return "text_to_image"
