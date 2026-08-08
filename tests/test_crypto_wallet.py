from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from substrate.agents.core import check_action_permission
from substrate.crypto import WalletError, WalletManager, WalletPermissionError

try:
    from eth_account import Account  # noqa: F401

    ETH_ACCOUNT_AVAILABLE = True
except ImportError:  # pragma: no cover - crypto extra not installed
    ETH_ACCOUNT_AVAILABLE = False

# Well-known BIP-39 test vector (Hardhat/Anvil default). The first derived
# address at m/44'/60'/0'/0/0 is fixed — a real derivation check.
TEST_MNEMONIC = "test test test test test test test test test test test junk"
KNOWN_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

DIRECTIVE = "human: generate test wallet"


def _manager(tmp: str, key: bytes = b"test-key-material") -> WalletManager:
    return WalletManager(Path(tmp), encryption_key=key)


@unittest.skipUnless(ETH_ACCOUNT_AVAILABLE, "crypto extra not installed")
class WalletManagerTest(unittest.TestCase):
    def test_derivation_vector(self) -> None:
        manager = _manager(tempfile.mkdtemp())
        address = manager.derive_address(TEST_MNEMONIC, 0)
        self.assertEqual(KNOWN_ADDRESS, address)

    def test_generation_requires_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _manager(tmp)
            with self.assertRaises(WalletPermissionError):
                manager.generate_wallet("donations", directive="")
            trail = manager.audit.records()
            self.assertTrue(any(r["action"] == "wallet_generate_blocked" for r in trail))

    def test_generate_list_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _manager(tmp)
            wallet = manager.generate_wallet("donations", directive=DIRECTIVE)
            self.assertEqual("donations", wallet["purpose"])
            address = wallet["addresses"][0]
            self.assertTrue(address.startswith("0x"))
            self.assertEqual(address, manager.get_public_address("donations"))
            wallets = manager.list_wallets()
            self.assertEqual(1, len(wallets))
            exported = manager.export_public_data()
            self.assertEqual(1, len(exported["wallets"]))
            self.assertNotIn("seeds", exported["wallets"][0])
            self.assertIn("addresses", exported["wallets"][0])

    def test_seed_encrypted_at_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _manager(tmp)
            manager.generate_wallet("payments", directive=DIRECTIVE)
            raw = (Path(tmp) / "state" / "crypto" / "seeds.enc").read_bytes()
            self.assertNotIn(b"test test", raw)
            self.assertNotIn(b"junk", raw)

    def test_recovery_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _manager(tmp)
            manager.generate_wallet("rewards", directive=DIRECTIVE)
            address = manager.get_public_address("rewards")
            self.assertTrue(address.startswith("0x"))
            result = manager.verify_recovery("rewards", TEST_MNEMONIC)
            self.assertFalse(result["ok"])  # wrong seed must not match

    def test_purpose_must_be_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _manager(tmp)
            with self.assertRaises(WalletError):
                manager.generate_wallet("nonsense", directive=DIRECTIVE)

    def test_tier2_gate_helper(self) -> None:
        allowed, reason = check_action_permission(
            agent_tier_cap=2, action_tier=2, directive=DIRECTIVE
        )
        self.assertTrue(allowed)
        self.assertEqual("human_directive", reason)


if __name__ == "__main__":
    unittest.main()
