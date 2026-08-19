"""Web-facing Proton integration support for the control panel.

Security invariants (non-negotiable):
- Proton passwords only ever enter the OS keyring via CredentialStore (the
  same SecretService collection the vault uses). The web layer never logs,
  echoes, or persists a secret value.
- The connect flow runs in a background subprocess so the HTTP request
  returns immediately; the panel polls ``GET /api/proton/last-run``.
  The TOTP code (future 2FA) is passed to the child via the PROTON_TOTP
  environment variable — never argv, never in the URL or state files.
- No network probe happens automatically. The status endpoint reports
  configuration + service state only; probing occurs exclusively on an
  explicit user action (Verify / Connect).
- Run reports are sanitized (passwords/codes replaced with ***) before
  being written to state or returned to the panel.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .credentials import CredentialStore
from .integrations import _load_state
from .registry import SubstrateRuntime
from .vault import delete_secret as vault_delete_secret
from .vault import put_secret as vault_put_secret

BRIDGE_SERVICE = "protonmail-bridge.service"
HOOK_SERVICE = "proton-bridge-hook.service"
STATE_FILE = "state/proton-connect-last.json"
LOG_FILE = "state/proton-connect-last.log"
IMAP_HOST, IMAP_PORT = "127.0.0.1", 1143
DEFAULT_EMAIL = "ahronzombi@protonmail.com"

# Keyring account names (CredentialStore -> SecretService "substrate-credentials").
PASSWORD_KEYS = ("proton-bridge-smtp", "proton-mail-password", "integration:proton_mail")
EMAIL_KEYS = ("proton-mail", "proton-bridge-smtp")


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def _stored_secrets(runtime: SubstrateRuntime) -> list[str]:
    store = CredentialStore(runtime.root)
    values: list[str] = []
    for key in (*PASSWORD_KEYS, *EMAIL_KEYS):
        try:
            val = store.get_token(key)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            values.append(val)
    return values


def redact(runtime: SubstrateRuntime, text: str) -> str:
    """Replace any known secret value in *text* with *** (defense in depth)."""
    out = text or ""
    for value in sorted(set(_stored_secrets(runtime)), key=len, reverse=True):
        if value and value in out:
            out = out.replace(value, "***")
    return out


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _run_unit(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _service_active(name: str) -> bool:
    try:
        r = _run_unit(["systemctl", "--user", "is-active", name], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:  # noqa: BLE001
        return False


def _has_keyring_value(runtime: SubstrateRuntime, key: str) -> bool:
    try:
        return bool(CredentialStore(runtime.root).get_token(key))
    except Exception:  # noqa: BLE001
        return False


def _drive_remotes() -> list[dict[str, str]]:
    """Detect configured rclone Proton Drive remotes (config only — no network)."""
    try:
        r = _run_unit(["rclone", "config", "show"], timeout=20)
    except Exception:  # noqa: BLE001
        return []
    remotes: list[dict[str, str]] = []
    name = None
    for line in (r.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip()
            continue
        if name and stripped.lower() == "type = protondrive":
            remotes.append({"name": name, "type": "protondrive"})
    return remotes


def _last_run_payload(runtime: SubstrateRuntime) -> dict[str, Any]:
    path = runtime.root / STATE_FILE
    if not path.exists():
        return {"status": "none"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "unreadable"}
    return redact_payload(runtime, payload)


def redact_payload(runtime: SubstrateRuntime, payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a run payload before exposing it (values never leave the box)."""
    out = dict(payload)
    for key in ("detail", "imap_detail", "email"):
        if isinstance(out.get(key), str):
            out[key] = redact(runtime, out[key])
    return out


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def proton_status_payload(runtime: SubstrateRuntime) -> dict[str, Any]:
    """Report configuration + service state. Deliberately no network probes."""
    email = None
    for key in EMAIL_KEYS:
        try:
            val = CredentialStore(runtime.root).get_token(key)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            email = val
            break

    integrations = _load_state(runtime.paths["integrations_state"])
    mail_conn = integrations.get("connections", {}).get("proton_mail", {})

    password_stored = False
    for key in PASSWORD_KEYS:
        if _has_keyring_value(runtime, key):
            password_stored = True
            break

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mail": {
            "service": BRIDGE_SERVICE,
            "bridge_active": _service_active(BRIDGE_SERVICE),
            "hook_active": _service_active(HOOK_SERVICE),
            "email_stored": bool(email),
            "email": email or None,
            "password_stored": password_stored,
            "connected": bool(mail_conn.get("connected")),
            "auth_method": mail_conn.get("auth_method"),
            "updated_at": mail_conn.get("updated_at"),
            "imap": f"{IMAP_HOST}:{IMAP_PORT}",
            "note": "Account state is probed only on Verify/Connect (avoids login-attempt lockouts).",
        },
        "drive": {
            "remotes": _drive_remotes(),
            "api_note": "Proton Drive has no public write API; rclone OAuth + CAPTCHA is interactive-only.",
        },
        "last_run": _last_run_payload(runtime),
    }


