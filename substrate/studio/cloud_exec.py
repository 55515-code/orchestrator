from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .models import AppConfig

FAILURE_AUTH_MISSING = "auth_missing"
FAILURE_AUTH_INVALID = "auth_invalid"
FAILURE_ENV_MISSING = "env_missing"
FAILURE_CLI_INCOMPATIBLE = "cli_incompatible"
FAILURE_PROVIDER_TRANSIENT = "provider_transient"
FAILURE_RATE_LIMITED = "rate_limited"
FAILURE_UNKNOWN = "unknown"


@dataclass
class CloudFailure:
    category: str
    retryable: bool
    summary: str


@dataclass
class CloudTarget:
    id: str
    label: str
    repo: str | None = None
    detail: str | None = None
    is_recommended: bool = False


def _resolve_auth_path(codex_home: str | None) -> Path:
    if codex_home:
        return Path(codex_home) / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _parse_args(codex_args: str | None) -> list[str]:
    if not codex_args:
        return []
    try:
        parsed = json.loads(codex_args)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        return shlex.split(codex_args)
    return []


def build_cloud_exec_command(
    executable: str,
    cloud_env_id: str,
    prompt: str,
    attempts: int,
    codex_args: str | None = None,
) -> list[str]:
    command = [
        executable,
        "cloud",
        "exec",
        "--env",
        cloud_env_id,
        "--attempts",
        str(max(1, attempts)),
    ]
    command.extend(_parse_args(codex_args))
    command.append(prompt)
    return command


def classify_cloud_failure(output: str, return_code: int | None) -> CloudFailure:
    text = (output or "").lower()

    if "unexpected argument" in text or "unrecognized option" in text or "unknown option" in text:
        return CloudFailure(
            FAILURE_CLI_INCOMPATIBLE,
            False,
            "Codex CLI does not support the requested cloud option in this version.",
        )
    if "not inside a trusted directory" in text or "trusted directory" in text:
        return CloudFailure(
            FAILURE_ENV_MISSING,
            False,
            "Working directory is not trusted by Codex CLI.",
        )
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return CloudFailure(FAILURE_RATE_LIMITED, True, "Cloud provider rate-limited this request.")
    if "missing bearer" in text or "unauthorized" in text or "401" in text or "forbidden" in text:
        return CloudFailure(FAILURE_AUTH_INVALID, False, "Cloud credentials are invalid for cloud execution.")
    if "not authenticated" in text or "login required" in text or "please login" in text or "not signed in" in text:
        return CloudFailure(FAILURE_AUTH_MISSING, False, "Cloud credentials are missing for cloud execution.")
    if "environment" in text and ("not found" in text or "invalid" in text or "missing" in text):
        return CloudFailure(FAILURE_ENV_MISSING, False, "Configured cloud environment is missing or invalid.")
    if "env" in text and ("not found" in text or "invalid" in text or "missing" in text):
        return CloudFailure(FAILURE_ENV_MISSING, False, "Configured cloud environment is missing or invalid.")
    if (
        "500" in text
        or "502" in text
        or "503" in text
        or "504" in text
        or "websocket" in text
        or "reconnecting" in text
        or "connection reset" in text
        or "timed out" in text
    ):
        return CloudFailure(FAILURE_PROVIDER_TRANSIENT, True, "Cloud provider returned a transient error.")
    if return_code == 0:
        return CloudFailure(FAILURE_UNKNOWN, False, "")
    return CloudFailure(FAILURE_UNKNOWN, False, "Cloud execution failed for an unknown reason.")


def _diagnostic_code_for_failure(output: str, category: str) -> str:
    text = (output or "").lower()
    if category == FAILURE_ENV_MISSING and "trusted directory" in text:
        return "trusted_directory_required"
    if category == FAILURE_AUTH_MISSING:
        return "auth_session_missing"
    if category == FAILURE_AUTH_INVALID:
        return "auth_session_invalid"
    if category == FAILURE_ENV_MISSING:
        return "cloud_env_missing"
    if category == FAILURE_CLI_INCOMPATIBLE:
        return "cli_incompatible"
    if category == FAILURE_RATE_LIMITED:
        return "provider_rate_limited"
    if category == FAILURE_PROVIDER_TRANSIENT:
        return "provider_transient_error"
    return "cloud_unknown_failure"


