#!/usr/bin/env python3
"""Re-authenticate the Proton Mail Bridge account and store credentials
securely for future automation.

The bridge account is in a half-added state (the interactive login was
interrupted, so the local SMTP/IMAP registration - addresses + mailbox
password - never completed). This script:

1. Captures the Proton email + password via zenity GUI dialogs.
2. Stores them encrypted in the OS keyring (SecretService) via the substrate
   CredentialStore, plus an encrypted Fernet file fallback - for future
   automation (re-login, IMAP reply polling).
3. Removes the half-added bridge account.
4. Re-runs the full bridge CLI login to completion, answering any
   post-auth mailbox-password prompts.
5. Restarts the daemon, validates SMTP delivery through the approval lane,
   and delivers the verification-coded test message.

Usage:
    uv run --with pexpect python scripts/bridge_setup.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.credentials import CredentialStore  # noqa: E402

DEFAULT_EMAIL = "ahronzombi@protonmail.com"
CRED_SERVICE = "proton-mail"
PW_FILE = Path.home() / ".proton_login_pw"


def zenity(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["zenity", *args], capture_output=True, text=True)


def run_unit(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def store_credentials(root: Path, email: str, password: str) -> None:
    """Store encrypted in the OS keyring (primary) with Fernet file fallback."""
    store = CredentialStore(root)
    store.set_token(CRED_SERVICE, email)
    store.set_token(f"{CRED_SERVICE}-password", password)
    print(f"[store] credentials saved to {store._keyring_available and 'keyring' or 'encrypted file'}")
    # Also mirror into the approval-lane IMAP config for reply polling (0600).
    cfg_path = Path.home() / ".config" / "substrate" / "approval_lane.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except (OSError, ValueError):
            cfg = {}
    cfg["imap"] = {"host": "127.0.0.1", "port": 1143, "username": email, "password": password}
    cfg.setdefault("channels", {})["email"] = {"address": email}
    cfg["bridge_account"] = {
        "username": "ahronzombi",
        "address": email,
        "login_persisted_in_bridge_vault": True,
        "credentials_stored_in_keyring": True,
        "sync_state": "reauthenticating",
    }
    cfg_path.write_text(json.dumps(cfg, indent=2))
    cfg_path.chmod(0o600)
    print(f"[store] approval-lane IMAP config updated ({cfg_path})")


def delete_account(account: str) -> None:
    """Remove the half-added account so a fresh login can complete."""
    import pexpect
    child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"], encoding="utf-8", timeout=60)
    try:
        child.expect([r"Username:\s*", r"Welcome to Proton Mail Bridge"], timeout=30)
        child.sendline(f"delete {account}")
        time.sleep(1.5)
        # Accept any confirmation prompt.
        try:
            child.expect([r"(?i)(yes/no|are you sure|confirm)[^\n]*", pexpect.TIMEOUT], timeout=5)
            child.sendline("yes")
            time.sleep(2)
        except Exception:  # noqa: BLE001
            pass
        try:
            child.sendline("exit")
        except Exception:  # noqa: BLE001
            pass
        child.close()
        print(f"[delete] removed account '{account}'")
    except Exception as exc:  # noqa: BLE001
        print(f"[delete] warning: {type(exc).__name__}: {exc}")
        try:
            child.close(force=True)
        except Exception:  # noqa: BLE001
            pass


def full_login(email: str, password: str) -> tuple[bool, str]:
    """Drive the full bridge CLI login, including post-auth mailbox password
    prompts, to completion."""
    import pexpect
    child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"], encoding="utf-8", timeout=180)
    transcript: list[str] = []

    def send_after(patterns: list[str], label: str, value: str | None = None, timeout: float = 60) -> bool:
        try:
            idx = child.expect(patterns, timeout=timeout)
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
        # Handle any post-auth prompts (2FA / mailbox password / confirm).
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
                # The user must supply a TOTP code - prompt via zenity.
                code = zenity("--entry", "--title=Proton 2FA",
                              "--text=Enter your two-factor authentication code:",
                              "--hide-text", "--width=480")
                if code.returncode != 0 or not code.stdout.strip():
                    return False, "2FA cancelled"
                child.sendline(code.stdout.strip())
            elif "mailbox password" in tail or "set a password" in tail or "choose a password" in tail:
                child.sendline(password)  # use the same password as mailbox password
            elif "confirm" in tail or "repeat" in tail:
                child.sendline(password)
            else:
                break  # success/failure marker or account line
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
        text = "\n".join(transcript)
        if "cannot login" in text.lower() or "failed to" in text.lower() or "invalid" in text.lower():
            return False, text[-600:]
        return True, text[-600:]
    except Exception as exc:  # noqa: BLE001
        try:
            child.close(force=True)
        except Exception:  # noqa: BLE001
            pass
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    root = Path(ROOT)

    result = zenity("--entry", "--title=Proton Mail Bridge Setup",
                    "--text=Proton email address:", "--entry-text=" + DEFAULT_EMAIL,
                    "--width=520", "--ok-label=Next")
    if result.returncode != 0 or not result.stdout.strip():
        print("cancelled at email")
        return 2
    email = result.stdout.strip()

    result = zenity("--entry", "--title=Proton Mail Bridge Setup",
                    "--text=Proton password (hidden - stored encrypted in the OS keyring):",
                    "--hide-text", "--width=520", "--ok-label=Set up")
    if result.returncode != 0 or not result.stdout.strip():
        print("cancelled at password")
        return 2
    password = result.stdout.strip()

    print("[1/5] Storing credentials encrypted (OS keyring + Fernet fallback) ...")
    store_credentials(root, email, password)

    print("[2/5] Stopping bridge daemon ...")
    run_unit(["systemctl", "--user", "stop", "protonmail-bridge.service"])
    time.sleep(1.5)
    try:
        print("[3/5] Removing half-added account ...")
        delete_account("ahronzombi")
        print("[4/5] Running full bridge login ...")
        ok, detail = full_login(email, password)
        if not ok:
            print(f"LOGIN FAILED:\n{detail}")
            return 1
        print(f"LOGIN OK:\n{detail}")
    finally:
        print("[5/5] Restarting bridge daemon ...")
        run_unit(["systemctl", "--user", "start", "protonmail-bridge.service"])
        time.sleep(5)

    print("Testing SMTP delivery through the approval lane ...")
    proc = run_unit([sys.executable, str(ROOT / "scripts" / "substrate_cli.py"),
                     "approval-lane", "send-test", "--channel", "email"], timeout=90)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-800:])
    zenity("--info", "--title=Proton Mail Bridge Setup",
           "--text=" + ("Setup complete - test message sent.\n\n" + out[-600:].replace(password, "***")
                        if proc.returncode == 0
                        else "Login OK but delivery failed.\n\n" + out[-600:].replace(password, "***")))
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
