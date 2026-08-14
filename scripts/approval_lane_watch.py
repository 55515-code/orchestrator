#!/usr/bin/env python3
"""Autonomous approval-lane watch loop.

Runs ``approval-lane watch`` (one pass) every ``--interval`` seconds, keeping
the lane alive without any operator login:

1. Retries test-message delivery for unverified channels (email/SMS become
   deliverable the moment the operator supplies the missing credentials).
2. Polls the verified primary channel for coded replies and auto-verifies /
   auto-resolves approvals.
3. Emits the "primary lane is live" confirmation through the verified channel
   exactly once.

Each pass is appended to ``state/approval-lane-watch.json``. Failures are
logged, never fatal. Idempotent: it never re-sends a test while a code is
awaiting reply, and never verifies without a matching reply code.

Usage:
    uv run python scripts/approval_lane_watch.py                # default 30min
    uv run python scripts/approval_lane_watch.py --interval 300 # every 5 min
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.approvals import watch_once


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=1800, help="Seconds between passes (default 1800).")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit.")
    args = parser.parse_args()

    log_path = Path(ROOT) / "state" / "approval-lane-watch.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    runtime = _runtime()
    passes = 0
    while True:
        passes += 1
        started = utc_now()
        try:
            summary = watch_once(runtime)
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - never die; report and continue
            summary = {"error": f"{type(exc).__name__}: {exc}"}
            status = "error"
        record = {
            "pass": passes,
            "started_at": started,
            "finished_at": utc_now(),
            "status": status,
            "summary": summary,
        }
        history = []
        if log_path.exists():
            try:
                history = json.loads(log_path.read_text())
                if not isinstance(history, list):
                    history = []
            except (OSError, ValueError):
                history = []
        history.append(record)
        log_path.write_text(json.dumps(history[-500:], indent=2, ensure_ascii=False))

        print(json.dumps(record, indent=2, ensure_ascii=False))
        if args.once:
            return 0 if status == "ok" else 1
        time.sleep(max(60, args.interval))


def _runtime():
    from types import SimpleNamespace

    from substrate.settings import workspace_paths

    root = Path(ROOT)
    paths = workspace_paths(root)
    return SimpleNamespace(root=root, paths=paths)


if __name__ == "__main__":
    raise SystemExit(main())
