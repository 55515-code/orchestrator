from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import SubstrateRuntime

MAX_SNIPPET = 1200
NUMERIC_TOKEN_RE = re.compile(r"\b\d+\b")
UUID_TOKEN_RE = re.compile(
    r"\b[0-9a-fA-F]{8}\b(?:-[0-9a-fA-F]{4}\b){3}-[0-9a-fA-F]{12}\b"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: str | None, size: int = MAX_SNIPPET) -> str:
    if not value:
        return ""
    return value.strip()[:size]


def _command_key(command: str | list[str]) -> str:
    if isinstance(command, list):
        return " ".join(command).strip()
    return command.strip()


def _error_signature(command_key: str, error_text: str) -> str:
    normalized = error_text.lower()
    normalized = UUID_TOKEN_RE.sub("<uuid>", normalized)
    normalized = NUMERIC_TOKEN_RE.sub("<n>", normalized)
    digest = hashlib.sha1(
        f"{command_key}|{normalized[:800]}".encode("utf-8")
    ).hexdigest()
    return digest[:16]


def _load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": 1,
            "updated_at": None,
            "known_good": {},
            "errors": {},
            "tests": {"total": 0, "passed": 0, "failed": 0},
        }
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(payload, dict):
        return {
            "version": 1,
            "updated_at": None,
            "known_good": {},
            "errors": {},
            "tests": {"total": 0, "passed": 0, "failed": 0},
        }
    payload.setdefault("known_good", {})
    payload.setdefault("errors", {})
    payload.setdefault("tests", {"total": 0, "passed": 0, "failed": 0})
    return payload


def _save_index(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _utc_now()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_log(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _repo_change_snapshot(
    runtime: SubstrateRuntime, repo_slug: str | None
) -> dict[str, Any] | None:
    if not repo_slug:
        return None
    try:
        repo = runtime.resolve_repo(repo_slug)
    except KeyError:
        return None
    snapshot = runtime.inspect_repository(repo)
    return {
        "repo_slug": repo_slug,
        "branch": snapshot.get("branch"),
        "dirty": snapshot.get("dirty"),
        "last_commit_at": snapshot.get("last_commit_at"),
        "remote_url": snapshot.get("remote_url"),
    }


def record_execution(
    runtime: SubstrateRuntime,
    *,
    run_type: str,
    run_id: str | None,
    repo_slug: str | None,
    stage: str | None,
    command: str | list[str],
    status: str,
    exit_code: int | None,
    stdout: str | None = None,
    stderr: str | None = None,
    artifact: str | None = None,
    note: str | None = None,
    classify_as_test: bool = False,
) -> dict[str, Any]:
    command_line = _command_key(command)
    event = {
        "ts": _utc_now(),
        "run_type": run_type,
        "run_id": run_id,
        "repo_slug": repo_slug,
        "stage": stage,
        "command": command_line,
        "status": status,
        "exit_code": exit_code,
        "artifact": artifact,
        "note": note or "",
        "stdout_snippet": _truncate(stdout),
        "stderr_snippet": _truncate(stderr),
        "change_snapshot": _repo_change_snapshot(runtime, repo_slug),
    }
    _append_log(runtime.paths["learning_log"], event)

    index = _load_index(runtime.paths["learning_index"])
    known_good = index["known_good"]
    errors = index["errors"]
    tests = index["tests"]

    if classify_as_test:
        tests["total"] = int(tests.get("total", 0)) + 1

    if status == "success":
        entry = known_good.get(command_line, {})
        entry["command"] = command_line
        entry["run_type"] = run_type
        entry["repo_slug"] = repo_slug
        entry["stage"] = stage
        entry["last_success_at"] = event["ts"]
        entry["success_count"] = int(entry.get("success_count", 0)) + 1
        entry["last_run_id"] = run_id
        entry["artifact"] = artifact
        entry["stdout_snippet"] = event["stdout_snippet"]
        entry["change_snapshot"] = event["change_snapshot"]
        known_good[command_line] = entry
        if classify_as_test:
            tests["passed"] = int(tests.get("passed", 0)) + 1
    else:
        error_text = _truncate(stderr or note or "unknown error", 2400)
        signature = _error_signature(command_line, error_text)
        entry = errors.get(signature, {})
        entry["signature"] = signature
        entry["command"] = command_line
        entry["repo_slug"] = repo_slug
        entry["stage"] = stage
        entry["first_seen"] = entry.get("first_seen") or event["ts"]
        entry["last_seen"] = event["ts"]
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_run_id"] = run_id
        entry["artifact"] = artifact
        entry["error_snippet"] = error_text
        entry["change_snapshot"] = event["change_snapshot"]
        errors[signature] = entry
        if classify_as_test:
            tests["failed"] = int(tests.get("failed", 0)) + 1

    _save_index(runtime.paths["learning_index"], index)
    return event


def record_resolution_note(
    runtime: SubstrateRuntime,
    *,
    signature: str,
    resolution: str,
    path_reference: str | None = None,
) -> dict[str, Any]:
    index = _load_index(runtime.paths["learning_index"])
    errors = index["errors"]
    if signature not in errors:
        raise KeyError(f"Unknown error signature: {signature}")
    notes = errors[signature].get("resolution_notes")
    if not isinstance(notes, list):
        notes = []
    note = {
        "ts": _utc_now(),
        "resolution": resolution.strip(),
        "path_reference": path_reference,
    }
    notes.append(note)
    errors[signature]["resolution_notes"] = notes
    _save_index(runtime.paths["learning_index"], index)
    return note


def learning_payload(runtime: SubstrateRuntime, *, limit: int = 30) -> dict[str, Any]:
    index = _load_index(runtime.paths["learning_index"])
    known_good_entries = sorted(
        index["known_good"].values(),
        key=lambda item: item.get("last_success_at") or "",
        reverse=True,
    )[:limit]
    error_entries = sorted(
        index["errors"].values(),
        key=lambda item: item.get("last_seen") or "",
        reverse=True,
    )[:limit]
    return {
        "summary": {
            "known_good_total": len(index["known_good"]),
            "error_signatures_total": len(index["errors"]),
            "tests": index.get("tests", {}),
            "updated_at": index.get("updated_at"),
        },
        "known_good": known_good_entries,
        "errors": error_entries,
        "log_path": str(runtime.paths["learning_log"]),
        "index_path": str(runtime.paths["learning_index"]),
    }
