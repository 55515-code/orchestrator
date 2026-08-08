#!/usr/bin/env python3
"""Crypto wallet CLI — Tier 2 financial operations require a --directive.

Usage:
  python scripts/crypto/wallet_gen.py create --purpose <p> [--directive <text>] [--network <n>]
  python scripts/crypto/wallet_gen.py list
  python scripts/crypto/wallet_gen.py public-address --purpose <p>
  python scripts/crypto/wallet_gen.py backup [--sync-dir <dir>]
  python scripts/crypto/wallet_gen.py verify-recovery --purpose <p>   (seed via STDIN)
  python scripts/crypto/wallet_gen.py export                          (public data, JSON)
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir


def _manager() -> WalletManager:
    return WalletManager(ROOT)


def cmd_create(args: argparse.Namespace) -> int:
    manager = _manager()
    wallet = manager.generate_wallet(
        purpose=args.purpose, directive=args.directive, network=args.network
    )
    print(json.dumps({"created": wallet}, indent=2))
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    manager = _manager()
    print(json.dumps(manager.list_wallets(), indent=2))
    return 0


def cmd_address(args: argparse.Namespace) -> int:
    manager = _manager()
    print(manager.get_public_address(args.purpose))
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    manager = _manager()
    sync_dir = Path(args.sync_dir).expanduser() if args.sync_dir else None
    report = backup_wallet_seeds(manager, sync_dir=sync_dir)
    print(json.dumps(report, indent=2))
    if report.get("manual_upload_required"):
        sync = proton_sync_dir()
        if sync is not None:
            print(f"Proton Drive sync folder detected: {sync}")
        print(
            "Manual upload required: no Proton Drive sync folder detected. "
            "Upload the staged file via the Proton Drive app, or set "
            "PROTON_DRIVE_SYNC_DIR."
        )
    return 0


def cmd_verify_recovery(args: argparse.Namespace) -> int:
    manager = _manager()
    seed = getpass.getpass("Enter seed phrase (not echoed): ").strip()
    if not seed:
        print("no seed entered", file=sys.stderr)
        return 2
    result = manager.verify_recovery(args.purpose, seed)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def cmd_export(_: argparse.Namespace) -> int:
    manager = _manager()
    print(json.dumps(manager.export_public_data(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Substrate crypto wallet CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Generate a new wallet (Tier 2)")
    create.add_argument("--purpose", required=True)
    create.add_argument("--network", default="polygon")
    create.add_argument("--directive", default="", help="Explicit human directive (required)")

    sub.add_parser("list", help="List public wallet metadata")
    address = sub.add_parser("public-address", help="Print a public address")
    address.add_argument("--purpose", required=True)

    backup = sub.add_parser("backup", help="Encrypt, write, and verify a backup")
    backup.add_argument("--sync-dir", default=None, help="Proton Drive sync folder override")

    verify = sub.add_parser("verify-recovery", help="Verify a seed recovers addresses")
    verify.add_argument("--purpose", required=True)

    sub.add_parser("export", help="Export public wallet data as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "create": cmd_create,
        "list": cmd_list,
        "public-address": cmd_address,
        "backup": cmd_backup,
        "verify-recovery": cmd_verify_recovery,
        "export": cmd_export,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
