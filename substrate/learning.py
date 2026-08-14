"""Execution learning index for the Local Agent Substrate.

This module records run outcomes to a local log and JSON index so that the
orchestrator can recognize known-good commands and recurring error signatures.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import _utils
from .registry import SubstrateRuntime

MAX_SNIPPET = 1200
NUMERIC_TOKEN_RE = re.compile(r"\b\d+\b")
UUID_TOKEN_RE = re.compile(
    r"\b[0-9a-fA-F]{8}\b(?:-[0-9a-fA-F]{4}\b){3}-[0-9a-fA-F]{12}\b"
)


def _truncate(value: str | None, size: int = MAX_SNIPPET) -> str:
    """Return *value* trimmed to *size* characters, or an empty string."""
    if not value:
        return ""
    return value.strip()[:size]


def _command_key(command: str | list[str]) -> str:
    """Normalize a command into a single string for indexing."""
    if isinstance(command, list):
        return " ".join(command).strip()
    return command.strip()


def _error_signature(command_key: str, error_text: str) -> str:
    """Create a stable, de-identified signature for an error text.

    UUIDs and numeric tokens are replaced before hashing so that functionally
    identical errors do not create duplicate index entries. SHA-256 is used
    for collision resistance even though the stored digest is truncated.
    """
    normalized = error_text.lower()
    normalized = UUID_TOKEN_RE.sub("<uuid>", normalized)
    normalized = NUMERIC_TOKEN_RE.sub("<n>", normalized)
    digest = hashlib.sha256(
        f"{command_key}|{normalized[:800]}".encode()
    ).hexdigest()
    return digest[:16]


def _load_index(path: Path) -> dict[str, Any]:
    """Load the learning index, returning an empty default if missing/invalid."""
    default = {
        "version": 1,
        "updated_at": None,
        "known_good": {},
        "errors": {},
        "tests": {"total": 0, "passed": 0, "failed": 0},
    }
    payload = _utils.load_json(path, default=default)
    payload.setdefault("known_good", {})
    payload.setdefault("errors", {})
    payload.setdefault("tests", {"total": 0, "passed": 0, "failed": 0})
    return payload


def _save_index(path: Path, payload: dict[str, Any]) -> None:
    """Persist the learning index to *path*."""
    payload["updated_at"] = _utils.utc_now()
    _utils.write_json(path, payload)


def _append_log(path: Path, event: dict[str, Any]) -> None:
    """Append a single JSON line to the learning log at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _repo_change_snapshot(
    runtime: SubstrateRuntime, repo_slug: str | None
) -> dict[str, Any] | None:
    """Capture a minimal repository snapshot for the learning log."""
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
    """Record a single execution outcome to the learning log and index.

    Args:
        runtime: The substrate runtime used to resolve repo metadata.
        run_type: Category of run (e.g. ``task``, ``chain``).
        run_id: Optional run identifier.
        repo_slug: Optional repository slug.
        stage: Lifecycle stage (``local``, ``hosted_dev``, ``production``).
        command: Command string or argument list.
        status: Outcome string such as ``success`` or ``error``.
        exit_code: Shell exit code if applicable.
        stdout: Optional captured standard output.
        stderr: Optional captured standard error.
        artifact: Optional artifact path or identifier.
        note: Optional free-form note.
        classify_as_test: Whether to increment the test ledger counters.

    Returns:
        A payload describing the updated learning index entry.
    """
    command_line = _command_key(command)
    event = {
        "ts": _utils.utc_now(),
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
        if stdout:
            entry["last_stdout_snippet"] = event["stdout_snippet"]
        if stderr:
            entry["last_stderr_snippet"] = event["stderr_snippet"]
        if artifact:
            entry["last_artifact"] = artifact
        known_good[command_line] = entry
        if classify_as_test:
            tests["passed"] = int(tests.get("passed", 0)) + 1
    elif status == "error" and stderr:
        signature = _error_signature(command_line, stderr)
        entry = errors.get(signature, {})
        entry["signature"] = signature
        entry["command"] = command_line
        entry["run_type"] = run_type
        entry["repo_slug"] = repo_slug
        entry["stage"] = stage
        entry["last_seen_at"] = event["ts"]
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["stderr_snippet"] = event["stderr_snippet"]
        entry["exit_codes"] = list(
            set(entry.get("exit_codes", [])) | ({exit_code} if exit_code is not None else set())
        )
        errors[signature] = entry
        if classify_as_test:
            tests["failed"] = int(tests.get("failed", 0)) + 1

    _save_index(runtime.paths["learning_index"], index)
    return event


def record_resolution_note(
    runtime: SubstrateRuntime,
    *,
    command: str | list[str],
    note: str,
) -> dict[str, Any]:
    """Attach a free-form resolution note to a known-good command entry."""
    index = _load_index(runtime.paths["learning_index"])
    command_line = _command_key(command)
    entry = index["known_good"].setdefault(command_line, {"command": command_line})
    notes = entry.setdefault("resolution_notes", [])
    notes.append({"ts": _utils.utc_now(), "note": note})
    _save_index(runtime.paths["learning_index"], index)
    return entry


def _bounded_items(mapping: dict[str, Any], limit: int) -> dict[str, Any]:
    """Return *mapping* truncated to at most ``limit`` entries.

    Insertion order is preserved. A non-positive ``limit`` is treated as
    unbounded so callers that opt out of bounding always receive the full
    set; when ``limit`` already covers every entry the original mapping is
    returned unchanged to keep the common (small-index) case lossless.
    """
    if limit <= 0 or limit >= len(mapping):
        return mapping
    return dict(list(mapping.items())[:limit])


def learning_payload(runtime: SubstrateRuntime, limit: int = 30) -> dict[str, Any]:
    """Return the full learning index augmented with runtime metadata.

    ``limit`` bounds the number of entries returned for the potentially
    unbounded ``known_good`` and ``errors`` collections so that API consumers
    receive a bounded payload. The aggregate ``tests`` counters are always
    reported in full. The default mirrors the historical API default.
    """
    index = _load_index(runtime.paths["learning_index"])
    return {
        "learning_index_path": str(runtime.paths["learning_index"]),
        "learning_log_path": str(runtime.paths["learning_log"]),
        "updated_at": index.get("updated_at"),
        "known_good": _bounded_items(index.get("known_good", {}), limit),
        "errors": _bounded_items(index.get("errors", {}), limit),
        "tests": index.get("tests", {"total": 0, "passed": 0, "failed": 0}),
    }
