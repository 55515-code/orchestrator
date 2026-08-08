from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir

DIRECTIVE = "human: test backup"
KEY = b"test-key-material"


class BackupTest(unittest.TestCase):
    def _manager(self, tmp: str) -> WalletManager:
        return WalletManager(Path(tmp), encryption_key=KEY)

    def test_staged_fallback_when_no_sync_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._manager(tmp)
            manager.generate_wallet("payments", directive=DIRECTIVE)
            report = backup_wallet_seeds(manager)
            self.assertEqual("staged", report["status"])
            self.assertTrue(report["verified"])
            self.assertTrue(report["manual_upload_required"])
            bundle = Path(report["path"])
            self.assertTrue(bundle.exists())
            self.assertNotIn(b"junk", bundle.read_bytes())

    def test_sync_dir_mode_and_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._manager(tmp)
            manager.generate_wallet("donations", directive=DIRECTIVE)
            sync = Path(tmp) / "ProtonDrive"
            sync.mkdir()
            report = backup_wallet_seeds(manager, sync_dir=sync)
            self.assertEqual("synced", report["status"])
            self.assertTrue(report["verified"])
            self.assertEqual(1, report["attempts"])
            target = Path(report["path"])
            self.assertTrue(target.exists())
            self.assertTrue(target.is_relative_to(sync / "CryptoBackups"))

    def test_no_seeds_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._manager(tmp)
            with self.assertRaises(FileNotFoundError):
                backup_wallet_seeds(manager)

    def test_proton_sync_dir_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sync = Path(tmp) / "sync"
            sync.mkdir()
            config = {"sync_dir": str(sync)}
            self.assertEqual(sync, proton_sync_dir(config))
            self.assertIsNone(proton_sync_dir({"sync_dir": str(Path(tmp) / "missing")}))


if __name__ == "__main__":
    unittest.main()
