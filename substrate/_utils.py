"""Shared utility helpers for the Local Agent Substrate.

This module collects small, duplicated helpers that previously lived scattered
across substrate modules. Centralizing them reduces duplication, makes testing
straightforward, and provides a single place to update conventions such as
serialization formats or timestamp precision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def utc_now_iso() -> str:
    """Alias of :func:`utc_now` for modules that prefer an explicit ISO suffix."""
    return utc_now()


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from *path* or return an empty dict if missing.

    Raises:
        ValueError: If the file exists but does not contain a YAML mapping.
    """
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must be a YAML mapping.")
    return payload


def ensure_list(payload: Any, field: str) -> list[Any]:
    """Return *payload* if it is a list, or raise a descriptive error."""
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError(f"{field} must be a list.")
    return payload


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load a JSON object from *path* or return *default* if missing/invalid.

    The *default* is returned as-is; callers that mutate it are responsible for
    copying it if mutation must not affect future defaults.
    """
    if default is None:
        default = {}
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(payload, dict):
        return default
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Serialize *payload* to *path* as indented UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def percentile(values: list[float], q: float) -> float:
    """Return the *q* percentile of *values* using nearest-rank interpolation.

    Args:
        values: A list of numeric values.
        q: A percentile in the range [0.0, 1.0].

    Returns:
        The interpolated percentile value, or ``0.0`` if *values* is empty.
    """
    if not values:
        return 0.0
    if not 0.0 <= q <= 1.0:
        raise ValueError("percentile q must be between 0.0 and 1.0")
    ordered = sorted(values)
    index = round(q * (len(ordered) - 1))
    return float(ordered[index])


def p95(values: list[float]) -> float:
    """Return the 95th percentile of *values*."""
    return percentile(values, 0.95)


def median(values: list[float]) -> float:
    """Return the median of *values*, or ``0.0`` if empty."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0
