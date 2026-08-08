"""Credential management for the Local Agent Substrate.

Stores API tokens in the OS keyring (gnome-keyring/kwallet) with an encrypted
file fallback. Manages browser automation sessions via Playwright persistent
contexts with storage state persistence.

Security invariants:
- Secrets never appear in code, logs, or the audit trail.
- Keyring is the primary store; encrypted files are fallback only.
- Browser sessions persist via storage state (cookies + localStorage).
- All credential access is audited.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .. import _utils
from ..security.audit_trail import AuditTrail

KEYRING_SERVICE = "substrate-credentials"
ENCRYPTED_FILE = Path("state") / "credentials.enc"


class CredentialStore:
    """Manage API tokens and browser session state."""

    def __init__(self, root: Path, *, audit: AuditTrail | None = None) -> None:
        self.root = Path(root)
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")
        self._keyring_available = self._check_keyring()

    def _check_keyring(self) -> bool:
        try:
            import keyring
            keyring.get_password(KEYRING_SERVICE, "test")
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_token(self, service: str) -> str | None:
        """Retrieve a token from the keyring or encrypted file."""
        if self._keyring_available:
            import keyring
            token = keyring.get_password(KEYRING_SERVICE, service)
            if token:
                self.audit.append("credential_accessed", tier=0, details={"service": service})
                return token
        encrypted = self.root / ENCRYPTED_FILE
        if encrypted.exists():
            tokens = self._load_encrypted()
            if service in tokens:
                self.audit.append("credential_accessed", tier=0, details={"service": service, "source": "file"})
                return tokens[service]
        return None

    def set_token(self, service: str, token: str) -> None:
        """Store a token in the keyring (primary) or encrypted file (fallback)."""
        if self._keyring_available:
            import keyring
            keyring.set_password(KEYRING_SERVICE, service, token)
            self.audit.append("credential_stored", tier=0, details={"service": service, "store": "keyring"})
        else:
            tokens = self._load_encrypted()
            tokens[service] = token
            self._save_encrypted(tokens)
            self.audit.append("credential_stored", tier=0, details={"service": service, "store": "file"})

    def list_services(self) -> list[str]:
        """List services with stored credentials (not the values)."""
        services = []
        if self._keyring_available:
            try:
                import keyring
                backend = keyring.get_keyring()
                if hasattr(backend, "get_credential"):
                    for service in ["cloudflare", "github", "stripe"]:
                        if backend.get_credential(service, ""):
                            services.append(service)
            except Exception:  # noqa: BLE001
                pass
        encrypted = self.root / ENCRYPTED_FILE
        if encrypted.exists():
            tokens = self._load_encrypted()
            services.extend(tokens.keys())
        return sorted(set(services))

    def _load_encrypted(self) -> dict[str, str]:
        encrypted = self.root / ENCRYPTED_FILE
        if not encrypted.exists():
            return {}
        from cryptography.fernet import Fernet
        key = self._get_or_create_key()
        fernet = Fernet(key)
        plaintext = fernet.decrypt(encrypted.read_bytes())
        return json.loads(plaintext.decode("utf-8"))

    def _save_encrypted(self, tokens: dict[str, str]) -> None:
        from cryptography.fernet import Fernet
        key = self._get_or_create_key()
        fernet = Fernet(key)
        encrypted = self.root / ENCRYPTED_FILE
        encrypted.parent.mkdir(parents=True, exist_ok=True)
        encrypted.write_bytes(fernet.encrypt(json.dumps(tokens).encode("utf-8")))
        encrypted.chmod(0o600)

    def _get_or_create_key(self) -> bytes:
        key_file = self.root / "state" / "crypto" / "master.key"
        if key_file.exists():
            return key_file.read_bytes().strip()
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(key)
        key_file.chmod(0o600)
        return key
