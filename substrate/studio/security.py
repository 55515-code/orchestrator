from __future__ import annotations

import keyring
from keyring.errors import KeyringError

SERVICE_NAME = "codex-scheduler-studio"


def save_secret(secret_ref: str, value: str) -> None:
    try:
        keyring.set_password(SERVICE_NAME, secret_ref, value)
    except KeyringError as exc:
        raise RuntimeError(f"Unable to store secret in keyring: {exc}") from exc


def load_secret(secret_ref: str) -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, secret_ref)
    except KeyringError as exc:
        raise RuntimeError(f"Unable to load secret from keyring: {exc}") from exc


def clear_secret(secret_ref: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, secret_ref)
    except Exception:
        return
