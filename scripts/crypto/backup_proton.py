#!/usr/bin/env python3
"""Proton Drive backup CLI — encrypts wallet seeds and verifies the backup.

Usage:
  python scripts/crypto/backup_proton.py [--sync-dir <dir>]

Without a configured Proton Drive sync folder the bundle is staged under
state/crypto/backups/ and manual upload instructions are printed (Proton Drive
has no public write API).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.crypto import WalletManager, backup_wallet_seeds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up wallet seeds (verified)")
    parser.add_argument("--sync-dir", default=None, help="Proton Drive sync folder override")
    args = parser.parse_args(argv)

    manager = WalletManager(ROOT)
    try:
        report = backup_wallet_seeds(manager, sync_dir=Path(args.sync_dir).expanduser() if args.sync_dir else None)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report.get("verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
