#!/usr/bin/env python3
"""Fully automated bridge fix: logout -> delete -> fresh login -> deliver.

The bridge account is "locked" (the interrupted login never set the mailbox
password). This script uses the credentials already stored in the substrate
keyring (proton-mail / proton-mail-password) to:

1. Stop the daemon.
2. Log out the half-added account (frees it from use).
3. Delete it.
4. Run a fresh login, answering Username / Password / 2FA / mailbox-password
   prompts (mailbox password = the stored password).
5. Restart the daemon.
6. Test SMTP delivery via the approval lane and deliver the test message.

No GUI interaction required - credentials come from the keyring.

Usage:
    uv run --with pexpect python scripts/bridge_fix_login.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.credentials import CredentialStore  # noqa: E402

EMAIL = "ahronzombi@protonmail.com"


def run_unit(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def cli_cmd(commands: list[str], timeout: float = 60) -> list[str]:
    """Run a sequence of bridge CLI commands via pexpect, capturing output."""
    import pexpect
    child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"],
                          encoding="utf-8", timeout=timeout)
    lines: list[str] = []
    try:
        child.expect([r"Username:\s*", r"Welcome to Proton Mail Bridge"], timeout=30)
        for cmd in commands:
            child.sendline(cmd)
            time.sleep(2)
        try:
            child.sendline("exit")
        except Exception:  # noqa: BLE001
            pass
        try:
            child.expect(pexpect.EOF, timeout=10)
        except Exception:  # noqa: BLE001
            pass
        child.close()
        return lines
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[cli error: {type(exc).__name__}: {exc}]")
        try:
            child.close(force=True)
        except Exception:  # noqa: BLE001
            pass
        return lines


def fresh_login(email: str, password: str) -> tuple[bool, str]:
    import pexpect
    child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"],
                          encoding="utf-8", timeout=180)
    transcript: list[str] = []

    def step(patterns: list[str], label: str, send: str | None = None,
             timeout: float = 90) -> bool:
        try:
            child.expect(patterns, timeout=timeout)
            transcript.append((child.before or "")[-200:])
            transcript.append(child.after or "")
            if send is not None:
                child.sendline(send)
            return True
        except pexpect.TIMEOUT:
            transcript.append(f"[timeout: {label}]")
            return False

    try:
        step([r"Username:\s*", r"Welcome to Proton Mail Bridge"], "shell", timeout=30)
        child.sendline("login")
        if not step([r"Username:\s*"], "username"):
            return False, "\n".join(transcript)
        child.sendline(email)
        if not step([r"Password:\s*"], "password"):
            return False, "\n".join(transcript)
        child.sendline(password)
        # Post-auth prompts: 2FA, mailbox password, confirm, or result.
        for _ in range(8):
            ok = step(
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
            if not ok:
                break
            tail = ((child.after or "") + (child.before or "")).lower()
            if any(k in tail for k in ("2fa", "two.factor", "totp", "security code")):
                transcript.append("[2FA required - prompting]")
                code = subprocess.run(
                    ["zenity", "--entry", "--title=Proton 2FA",
                     "--text=Enter your two-factor authentication code:",
                     "--hide-text", "--width=480"],
                    capture_output=True, text=True)
                if code.returncode != 0 or not code.stdout.strip():
                    return False, "2FA cancelled"
                child.sendline(code.stdout.strip())
            elif any(k in tail for k in ("mailbox password", "set a password", "choose a password", "new password")):
                child.sendline(password)  # mailbox password = stored password
            elif any(k in tail for k in ("confirm", "repeat")):
                child.sendline(password)
            else:
                break  # result marker / account line
        time.sleep(3)
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
        if "cannot login" in text.lower() or "failed to" in text.lower():
            return False, text[-700:]
        return True, text[-700:]
    except Exception as exc:  # noqa: BLE001
        try:
            child.close(force=True)
        except Exception:  # noqa: BLE001
            pass
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    store = CredentialStore(Path(ROOT))
    password = store.get_token("proton-mail-password")
    if not password:
        print("ERROR: password not found in keyring. Run bridge_setup.py once to store it.")
        return 2
    print(f"[creds] password loaded from keyring for {EMAIL}")

    print("[1/5] Stopping bridge daemon ...")
    run_unit(["systemctl", "--user", "stop", "protonmail-bridge.service"])
    time.sleep(2)
    try:
        print("[2/5] Logging out the half-added account ...")
        cli_cmd([f"logout {EMAIL}"])
        print("[3/5] Deleting the account ...")
        cli_cmd([f"delete {EMAIL}", "yes"])
        time.sleep(2)
        print("[4/5] Fresh full login (mailbox password = stored password) ...")
        ok, detail = fresh_login(EMAIL, password)
        if not ok:
            print(f"LOGIN FAILED:\n{detail}")
            return 1
        print(f"LOGIN OK:\n{detail}")
    finally:
        print("[5/5] Restarting bridge daemon ...")
        run_unit(["systemctl", "--user", "start", "protonmail-bridge.service"])
        time.sleep(6)

    print("Testing SMTP delivery ...")
    proc = run_unit([sys.executable, str(ROOT / "scripts" / "substrate_cli.py"),
                     "approval-lane", "send-test", "--channel", "email"], timeout=90)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-900:])
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
