from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...cloud_exec import assess_cloud_readiness, list_cloud_targets
from ...models import AppConfig
from ...rc2.services.settings_service import parse_env_map

def resolve_cloud_env(config: AppConfig, cloud_env_id: str | None) -> tuple[str | None, str]:
    if cloud_env_id and cloud_env_id.strip():
        return cloud_env_id.strip(), "job_override"
    default_env = (str(getattr(config, "default_cloud_env_id", "") or "")).strip()
    if default_env:
        return default_env, "global_default"
    return None, "none"


def compute_cloud_readiness(
    *,
    session: Session,
    config: AppConfig,
    cloud_env_id: str | None = None,
    working_directory: str | None = None,
) -> dict:
    resolved_env_id, env_source = resolve_cloud_env(config, cloud_env_id)
    env = dict(os.environ)
    if config.codex_home:
        env["CODEX_HOME"] = config.codex_home
    env.update(parse_env_map(config.global_env_json))
    readiness = assess_cloud_readiness(
        config=config,
        cloud_env_id=resolved_env_id,
        working_directory=working_directory or config.default_working_directory,
        env=env,
    )
    readiness["resolved_cloud_env_id"] = resolved_env_id
    readiness["env_source"] = env_source
    return readiness


def discover_cloud_targets(*, config: AppConfig, working_directory: str | None = None) -> dict:
    env = dict(os.environ)
    if config.codex_home:
        env["CODEX_HOME"] = config.codex_home
    env.update(parse_env_map(config.global_env_json))
    cwd = Path(working_directory or config.default_working_directory or ".").resolve()
    return list_cloud_targets(
        executable=(config.codex_executable or "codex").strip(),
        cwd=cwd,
        env=env,
    )


def assert_cloud_readiness(
    *,
    session: Session,
    config: AppConfig,
    cloud_env_id: str | None,
    working_directory: str | None,
) -> None:
    readiness = compute_cloud_readiness(
        session=session,
        config=config,
        cloud_env_id=cloud_env_id,
        working_directory=working_directory,
    )
    if not readiness["ready"]:
        raise HTTPException(status_code=409, detail={"message": "Cloud execution is not ready.", "readiness": readiness})
