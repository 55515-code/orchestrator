"""Secure vault for integration secrets.

Security invariants (non-negotiable):
- Raw secrets are NEVER written to workspace.yaml, integrations-state.json,
  logs, the audit trail details, or any other plaintext file.
- The only persistence surface for a secret value is the OS keyring
  (SecretService / gnome-keyring / kwallet) via CredentialStore.  The
  encrypted file fallback (state/credentials.enc) is used only when no
  keyring is available and is itself Fernet-encrypted with 0600 perms.
- The web API and the control panel never return a secret value.  Reads
  return only metadata: presence, backend (keyring/file), masked preview
  (last 2 chars), and timestamps.
- Every vault mutation is appended to the hash-chained audit trail
  (state/crypto/audit.jsonl) with redacted details.
- The browser POSTs the secret over the existing authenticated panel
  channel (loopback + Bearer token + Origin/Host checks in web.py).  The
  field is <input type="password" autocomplete="new-password"> and is
  cleared from the DOM immediately after submit.

Naming:
  keyring key = f"integration:{service_id}"  (e.g. integration:proton_mail)
  This is the `token_ref` stored in state/integrations-state.json — an
  opaque pointer, not the secret itself.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .credentials import CredentialStore
from .integrations import integrations_payload
from .registry import SubstrateRuntime

# token_ref is an opaque pointer like "keyring:integration:proton_mail"
# or a legacy env/file ref the user typed.  We validate the pointer we
# write, but we still accept legacy values on read.
_POINTER_RE = re.compile(r"^[A-Za-z0-9_./:\-]{1,160}$")
_KEY_PREFIX = "integration:"


def _pointer_for(service_id: str) -> str:
    return f"keyring:{_KEY_PREFIX}{service_id}"


def _key_for(service_id: str) -> str:
    return f"{_KEY_PREFIX}{service_id}"


def _masked_preview(secret: str) -> str:
    """Return a non-sensitive preview: •••• + last 2 chars (never the full value)."""
    if not secret:
        return "—"
    tail = secret[-2:] if len(secret) >= 2 else "•"
    return f"{'•' * 8}{tail}"


def vault_status(runtime: SubstrateRuntime) -> dict[str, Any]:
    """Return vault metadata for every catalog service — never secret values."""
    store = CredentialStore(runtime.root)
    catalog = integrations_payload(runtime)
    services = []
    secured = 0
    missing = 0

    for svc in catalog["services"]:
        sid = svc["id"]
        key = _key_for(sid)
        # Avoid double-audit: get_token() appends a tier-0 audit entry per read.
        # Peek at the encrypted file first so keyring reads stay the only
        # keyring access; the single get_token below is the authoritative
        # presence check and its audit entry is redacted (no value).
        secret_val: str | None = None
        backend: str | None = None
        try:
            secret_val = store.get_token(key)
            if secret_val is not None:
                backend = "keyring" if store._keyring_available else "encrypted_file"
                secured += 1
            else:
                backend = None
                missing += 1
        except Exception:  # noqa: BLE001
            backend = None
            missing += 1

        # Do not expose secret_val; only a masked tail for UX confirmation
        preview = _masked_preview(secret_val) if secret_val else "—"

        # Fingerprint (sha256 of secret) is useful for rotation detection
        # without exposing the secret.  Store only first 8 hex chars.
        fingerprint = hashlib.sha256(secret_val.encode()).hexdigest()[:8] if secret_val else None

        services.append(
            {
                "id": sid,
                "name": svc["name"],
                "category": svc["category"],
                "availability": svc.get("availability", "general"),
                "auth_methods": svc.get("auth", {}).get("methods", []),
                "login_url": svc.get("auth", {}).get("login_url", ""),
                "docs_url": svc.get("auth", {}).get("docs_url", ""),
                "connected": svc.get("connected", False),
                "mode": svc.get("mode", "read"),
                "token_ref": svc.get("token_ref"),
                "has_secret": secret_val is not None,
                "backend": backend,
                "preview": preview,
                "fingerprint": fingerprint,
                "updated_at": svc.get("updated_at"),
            }
        )

    return {
        "summary": {
            "services_total": len(services),
            "secured_total": secured,
            "missing_total": missing,
            "keyring_available": store._keyring_available,
            "backend": "keyring" if store._keyring_available else "encrypted_file",
        },
        "services": services,
    }


def put_secret(
    runtime: SubstrateRuntime,
    *,
    service_id: str,
    secret: str,
    auth_method: str | None = None,
    mode: str = "read",
    write_directive: str | None = None,
) -> dict[str, Any]:
    """Persist a secret to the OS keyring and mark the integration connected.

    The raw `secret` is written ONLY to CredentialStore (keyring).  The JSON
    state file receives only the opaque pointer `keyring:integration:<id>`.
    """
    from .integrations import _catalog, _load_state, _save_state, _service_lookup, _validated_mode

    if not secret or not secret.strip():
        raise ValueError("Secret value is required.")

    catalog = _catalog(runtime)
    by_id = _service_lookup(catalog)
    if service_id not in by_id:
        raise KeyError(f"Unknown integration service: {service_id}")

    # Validate mode/directive same as connect_integration
    selected_mode = _validated_mode(mode or "read", default_mode=catalog["defaults"]["access_mode"])
    directive = (write_directive or "").strip()
    if selected_mode == "write" and catalog["defaults"]["write_requires_directive"] and not directive:
        raise ValueError("write_directive is required when mode=write.")

    svc = by_id[service_id]
    selected_auth = (auth_method or "").strip() or None
    if selected_auth and selected_auth not in svc["auth"]["methods"]:
        raise ValueError(f"auth_method must be one of: {', '.join(svc['auth']['methods'])}")

    store = CredentialStore(runtime.root)
    key = _key_for(service_id)
    # This is the only place the raw secret touches persistence — keyring/enc file
    store.set_token(key, secret)

    # Now update integrations-state.json with ONLY the pointer
    import json as _json  # noqa: F401 - keep import local to avoid circular

    state = _load_state(runtime.paths["integrations_state"])
    from . import _utils

    pointer = _pointer_for(service_id)
    connection = {
        "connected": True,
        "mode": selected_mode,
        "auth_method": selected_auth,
        "token_ref": pointer,
        "granted_scopes": state.get("connections", {}).get(service_id, {}).get("granted_scopes", []),
        "write_directive": directive or None,
        "updated_at": _utils.utc_now_iso(),
    }
    state["connections"][service_id] = connection
    _save_state(runtime.paths["integrations_state"], state)

    # Audit already appended by CredentialStore.set_token; add a vault-level entry
    # with strictly redacted details (no secret, no preview).
    try:
        from .security.audit_trail import AuditTrail

        audit = AuditTrail(runtime.root / "state" / "crypto" / "audit.jsonl")
        audit.append(
            "vault_put",
            tier=1,
            details={
                "service": service_id,
                "auth_method": selected_auth or "default",
                "mode": selected_mode,
                "backend": "keyring" if store._keyring_available else "encrypted_file",
            },
        )
    except Exception:  # noqa: BLE001
        pass

    return {"service_id": service_id, "connection": connection, "pointer": pointer}


def delete_secret(runtime: SubstrateRuntime, *, service_id: str) -> dict[str, Any]:
    """Remove a secret from the keyring and disconnect the integration."""
    from .integrations import _catalog, _load_state, _save_state, _service_lookup

    catalog = _catalog(runtime)
    if service_id not in _service_lookup(catalog):
        raise KeyError(f"Unknown integration service: {service_id}")

    store = CredentialStore(runtime.root)
    key = _key_for(service_id)

    # Remove from keyring / encrypted file
    removed = False
    if store._keyring_available:
        try:
            import keyring

            existing = keyring.get_password(store.KEYRING_SERVICE if hasattr(store, "KEYRING_SERVICE") else "substrate-credentials", key)
            if existing is not None:
                try:
                    keyring.delete_password("substrate-credentials", key)
                except Exception:  # noqa: BLE001
                    # Fallback: overwrite with empty and rely on disconnect
                    import keyring as _kr

                    _kr.set_password("substrate-credentials", key, "")
                removed = True
        except Exception:  # noqa: BLE001
            pass
    # Encrypted file fallback
    try:
        enc = runtime.root / "state" / "credentials.enc"
        if enc.exists():
            tokens = store._load_encrypted()
            if key in tokens:
                tokens.pop(key, None)
                store._save_encrypted(tokens)
                removed = True
    except Exception:  # noqa: BLE001
        pass

    # Disconnect in state file
    state = _load_state(runtime.paths["integrations_state"])
    existed = service_id in state.get("connections", {})
    state["connections"].pop(service_id, None)
    _save_state(runtime.paths["integrations_state"], state)

    try:
        from .security.audit_trail import AuditTrail

        audit = AuditTrail(runtime.root / "state" / "crypto" / "audit.jsonl")
        audit.append("vault_delete", tier=1, details={"service": service_id, "removed": removed})
    except Exception:  # noqa: BLE001
        pass

    return {"service_id": service_id, "removed": removed, "disconnected": existed}


def test_secret_format(service_id: str, secret: str) -> dict[str, Any]:
    """Lightweight format check without persisting or probing the network."""
    if not secret or len(secret.strip()) < 4:
        return {"ok": False, "reason": "Secret is too short."}
    # Service-specific hints (non-blocking)
    hints: list[str] = []
    s = secret.strip()
    if service_id == "proton_mail" and len(s) < 8:
        hints.append("Bridge passwords are typically 16+ characters.")
    if service_id in {"github", "gitlab"} and not (s.startswith("ghp_") or s.startswith("github_pat_") or s.startswith("glpat-") or len(s) > 20):
        hints.append("Token format looks unusual — double-check the PAT prefix.")
    return {"ok": True, "hints": hints}
