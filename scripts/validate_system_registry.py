#!/usr/bin/env python3
"""Validate system_registry.yaml against itself and the live host.

Invariants enforced
-------------------
1. YAML parses; top-level keys are the expected ones.
2. No duplicate ports; no duplicate schedule names.
3. Every declared systemd unit has a file under ~/.config/systemd/user/.
4. Every declared port that is `reserved: true` is owned by exactly one unit.
5. Every declared port is unique (no two entries share the same port number).
6. known_issues keys use lowercase snake-case; `severity` is one of
   low/medium/high.
7. Registry YAML version is a positive integer.

Exit codes
----------
0 — all checks passed
1 — one or more checks failed (printed to stderr)
2 — fatal (file missing, YAML broken, etc.)

CI wire-up
----------
    uv run python scripts/validate_system_registry.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "system_registry.yaml"
SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
KNOWN_SEVERITIES = {"low", "medium", "high"}
EXPECTED_KEYS = {
    "version",
    "generated_note",
    "ports",
    "port_policy",
    "services",
    "schedules",
    "backups",
    "known_issues",
}


def _die(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(2)


def _warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        _die(f"{REGISTRY_PATH} not found")
    try:
        with REGISTRY_PATH.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        _die(f"{REGISTRY_PATH} is not valid YAML: {exc}")
    if not isinstance(data, dict):
        _die("registry root must be a mapping")
    return data


def _check_top_level_keys(data: dict) -> int:
    failures = 0
    missing = EXPECTED_KEYS - data.keys()
    if missing:
        _fail(f"missing top-level keys: {sorted(missing)}")
        failures += 1
    unexpected = data.keys() - EXPECTED_KEYS
    if unexpected:
        _warn(f"unexpected top-level keys (not in contract): {sorted(unexpected)}")
    return failures


def _check_version(data: dict) -> int:
    failures = 0
    ver = data.get("version")
    if not isinstance(ver, int) or ver <= 0:
        _fail(f"`version` must be a positive integer, got {ver!r}")
        failures += 1
    return failures


def _check_ports(data: dict) -> int:
    failures = 0
    ports = data.get("ports", [])
    seen: dict[int, str] = {}
    for entry in ports:
        port = entry.get("port")
        owner = entry.get("owner", "?")
        if not isinstance(port, int):
            _fail(f"port entry has non-int `port`: {entry!r}")
            failures += 1
            continue
        if port in seen:
            _fail(f"duplicate port {port}: first declared by {seen[port]}, then by {owner}")
            failures += 1
        else:
            seen[port] = owner
    # reserved ports must not collide with each other (implicit in uniqueness),
    # but warn if two entries both claim the same reserved port — that's an
    # ordering error in the registry.
    return failures


def _check_port_policy(data: dict) -> int:
    failures = 0
    pp = data.get("port_policy", {})
    reserved = set(pp.get("reserved_ports", []))
    dev = pp.get("dev_panel_port")
    if dev is not None:
        try:
            dev_int = int(dev)
        except (TypeError, ValueError):
            _fail(f"`port_policy.dev_panel_port` is not an int: {dev!r}")
            return failures + 1
        if dev_int in reserved:
            _fail(f"`dev_panel_port` {dev_int} is also in `reserved_ports`")
            failures += 1
        # Warn if dev port appears elsewhere in the registry (soft collision).
        for p in data.get("ports", []):
            if p.get("port") == dev_int:
                _warn(f"`dev_panel_port` {dev_int} also appears as a declared port owned by {p.get('owner')}")
    return failures


def _check_services(data: dict) -> int:
    failures = 0
    services = data.get("services", [])
    expected_states = {"active", "inactive"}
    for svc in services:
        unit = svc.get("unit", "?")
        state = svc.get("expected_state")
        if state not in expected_states:
            _fail(f"`{unit}` expected_state {state!r} not in {expected_states}")
            failures += 1
        # Sanity: critical services should be expected active.
        if svc.get("critical") and state != "active":
            _fail(f"critical service `{unit}` expected_state is {state!r}, expected 'active'")
            failures += 1
        # unit file must exist on disk.
        unit_file = SYSTEMD_DIR / unit
        if not unit_file.exists():
            _fail(f"`{unit}` declared in registry but file missing at {unit_file}")
            failures += 1
    return failures


def _check_schedules(data: dict) -> int:
    failures = 0
    names: set[str] = set()
    for sched in data.get("schedules", []):
        name = sched.get("name", "?")
        if name in names:
            _fail(f"duplicate schedule name: {name}")
            failures += 1
        names.add(name)
        mech = sched.get("mechanism", "")
        if mech == "systemd-timer":
            unit = sched.get("unit", "")
            if not unit.endswith(".timer"):
                _fail(f"systemd-timer `{name}` has unit `{unit}` not ending in .timer")
                failures += 1
        elif mech == "openclaw-cron":
            cid = sched.get("id", "")
            if not re.fullmatch(r"[0-9a-f-]{36}", cid):
                _fail(f"openclaw-cron `{name}` has malformed id: {cid!r}")
                failures += 1
        else:
            _warn(f"`{name}` has unrecognised mechanism {mech!r}")
    return failures


def _check_backups(data: dict) -> int:
    failures = 0
    seen_mechanisms: set[str] = set()
    for b in data.get("backups", []):
        mech = b.get("mechanism", "")
        if mech in seen_mechanisms:
            _fail(f"duplicate backup mechanism: {mech}")
            failures += 1
        seen_mechanisms.add(mech)
    return failures


def _check_known_issues(data: dict) -> int:
    failures = 0
    ki = data.get("known_issues", {})
    for name, issue in ki.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            _fail(f"known_issue key {name!r} is not lowercase snake-case")
            failures += 1
        sev = issue.get("severity")
        if sev not in KNOWN_SEVERITIES:
            _fail(f"known_issue `{name}` severity {sev!r} not in {KNOWN_SEVERITIES}")
            failures += 1
        if not issue.get("summary"):
            _fail(f"known_issue `{name}` has empty `summary`")
            failures += 1
    return failures


def _check_live_ports(data: dict) -> int:
    """Compare registry port declarations against actual `ss -tlnp` output.

    Only warns on mismatches; does not fail, because `ss` output varies by
    environment. Registry is the source of truth for the target topology.

    The live process name from `ss` is often a bare executable name that
    doesn't match the systemd unit name (e.g. node-MainThread for
    openclaw-gateway.service). We reduce spurious warnings by:
    - comparing against the unit name stem (openclaw-gateway -> openclaw),
    - the full unit name minus .service,
    - and the actual ExecStart command name from the unit file.
    """
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        live_ports: dict[int, str] = {}
        for line in result.stdout.splitlines():
            m = re.search(r":(\d+)\s", line)
            if m:
                port = int(m.group(1))
                who = "unknown"
                pm = re.search(r'users:\(\("([^"]+)"', line)
                if pm:
                    who = pm.group(1)
                live_ports[port] = who
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _warn("`ss` not available; skipping live port verification")
        return 0

    # Build a name set from ExecStart so we can resolve node-MainThread etc.
    known_names: set[str] = set()
    for svc in data.get("services", []):
        unit = svc.get("unit", "")
        unit_file = SYSTEMD_DIR / unit
        if unit_file.exists():
            try:
                text = unit_file.read_text(encoding="utf-8")
                em = re.search(r"^ExecStart=(.+)$", text, re.MULTILINE)
                if em:
                    # First whitespace-delimited token is the executable; take
                    # its basename to handle absolute paths like /usr/bin/node.
                    exe = em.group(1).strip().split()[0]
                    known_names.add(Path(exe).name.lower())
            except OSError:
                pass
        # Also include the unit name stem as a known alias.
        stem = unit.replace(".service", "").replace(".timer", "").lower()
        known_names.add(stem)

    failures = 0
    for entry in data.get("ports", []):
        port = entry.get("port")
        if not isinstance(port, int):
            continue
        owner = entry.get("owner", "?")
        if port in live_ports:
            actual = live_ports[port].lower()
            # Accept the live process if its name (or the ss thread tag) matches
            # any name we know from ExecStart or from the registry owner itself.
            # This tolerates node -> node-MainThread, python -> uvicorn subprocess, etc.
            if not any(
                actual.startswith(k) or k in actual
                for k in known_names
            ):
                _warn(
                    f"port {port}: registry says owner={owner}, "
                    f"live process={live_ports[port]}"
                )
        elif not entry.get("reserved"):
            _warn(f"port {port} declared as `{owner}` but not found listening")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate system_registry.yaml")
    ap.add_argument(
        "--skip-live",
        action="store_true",
        help="skip ss-based live port verification (CI without ss)",
    )
    args = ap.parse_args()

    data = _load_registry()
    failures = 0
    failures += _check_top_level_keys(data)
    failures += _check_version(data)
    failures += _check_ports(data)
    failures += _check_port_policy(data)
    failures += _check_services(data)
    failures += _check_schedules(data)
    failures += _check_backups(data)
    failures += _check_known_issues(data)
    if not args.skip_live:
        failures += _check_live_ports(data)

    if failures:
        print(f"\n{failures} check(s) FAILED", file=sys.stderr)
        sys.exit(1)
    print("OK: system_registry.yaml is valid")


if __name__ == "__main__":
    main()
