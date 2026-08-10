"""Rate limiting and abuse detection for payment and delivery endpoints.

IP-based limiting alone is insufficient behind NAT, so the detector also
supports wallet-based limiting and simple anomaly heuristics (rapid repeat
downloads of the same resource, access to paid resources without payment).
State is persisted as JSON so it survives process restarts.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .. import _utils


class RateLimiter:
    """Sliding-window rate limiter keyed by arbitrary subject strings."""

    def __init__(
        self,
        *,
        max_requests: int = 100,
        window_seconds: int = 3600,
        state_path: Path | None = None,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.state_path = state_path
        self._state: dict[str, list[float]] = {}
        if state_path is not None:
            self._load()

    def _load(self) -> None:
        assert self.state_path is not None
        payload = _utils.load_json(self.state_path, default={})
        windows = payload.get("windows")
        if isinstance(windows, dict):
            for key, stamps in windows.items():
                if isinstance(stamps, list):
                    self._state[str(key)] = [float(s) for s in stamps]

    def _save(self) -> None:
        if self.state_path is None:
            return
        _utils.write_json(self.state_path, {"windows": self._state})

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """Return True and record the request when under the limit."""
        current = now if now is not None else time.time()
        cutoff = current - self.window_seconds
        stamps = [s for s in self._state.get(key, []) if s > cutoff]
        if len(stamps) >= self.max_requests:
            self._state[key] = stamps
            self._save()
            return False
        stamps.append(current)
        self._state[key] = stamps
        self._save()
        return True

    def remaining(self, key: str, *, now: float | None = None) -> int:
        current = now if now is not None else time.time()
        cutoff = current - self.window_seconds
        stamps = [s for s in self._state.get(key, []) if s > cutoff]
        return max(0, self.max_requests - len(stamps))


class AbuseDetector:
    """Combine rate limits with lightweight anomaly heuristics."""

    def __init__(
        self,
        *,
        ip_limiter: RateLimiter | None = None,
        wallet_limiter: RateLimiter | None = None,
        burst_limit: int = 5,
        state_path: Path | None = None,
    ) -> None:
        self.ip_limiter = ip_limiter or RateLimiter(max_requests=100, window_seconds=3600)
        self.wallet_limiter = wallet_limiter or RateLimiter(max_requests=40, window_seconds=3600)
        self.burst_limit = burst_limit
        self.state_path = state_path
        self._recent: dict[str, list[float]] = {}
        self._flags: list[dict[str, Any]] = []
        if state_path is not None:
            payload = _utils.load_json(state_path, default={})
            flags = payload.get("flags")
            if isinstance(flags, list):
                self._flags = list(flags)

    def _persist_flags(self) -> None:
        if self.state_path is None:
            return
        _utils.write_json(self.state_path, {"flags": self._flags[-200:]})

    def _is_burst(self, key: str, *, now: float) -> bool:
        cutoff = now - 60.0
        stamps = [s for s in self._recent.get(key, []) if s > cutoff]
        stamps.append(now)
        self._recent[key] = stamps
        return len(stamps) > self.burst_limit

    def flag_for_review(self, reason: str, *, subject: str, resource_id: str = "") -> None:
        self._flags.append(
            {
                "flagged_at": _utils.utc_now_iso(),
                "reason": reason,
                "subject": subject,
                "resource_id": resource_id,
            }
        )
        self._persist_flags()

    def flags(self) -> list[dict[str, Any]]:
        return list(self._flags)

    def check_request(
        self,
        ip: str,
        *,
        wallet: str = "",
        resource_id: str = "",
        paid: bool = False,
        is_paid_resource: bool = True,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """Return (allowed, reason) for an access attempt."""
        current = now if now is not None else time.time()

        if not self.ip_limiter.allow(f"ip:{ip}", now=current):
            self.flag_for_review("ip_rate_limited", subject=ip, resource_id=resource_id)
            return False, "ip_rate_limited"

        if wallet and not self.wallet_limiter.allow(f"wallet:{wallet}", now=current):
            self.flag_for_review("wallet_rate_limited", subject=wallet, resource_id=resource_id)
            return False, "wallet_rate_limited"

        if resource_id and self._is_burst(f"{ip}:{resource_id}", now=current):
            self.flag_for_review("download_burst", subject=ip, resource_id=resource_id)
            return False, "download_burst"

        if is_paid_resource and not paid:
            self.flag_for_review("unpaid_paid_resource_access", subject=ip, resource_id=resource_id)
            return False, "payment_required"

        return True, "allowed"
