from __future__ import annotations

from datetime import datetime
from datetime import timezone

from substrate.studio.models import AppConfig
from substrate.studio.rc2.services.connection_service import build_connection_status
from substrate.studio.rc2.services.connection_service import remaining_auth_cooldown_seconds


def test_build_connection_status_handles_partial_diagnostics() -> None:
    config = AppConfig(auth_mode=None, api_key_secret_ref=None)

    status = build_connection_status(config, diagnostics={"installed": True}, retry_after=0)

    assert status.installed is True
    assert status.resolved_executable is None
    assert status.auth_mode == "chatgpt_account"
    assert status.api_key_configured is False


def test_remaining_auth_cooldown_clamps_negative_values() -> None:
    now = datetime(2026, 4, 4, 0, 0, 30)
    config = AppConfig(auth_rate_limited_until=datetime(2026, 4, 4, 0, 0, 0))

    assert remaining_auth_cooldown_seconds(config, now) == 0


def test_remaining_auth_cooldown_handles_naive_and_aware_datetimes() -> None:
    now = datetime(2026, 4, 4, 0, 0, 0)
    config = AppConfig(auth_rate_limited_until=datetime(2026, 4, 4, 0, 1, 0, tzinfo=timezone.utc))

    assert remaining_auth_cooldown_seconds(config, now) == 60
