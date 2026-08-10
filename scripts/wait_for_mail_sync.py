#!/usr/bin/env python3
"""Wait for the Proton Mail Bridge account sync to finish, then deliver the
approval-lane test message automatically.

The bridge account (ahronzombi@protonmail.com) is loaded and syncing; the SMTP
relay only accepts sends once the account's address registers after the initial
sync. This script polls the lane every ``--interval`` seconds and issues
``approval-lane send-test --channel email`` the moment delivery succeeds (the
verification-coded message lands in the inbox).

Usage:
    uv run python scripts/wait_for_mail_sync.py            # default 30s poll
    uv run python scripts/wait_for_mail_sync.py --timeout 1800
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=30, help="Seconds between attempts (default 30).")
    parser.add_argument("--timeout", type=int, default=1800, help="Give up after N seconds (default 1800).")
    args = parser.parse_args()

    started = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "substrate_cli.py"),
             "approval-lane", "send-test", "--channel", "email"],
            capture_output=True, text=True, timeout=60,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if '"ok": true' in out:
            print(f"DELIVERY OK on attempt {attempts}:")
            print(out[-800:])
            return 0
        detail = ""
        for line in out.splitlines():
            if '"detail"' in line:
                detail = line.strip()
        if attempts == 1 or attempts % 4 == 0:
            print(f"attempt {attempts} [{int(time.monotonic() - started)}s]: sync pending - {detail[:110]}")
        if time.monotonic() - started > args.timeout:
            print(f"TIMEOUT after {args.timeout}s; sync not complete yet. Last: {detail[:160]}")
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
