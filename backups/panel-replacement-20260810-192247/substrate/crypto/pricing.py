"""Dynamic pricing for resources across multiple tokens.

Base prices are stored in USD. Live rates are fetched from CoinGecko's public
API; on failure the engine degrades gracefully — stablecoin prices remain
available (pegged 1:1), volatile-token prices are withheld rather than served
stale. Persisted price changes are Tier 2 and require a human directive.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail
from .token_registry import SUPPORTED_TOKENS

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=matic-network,ethereum&vs_currencies=usd"
)
RATE_TTL_SECONDS = 300
UNDERCUT_BPS = 500  # 5% under the comparable market price
FLOOR_FACTOR = 0.5  # never undercut below 50% of our base (cost-cover floor)


def fetch_coingecko_rates(timeout: float = 10.0) -> dict[str, float]:
    """Fetch USD rates for volatile tokens. Raises on network failure."""
    request = urllib.request.Request(COINGECKO_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "POL": float(payload["matic-network"]["usd"]),
        "ETH": float(payload["ethereum"]["usd"]),
    }


class PricingEngine:
    """Calculate per-resource prices in supported tokens."""

    def __init__(
        self,
        base_prices_usd: dict[str, float],
        *,
        rate_fetcher: Callable[[], dict[str, float]] | None = None,
        state_path: Path | None = None,
        audit: AuditTrail | None = None,
        ttl_seconds: int = RATE_TTL_SECONDS,
    ) -> None:
        self.base_prices_usd = dict(base_prices_usd)
        self.rate_fetcher = rate_fetcher or fetch_coingecko_rates
        self.state_path = state_path
        self.audit = audit
        self.ttl_seconds = ttl_seconds
        self._rate_cache: dict[str, Any] = {}

    def _load_persisted_prices(self) -> dict[str, float]:
        if self.state_path is None:
            return {}
        payload = _utils.load_json(self.state_path, default={})
        prices = payload.get("base_prices_usd")
        return {str(k): float(v) for k, v in prices.items()} if isinstance(prices, dict) else {}

    def effective_base_prices(self) -> dict[str, float]:
        persisted = self._load_persisted_prices()
        merged = {**self.base_prices_usd, **persisted}
        return merged

    def _fetch_rates_cached(self) -> dict[str, float] | None:
        now = time.time()
        if self._rate_cache and now - self._rate_cache.get("at", 0) < self.ttl_seconds:
            return self._rate_cache.get("rates")
        try:
            rates = self.rate_fetcher()
        except Exception:  # noqa: BLE001 - network failure must not break pricing
            return self._rate_cache.get("rates")
        self._rate_cache = {"at": now, "rates": rates}
        return rates

    def get_price(self, resource_id: str, *, network: str = "polygon") -> dict[str, Any]:
        """Return prices for a resource. Stablecoins always priced; volatile
        tokens only when a live rate is available."""
        base_usd = self.effective_base_prices().get(resource_id)
        if base_usd is None:
            raise KeyError(f"no base price for resource '{resource_id}'")
        result: dict[str, Any] = {
            "resource_id": resource_id,
            "base_usd": base_usd,
            "usdc": round(base_usd, 2),
            "dai": round(base_usd, 2),
            "network": network,
            "rates_fresh": False,
        }
        rates = self._fetch_rates_cached()
        if rates:
            result["rates_fresh"] = True
            for symbol in ("POL", "ETH"):
                if SUPPORTED_TOKENS.get(symbol, {}).get("network") == network and rates.get(symbol):
                    result[symbol.lower()] = round(base_usd / rates[symbol], 6)
        return result

    def update_prices(
        self, new_prices: dict[str, float], *, directive: str = ""
    ) -> dict[str, Any]:
        """Persist new base prices. Tier 2: requires a human directive."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(f"price updates are Tier 2 ({reason})")
        if self.state_path is None:
            raise ValueError("pricing engine has no state_path; cannot persist updates")
        merged = {**self.effective_base_prices(), **{k: float(v) for k, v in new_prices.items()}}
        _utils.write_json(
            self.state_path,
            {"base_prices_usd": merged, "updated_at": _utils.utc_now_iso()},
        )
        if self.audit is not None:
            self.audit.append(
                "price_update",
                tier=TIER_HUMAN,
                details={"changed": sorted(new_prices.keys()), "directive_present": True},
            )
        return {"updated": sorted(new_prices.keys()), "total": len(merged)}

    def propose_competitive_prices(
        self,
        *,
        comparator_prices: dict[str, float],
        undercut_bps: int = UNDERCUT_BPS,
        floor_factor: float = FLOOR_FACTOR,
    ) -> dict[str, Any]:
        """Propose undercut prices below comparables, never below the floor.

        Only proposes; persisting is :meth:`apply_competitive_update` (Tier 2).
        The floor (``base * floor_factor``) keeps prices above cost-covering
        levels, so undercutting never turns into a loss.
        """
        proposals: dict[str, Any] = {}
        for resource_id, base_usd in self.effective_base_prices().items():
            comparator = comparator_prices.get(resource_id)
            if comparator is None:
                continue
            floor = base_usd * floor_factor
            candidate = comparator * (1 - undercut_bps / 10_000)
            if candidate <= 0:
                continue
            price = round(max(floor, min(base_usd, candidate)), 2)
            if price < base_usd:
                proposals[resource_id] = {
                    "from_usd": base_usd,
                    "to_usd": price,
                    "floor_usd": round(floor, 2),
                    "comparator_usd": comparator,
                    "savings_pct": round((base_usd - price) / base_usd * 100, 1),
                }
        return proposals

    def apply_competitive_update(
        self,
        *,
        comparator_prices: dict[str, float],
        revenue_trend_ok: bool = True,
        directive: str = "",
        undercut_bps: int = UNDERCUT_BPS,
        floor_factor: float = FLOOR_FACTOR,
    ) -> dict[str, Any]:
        """Persist proposed undercut prices. Tier 2 + revenue-trend guard.

        Undercutting is only applied while numbers are moving up: when
        ``revenue_trend_ok`` is False the cut is refused so a declining
        revenue trend is never accelerated by discounting.
        """
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(f"competitive price updates are Tier 2 ({reason})")
        if not revenue_trend_ok:
            raise PermissionError(
                "competitive price cuts blocked: revenue trend is not upward (PF-011)"
            )
        proposals = self.propose_competitive_prices(
            comparator_prices=comparator_prices,
            undercut_bps=undercut_bps,
            floor_factor=floor_factor,
        )
        if not proposals:
            return {"updated": [], "note": "no undercut applicable"}
        new_prices = {rid: entry["to_usd"] for rid, entry in proposals.items()}
        return self.update_prices(new_prices, directive=directive)
