#!/usr/bin/env python3
"""Drive the Proton Mail Bridge interactive CLI login.

Purpose
-------
The Proton Mail Bridge (v3) loads zero accounts because the v2->v3 migration
failed before the keychain was available. The keychain (Secret Service) is now
usable, so the account must be added through the bridge's interactive CLI.

This script drives that login non-interactively:
  1. Stops the systemd bridge service (the daemon holds the CLI lock).
  2. Spawns ``protonmail-bridge-core --cli`` and answers the login prompts.
  3. Waits for success/failure, prints the account info, exits.
  4. Restarts the service (always, even on failure).
  5. Verifies the lane with ``approval-lane send-test --channel email``.

Credentials intake
------------------
The password is read from a file (default ``~/.proton_login_pw``), never from
argv or the chat transcript. Create it yourself and ``chmod 600`` it, e.g.:

    printf '%s\\n' 'YOUR-PROTON-PASSWORD' > ~/.proton_login_pw
    chmod 600 ~/.proton_login_pw

Optionally pass ``--twofa CODE`` for a TOTP code when 2FA is enabled. After a
successful login the temporary password file is deleted (the password is only
retained in the IMAP section of the substrate approval-lane config, 0600, for
reply polling).

Usage:
    uv run --with pexpect python scripts/bridge_login.py --email ahronzombi@proton.me
    uv run --with pexpect python scripts/bridge_login.py --email ahronzombi@proton.me --twofa 123456
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PW_FILE = Path.home() / ".proton_login_pw"
IMAP_CFG_PATH = Path.home() / ".config" / "substrate" / "approval_lane.json"

SUCCESS_MARKERS = (
    "successfully logged in",
    "logged in",
    "account added",
    "account connected",
    "welcome",
)
FAILURE_MARKERS = ("cannot login", "failed to", "invalid", "wrong", "error")


def run_unit(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def stop_bridge() -> None:
    run_unit(["systemctl", "--user", "stop", "protonmail-bridge.service"])
    time.sleep(1.5)


def start_bridge() -> None:
    run_unit(["systemctl", "--user", "start", "protonmail-bridge.service"])
    time.sleep(3)


def drive_login(email: str, password: str, twofa: str | None) -> tuple[bool, str]:
    import pexpect  # available via `uv run --with pexpect`

    child = pexpect.spawn("/usr/bin/protonmail-bridge-core", ["--cli"],
                          encoding="utf-8", timeout=90)
    transcript: list[str] = []

    def wait_for(patterns: list[str], label: str, send: str | None = None) -> bool:
        try:
            child.expect(patterns, timeout=60)
            transcript.append(child.before or "")
            transcript.append(child.after or "")
            if send is not None:
                child.sendline(send)
            return True
        except pexpect.TIMEOUT:
            transcript.append(f"[timeout waiting for {label}]")
            return False

    try:
        # Shell banner; the first "Username:" comes after we issue `login`.
        wait_for([r"Username:\s*", r"Welcome to Proton Mail Bridge"], "shell ready")
        child.sendline("login")
        if not wait_for([r"Username:\s*"], "username prompt"):
            return False, "timed out waiting for username prompt"
        child.sendline(email)
        if not wait_for([r"Password:\s*"], "password prompt"):
            return False, "timed out waiting for password prompt"
        child.sendline(password)
        if twofa:
            if not wait_for(
                [r"(?i)(2fa|two.factor|authentication code|totp|security code)[^\n]*[:.]\s*"],
                "2FA prompt",
            ):
                return False, "timed out waiting for 2FA prompt"
            child.sendline(twofa)
        # Success or failure marker, or the prompt returning.
        try:
            child.expect(
                [r"(?i)(successfully logged in|logged in|account (added|connected)|welcome|already logged in)",
                 r"(?i)(cannot login|failed to|invalid|wrong|error)",
                 r"(\w+@\w+\.\w+|All accounts are managed|>)", ],
                timeout=90,
            )
            transcript.append(child.before or "")
            transcript.append(child.after or "")
        except pexpect.TIMEOUT:
            transcript.append("[timeout waiting for login result]")
        time.sleep(2)
        # Capture account info, then exit cleanly.
        child.sendline("info")
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
        text = "\n".join(transcript)
        lowered = text.lower()
        if any(m in lowered for m in FAILURE_MARKERS) and "already logged in" not in lowered:
            return False, text[-800:]
        return True, text[-800:]
    except Exception as exc:  # noqa: BLE001
        try:
            child.close(force=True)
        except Exception:  # noqa: BLE001
            pass
        return False, f"{type(exc).__name__}: {exc}"


def write_imap_config(email: str, password: str) -> None:
    IMAP_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if IMAP_CFG_PATH.exists():
        try:
            cfg = json.loads(IMAP_CFG_PATH.read_text())
        except (OSError, ValueError):
            cfg = {}
    cfg.setdefault("channels", {})
    cfg.setdefault("imap", {
        "host": "127.0.0.1",
        "port": 1143,
        "username": email,
        "password": password,
    })
    IMAP_CFG_PATH.write_text(json.dumps(cfg, indent=2))
    IMAP_CFG_PATH.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Proton Mail address for the bridge account.")
    parser.add_argument("--password-file", type=Path, default=DEFAULT_PW_FILE,
                        help="Path to the 0600 file containing the password.")
    parser.add_argument("--twofa", default=None, help="TOTP code (only when 2FA is enabled).")
    parser.add_argument("--keep-creds", action="store_true",
                        help="Do not delete the temporary password file after success.")
    args = parser.parse_args()

    pw_path = args.password_file.expanduser()
    if not pw_path.exists():
        print(f"ERROR: password file not found: {pw_path}\n"
              f"Create it with: printf '%s\\n' 'PASSWORD' > {pw_path} && chmod 600 {pw_path}")
        return 2
    if (pw_path.stat().st_mode & 0o777) not in (0o600, 0o400):
        print(f"ERROR: password file must be 0600: {pw_path} (mode {oct(pw_path.stat().st_mode & 0o777)})")
        return 2
    password = pw_path.read_text().strip().splitlines()[0]

    print("[1/4] Stopping bridge daemon ...")
    stop_bridge()
    try:
        print(f"[2/4] Driving interactive login for {args.email} ...")
        ok, detail = drive_login(args.email, password, args.twofa)
    finally:
        print("[3/4] Restarting bridge daemon ...")
        start_bridge()

    if not ok:
        print(f"LOGIN FAILED:\n{detail}")
        print("\nThe daemon has been restarted. Check the address, password, and 2FA code.")
        return 1

    print(f"LOGIN OK:\n{detail}")
    if not args.keep_creds:
        try:
            pw_path.unlink(missing_ok=True)
            print(f"Temporary password file deleted: {pw_path}")
        except OSError as exc:
            print(f"WARN: could not delete {pw_path}: {exc}")
    write_imap_config(args.email, password)
    print(f"IMAP reply-polling credentials written to {IMAP_CFG_PATH} (0600)")

    print("[4/4] Verifying delivery through the approval lane ...")
    r = run_unit([sys.executable, "scripts/substrate_cli.py", "approval-lane",
                  "send-test", "--channel", "email"], timeout=90)
    print(r.stdout[-600:] if r.stdout else r.stderr[-600:])
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
