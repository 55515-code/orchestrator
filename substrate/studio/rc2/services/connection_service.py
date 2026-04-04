from __future__ import annotations

from datetime import datetime

from ...models import AppConfig
from ...schemas import ConnectionStatusOut


def remaining_auth_cooldown_seconds(config: AppConfig, now: datetime) -> int:
    if not config.auth_rate_limited_until:
        return 0
    remaining = int((config.auth_rate_limited_until - now).total_seconds())
    return max(0, remaining)


def next_backoff_seconds(current_hits: int) -> int:
    schedule = [60, 120, 300, 600, 900, 1800]
    index = min(max(current_hits, 0), len(schedule) - 1)
    return schedule[index]


def build_connection_status(config: AppConfig, diagnostics: dict, retry_after: int) -> ConnectionStatusOut:
    return ConnectionStatusOut(
        installed=diagnostics["installed"],
        resolved_executable=diagnostics["resolved_executable"],
        version=diagnostics["version"],
        auth_file_exists=diagnostics["auth_file_exists"],
        auth_file_path=diagnostics["auth_file_path"],
        error=diagnostics["error"],
        auth_mode=config.auth_mode or "chatgpt_account",
        api_key_configured=bool(config.api_key_secret_ref),
        rate_limited=retry_after > 0,
        retry_after_seconds=retry_after,
        rate_limited_until=config.auth_rate_limited_until,
    )

