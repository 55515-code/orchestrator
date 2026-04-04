from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def _resolve_auth_path(codex_home: str | None) -> Path:
    if codex_home:
        return Path(codex_home) / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _resolve_executable_token(token: str) -> str | None:
    candidate = token.strip()
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    if Path(candidate).name == candidate:
        return candidate
    return None


def _resolve_codex_executable(codex_executable: str | None) -> tuple[str | None, str | None]:
    configured = (codex_executable or "").strip()
    configured_resolved = _resolve_executable_token(configured)
    if configured_resolved:
        return configured_resolved, None

    fallback = _resolve_executable_token("codex")
    if fallback:
        if configured and configured != "codex":
            return fallback, (
                f"Configured executable '{configured}' was unavailable; "
                f"using '{fallback}' from PATH."
            )
        return fallback, None
    return None, "codex executable not found on PATH or configured location."


def _is_git_repository(path: Path) -> bool:
    candidate = path
    if not candidate.exists():
        return False
    if candidate.is_file():
        candidate = candidate.parent
    for probe in [candidate, *candidate.parents]:
        if (probe / ".git").exists():
            return True
    return False


def _detect_rate_limited(output: str) -> bool:
    lowered = output.lower()
    return "429" in lowered or "too many requests" in lowered or "rate limit" in lowered


def _parse_retry_after_seconds(output: str) -> int | None:
    lowered = output.lower()
    if not lowered:
        return None
    patterns = [
        (r"retry after\s+(\d+)\s*(seconds|second|secs|sec)\b", 1),
        (r"retry after\s+(\d+)\s*(minutes|minute|mins|min)\b", 60),
        (r"retry after\s+(\d+)\s*(hours|hour|hrs|hr)\b", 3600),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, lowered)
        if match:
            try:
                return max(1, int(match.group(1)) * multiplier)
            except ValueError:
                return None
    compact_match = re.search(
        r"(?:retry after|try again in)\s+((?:\d+\s*[hms]\s*)+)",
        lowered,
    )
    if compact_match:
        total = 0
        for amount, unit in re.findall(r"(\d+)\s*([hms])", compact_match.group(1)):
            multiplier = {"h": 3600, "m": 60, "s": 1}[unit]
            total += int(amount) * multiplier
        if total > 0:
            return total
    return None


def codex_diagnostics(codex_executable: str, codex_home: str | None) -> dict:
    executable, resolver_warning = _resolve_codex_executable(codex_executable)
    installed = bool(executable)
    version = None
    error = None

    if installed:
        try:
            completed = subprocess.run(
                [executable, "--version"],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            version = (completed.stdout or completed.stderr).strip() or None
            if completed.returncode != 0 and not version:
                error = f"Non-zero exit ({completed.returncode}) when checking version."
        except Exception as exc:
            error = str(exc)
    else:
        error = resolver_warning or "codex executable not found on PATH or configured location."

    auth_path = _resolve_auth_path(codex_home)
    auth_file_exists = auth_path.exists()

    return {
        "installed": installed,
        "resolved_executable": executable,
        "version": version,
        "warning": resolver_warning,
        "auth_file_exists": auth_file_exists,
        "auth_file_path": str(auth_path),
        "error": error,
    }


def start_device_auth(codex_executable: str, codex_home: str | None) -> dict:
    executable, resolver_warning = _resolve_codex_executable(codex_executable)
    if not executable:
        return {"ok": False, "error": "codex executable not found."}
    env = None
    if codex_home:
        env = dict(os.environ)
        env.update({"CODEX_HOME": codex_home})

    try:
        completed = subprocess.run(
            [executable, "login", "--device-auth"],
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
            env=env,
        )
        output = "\n".join([_to_text(completed.stdout), _to_text(completed.stderr)]).strip()
    except subprocess.TimeoutExpired as exc:
        output = "\n".join([_to_text(exc.stdout), _to_text(exc.stderr)]).strip()
    except FileNotFoundError:
        return {"ok": False, "error": "codex executable not found."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    clean_output = _strip_ansi(output)
    url_match = re.search(r"https?://\S+", clean_output)
    code_match = re.search(r"\b[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})?\b", clean_output)
    verification_url = url_match.group(0) if url_match else None
    user_code = code_match.group(0) if code_match else None
    rate_limited = _detect_rate_limited(clean_output)
    retry_after_seconds = _parse_retry_after_seconds(clean_output)
    return {
        "ok": bool(verification_url or user_code),
        "verification_url": verification_url,
        "user_code": user_code,
        "raw_output": clean_output[:4000],
        "warning": resolver_warning,
        "rate_limited": rate_limited,
        "retry_after_seconds": retry_after_seconds,
        "error": None if (verification_url or user_code) else (clean_output[:500] or "No device-auth instructions detected from codex login output."),
    }


def test_connection(codex_executable: str, codex_home: str | None, working_directory: str | None = None) -> dict:
    executable, resolver_warning = _resolve_codex_executable(codex_executable)
    if not executable:
        return {"ok": False, "message": "codex executable not found."}
    env = None
    if codex_home:
        env = dict(os.environ)
        env.update({"CODEX_HOME": codex_home})
    working_dir = Path(working_directory or ".").resolve()
    command = [
        executable,
        "exec",
        "--sandbox",
        "read-only",
    ]
    if not _is_git_repository(working_dir):
        command.append("--skip-git-repo-check")
    command.append("Reply with exactly: connection_ok")
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
            env=env,
            cwd=working_dir,
        )
    except FileNotFoundError:
        return {"ok": False, "message": "codex executable not found."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    output = "\n".join([completed.stdout or "", completed.stderr or ""]).strip()
    ok = completed.returncode == 0 and "connection_ok" in output.lower()
    return {
        "ok": ok,
        "return_code": completed.returncode,
        "warning": resolver_warning,
        "output": output[:4000],
    }