# ---------------------------------------------------------------------------
# Credential storage (keyring only)
# ---------------------------------------------------------------------------


def store_proton_credentials(runtime: SubstrateRuntime, email: str, password: str) -> None:
    """Persist Proton credentials to the OS keyring (never plaintext files).

    Writes the accounts used by the vault, the email manager, and the IMAP
    hook, plus the vault integration record for proton_mail.
    """
    store = CredentialStore(runtime.root)
    store.set_token("proton-mail", email)
    store.set_token("proton-mail-password", password)
    store.set_token("proton-bridge-smtp", password)  # email_manager + hook lookup
    # Vault integration record (keyring:integration:proton_mail + state).
    vault_put_secret(
        runtime,
        service_id="proton_mail",
        secret=password,
        auth_method="bridge_imap_smtp",
        mode="read",
    )


# ---------------------------------------------------------------------------
# Connect (background)
# ---------------------------------------------------------------------------


def launch_proton_connect(runtime: SubstrateRuntime, email: str = "", totp: str = "") -> dict[str, Any]:
    """Kick off the bridge login in a background thread; returns immediately."""
    if not email or not email.strip():
        # Driver falls back to a stored email; only set a default if none stored.
        from .proton_support import EMAIL_KEYS as _EK  # noqa: PLC0415
        try:
            has = any(CredentialStore(runtime.root).get_token(k) for k in _EK)
        except Exception:  # noqa: BLE001
            has = False
        email = ("" if has else DEFAULT_EMAIL)
    uv = shutil.which("uv") or "/home/ahron/.local/bin/uv"
    cmd = [uv, "run", "--with", "pexpect", "python", "scripts/proton_connect.py", "connect"]
    if email and email.strip():
        cmd += ["--email", email]
    env = {"SUBSTRATE_ROOT": str(runtime.root)}
    if totp and totp.strip():
        env["PROTON_TOTP"] = totp.strip()

    started_at = datetime.now(UTC).isoformat()
    state_path = runtime.root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"status": "starting", "stage": "launch", "started_at": started_at,
                    "email": redact(runtime, email)}, indent=2),
        encoding="utf-8",
    )

    def _worker() -> None:
        log_path = runtime.root / LOG_FILE
        try:
            with open(log_path, "w", encoding="utf-8") as fh:
                proc = subprocess.run(cmd, cwd=runtime.root, env=env, stdout=fh,
                                      stderr=subprocess.STDOUT, timeout=600)
            if proc.returncode != 0:
                # The script already wrote a sanitized state payload; ensure a
                # terminal state exists even if it crashed early.
                current = json.loads(state_path.read_text(encoding="utf-8"))
                if current.get("status") in ("running", "starting"):
                    state_path.write_text(
                        json.dumps({"status": "failed", "stage": "driver",
                                    "detail": f"driver exit code {proc.returncode}; see log",
                                    "finished_at": datetime.now(UTC).isoformat()}, indent=2),
                        encoding="utf-8",
                    )
        except Exception as exc:  # noqa: BLE001
            state_path.write_text(
                json.dumps({"status": "failed", "stage": "launch",
                            "detail": f"{type(exc).__name__}: {exc}",
                            "finished_at": datetime.now(UTC).isoformat()}, indent=2),
                encoding="utf-8",
            )

    thread = threading.Thread(target=_worker, name="proton-connect", daemon=True)
    thread.start()
    return {"ok": True, "started_at": started_at, "email": redact(runtime, email)}