def recommended_actions(category: str) -> list[dict[str, str]]:
    if category in {FAILURE_AUTH_MISSING, FAILURE_AUTH_INVALID}:
        return [
            {"action": "reauth_account", "label": "Reconnect account"},
            {"action": "rerun_cloud_check", "label": "Re-check cloud readiness"},
            {"action": "enable_automation_credential", "label": "Enable automation credential"},
        ]
    if category == FAILURE_ENV_MISSING:
        return [
            {"action": "configure_cloud_env", "label": "Set cloud environment ID"},
            {"action": "rerun_cloud_check", "label": "Re-check cloud readiness"},
        ]
    if category == FAILURE_CLI_INCOMPATIBLE:
        return [
            {"action": "update_codex_cli", "label": "Update Codex CLI"},
            {"action": "rerun_cloud_check", "label": "Re-check cloud readiness"},
        ]
    if category in {FAILURE_PROVIDER_TRANSIENT, FAILURE_RATE_LIMITED}:
        return [
            {"action": "wait_and_retry", "label": "Wait and retry"},
            {"action": "rerun_cloud_check", "label": "Re-check cloud readiness"},
        ]
    return [{"action": "rerun_cloud_check", "label": "Re-check cloud readiness"}]


def parse_cloud_targets(output: str, working_directory: str | None = None) -> list[CloudTarget]:
    cwd_name = ""
    if working_directory:
        try:
            cwd_name = Path(working_directory).resolve().name.lower()
        except OSError:
            cwd_name = Path(working_directory).name.lower()

    lines = [line.rstrip() for line in (output or "").splitlines()]
    targets: list[CloudTarget] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("https://chatgpt.com/codex/tasks/"):
            index += 1
            continue

        label_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        repo_line = lines[index + 2].strip() if index + 2 < len(lines) else ""
        label = re.sub(r"^\[[^\]]+\]\s*", "", label_line).strip() or "Cloud target"
        repo = repo_line.split("  •", 1)[0].strip() or None
        target_id = repo or line.rsplit("/", 1)[-1]
        detail = repo_line or None
        repo_name = (repo or "").split("/", 1)[-1].lower()
        is_recommended = bool(cwd_name and cwd_name == repo_name)
        targets.append(
            CloudTarget(
                id=target_id,
                label=label,
                repo=repo,
                detail=detail,
                is_recommended=is_recommended,
            )
        )
        index += 3
    return targets


def list_cloud_targets(
    *,
    executable: str,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int = 60,
) -> dict:
    command = [executable, "cloud", "list"]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "category": FAILURE_PROVIDER_TRANSIENT,
            "summary": "Timed out while loading cloud targets.",
            "targets": [],
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "category": FAILURE_ENV_MISSING,
            "summary": f"Codex executable '{executable}' was not found.",
            "targets": [],
        }

    output = "\n".join([completed.stdout or "", completed.stderr or ""]).strip()
    if completed.returncode != 0:
        failure = classify_cloud_failure(output, completed.returncode)
        return {
            "ok": False,
            "category": failure.category,
            "summary": failure.summary,
            "targets": [],
        }

    targets = parse_cloud_targets(output, str(cwd))
    return {
        "ok": True,
        "category": None,
        "summary": None if targets else "No cloud targets were found for this account.",
        "targets": [target.__dict__ for target in targets],
    }


def run_cloud_exec(
    *,
    executable: str,
    cloud_env_id: str,
    prompt: str,
    attempts: int,
    codex_args: str | None,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
    max_retries: int = 2,
) -> dict:
    command = build_cloud_exec_command(executable, cloud_env_id, prompt, attempts, codex_args)
    retries = max(0, max_retries)
    backoff_seconds = [2, 5, 10]
    last_output = ""
    last_code: int | None = None
    last_failure = CloudFailure(FAILURE_UNKNOWN, False, "Cloud execution failed.")

    for index in range(retries + 1):
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
            output = "\n".join([completed.stdout or "", completed.stderr or ""]).strip()
            failure = classify_cloud_failure(output, completed.returncode)
            if completed.returncode == 0:
                return {
                    "ok": True,
                    "return_code": completed.returncode,
                    "output": output[:8000],
                    "command": command,
                    "failure_category": None,
                    "retryable": False,
                }
            last_output = output
            last_code = completed.returncode
            last_failure = failure
            if failure.retryable and index < retries:
                time.sleep(backoff_seconds[min(index, len(backoff_seconds) - 1)])
                continue
            break
        except subprocess.TimeoutExpired:
            last_output = "Cloud execution timed out."
            last_code = 124
            last_failure = CloudFailure(FAILURE_PROVIDER_TRANSIENT, True, "Cloud execution timed out.")
            if index < retries:
                time.sleep(backoff_seconds[min(index, len(backoff_seconds) - 1)])
                continue
            break
        except FileNotFoundError:
            last_output = f"Codex executable '{executable}' was not found."
            last_code = 127
            last_failure = CloudFailure(FAILURE_ENV_MISSING, False, "Codex executable is not available in runtime.")
            break

    return {
        "ok": False,
        "return_code": last_code,
        "output": last_output[:8000],
        "command": command,
        "failure_category": last_failure.category,
        "retryable": last_failure.retryable,
        "summary": last_failure.summary,
        "diagnostic_code": _diagnostic_code_for_failure(last_output, last_failure.category),
    }


