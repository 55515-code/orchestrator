#!/usr/bin/env python3
"""Wire the free Gmail SMTP relay as the approval-lane email backend.

Fallback while the Proton Mail Bridge is being repaired. Uses Gmail's free
SMTP (smtp.gmail.com, STARTTLS) with an app password as the sender relay; the
lane still delivers to the operator's Proton inbox address.

Setup required (one minute, free):
1. Go to https://myaccount.google.com/apppasswords
   (create the app password; requires 2-step verification enabled).
2. This script prompts for it via a zenity GUI dialog (hidden entry).
3. It stores the app password in the OS keyring, writes the SMTP/IMAP config
   (0600), switches the lane's email channel to the 'smtp' backend, and sends
   the verification-coded test message.

Usage:
    uv run python scripts/setup_gmail_lane.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.credentials import CredentialStore  # noqa: E402

GMAIL = "ahronzombi@gmail.com"
TO_ADDRESS = "ahronzombi@protonmail.com"
LANE_STATE = Path(ROOT) / "state" / "approval-lane.json"
CONFIG_PATH = Path.home() / ".config" / "substrate" / "approval_lane.json"
CRED_SERVICE = "gmail-app-password"


def zenity(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["zenity", *args], capture_output=True, text=True)


def main() -> int:
    result = zenity(
        "--entry",
        "--title=Gmail App Password",
        "--text=Enter a Gmail app password for " + GMAIL + ".\n"
        "Create one at https://myaccount.google.com/apppasswords "
        "(free; needs 2-step verification on). Hidden entry:",
        "--hide-text",
        "--width=620",
        "--ok-label=Save & Test",
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("cancelled")
        return 2
    app_password = result.stdout.strip()

    # 1. Store in the OS keyring.
    store = CredentialStore(Path(ROOT))
    store.set_token(CRED_SERVICE, app_password)
    print("[1/4] app password stored in OS keyring")

    # 2. Write operator config (SMTP + IMAP), 0600.
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
        except (OSError, ValueError):
            cfg = {}
    cfg["smtp"] = {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": GMAIL,
        "password": app_password,
        "from": GMAIL,
    }
    cfg["imap"] = {
        "host": "imap.gmail.com",
        "port": 993,
        "username": GMAIL,
        "password": app_password,
    }
    cfg["lane"] = {"sender": "gmail_smtp", "to": TO_ADDRESS}
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)
    print("[2/4] SMTP/IMAP config written (0600)")

    # 3. Switch the lane email channel to the smtp backend (keep Proton to address).
    lane: dict = json.loads(LANE_STATE.read_text())
    em = lane.setdefault("channels", {}).setdefault("email", {})
    em["address"] = TO_ADDRESS
    em["backend"] = "smtp"
    em["status"] = "unconfigured"
    em["last_error"] = ""
    LANE_STATE.write_text(json.dumps(lane, indent=2, ensure_ascii=False))
    LANE_STATE.chmod(0o600)
    print("[3/4] lane email channel switched to gmail SMTP backend")

    # 4. Send the verification-coded test message.
    print("[4/4] sending test message ...")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "substrate_cli.py"),
         "approval-lane", "send-test", "--channel", "email"],
        capture_output=True, text=True, timeout=90,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-800:])
    zenity("--info", "--title=Approval Lane",
           "--text=" + (out[-700:].replace(app_password, "***")
                        if proc.returncode == 0
                        else "Delivery failed.\n\n" + out[-700:].replace(app_password, "***")))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
