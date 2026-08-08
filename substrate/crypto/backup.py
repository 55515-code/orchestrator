"""Encrypted wallet backup for Proton Drive.

Proton Drive exposes no public write API (``integrations.yaml`` records
``api_status: sdk_preview_only``), so automation is limited to:

1. Writing an envelope-encrypted backup bundle into the Proton Drive *local
   sync folder* when one is configured (the official desktop app syncs it), or
2. Staging the bundle under ``state/crypto/backups/`` and instructing the
   operator to upload it through an official Proton app.

Every backup is verified by reading it back and comparing checksums; failures
retry up to three times. Verification status is recorded in
``state/crypto/backup-status.json`` and the audit trail so unverified backups
are always visible to monitoring.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..security.audit_trail import AuditTrail
from .wallet_manager import WalletManager

ENV_SYNC_DIR = "PROTON_DRIVE_SYNC_DIR"
CONFIG_PATH = Path.home() / ".config" / "substrate" / "crypto_backup.json"
SYNC_DIR_CANDIDATES = (
    Path.home() / "ProtonDrive",
    Path.home() / "Proton Drive",
    Path.home() / "proton-drive",
)
BACKUP_FOLDER_NAME = "CryptoBackups"
MAX_ATTEMPTS = 3


def proton_sync_dir(config: dict[str, Any] | None = None) -> Path | None:
    """Resolve the Proton Drive sync folder, or None when not configured."""
    if config is None:
        config = _utils.load_json(CONFIG_PATH, default={})
    explicit = str(config.get("sync_dir") or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_dir() else None
    env_dir = os.getenv(ENV_SYNC_DIR, "").strip()
    if env_dir:
        path = Path(env_dir).expanduser()
        return path if path.is_dir() else None
    for candidate in SYNC_DIR_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_backup_bundle(manager: WalletManager) -> tuple[bytes, str]:
    """Build a double-encrypted backup bundle. Returns (token, checksum)."""
    seeds = manager._load_seeds()
    wallets = manager._load_wallets()["wallets"]
    bundle = {
        "exported_at": _utils.utc_now_iso(),
        "format": "substrate-crypto-backup-v1",
        "wallets": {
            purpose: {
                "network": entry.get("network"),
                "addresses": entry.get("addresses"),
            }
            for purpose, entry in wallets.items()
        },
        "seeds_encrypted": True,
    }
    inner = manager._cipher().encrypt(json.dumps(seeds, ensure_ascii=False).encode("utf-8"))
    bundle["seeds_token"] = inner.decode("utf-8")
    plaintext = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    token = manager._cipher().encrypt(plaintext)
    return token, _sha256(token)


def _read_back_and_verify(path: Path, manager: WalletManager, expected_checksum: str) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if _sha256(data) != expected_checksum:
        return False
    try:
        bundle = json.loads(manager._cipher().decrypt(data).decode("utf-8"))
        seeds = json.loads(
            manager._cipher().decrypt(bundle["seeds_token"].encode("utf-8")).decode("utf-8")
        )
    except Exception:  # noqa: BLE001 - any decrypt failure means unverified
        return False
    return isinstance(seeds, dict) and len(seeds) > 0


def backup_wallet_seeds(
    manager: WalletManager,
    *,
    sync_dir: Path | None = None,
    audit: AuditTrail | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Encrypt, write, and verify a wallet backup bundle.

    Returns a report: ``status`` is ``synced`` (written into the Proton sync
    folder) or ``staged`` (manual upload required), with ``verified`` and the
    destination path.
    """
    audit = audit or manager.audit
    if not manager.seeds_path.exists():
        raise FileNotFoundError("no wallet seeds to back up; generate a wallet first")

    token, checksum = build_backup_bundle(manager)
    resolved_sync = sync_dir if sync_dir is not None else proton_sync_dir(config)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}-substrate-wallets.enc"

    if resolved_sync is not None:
        target_dir = Path(resolved_sync) / BACKUP_FOLDER_NAME
        mode = "synced"
        manual_upload_required = False
    else:
        target_dir = manager.state_dir / "backups"
        mode = "staged"
        manual_upload_required = True

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    verified = False
    attempts = 0
    while attempts < MAX_ATTEMPTS and not verified:
        attempts += 1
        target_path.write_bytes(token)
        verified = _read_back_and_verify(target_path, manager, checksum)

    status_payload = {
        "status": mode if verified else "failed",
        "verified": verified,
        "attempts": attempts,
        "path": str(target_path),
        "checksum_sha256": checksum,
        "manual_upload_required": manual_upload_required,
        "backup_at": _utils.utc_now_iso(),
    }
    _utils.write_json(manager.state_dir / "backup-status.json", status_payload)
    audit.append(
        "wallet_backup",
        tier=1,
        details={
            "status": status_payload["status"],
            "verified": verified,
            "attempts": attempts,
            "mode": mode,
            "checksum_sha256": checksum[:16],
        },
    )
    return status_payload
