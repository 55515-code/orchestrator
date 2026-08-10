"""Token registry and L2 network configuration.

Stablecoins are preferred for value preservation; volatile tokens carry a
conversion note. Actual swaps are Tier 2, human-directed operations and are
never executed automatically — this module only models configuration and
quotes with slippage protection.
"""

from __future__ import annotations

from typing import Any

NETWORKS: dict[str, dict[str, Any]] = {
    "polygon": {
        "chain_id": 137,
        "native_token": "POL",
        "avg_fee_usd": 0.01,
        "public_rpcs": ["https://polygon-rpc.com"],
        "explorer": "https://polygonscan.com",
    },
    "base": {
        "chain_id": 8453,
        "native_token": "ETH",
        "avg_fee_usd": 0.01,
        "public_rpcs": ["https://mainnet.base.org"],
        "explorer": "https://basescan.org",
    },
    "arbitrum": {
        "chain_id": 42161,
        "native_token": "ETH",
        "avg_fee_usd": 0.02,
        "public_rpcs": ["https://arb1.arbitrum.io/rpc"],
        "explorer": "https://arbiscan.io",
    },
}

SUPPORTED_TOKENS: dict[str, dict[str, Any]] = {
    "USDC": {"network": "polygon", "decimals": 6, "stable": True,
             "contract": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"},
    "DAI": {"network": "polygon", "decimals": 18, "stable": True,
            "contract": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063"},
    "POL": {"network": "polygon", "decimals": 18, "stable": False, "contract": None},
    "ETH": {"network": "base", "decimals": 18, "stable": False, "contract": None},
}

DEFAULT_MAX_SLIPPAGE_BPS = 50  # 0.5%


class TokenRegistry:
    """Lookup and quote helpers for supported tokens and networks."""

    def __init__(self, tokens: dict[str, dict[str, Any]] | None = None) -> None:
        self.tokens = dict(tokens or SUPPORTED_TOKENS)

    def get_token_config(self, symbol: str) -> dict[str, Any] | None:
        return self.tokens.get(symbol.upper())

    def tokens_for_network(self, network: str) -> list[str]:
        return sorted(
            symbol
            for symbol, config in self.tokens.items()
            if config.get("network") == network
        )

    def is_stable(self, symbol: str) -> bool:
        config = self.get_token_config(symbol)
        return bool(config and config.get("stable"))

    def quote_stable_conversion(
        self,
        amount: float,
        from_token: str,
        *,
        rates: dict[str, float],
        max_slippage_bps: int = DEFAULT_MAX_SLIPPAGE_BPS,
    ) -> dict[str, Any]:
        """Quote converting a volatile token to USDC. Tier 2 to execute.

        Returns a quote with slippage protection. Execution requires an
        explicit human directive and happens outside this module.
        """
        config = self.get_token_config(from_token)
        if config is None:
            raise ValueError(f"unsupported token: {from_token}")
        if config.get("stable"):
            return {
                "from": from_token,
                "to": "USDC",
                "amount_in": amount,
                "amount_out": amount,
                "action_required": False,
                "note": "already stable; no swap needed",
            }
        rate = rates.get(from_token.upper()) or rates.get(from_token)
        if not rate:
            raise ValueError(f"no rate available for {from_token}")
        gross = amount * float(rate)
        slippage = gross * (max_slippage_bps / 10_000)
        return {
            "from": from_token,
            "to": "USDC",
            "amount_in": amount,
            "amount_out_estimate": round(gross, 6),
            "min_amount_out": round(gross - slippage, 6),
            "max_slippage_bps": max_slippage_bps,
            "action_required": True,
            "tier": 2,
            "note": "swap execution requires an explicit human directive",
        }
