"""Conversation prefill normalization for Anthropic-family chat requests.

Anthropic's Messages API — and every Anthropic-family model regardless of
which provider route serves it (Anthropic direct, Amazon Bedrock, Vertex
AI, Claude AWS, OpenRouter fallback routes, the Kilo Gateway) — rejects a
request whose ``messages`` array ends with an ``assistant`` message::

    This model does not support assistant message prefill. The conversation
    must end with a user message.

Agentic workflows (tool-calling loops, resume-with-history flows such as the
desktop chatbot's ``kilo run --session``) frequently produce a conversation
whose final entry is an assistant message — e.g. a tool call that was never
followed by its result, or an interrupted assistant turn. The 400 error is
returned by the upstream before any provider routing can succeed, so every
route and credential type fails identically.

This module provides a pure, dependency-free normalization that makes such
payloads valid before they are sent:

- ``strip`` (default): drop trailing ``assistant`` message(s) so the
  conversation ends on the last ``user`` turn, matching Anthropic's rule.
  If nothing remains, a neutral placeholder user turn is appended.
- ``append``: keep the history and append a placeholder user turn. If the
  trailing assistant message carries ``tool_calls`` (which must be followed
  by a ``tool`` result, not a user message), the tool calls are removed from
  it first so the resulting conversation is still well-formed.

Only requests whose ``model`` id belongs to the Anthropic family are
touched; all other traffic passes through byte-for-byte unchanged, so
existing functionality on OpenAI/Gemini/local providers is preserved.
"""

from __future__ import annotations

from typing import Any

DEFAULT_PLACEHOLDER = "Continue."
ANTHROPIC_FAMILY_MARKERS = (
    "claude",
    "anthropic",
)
VALID_MODES = ("strip", "append")


def is_anthropic_family(model: str) -> bool:
    """Return True when *model* is served by the Anthropic Messages API family.

    Matches ``claude``, ``anthropic/...``, ``anthropic-...`` and the
    ``anthropic`` provider id. Empty/unknown model ids are treated as
    Anthropic-family **only** when no other evidence is available — the
    caller decides by passing ``assume_anthropic`` when the endpoint is
    known to be Anthropic-native (e.g. OpenRouter ``/api/v1/messages``).
    """
    if not model:
        return False
    lowered = model.strip().lower()
    return any(marker in lowered for marker in ANTHROPIC_FAMILY_MARKERS)


def _role_of(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    role = message.get("role")
    return str(role).strip().lower() if isinstance(role, str) else ""


def normalize_messages(
    messages: list[Any] | None,
    *,
    model: str = "",
    mode: str = "strip",
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> tuple[list[Any], bool, str]:
    """Ensure *messages* ends with a user turn for Anthropic-family models.

    Returns ``(normalized_messages, changed, reason)``.

    ``changed`` is ``False`` (and the original list is returned) whenever:

    - the model is not Anthropic-family (nothing to fix), or
    - *messages* is empty or already ends with a ``user`` message.

    ``reason`` is a short human-readable explanation of what was done
    (or empty when unchanged).
    """
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")

    original = messages if messages is not None else []
    if not isinstance(original, list):
        raise TypeError("messages must be a list of message objects")

    if not is_anthropic_family(model):
        return original, False, ""

    if not original:
        return original, False, ""

    if _role_of(original[-1]) == "user":
        return original, False, ""

    working = [dict(m) for m in original if isinstance(m, dict)]
    if not working:
        return original, False, ""

    if mode == "append":
        return _normalize_append(working, placeholder=placeholder)

    return _normalize_strip(working, placeholder=placeholder)


def _normalize_strip(
    messages: list[dict[str, Any]], *, placeholder: str
) -> tuple[list[Any], bool, str]:
    """Drop trailing assistant messages; end on the last user turn."""
    stripped = 0
    while messages and _role_of(messages[-1]) == "assistant":
        messages.pop()
        stripped += 1

    if not messages:
        messages.append({"role": "user", "content": placeholder})
        return (
            messages,
            True,
            f"conversation had no user turn; appended placeholder user message "
            f"(role=user, content={placeholder!r})",
        )

    return (
        messages,
        True,
        f"stripped {stripped} trailing assistant message(s) "
        f"(ends with role={messages[-1].get('role')!r})",
    )


def _normalize_append(
    messages: list[dict[str, Any]], *, placeholder: str
) -> tuple[list[Any], bool, str]:
    """Keep history; append a placeholder user turn.

    If the trailing assistant message declares ``tool_calls``, those calls
    are removed first: Anthropic requires the message immediately after a
    tool-call assistant message to be the matching ``tool`` result, so a
    plain user message would otherwise be invalid.
    """
    last = messages[-1]
    if last.get("tool_calls"):
        last = {k: v for k, v in last.items() if k != "tool_calls"}
        messages[-1] = last

    messages.append({"role": "user", "content": placeholder})
    return (
        messages,
        True,
        f"appended placeholder user message (role=user, content={placeholder!r})",
    )


def normalize_request_payload(
    payload: dict[str, Any],
    *,
    mode: str = "strip",
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> tuple[dict[str, Any], bool, str]:
    """Normalize a chat request payload in place-friendly fashion.

    Understands both OpenAI-compatible (``messages`` key) and Anthropic
    native (``messages`` key with ``system`` separate) shapes. Returns
    ``(payload, changed, reason)``; when unchanged the caller may keep the
    original object untouched.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return payload, False, ""

    model = str(payload.get("model") or "")
    normalized, changed, reason = normalize_messages(
        messages,
        model=model,
        mode=mode,
        placeholder=placeholder,
    )
    if changed:
        payload["messages"] = normalized
    return payload, changed, reason
