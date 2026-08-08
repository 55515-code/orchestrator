"""Deterministic wallet management with autonomy-tier gating.

Wallets follow BIP-39 (256-bit entropy mnemonic) and BIP-44 derivation
(``m/44'/60'/0'/0/<index>``). One master seed is kept per service category
(payments, donations, rewards, operations); child addresses are derived on
demand so a single backup recovers every address.

Storage layout (all under ``<root>/state/crypto/``, gitignored):
- ``wallets.json`` — public metadata only (addresses, purposes, timestamps).
- ``seeds.enc``    — Fernet-encrypted JSON mapping purpose -> seed phrase.
- ``master.key``   — Fernet key (chmod 600) used when keyring/env are absent.
- ``audit.jsonl``  — hash-chained audit trail.

Optional dependencies: ``mnemonic`` and ``eth-account`` (install with
``uv sync --extra crypto``).
"""

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path
from typing import Any

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail

DEFAULT_NETWORK = "polygon"
BIP44_BASE_PATH = "m/44'/60'/0'/0"
KEYRING_SERVICE = "substrate-crypto"
KEYRING_USERNAME = "fernet-key"
ENV_KEY = "SUBSTRATE_CRYPTO_KEY"
VALID_PURPOSES = ("payments", "donations", "rewards", "operations", "kilo-code")


class WalletError(RuntimeError):
    pass


class WalletPermissionError(WalletError):
    pass


def _crypto_optional_import() -> tuple[Any, Any]:
    try:
        from eth_account import Account  # type: ignore
        from mnemonic import Mnemonic  # type: ignore
    except ImportError as exc:
        raise WalletError(
            "crypto extra dependencies missing. Run: uv sync --extra crypto"
        ) from exc
    return Mnemonic, Account


