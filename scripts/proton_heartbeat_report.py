#!/usr/bin/env python3
"""Heartbeat alert reporter for the Proton Mail subsystem.

Deterministic companion to proton_health_check.py for heartbeat polls.
The heartbeat agent runs this script; it prints either:

  SILENT
or one or more alert/recovery lines (which the agent may relay).

Transition policy (no spam):
  - ok -> ok            : SILENT
  - ok -> degraded/down : alert (once per transition)
  - degraded -> down    : alert (escalation)
  - down/degraded -> ok : recovery notice (once)
  - down -> degraded    : de-escalation notice (once)
  - persistent degraded : re-alert at most every 24h
  - persistent down     : re-alert at most every 6h
  - ok -> degraded that self-heals within one health cycle is not alerted
    if it never reached the heartbeat (handled by state transitions above)

State: /home/ahron/codespace/state/proton-heartbeat-state.json
  last_status, last_alert_at, last_alert_kind
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HEALTH_FILE = Path.home() / "codespace" / "state" / "proton-health.json"
ALERT_STATE = Path.home() / "codespace" / "state" / "proton-heartbeat-state.json"

REALERT_DEGRADED_S = 24 * 3600
REALERT_DOWN_S = 6 * 3600

STATUS_EMOJI = {"ok": "✅", "degraded": "⚠️", "down": "🔴"}


def _load_health() -> dict | None:
    try:
        return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _load_state() -> dict:
    try:
        return json.loads(ALERT_STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state: dict) -> None:
    ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    health = _load_health()
    if health is None:
        print("⚠️ Proton health state file unreadable — health check may not be running.")
        return 0

    status = health.get("status", "unknown")
    prev = _load_state()
    last_status = prev.get("last_status")
    last_alert_at = prev.get("last_alert_at")

    now = time.time()
    out: list[str] = []
    # Preserve prior alert metadata; only overwrite fields on a fresh alert.
    # Rebuilding the dict from scratch here would silently clear
    # last_alert_at/last_alert_kind on every silent heartbeat, resetting the
    # re-alert throttle (degraded 24h / down 6h) to fire on the very next run.
    new_state: dict = dict(prev)
    new_state["last_status"] = status

    def _ts(iso: str | None) -> float:
        if not iso:
            return 0.0
        try:
            return datetime.fromisoformat(iso).timestamp()
        except ValueError:
            return 0.0

    # Transition detection
    if status == "ok":
        if last_status in ("degraded", "down"):
            out.append("✅ Proton Mail subsystem recovered (now ok).")
            new_state["last_alert_at"] = _now_iso()
            new_state["last_alert_kind"] = "recovery"
        # ok -> ok: SILENT
    elif status in ("degraded", "down"):
        if last_status != status:
            # fresh transition into a problem state
            detail = health.get("checks", {})
            bad = [f"{k}: {v.get('detail', 'failed')}" for k, v in detail.items() if not v.get("ok")]
            emoji = STATUS_EMOJI.get(status, "⚠️")
            out.append(
                f"{emoji} Proton Mail subsystem {status} — "
                + ("; ".join(bad) if bad else "see state/proton-health.json")
            )
            new_state["last_alert_at"] = _now_iso()
            new_state["last_alert_kind"] = "transition"
        else:
            # persistent problem: re-alert on a bounded schedule
            interval = REALERT_DOWN_S if status == "down" else REALERT_DEGRADED_S
            if last_alert_at is None or now - _ts(last_alert_at) >= interval:
                emoji = STATUS_EMOJI.get(status, "⚠️")
                out.append(
                    f"{emoji} Proton Mail subsystem still {status} "
                    f"(first failure {health.get('first_failure_at', '?')})."
                )
                new_state["last_alert_at"] = _now_iso()
                new_state["last_alert_kind"] = "repeat"
    else:
        out.append(f"⚠️ Proton Mail subsystem status unknown: {status!r}")

    _save_state(new_state)
    if not out:
        print("SILENT")
    else:
        print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
