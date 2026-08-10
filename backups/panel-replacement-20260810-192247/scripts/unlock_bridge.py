#!/usr/bin/env python3
"""Unlock the Proton Mail Bridge account for local IMAP/SMTP access.

The bridge account is loaded and syncing but **locked**: its addresses are not
registered with the local IMAP/SMTP servers until the mailbox password is
entered. This script:

1. Prompts for the mailbox password via a zenity GUI dialog (hidden entry) -
   the password is the one set at bridge login (the Proton password, or the
   custom mailbox password chosen during the CLI login).
2. Tries an IMAP login (127.0.0.1:1143) with the password, which unlocks the
   account and registers its addresses.
3. Persists the password (0600) in the approval-lane IMAP config for reply
   polling, then issues ``approval-lane send-test --channel email``.
4. Reports the result in a GUI dialog.

Usage:
    uv run python scripts/unlock_bridge.py
"""

from __future__ import annotations

import imaplib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAP_CFG_PATH = Path.home() / ".config" / "substrate" / "approval_lane.json"

EMAIL = "ahronzombi@protonmail.com"


def zenity(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["zenity", *args], capture_output=True, text=True)


def try_imap_login(username: str, password: str) -> tuple[bool, str]:
    try:
        conn = imaplib.IMAP4("127.0.0.1", 1143, timeout=10)
        conn.starttls()
        conn.login(username, password)
        conn.select("INBOX")
        conn.logout()
        return True, f"IMAP login OK for {username}"
    except imaplib.IMAP4.error as exc:
        return False, f"IMAP login failed for {username}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def save_imap_password(password: str) -> None:
    IMAP_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if IMAP_CFG_PATH.exists():
        try:
            cfg = json.loads(IMAP_CFG_PATH.read_text())
        except (OSError, ValueError):
            cfg = {}
    cfg["imap"] = {
        "host": "127.0.0.1",
        "port": 1143,
        "username": EMAIL,
        "password": password,
    }
    cfg.setdefault("channels", {})["email"] = {"address": EMAIL}
    IMAP_CFG_PATH.write_text(json.dumps(cfg, indent=2))
    IMAP_CFG_PATH.chmod(0o600)


def main() -> int:
    result = zenity(
        "--entry",
        "--title=Proton Mail Bridge Unlock",
        "--text=Enter the mailbox password for ahronzombi@protonmail.com "
        "(the password you used to log into the bridge - your Proton password "
        "or the custom mailbox password set during login):",
        "--hide-text",
        "--width=560",
        "--ok-label=Unlock",
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("cancelled - no password provided")
        return 2
    password = result.stdout.strip()

    for username in (EMAIL, "ahronzombi"):
        ok, detail = try_imap_login(username, password)
        if ok:
            save_imap_password(password)
            print(f"UNLOCKED ({detail})")
            zenity("--info", "--title=Proton Mail Bridge",
                   "--text=Account unlocked. Sending the approval-lane test message...")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "substrate_cli.py"),
                 "approval-lane", "send-test", "--channel", "email"],
                capture_output=True, text=True, timeout=90,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            print(out[-800:])
            zenity("--info", "--title=Approval Lane",
                   "--text=Delivery attempt complete.\n\n" + out[-800:].replace(password, "***"))
            return 0 if proc.returncode == 0 else 1
        print(detail)

    zenity("--error", "--title=Proton Mail Bridge",
           "--text=Unlock failed - the mailbox password was rejected. "
           "Check the password and try again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
