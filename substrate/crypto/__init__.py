"""Crypto value automation: wallets, payments, pricing, and governance.

Modules here implement the financial side of the Local Agent Substrate:
deterministic BIP-39/BIP-44 wallet management, encrypted Proton Drive
backups, pricing, token registry, resource inventory, and payment-flow
governance rules.

All financial operations are Tier 2 under the substrate autonomy model and
require an explicit human directive. Every operation is recorded in the
hash-chained audit trail (``state/crypto/audit.jsonl``).

Security invariants:
- Private keys / seed phrases never appear in code, logs, or the audit trail.
- Seeds are encrypted at rest with Fernet (``state/crypto/seeds.enc``).
- Public addresses may be exported (site, D1); secrets may not.
"""

from .backup import backup_wallet_seeds, proton_sync_dir
from .inventory import ResourceInventory
from .policy import PaymentFlowGovernance, load_payment_rules
from .pricing import PricingEngine
from .token_registry import SUPPORTED_TOKENS, TokenRegistry
from .wallet_manager import WalletError, WalletManager, WalletPermissionError

__all__ = [
    "PaymentFlowGovernance",
    "PricingEngine",
    "ResourceInventory",
    "SUPPORTED_TOKENS",
    "TokenRegistry",
    "WalletError",
    "WalletManager",
    "WalletPermissionError",
    "backup_wallet_seeds",
    "load_payment_rules",
    "proton_sync_dir",
]
