from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ...models import AppConfig
from ...runtime_config import RuntimeOptions
from ...schemas import SettingsOut, SettingsUpdate


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_env_map(env_json: str | None) -> dict[str, str]:
    if not env_json:
        return {}
    try:
        parsed = json.loads(env_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


def _is_executable_available(raw_executable: str | None) -> bool:
    executable = (raw_executable or "").strip()
    if not executable:
        return False
    candidate = Path(executable).expanduser()
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return True
    return bool(shutil.which(executable))


def ensure_app_config(session: Session) -> AppConfig:
    config = session.query(AppConfig).filter(AppConfig.id == 1).one_or_none()
    if config:
        changed = False
        executable_healed = False
        if not _is_executable_available(config.codex_executable) and shutil.which("codex"):
            # Self-heal stale absolute paths (for example old test/runtime temp dirs).
            config.codex_executable = "codex"
            changed = True
            executable_healed = True
        codex_home = (config.codex_home or "").strip()
        if codex_home:
            home_path = Path(codex_home).expanduser()
            default_home = Path.home() / ".codex"
            if not home_path.exists() and default_home.exists():
                config.codex_home = str(default_home)
                changed = True
        if (
            executable_healed
            and (config.last_connection_message or "").strip().lower().find("executable not found")
            != -1
        ):
            config.last_connection_status = None
            config.last_connection_message = None
            changed = True
        if config.default_notification_to is None:
            config.default_notification_to = "adarnell@concepts2code.com"
            changed = True
        if changed:
            config.updated_at = utcnow_naive()
            session.add(config)
            session.commit()
            session.refresh(config)
        return config
    config = AppConfig(
        id=1,
        auth_mode="chatgpt_account",
        notifications_enabled=True,
        default_notification_to="adarnell@concepts2code.com",
        updated_at=utcnow_naive(),
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def to_settings_out(config: AppConfig) -> SettingsOut:
    return SettingsOut(
        codex_executable=config.codex_executable,
        codex_home=config.codex_home,
        default_working_directory=config.default_working_directory,
        default_cloud_env_id=getattr(config, "default_cloud_env_id", None),
        api_key_env_var=config.api_key_env_var,
        global_env_json=config.global_env_json,
        deployment_task_name=config.deployment_task_name,
        deployment_host=config.deployment_host,
        deployment_port=config.deployment_port,
        deployment_user=config.deployment_user,
        auth_mode=config.auth_mode or "chatgpt_account",
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port or 587,
        smtp_security=config.smtp_security or "starttls",
        smtp_username=config.smtp_username,
        smtp_from_email=config.smtp_from_email,
        notifications_enabled=True if config.notifications_enabled is None else bool(config.notifications_enabled),
        default_notification_to=config.default_notification_to or "adarnell@concepts2code.com",
        api_key_configured=bool(config.api_key_secret_ref),
        smtp_password_configured=bool(config.smtp_password_secret_ref),
        last_connection_status=config.last_connection_status,
        last_connection_message=config.last_connection_message,
        auth_rate_limited_until=config.auth_rate_limited_until,
        auth_rate_limit_hits=config.auth_rate_limit_hits or 0,
    )


def apply_settings_update(config: AppConfig, payload: SettingsUpdate) -> AppConfig:
    for key, value in payload.model_dump().items():
        setattr(config, key, value)
    config.updated_at = utcnow_naive()
    return config


def apply_runtime_defaults(config: AppConfig, runtime_options: RuntimeOptions, project_root) -> AppConfig:
    if not runtime_options.desktop_mode:
        return config

    changed = False
    desktop_codex_home = str(runtime_options.codex_home_dir(project_root))
    if not (config.codex_home or "").strip():
        config.codex_home = desktop_codex_home
        changed = True

    if (config.default_working_directory or ".").strip() == ".":
        config.default_working_directory = str(Path.home())
        changed = True

    if runtime_options.bundled_codex_executable and (config.codex_executable or "codex").strip() == "codex":
        config.codex_executable = runtime_options.bundled_codex_executable
        changed = True

    if changed:
        config.updated_at = utcnow_naive()
    return config
