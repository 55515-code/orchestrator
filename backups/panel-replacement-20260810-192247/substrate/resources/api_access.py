"""API key management for programmatic access by bots and agents.

Bots can purchase API access to use our services as an offload target.
Keys are issued Tier 2 (requires human directive), verified per-request,
and revoked on abuse or expiration. Keys are stored in
``state/crypto/api_keys.json`` (gitignored).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail

API_KEYS_RELATIVE = Path("state") / "crypto" / "api_keys.json"
DEFAULT_TTL_DAYS = 90


class APIAccessManager:
    def __init__(self, root: Path, *, audit: AuditTrail | None = None) -> None:
        self.root = Path(root)
        self.keys_path = self.root / API_KEYS_RELATIVE
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")

    def _load(self) -> dict[str, Any]:
        payload = _utils.load_json(self.keys_path, default={"keys": []})
        keys = payload.get("keys")
        if not isinstance(keys, list):
            payload["keys"] = []
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        _utils.write_json(self.keys_path, payload)

    def issue_key(
        self,
        *,
        owner: str,
        tier: str = "standard",
        ttl_days: int = DEFAULT_TTL_DAYS,
        directive: str = "",
    ) -> dict[str, Any]:
        """Issue a new API key. Tier 2: requires a human directive."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(f"API key issuance is Tier 2 ({reason})")

        key = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
        entry = {
            "key": key,
            "owner": owner,
            "tier": tier,
            "issued_at": _utils.utc_now_iso(),
            "expires_at": expires_at.isoformat(),
            "revoked": False,
        }
        payload = self._load()
        payload["keys"].append(entry)
        self._save(payload)
        self.audit.append(
            "api_key_issued",
            tier=TIER_HUMAN,
            details={"owner": owner, "tier": tier, "ttl_days": ttl_days},
        )
        return entry

    def verify_key(self, key: str) -> dict[str, Any] | None:
        """Verify an API key is valid and not expired. Returns the entry or None."""
        payload = self._load()
        for entry in payload["keys"]:
            if entry.get("key") != key:
                continue
            if entry.get("revoked"):
                return None
            try:
                expires_at = datetime.fromisoformat(str(entry.get("expires_at") or ""))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if datetime.now(UTC) > expires_at:
                    return None
            except ValueError:
                return None
            return entry
        return None

    def revoke_key(self, key: str, *, directive: str = "") -> bool:
        """Revoke an API key. Tier 2: requires a human directive."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(f"API key revocation is Tier 2 ({reason})")

        payload = self._load()
        for entry in payload["keys"]:
            if entry.get("key") == key:
                entry["revoked"] = True
                entry["revoked_at"] = _utils.utc_now_iso()
                self._save(payload)
                self.audit.append(
                    "api_key_revoked",
                    tier=TIER_HUMAN,
                    details={"owner": entry.get("owner"), "key_prefix": key[:8]},
                )
                return True
        return False

    def list_keys(self) -> list[dict[str, Any]]:
        """List all keys (redacted: only first 8 chars shown)."""
        payload = self._load()
        return [
            {
                "key_prefix": entry.get("key", "")[:8],
                "owner": entry.get("owner"),
                "tier": entry.get("tier"),
                "issued_at": entry.get("issued_at"),
                "expires_at": entry.get("expires_at"),
                "revoked": entry.get("revoked", False),
            }
            for entry in payload["keys"]
        ]