class WalletManager:
    """Manage BIP-39/BIP-44 wallets with encrypted seed storage."""

    def __init__(
        self,
        root: Path,
        *,
        encryption_key: bytes | str | None = None,
        audit: AuditTrail | None = None,
    ) -> None:
        self.root = Path(root)
        self.state_dir = self.root / "state" / "crypto"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.wallets_path = self.state_dir / "wallets.json"
        self.seeds_path = self.state_dir / "seeds.enc"
        self.audit = audit or AuditTrail(self.state_dir / "audit.jsonl")
        self._explicit_key = self._normalize_key(encryption_key) if encryption_key else None

    @staticmethod
    def _normalize_key(key: bytes | str) -> bytes:
        if isinstance(key, str):
            key = key.encode("utf-8")
        return base64.urlsafe_b64encode(key.ljust(32, b"0")[:32])

    def _cipher(self):
        from cryptography.fernet import Fernet, InvalidToken

        _ = InvalidToken
        return Fernet(self._resolve_key())

    def _resolve_key(self) -> bytes:
        if self._explicit_key:
            return self._explicit_key
        env_key = os.getenv(ENV_KEY)
        if env_key:
            return self._normalize_key(env_key)
        try:
            import keyring

            stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if stored:
                return stored.encode("utf-8")
        except Exception:  # noqa: BLE001 - keyring backends vary; fall through
            pass
        key_file = self.state_dir / "master.key"
        if key_file.exists():
            return key_file.read_bytes().strip()
        from cryptography.fernet import Fernet

        generated = Fernet.generate_key()
        key_file.write_bytes(generated)
        key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.audit.append(
            "wallet_key_generated",
            tier=TIER_HUMAN,
            details={"note": "Fernet key generated and stored at state/crypto/master.key"},
        )
        return generated

    def _load_wallets(self) -> dict[str, Any]:
        payload = _utils.load_json(self.wallets_path, default={"wallets": {}})
        wallets = payload.get("wallets")
        if not isinstance(wallets, dict):
            payload["wallets"] = {}
        return payload

    def _save_wallets(self, payload: dict[str, Any]) -> None:
        _utils.write_json(self.wallets_path, payload)

    def _load_seeds(self) -> dict[str, str]:
        if not self.seeds_path.exists():
            return {}
        token = self.seeds_path.read_bytes()
        plaintext = self._cipher().decrypt(token)
        payload = json.loads(plaintext.decode("utf-8"))
        return {str(k): str(v) for k, v in payload.items()}

    def _save_seeds(self, seeds: dict[str, str]) -> None:
        plaintext = json.dumps(seeds, ensure_ascii=False).encode("utf-8")
        token = self._cipher().encrypt(plaintext)
        self.seeds_path.write_bytes(token)
        try:
            self.seeds_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def derive_address(self, seed_phrase: str, index: int = 0) -> str:
        """Derive the EVM address for BIP-44 path m/44'/60'/0'/0/<index>."""
        if index < 0:
            raise WalletError("index must be >= 0")
        _, Account = _crypto_optional_import()
        try:
            Account.enable_unaudited_hdwallet_features()
        except Exception:  # noqa: BLE001 - already enabled in some versions
            pass
        account = Account.from_mnemonic(seed_phrase, account_path=f"{BIP44_BASE_PATH}/{index}")
        return account.address

    def generate_wallet(
        self,
        purpose: str = "payments",
        *,
        directive: str = "",
        network: str = DEFAULT_NETWORK,
    ) -> dict[str, Any]:
        """Generate a new master wallet for *purpose*. Tier 2: needs directive."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            self.audit.append(
                "wallet_generate_blocked",
                tier=TIER_HUMAN,
                details={"purpose": purpose, "reason": reason},
            )
            raise WalletPermissionError(
                f"wallet generation is Tier 2 and requires an explicit human directive ({reason})"
            )
        if purpose not in VALID_PURPOSES:
            raise WalletError(f"purpose must be one of {VALID_PURPOSES}")

        payload = self._load_wallets()
        if purpose in payload["wallets"]:
            raise WalletError(f"wallet for purpose '{purpose}' already exists")

        Mnemonic, _ = _crypto_optional_import()
        seed_phrase = Mnemonic("english").generate(strength=256)
        address = self.derive_address(seed_phrase, 0)

        seeds = self._load_seeds()
        seeds[purpose] = seed_phrase
        self._save_seeds(seeds)

        entry = {
            "purpose": purpose,
            "network": network,
            "addresses": [address],
            "next_index": 1,
            "created_at": _utils.utc_now_iso(),
        }
        payload["wallets"][purpose] = entry
        self._save_wallets(payload)
        self.audit.append(
            "wallet_generated",
            tier=TIER_HUMAN,
            details={"purpose": purpose, "network": network, "address": address},
        )
        return {k: v for k, v in entry.items()}

    def derive_next_address(self, purpose: str, *, directive: str = "") -> str:
        """Derive the next child address for an existing wallet (Tier 2)."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise WalletPermissionError(f"address derivation is Tier 2 ({reason})")
        payload = self._load_wallets()
        entry = payload["wallets"].get(purpose)
        if entry is None:
            raise WalletError(f"no wallet for purpose '{purpose}'")
        seeds = self._load_seeds()
        seed_phrase = seeds.get(purpose)
        if not seed_phrase:
            raise WalletError(f"seed for purpose '{purpose}' missing")
        index = int(entry.get("next_index", len(entry.get("addresses", []))))
        address = self.derive_address(seed_phrase, index)
        entry.setdefault("addresses", []).append(address)
        entry["next_index"] = index + 1
        payload["wallets"][purpose] = entry
        self._save_wallets(payload)
        self.audit.append(
            "wallet_address_derived",
            tier=TIER_HUMAN,
            details={"purpose": purpose, "index": index, "address": address},
        )
        return address

    def list_wallets(self) -> list[dict[str, Any]]:
        payload = self._load_wallets()
        return [dict(entry) for entry in payload["wallets"].values()]

    def get_public_address(self, purpose: str, index: int = 0) -> str:
        payload = self._load_wallets()
        entry = payload["wallets"].get(purpose)
        if entry is None:
            raise WalletError(f"no wallet for purpose '{purpose}'")
        addresses = entry.get("addresses") or []
        if index >= len(addresses):
            raise WalletError(f"address index {index} not derived for '{purpose}'")
        return str(addresses[index])

    def export_public_data(self) -> dict[str, Any]:
        """Public-only export (safe for the site and D1): addresses, no secrets."""
        return {
            "exported_at": _utils.utc_now_iso(),
            "wallets": [
                {
                    "purpose": entry.get("purpose"),
                    "network": entry.get("network"),
                    "addresses": list(entry.get("addresses") or []),
                }
                for entry in self.list_wallets()
            ],
        }

    def verify_recovery(self, purpose: str, seed_phrase: str) -> dict[str, Any]:
        """Verify a seed phrase recovers the recorded addresses (read-only)."""
        payload = self._load_wallets()
        entry = payload["wallets"].get(purpose)
        if entry is None:
            raise WalletError(f"no wallet for purpose '{purpose}'")
        expected = list(entry.get("addresses") or [])
        recovered: list[str] = []
        for index in range(len(expected)):
            recovered.append(self.derive_address(seed_phrase, index))
        ok = recovered == expected
        self.audit.append(
            "wallet_recovery_verified",
            tier=0,
            details={"purpose": purpose, "ok": ok, "addresses_checked": len(expected)},
        )
        return {"ok": ok, "addresses_checked": len(expected)}
