#!/usr/bin/env python3
"""GUI (zenity) login prompt for the Proton Mail Bridge account.

Pops up desktop dialogs that ask for the Proton email address, the password
(hidden entry), and an optional two-factor code. The password is written to a
0600 temp file and consumed by ``scripts/bridge_login.py`` (which stops the
daemon, drives the bridge CLI login, restarts the daemon, verifies the email
lane, and deletes the temp file). The password never enters the chat
transcript or argv.

Requires a graphical session (zenity + display). Cancel any dialog to abort.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PW_FILE = Path.home() / ".proton_login_pw"


def zenity(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["zenity", *args], capture_output=True, text=True)


def scrub_password(text: str, password: str) -> str:
    return text.replace(password, "***") if password else text


def main() -> int:
    # 1. Email address.
    result = zenity(
        "--entry",
        "--title=Proton Mail Bridge Login",
        "--text=Proton email address (the address you use to log in):",
        "--width=520",
        "--ok-label=Next",
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("aborted at email prompt (cancelled or empty)")
        return 2
    email = result.stdout.strip()

    # 2. Password (hidden entry).
    result = zenity(
        "--entry",
        "--title=Proton Mail Bridge Login",
        "--text=Proton password (hidden):",
        "--hide-text",
        "--width=520",
        "--ok-label=Next",
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("aborted at password prompt (cancelled or empty)")
        return 2
    password = result.stdout.strip()

    # 3. Optional two-factor code.
    twofa: str | None = None
    result = zenity(
        "--entry",
        "--title=Proton Mail Bridge Login",
        "--text=Two-factor authentication code (leave empty / press Cancel if "
        "2FA is not enabled):",
        "--width=520",
        "--ok-label=Log in",
    )
    if result.returncode == 0 and result.stdout.strip():
        twofa = result.stdout.strip()

    # Persist the password for the one-shot login driver.
    PW_FILE.write_text(password + "\n")
    PW_FILE.chmod(0o600)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "bridge_login.py"),
        "--email", email,
    ]
    if twofa:
        cmd += ["--twofa", twofa]
    print(f"running: bridge_login.py --email {email}" + (" --twofa <code>" if twofa else ""))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    output = scrub_password((proc.stdout or "") + (proc.stderr or ""), password)

    if proc.returncode == 0:
        zenity(
            "--info",
            "--title=Proton Mail Bridge",
            "--width=640",
            "--text=" + (
                "Login successful. The email approval lane is being verified.\n\n"
                f"{output[-900:]}"
            ),
        )
    else:
        zenity(
            "--error",
            "--title=Proton Mail Bridge",
            "--width=640",
            "--text=" + (
                "Login FAILED. See details below, then run this again.\n\n"
                f"{output[-900:]}"
            ),
        )
    print(output[-1200:])
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