# ---------------------------------------------------------------------------
# Verify (explicit user action; single bounded probe)
# ---------------------------------------------------------------------------


def verify_proton(runtime: SubstrateRuntime) -> dict[str, Any]:
    """One-shot IMAP probe + Drive remote check. Never retried in a loop."""
    from .credentials import CredentialStore as _CS  # noqa: PLC0415

    store = _CS(runtime.root)
    email = None
    for key in EMAIL_KEYS:
        val = store.get_token(key)
        if val:
            email = val
            break
    password = None
    for key in PASSWORD_KEYS:
        val = store.get_token(key)
        if val:
            password = val
            break

    surfaces = {
        "mail": {"ok": False, "detail": "no stored credentials"},
        "drive": {"ok": bool(_drive_remotes()), "detail": _drive_remotes() or "no rclone Proton Drive remote configured"},
    }
    if not email or not password:
        surfaces["mail"] = {"ok": False, "detail": "no stored credentials — connect first"}
    elif not _service_active(BRIDGE_SERVICE):
        surfaces["mail"] = {"ok": False, "detail": "Proton Mail Bridge service is not running"}
    else:
        import imaplib  # noqa: PLC0415

        try:
            conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
            conn.starttls()
            conn.login(email, password)
            typ, data = conn.select("INBOX", readonly=True)
            surfaces["mail"] = {
                "ok": typ == "OK",
                "detail": f"IMAP login OK; INBOX select {typ}"
                          + (f" ({len(data[0])} messages)" if typ == "OK" and data and data[0] else ""),
            }
            conn.logout()
        except Exception as exc:  # noqa: BLE001
            surfaces["mail"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    from .security.audit_trail import AuditTrail  # noqa: PLC0415

    AuditTrail(runtime.root / "state" / "crypto" / "audit.jsonl").append(
        "proton_verify", tier=1,
        details={"mail_ok": surfaces["mail"]["ok"], "drive_ok": surfaces["drive"]["ok"]},
    )
    return {"ok": all(s["ok"] for s in surfaces.values()), "surfaces": surfaces}


# ---------------------------------------------------------------------------
# Test email (explicit user action — outbound stays human-initiated)
# ---------------------------------------------------------------------------


def send_test_email(runtime: SubstrateRuntime) -> dict[str, Any]:
    """Send one verification email through the approval lane (user clicked)."""
    from .cli import main as cli_main

    try:
        code = cli_main(["approval-lane", "send-test", "--channel", "email"])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {"ok": code == 0, "detail": f"approval-lane send-test exit code {code}"}


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


def disconnect_proton(runtime: SubstrateRuntime) -> dict[str, Any]:
    """Remove Proton secrets from the keyring and mark integrations disconnected.

    Services are left running; without credentials they idle rather than
    retry (no login-attempt storms).
    """
    store = CredentialStore(runtime.root)
    removed: list[str] = []
    for key in ("proton-mail", "proton-mail-password", "proton-bridge-smtp", "integration:proton_mail"):
        try:
            store.set_token(key, "")  # overwrite; delete is best-effort below
            removed.append(key)
        except Exception:  # noqa: BLE001
            pass
    try:
        vault_delete_secret(runtime, service_id="proton_mail")
    except Exception:  # noqa: BLE001
        pass

    from .security.audit_trail import AuditTrail  # noqa: PLC0415

    AuditTrail(runtime.root / "state" / "crypto" / "audit.jsonl").append(
        "proton_disconnect", tier=1, details={"removed": removed},
    )
    return {"ok": True, "removed": removed, "note": "Services left running; re-connect from the panel to re-auth."}