def assess_cloud_readiness(
    *,
    config: AppConfig,
    cloud_env_id: str | None,
    working_directory: str | None,
    env: dict[str, str],
    env_source: str | None = None,
    resolved_cloud_env_id: str | None = None,
) -> dict:
    executable = (config.codex_executable or "codex").strip()
    resolved_executable = shutil.which(executable) or (executable if Path(executable).is_file() else None)
    if not resolved_executable:
        return {
            "ready": False,
            "category": FAILURE_ENV_MISSING,
            "summary": "Codex CLI is not available on this host.",
            "retryable": False,
            "diagnostic_code": "missing_codex_cli",
            "env_source": env_source,
            "resolved_cloud_env_id": resolved_cloud_env_id or cloud_env_id,
            "actions": recommended_actions(FAILURE_ENV_MISSING),
        }

    wd = Path(working_directory or config.default_working_directory or ".").resolve()
    if not wd.exists():
        return {
            "ready": False,
            "category": FAILURE_ENV_MISSING,
            "summary": f"Working directory '{wd}' does not exist.",
            "retryable": False,
            "diagnostic_code": "working_directory_missing",
            "env_source": env_source,
            "resolved_cloud_env_id": resolved_cloud_env_id or cloud_env_id,
            "actions": recommended_actions(FAILURE_ENV_MISSING),
        }

    env_id = (cloud_env_id or "").strip()
    if not env_id:
        return {
            "ready": False,
            "category": FAILURE_ENV_MISSING,
            "summary": "Cloud environment ID is required for cloud execution.",
            "retryable": False,
            "diagnostic_code": "cloud_env_unset",
            "env_source": env_source,
            "resolved_cloud_env_id": resolved_cloud_env_id,
            "actions": recommended_actions(FAILURE_ENV_MISSING),
        }

    auth_path = _resolve_auth_path(config.codex_home)
    if config.auth_mode == "chatgpt_account" and not auth_path.exists():
        return {
            "ready": False,
            "category": FAILURE_AUTH_MISSING,
            "summary": "No account auth session found for headless cloud execution.",
            "retryable": False,
            "diagnostic_code": "auth_session_missing",
            "env_source": env_source,
            "resolved_cloud_env_id": resolved_cloud_env_id or env_id,
            "actions": recommended_actions(FAILURE_AUTH_MISSING),
        }

    result = run_cloud_exec(
        executable=executable,
        cloud_env_id=env_id,
        prompt="Reply with exactly: cloud_ready_ok",
        attempts=1,
        codex_args=None,
        cwd=wd,
        env=env,
        timeout_seconds=90,
        max_retries=1,
    )
    if result["ok"]:
        return {
            "ready": True,
            "category": None,
            "summary": "Cloud execution is ready for scheduled runs.",
            "retryable": False,
            "diagnostic_code": "cloud_ready",
            "env_source": env_source,
            "resolved_cloud_env_id": resolved_cloud_env_id or env_id,
            "actions": [],
        }
    category = result.get("failure_category") or FAILURE_UNKNOWN
    return {
        "ready": False,
        "category": category,
        "summary": result.get("summary") or "Cloud readiness check failed.",
        "retryable": bool(result.get("retryable")),
        "diagnostic_code": result.get("diagnostic_code") or _diagnostic_code_for_failure(result.get("output") or "", category),
        "env_source": env_source,
        "resolved_cloud_env_id": resolved_cloud_env_id or env_id,
        "actions": recommended_actions(category),
    }
