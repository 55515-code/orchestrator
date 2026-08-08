"""Hash-chained append-only audit trail for financial operations.

Every financial or security-sensitive operation (wallet generation, payment
verification, price update, token swap, backup, delivery) is appended as a
record whose ``hash`` covers the previous record's ``hash``. Any tampering or
truncation breaks the chain and is detected by :meth:`AuditTrail.verify`.

Design constraints:
- Append-only. Records are never rewritten in place.
- The chain is stored as JSON Lines so partial writes are recoverable.
- No secrets are ever written to the trail. Callers pass redacted details.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from .. import _utils

GENESIS_HASH = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_record_hash(record: dict[str, Any]) -> str:
    """Compute the SHA-256 hash for a single audit record."""
    basis = {
        "seq": record["seq"],
        "timestamp": record["timestamp"],
        "actor": record["actor"],
        "action": record["action"],
        "tier": record["tier"],
        "details": record.get("details") or {},
        "prev_hash": record["prev_hash"],
    }
    return hashlib.sha256(_canonical(basis).encode("utf-8")).hexdigest()


class AuditTrail:
    """Append-only hash-chained audit log persisted as JSON Lines."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def _last(self) -> dict[str, Any] | None:
        records = self._read_records()
        return records[-1] if records else None

    def append(
        self,
        action: str,
        *,
        actor: str = "substrate",
        tier: int = 0,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a record and return it. Thread-safe."""
        with self._lock:
            last = self._last()
            prev_hash = last["hash"] if last else GENESIS_HASH
            seq = (last["seq"] + 1) if last else 1
            record = {
                "seq": seq,
                "timestamp": _utils.utc_now_iso(),
                "actor": actor,
                "action": action,
                "tier": int(tier),
                "details": details or {},
                "prev_hash": prev_hash,
            }
            record["hash"] = compute_record_hash(record)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            return record

    def records(self) -> list[dict[str, Any]]:
        return self._read_records()

    def verify(self) -> dict[str, Any]:
        """Verify chain integrity. Returns a report with ``ok`` and ``errors``."""
        records = self._read_records()
        errors: list[str] = []
        expected_prev = GENESIS_HASH
        for index, record in enumerate(records):
            if record.get("prev_hash") != expected_prev:
                errors.append(f"record {index}: prev_hash mismatch")
            if compute_record_hash(record) != record.get("hash"):
                errors.append(f"record {index}: hash mismatch")
            if record.get("seq") != index + 1:
                errors.append(f"record {index}: seq mismatch")
            expected_prev = record.get("hash")
        return {"ok": not errors, "count": len(records), "errors": errors}

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._read_records()[-limit:]
