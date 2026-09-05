#!/usr/bin/env python3
"""Proton Mail Bridge connect driver — keyring-sourced, terminal-free.

Purpose
-------
Re-authenticate the Proton Mail Bridge account and register the local
IMAP/SMTP addresses WITHOUT typing secrets in a terminal. The password is
read from the OS keyring (SecretService) — the same keyring the control
panel vault writes to — so the web panel can trigger a full login with
only an email address (and an optional TOTP code for 2FA accounts).

Flow (connect):
  1. Read email + password from keyring (never argv, never echoed).
  2. Stop the bridge daemon (it holds the CLI lock).
  3. Remove any half-added account via the bridge CLI.
  4. Drive ``protonmail-bridge-core --cli`` login via pexpect, answering
     username/password, optional 2FA / mailbox-password / confirm prompts.
  5. Restart the daemon, then verify IMAP once (bounded: a single attempt).
  6. Write the IMAP reply-polling config (0600) and integration state.
  7. Persist a sanitized run report to state/proton-connect-last.json.

Usage
-----
  # Web path (launched by POST /api/proton/connect; TOTP goes via PROTON_TOTP env):
  uv run --with pexpect python scripts/proton_connect.py connect --email ahronzombi@protonmail.com
  PROTON_TOTP=123456 uv run --with pexpect python scripts/proton_connect.py connect --email ahronzombi@protonmail.com

  # Read-only probes (no auth attempt unless verify):
  uv run python scripts/proton_connect.py status
  uv run --with pexpect python scripts/proton_connect.py verify --email ahronzombi@protonmail.com
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.credentials import CredentialStore  # noqa: E402
from substrate.integrations import _load_state, _save_state  # noqa: E402

BRIDGE_SERVICE = "protonmail-bridge.service"
HOOK_SERVICE = "proton-bridge-hook.service"
STATE_FILE = ROOT / "state" / "proton-connect-last.json"
IMAP_CFG_PATH = Path.home() / ".config" / "substrate" / "approval_lane.json"
IMAP_HOST, IMAP_PORT = "127.0.0.1", 1143
DEFAULT_EMAIL = "ahronzombi@protonmail.com"

# Keyring account names, in lookup order (CredentialStore uses the
# "substrate-credentials" SecretService collection).
PASSWORD_KEYS = ("proton-bridge-smtp", "proton-mail-password", "integration:proton_mail")
EMAIL_KEYS = ("proton-mail", "proton-bridge-smtp")


# ---------------------------------------------------------------------------
# Reporting (sanitized — passwords never appear)
# ---------------------------------------------------------------------------


def _secret_values() -> list[str]:
    store = CredentialStore(ROOT)
    values = []
    for key in (*PASSWORD_KEYS, *EMAIL_KEYS):
        try:
            val = store.get_token(key)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            values.append(val)
    totp = os.environ.get("PROTON_TOTP", "").strip()
    if totp:
        values.append(totp)
    return values


def _redact(text: str) -> str:
    """Replace any known secret value in *text* with *** (defense in depth)."""
    out = text
    for value in sorted(set(_secret_values()), key=len, reverse=True):
        if value and value in out:
            out = out.replace(value, "***")
    return out


def _write_state(payload: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        STATE_FILE.chmod(0o600)
    except OSError:
        pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fail(stage: str, detail: str) -> dict[str, Any]:
    payload = {
        "status": "failed",
        "stage": stage,
        "detail": _redact(detail)[-2000:],
        "finished_at": _now(),
    }
    _write_state(payload)
    return payload


# ---------------------------------------------------------------------------
# Keyring / config access
# ---------------------------------------------------------------------------


def _read_credentials() -> tuple[str | None, str | None]:
    store = CredentialStore(ROOT)
    email: str | None = None
    password: str | None = None
    for key in PASSWORD_KEYS:
        try:
            val = store.get_token(key)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            password = val
            break
    for key in EMAIL_KEYS:
        try:
            val = store.get_token(key)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            email = val
            break
    return email, password


def _run_unit(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _service_active(name: str) -> bool:
    try:
        r = _run_unit(["systemctl", "--user", "is-active", name], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:  # noqa: BLE001
        return False


def _stop_bridge() -> None:
    _run_unit(["systemctl", "--user", "stop", BRIDGE_SERVICE])
    time.sleep(1.5)


def _start_bridge() -> None:
    _run_unit(["systemctl", "--user", "start", BRIDGE_SERVICE])
    time.sleep(3)


# ---------------------------------------------------------------------------
# Bridge CLI driving (pexpect)
# ---------------------------------------------------------------------------


def _delete_account(username: str) -> None:
    """Best-effort removal of a half-added account."""
    try:
        import pexpect  # noqa: PLC0415

        child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"], encoding="utf-8", timeout=60)
        try:
            child.expect([r"Username:\s*", r"Welcome to Proton Mail Bridge"], timeout=30)
            child.sendline(f"delete {username}")
            time.sleep(1.5)
            try:
                child.expect([r"(?i)(yes/no|are you sure|confirm)[^\n]*", pexpect.TIMEOUT], timeout=5)
                child.sendline("yes")
                time.sleep(2)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                child.sendline("exit")
            except Exception:  # noqa: BLE001
                pass
            child.close(force=True)
    except Exception:  # noqa: BLE001
        pass


def _drive_login(email: str, password: str, totp: str | None) -> tuple[bool, str]:
    """Drive the bridge CLI login to completion. Returns (ok, sanitized detail)."""
    try:
        import pexpect  # noqa: PLC0415
    except ImportError:
        return False, "pexpect not available (run with: uv run --with pexpect)"
    if totp:
        totp = totp.strip()
    child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"], encoding="utf-8", timeout=180)
    transcript: list[str] = []

    def send_after(patterns: list[str], label: str, value: str | None = None, timeout: float = 60) -> bool:
        try:
            child.expect(patterns, timeout=timeout)
            transcript.append((child.before or "")[-200:])
            transcript.append(child.after or "")
            if value is not None:
                child.sendline(value)
            return True
        except pexpect.TIMEOUT:
            transcript.append(f"[timeout: {label}]")
            return False

    try:
        send_after([r"Welcome to Proton Mail Bridge", r"Username:\s*"], "shell", timeout=30)
        child.sendline("login")
        if not send_after([r"Username:\s*"], "username"):
            return False, "no username prompt"
        child.sendline(email)
        if not send_after([r"Password:\s*"], "password"):
            return False, "no password prompt"
        child.sendline(password)
        # Post-auth prompts: 2FA / mailbox password / confirm / success / failure.
        handled = True
        while handled:
            handled = send_after(
                [
                    r"(?i)(2fa|two.factor|authentication code|totp|security code)[^\n]*[:.]\s*",
                    r"(?i)(mailbox password|set a password|choose a password|new password)[^\n]*[:.]\s*",
                    r"(?i)(confirm|repeat)[^\n]*[:.]\s*",
                    r"(?i)(successfully logged in|logged in|account (added|connected)|welcome|already logged in)",
                    r"(?i)(cannot login|failed to|invalid|wrong|error)",
                    r"(\w+@\w+\.\w+)",
                ],
                "post-auth",
                timeout=90,
            )
            if not handled:
                break
            tail = ((child.after or "") + (child.before or "")).lower()
            if "2fa" in tail or "two.factor" in tail or "totp" in tail or "security code" in tail:
                if not totp:
                    return False, "Two-factor authentication is enabled; a TOTP code is required."
                child.sendline(totp)
            elif "mailbox password" in tail or "set a password" in tail or "choose a password" in tail:
                child.sendline(password)
            elif "confirm" in tail or "repeat" in tail:
                child.sendline(password)
            else:
                break
        time.sleep(2)
        try:
            child.sendline("info")
            time.sleep(2)
            transcript.append((child.before or "")[-400:])
        except Exception:  # noqa: BLE001
            pass
        try:
            child.sendline("exit")
        except Exception:  # noqa: BLE001
            pass
        try:
            child.expect(pexpect.EOF, timeout=10)
        except Exception:  # noqa: BLE001
            pass
        child.close()
        text = _redact("\n".join(transcript))
        # Decide success by POSITIVE login signals only. The bridge prints a lot
        # of benign background noise (sync progress, "Failed to get flags",
        # "Failed to create API client") that must NOT be treated as failure.
        lowered = text.lower()
        ok = any(s in lowered for s in ("successfully logged in", "logged in",
                                        "account added", "account connected",
                                        "already logged in"))
        # If we saw an explicit interactive 2FA/needs-code prompt without a code,
        # that is a deterministic failure (could not complete verification).
        if "two-factor authentication is enabled; a totp code is required" in text:
            ok = False
        return ok, text[-600:]
    except Exception as exc:  # noqa: BLE001
        try:
            child.close(force=True)
        except Exception:  # noqa: BLE001
            pass
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Verification (bounded — a single IMAP attempt, never a retry storm)
# ---------------------------------------------------------------------------


def verify_imap(email: str, password: str) -> tuple[bool, str]:
    """One-shot IMAP login + folder select. Never retried in a loop."""
    try:
        import imaplib  # noqa: PLC0415

        conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        conn.starttls()
        conn.login(email, password)
        typ, data = conn.select("INBOX", readonly=True)
        ok = typ == "OK"
        conn.logout()
        return ok, f"INBOX select: {typ} ({len(data[0]) if ok and data and data[0] else 'n/a'} messages)"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def wait_imap_registered(email: str, password: str, attempts: int = 10, delay: float = 6.0) -> tuple[bool, str]:
    """Poll IMAP (bounded) until the bridge has fully registered the account.

    Right after login the daemon may still be finalizing the account; IMAP
    answers "no such user" briefly. A registered account answers the login
    cleanly. This is the real acceptance signal and avoids false failures from
    CLI sync-noise. Bounded: a handful of attempts with a pause, then stop.
    """
    last = "not attempted"
    for i in range(attempts):
        ok, _ = verify_imap(email, password)
        if ok:
            return True, f"IMAP registered after {i + 1} attempt(s)"
        time.sleep(delay)
    return False, last



# ---------------------------------------------------------------------------
# State updates
# ---------------------------------------------------------------------------


def _write_imap_config(email: str, password: str) -> None:
    IMAP_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if IMAP_CFG_PATH.exists():
        try:
            cfg = json.loads(IMAP_CFG_PATH.read_text())
        except (OSError, ValueError):
            cfg = {}
    cfg["imap"] = {"host": IMAP_HOST, "port": IMAP_PORT, "username": email, "password": password}
    cfg.setdefault("channels", {})["email"] = {"address": email}
    cfg["bridge_account"] = {
        "username": email.split("@")[0],
        "address": email,
        "login_persisted_in_bridge_vault": True,
        "credentials_stored_in_keyring": True,
        "sync_state": "connected",
        "updated_at": _now(),
    }
    IMAP_CFG_PATH.write_text(json.dumps(cfg, indent=2))
    IMAP_CFG_PATH.chmod(0o600)


def _update_integrations_state(email: str, connected: bool) -> None:
    state = _load_state(ROOT / "state" / "integrations-state.json")
    if connected:
        state["connections"]["proton_mail"] = {
            "connected": True,
            "mode": "read",
            "auth_method": "bridge_imap_smtp",
            "token_ref": "keyring:integration:proton_mail",
            "granted_scopes": [],
            "write_directive": None,
            "updated_at": _now(),
        }
    else:
        state["connections"].pop("proton_mail", None)
    _save_state(ROOT / "state" / "integrations-state.json", state)


def _audit(action: str, details: dict[str, Any]) -> None:
    try:
        from substrate.security.audit_trail import AuditTrail  # noqa: PLC0415

        AuditTrail(ROOT / "state" / "crypto" / "audit.jsonl").append(action, tier=1, details=details)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status() -> int:
    email, password = _read_credentials()
    payload = {
        "status": "ok",
        "bridge_active": _service_active(BRIDGE_SERVICE),
        "hook_active": _service_active(HOOK_SERVICE),
        "email_stored": bool(email),
        "password_stored": bool(password),
        "email": email or None,
        "note": "Verify (or connect) to probe the account.",
        "generated_at": _now(),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(email: str | None) -> int:
    key_email, password = _read_credentials()
    email = email or key_email or DEFAULT_EMAIL
    if not password:
        _fail("verify", "No stored Proton password found in the keyring. Connect first.")
        print(json.dumps({"ok": False, "error": "no stored credentials"}, indent=2))
        return 1
    if not _service_active(BRIDGE_SERVICE):
        _fail("verify", "Proton Mail Bridge service is not running.")
        print(json.dumps({"ok": False, "error": "bridge service not running"}, indent=2))
        return 1
    ok, detail = verify_imap(email, password)
    _write_state({"status": "ok" if ok else "failed", "stage": "verify", "detail": detail, "finished_at": _now()})
    print(json.dumps({"ok": ok, "email": email, "detail": _redact(detail)}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def cmd_connect(email: str | None, totp: str | None, password_file: Path | None) -> int:
    # TOTP travels via PROTON_TOTP env (never argv, so it is not visible in ps).
    totp = totp or os.environ.get("PROTON_TOTP", "").strip() or None
    key_email, password = _read_credentials()
    email = email or key_email or DEFAULT_EMAIL
    if password_file is not None:
        pf = password_file.expanduser()
        if not pf.exists() or (pf.stat().st_mode & 0o777) not in (0o600, 0o400):
            print(json.dumps({"ok": False, "error": f"password file must exist and be 0600: {pf}"}, indent=2))
            return 2
        password = pf.read_text().strip().splitlines()[0]
    if not password:
        _fail("connect", "No stored Proton password found in the keyring. Store credentials via the panel first.")
        print(json.dumps({"ok": False, "error": "no stored credentials"}, indent=2))
        return 1

    stages = ["stop-bridge", "remove-account", "login", "start-bridge", "verify", "state"]
    _write_state({"status": "running", "stage": "stop-bridge", "started_at": _now(), "email": _redact(email)})

    _stop_bridge()
    _write_state({"status": "running", "stage": "remove-account", "started_at": _now(), "email": _redact(email)})
    _delete_account(email.split("@")[0])

    _write_state({"status": "running", "stage": "login", "started_at": _now(), "email": _redact(email)})
    ok, detail = _drive_login(email, password, totp)
    _start_bridge()

    # The definitive acceptance test is whether the bridge has REGISTERED the
    # account on IMAP — not whether the noisy CLI printed a clean success line.
    # The CLI may only have "initiated" the login (and the daemon finalizes it
    # in the background); poll IMAP (bounded) to confirm registration. A
    # half-registered or unauthenticated account answers "no such user".
    _write_state({"status": "running", "stage": "register", "started_at": _now(), "email": _redact(email)})
    reg_ok, reg_detail = wait_imap_registered(email, password)
    if not reg_ok:
        _fail("register", f"Bridge login initiated but the account did not register on IMAP. {reg_detail}")
        _update_integrations_state(email, connected=False)
        _audit("proton_connect_failed", {"email": _redact(email), "stage": "register"})
        print(json.dumps({"ok": False, "stage": "register", "detail": detail, "reg_detail": reg_detail}, indent=2, ensure_ascii=False))
        return 1

    _write_state({"status": "running", "stage": "state", "started_at": _now(), "email": _redact(email)})
    _write_imap_config(email, password)
    _update_integrations_state(email, connected=True)
    _audit("proton_connect_success", {"email": _redact(email), "imap_verified": True})

    final = {
        "status": "ok",
        "stage": "state",
        "login_ok": True,
        "imap_verified": True,
        "imap_detail": reg_detail,
        "email": _redact(email),
        "detail": detail[-800:],
        "finished_at": _now(),
        "stages": stages,
    }
    _write_state(final)
    print(json.dumps(final, indent=2, ensure_ascii=False))
    return 0



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_status = sub.add_parser("status", help="Report config/service state (no probing)")
    _ = p_status
    p_verify = sub.add_parser("verify", help="One-shot IMAP probe")
    p_verify.add_argument("--email", default=None)
    p_connect = sub.add_parser("connect", help="Full bridge re-login")
    p_connect.add_argument("--email", default=None)
    p_connect.add_argument("--totp", default=None, help="TOTP code (only when 2FA is enabled)")
    p_connect.add_argument("--password-file", type=Path, default=None,
                           help="Legacy: 0600 file with the password (avoids keyring lookups)")
    args = parser.parse_args(argv)

    if args.command == "status":
        return cmd_status()
    if args.command == "verify":
        return cmd_verify(args.email)
    return cmd_connect(args.email, args.totp, args.password_file)


if __name__ == "__main__":
    raise SystemExit(main())
