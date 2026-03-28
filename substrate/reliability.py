from __future__ import annotations

import hashlib
import json
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, TypeVar

FailureKind = Literal["transient", "terminal"]
CheckpointScope = Literal["run", "step", "recovery"]
IdempotencyStatus = Literal["in_progress", "completed"]
TaskLifecycleState = Literal[
    "queued",
    "dispatched",
    "running",
    "healthy",
    "suspect_stuck",
    "stuck_confirmed",
    "terminate_requested",
    "terminated",
    "respawn_pending",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "aborted_kill_switch",
]
RecoveryAction = Literal["none", "retry", "respawn"]

T = TypeVar("T")

_TRANSIENT_HINTS = (
    "timeout",
    "temporarily unavailable",
    "temporarily overloaded",
    "connection reset",
    "connection aborted",
    "service unavailable",
    "too many requests",
    "rate limit",
    "throttle",
    "try again",
    "econnreset",
    "econnrefused",
    "network",
)

_TERMINAL_HINTS = (
    "invalid api key",
    "authentication",
    "unauthorized",
    "forbidden",
    "unsupported",
    "bad request",
    "policy violation",
    "safety",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True, frozen=True)
class FailureClassification:
    kind: FailureKind
    reason: str


def classify_failure(exc: BaseException) -> FailureClassification:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return FailureClassification(kind="transient", reason="network_or_timeout")
    if isinstance(
        exc,
        (
            ValueError,
            TypeError,
            KeyError,
            PermissionError,
            FileNotFoundError,
            NotImplementedError,
        ),
    ):
        return FailureClassification(kind="terminal", reason="deterministic_or_policy")

    payload = f"{type(exc).__name__}: {exc}".lower()
    if any(token in payload for token in _TRANSIENT_HINTS):
        return FailureClassification(kind="transient", reason="matched_transient_pattern")
    if any(token in payload for token in _TERMINAL_HINTS):
        return FailureClassification(kind="terminal", reason="matched_terminal_pattern")
    return FailureClassification(kind="terminal", reason="default_terminal")


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.2
    retryable_kinds: frozenset[FailureKind] = field(
        default_factory=lambda: frozenset({"transient"})
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be >= 0")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be >= 0")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio must be >= 0")

    def backoff_delay(self, attempt: int, *, rng: random.Random | None = None) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        exponential = self.base_delay_seconds * (2 ** (attempt - 1))
        bounded = min(self.max_delay_seconds, exponential)
        jitter_window = bounded * self.jitter_ratio
        if jitter_window <= 0:
            return bounded
        generator = rng if rng is not None else random
        offset = generator.uniform(-jitter_window, jitter_window)
        return max(0.0, min(self.max_delay_seconds, bounded + offset))


@dataclass(slots=True, frozen=True)
class RetryEvent:
    attempt: int
    max_attempts: int
    delay_seconds: float
    classification: FailureClassification
    error: BaseException


@dataclass(slots=True, frozen=True)
class RestartDecision:
    next_state: TaskLifecycleState
    action: RecoveryAction
    reason: str


def decide_restart_action(
    *,
    attempts_used: int,
    max_attempts: int,
    respawns_used: int,
    max_respawns: int,
    respawn_enabled: bool,
    failure_state: TaskLifecycleState,
) -> RestartDecision:
    if attempts_used < 1:
        raise ValueError("attempts_used must be >= 1")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if respawns_used < 0:
        raise ValueError("respawns_used must be >= 0")
    if max_respawns < 0:
        raise ValueError("max_respawns must be >= 0")

    if failure_state == "aborted_kill_switch":
        return RestartDecision(
            next_state="aborted_kill_switch",
            action="none",
            reason="kill_switch_abort",
        )

    if attempts_used >= max_attempts:
        return RestartDecision(
            next_state="failed_terminal",
            action="none",
            reason="retry_ceiling_reached",
        )

    if (
        failure_state in {"terminated", "stuck_confirmed", "terminate_requested"}
        and respawn_enabled
        and respawns_used < max_respawns
    ):
        return RestartDecision(
            next_state="respawn_pending",
            action="respawn",
            reason="respawn_budget_available",
        )

    return RestartDecision(
        next_state="respawn_pending",
        action="retry",
        reason="retry_budget_available",
    )


