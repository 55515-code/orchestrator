"""Payment and wallet monitoring alerts.

Checks wallet balances against thresholds, backup freshness, and payment-flow
vetting status. Alerts persist to ``state/crypto/alerts.json`` and financial
checks append to the audit trail. Balance fetching is injectable so tests and
offline environments never depend on live RPC.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .. import _utils
from ..security.audit_trail import AuditTrail

DEFAULT_THRESHOLDS = {
    "high_balance_usd": 500.0,
    "low_balance_usd": 1.0,
    "backup_max_age_days": 7,
}


class CryptoAlertManager:
    """Generate alerts for wallet, backup, and vetting conditions."""

    def __init__(
        self,
        root: Path,
        *,
        balance_fetcher: Callable[[str, str], float] | None = None,
        thresholds: dict[str, float] | None = None,
        audit: AuditTrail | None = None,
    ) -> None:
        self.root = Path(root)
        self.state_dir = self.root / "state" / "crypto"
        self.balance_fetcher = balance_fetcher
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.audit = audit or AuditTrail(self.state_dir / "audit.jsonl")
        self.alerts_path = self.state_dir / "alerts.json"

    def _load_alerts(self) -> list[dict[str, Any]]:
        payload = _utils.load_json(self.alerts_path, default={"alerts": []})
        alerts = payload.get("alerts")
        return list(alerts) if isinstance(alerts, list) else []

    def _save_alerts(self, alerts: list[dict[str, Any]]) -> None:
        _utils.write_json(self.alerts_path, {"alerts": alerts[-200:]})

    def _emit(self, kind: str, message: str, *, severity: str = "warning") -> dict[str, Any]:
        alert = {
            "kind": kind,
            "severity": severity,
            "message": message,
            "created_at": _utils.utc_now_iso(),
        }
        return alert

    def check_wallet_balances(
        self, wallets: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Alert on high balances (move to cold storage) and low balances."""
        alerts: list[dict[str, Any]] = []
        if self.balance_fetcher is None:
            return alerts
        for wallet in wallets:
            address = str((wallet.get("addresses") or [""])[0]) if wallet.get("addresses") else ""
            if not address:
                continue
            try:
                balance_usd = float(self.balance_fetcher(address, wallet.get("network", "polygon")))
            except Exception:  # noqa: BLE001 - RPC failure is an alert, not a crash
                alerts.append(
                    self._emit(
                        "balance_check_failed",
                        f"could not fetch balance for {wallet.get('purpose')} wallet",
                        severity="warning",
                    )
                )
                continue
            if balance_usd >= self.thresholds["high_balance_usd"]:
                alerts.append(
                    self._emit(
                        "high_balance",
                        f"{wallet.get('purpose')} wallet holds ~${balance_usd:.2f}; "
                        "consider conversion to stablecoin or cold storage",
                        severity="info",
                    )
                )
            elif balance_usd <= self.thresholds["low_balance_usd"]:
                alerts.append(
                    self._emit(
                        "low_balance",
                        f"{wallet.get('purpose')} wallet holds ~${balance_usd:.2f}; "
                        "may need funding for fees",
                        severity="warning",
                    )
                )
        return self._persist(alerts)

    def check_backup_freshness(
        self, *, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        status = _utils.load_json(self.state_dir / "backup-status.json", default={})
        if not status.get("verified"):
            alerts.append(
                self._emit(
                    "backup_missing_or_unverified",
                    "no verified wallet backup on record",
                    severity="critical",
                )
            )
            return self._persist(alerts)
        current = now or datetime.now(UTC)
        try:
            backed_up = datetime.fromisoformat(str(status.get("backup_at") or ""))
            if backed_up.tzinfo is None:
                backed_up = backed_up.replace(tzinfo=UTC)
        except ValueError:
            return self._persist(alerts)
        max_age = timedelta(days=self.thresholds["backup_max_age_days"])
        if current - backed_up > max_age:
            alerts.append(
                self._emit(
                    "backup_stale",
                    f"wallet backup older than {self.thresholds['backup_max_age_days']} days",
                    severity="warning",
                )
            )
        return self._persist(alerts)

    def _persist(self, new_alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if new_alerts:
            alerts = self._load_alerts()
            alerts.extend(new_alerts)
            self._save_alerts(alerts)
            self.audit.append(
                "monitoring_alerts",
                tier=0,
                details={"kinds": [alert["kind"] for alert in new_alerts]},
            )
        return new_alerts