def execute_with_retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    classifier: Callable[[BaseException], FailureClassification] = classify_failure,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[RetryEvent], None] | None = None,
    rng: random.Random | None = None,
) -> T:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            classification = classifier(exc)
            if attempt >= policy.max_attempts:
                raise
            if classification.kind not in policy.retryable_kinds:
                raise
            delay = policy.backoff_delay(attempt, rng=rng)
            if on_retry is not None:
                on_retry(
                    RetryEvent(
                        attempt=attempt,
                        max_attempts=policy.max_attempts,
                        delay_seconds=delay,
                        classification=classification,
                        error=exc,
                    )
                )
            sleep(delay)
    raise RuntimeError("Retry policy exhausted without returning or raising")


@dataclass(slots=True, frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    run_id: str
    scope: CheckpointScope
    status: str
    stage: str
    step_id: str | None
    idempotency_key: str | None
    created_at: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "scope": self.scope,
            "status": self.status,
            "stage": self.stage,
            "step_id": self.step_id,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CheckpointRecord:
        payload = raw.get("payload")
        parsed_payload = payload if isinstance(payload, dict) else {}
        return cls(
            checkpoint_id=str(raw["checkpoint_id"]),
            run_id=str(raw["run_id"]),
            scope=str(raw["scope"]),  # type: ignore[arg-type]
            status=str(raw.get("status", "unknown")),
            stage=str(raw.get("stage", "local")),
            step_id=str(raw["step_id"]) if raw.get("step_id") is not None else None,
            idempotency_key=(
                str(raw["idempotency_key"])
                if raw.get("idempotency_key") is not None
                else None
            ),
            created_at=str(raw.get("created_at") or _utc_now_iso()),
            payload=parsed_payload,
        )


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _checkpoint_path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.jsonl"

    def write_checkpoint(self, record: CheckpointRecord) -> CheckpointRecord:
        path = self._checkpoint_path(record.run_id)
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return record

    def create_checkpoint(
        self,
        *,
        run_id: str,
        scope: CheckpointScope,
        status: str,
        stage: str,
        step_id: str | None = None,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        record = CheckpointRecord(
            checkpoint_id=uuid.uuid4().hex,
            run_id=run_id,
            scope=scope,
            status=status,
            stage=stage,
            step_id=step_id,
            idempotency_key=idempotency_key,
            created_at=_utc_now_iso(),
            payload=payload or {},
        )
        return self.write_checkpoint(record)

    def read_checkpoints(
        self, run_id: str, *, scope: CheckpointScope | None = None
    ) -> list[CheckpointRecord]:
        path = self._checkpoint_path(run_id)
        if not path.exists():
            return []
        records: list[CheckpointRecord] = []
        with self._lock, path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    continue
                record = CheckpointRecord.from_dict(parsed)
                if scope is not None and record.scope != scope:
                    continue
                records.append(record)
        return records

    def latest_checkpoint(
        self,
        run_id: str,
        *,
        scope: CheckpointScope | None = None,
        step_id: str | None = None,
    ) -> CheckpointRecord | None:
        records = self.read_checkpoints(run_id, scope=scope)
        for record in reversed(records):
            if step_id is not None and record.step_id != step_id:
                continue
            return record
        return None


@dataclass(slots=True, frozen=True)
class IdempotencyRecord:
    key: str
    status: IdempotencyStatus
    created_at: str
    updated_at: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IdempotencyRecord:
        payload = raw.get("payload")
        parsed_payload = payload if isinstance(payload, dict) else {}
        return cls(
            key=str(raw["key"]),
            status=str(raw.get("status", "in_progress")),  # type: ignore[arg-type]
            created_at=str(raw.get("created_at") or _utc_now_iso()),
            updated_at=str(raw.get("updated_at") or _utc_now_iso()),
            payload=parsed_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "payload": self.payload,
        }


class IdempotencyStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _state_path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def _load(self, run_id: str) -> dict[str, dict[str, Any]]:
        path = self._state_path(run_id)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, dict)
        }

    def _save(self, run_id: str, data: dict[str, dict[str, Any]]) -> None:
        path = self._state_path(run_id)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def begin(
        self, run_id: str, key: str, *, payload: dict[str, Any] | None = None
    ) -> IdempotencyRecord:
        with self._lock:
            data = self._load(run_id)
            existing = data.get(key)
            if existing is not None:
                return IdempotencyRecord.from_dict(existing)
            now = _utc_now_iso()
            record = IdempotencyRecord(
                key=key,
                status="in_progress",
                created_at=now,
                updated_at=now,
                payload=payload or {},
            )
            data[key] = record.to_dict()
            self._save(run_id, data)
            return record

    def mark_completed(
        self,
        run_id: str,
        key: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> IdempotencyRecord:
        with self._lock:
            data = self._load(run_id)
            existing = data.get(key)
            now = _utc_now_iso()
            created_at = (
                str(existing.get("created_at")) if isinstance(existing, dict) else now
            )
            merged_payload: dict[str, Any] = {}
            if isinstance(existing, dict) and isinstance(existing.get("payload"), dict):
                merged_payload.update(existing["payload"])
            if payload:
                merged_payload.update(payload)
            record = IdempotencyRecord(
                key=key,
                status="completed",
                created_at=created_at,
                updated_at=now,
                payload=merged_payload,
            )
            data[key] = record.to_dict()
            self._save(run_id, data)
            return record

    def get(self, run_id: str, key: str) -> IdempotencyRecord | None:
        with self._lock:
            data = self._load(run_id)
            existing = data.get(key)
            if existing is None:
                return None
            return IdempotencyRecord.from_dict(existing)

    def is_completed(self, run_id: str, key: str) -> bool:
        record = self.get(run_id, key)
        return bool(record and record.status == "completed")


def make_idempotency_key(*parts: str) -> str:
    normalized = "::".join(part.strip() for part in parts if part)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class ExecutionTarget:
    provider: str
    model: str


class FailoverHook(Protocol):
    def next_target(
        self,
        *,
        run_id: str,
        step_id: str | None,
        attempt: int,
        current: ExecutionTarget,
        failure: FailureClassification,
        error: BaseException,
    ) -> ExecutionTarget | None: ...


class ProviderFailoverHook:
    def __init__(
        self,
        *,
        fallback_order: list[str],
        provider_models: dict[str, str],
        allow_terminal_failover: bool = False,
    ) -> None:
        ordered: list[str] = []
        for provider in fallback_order:
            normalized = provider.strip()
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        self.fallback_order = tuple(ordered)
        self.provider_models = dict(provider_models)
        self.allow_terminal_failover = allow_terminal_failover

    def next_target(
        self,
        *,
        run_id: str,
        step_id: str | None,
        attempt: int,
        current: ExecutionTarget,
        failure: FailureClassification,
        error: BaseException,
    ) -> ExecutionTarget | None:
        _ = run_id, step_id, attempt, error
        if failure.kind == "terminal" and not self.allow_terminal_failover:
            return None
        ordered_providers = [current.provider, *self.fallback_order]
        unique_order: list[str] = []
        for provider in ordered_providers:
            if provider not in unique_order:
                unique_order.append(provider)
        try:
            index = unique_order.index(current.provider)
        except ValueError:
            index = -1
        for provider in unique_order[index + 1 :]:
            model = self.provider_models.get(provider)
            if not model:
                continue
            if provider == current.provider and model == current.model:
                continue
            return ExecutionTarget(provider=provider, model=model)
        return None
