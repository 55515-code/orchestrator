#!/usr/bin/env python3
"""Render system_registry.yaml into docs/generated/system-registry.md.

Usage
-----
    python scripts/generate_system_docs.py          # regenerate all
    python scripts/generate_system_docs.py --check   # CI mode: exit 1 if stale

This is the single writer for docs/generated/*.md. Any doc under that
directory MUST be produced by this script; hand-edits will be clobbered and
the --check mode will catch them.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "system_registry.yaml"
OUTPUT_PATH = REPO_ROOT / "docs" / "generated" / "system-registry.md"


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        print(f"fatal: {REGISTRY_PATH} not found", file=sys.stderr)
        sys.exit(2)
    with REGISTRY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _md_frontmatter(version: int | None = None) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "---\n"
        f"generated: {ts}\n"
        f"source: system_registry.yaml\n"
        f"generator: scripts/generate_system_docs.py\n"
        "status: auto-generated — DO NOT EDIT\n"
        "---\n"
        "\n"
    )


def _first_line(value: str | None) -> str:
    if not value:
        return "—"
    return value.splitlines()[0]


def _render_ports(registry: dict) -> str:
    lines = ["## Port Allocation\n", "| Port | Owner | Bind | Reserved | Purpose |\n",
             "|------|-------|------|----------|---------|\n"]
    for p in registry.get("ports", []):
        lines.append(
            f"| {p['port']} | {p['owner']} | {p['bind']} | "
            f"{'yes' if p.get('reserved') else 'no'} | "
            f"{_first_line(p.get('purpose'))} |\n"
        )
    pp = registry.get("port_policy", {})
    lines.append(f"\n**Dev panel port:** `{pp.get('dev_panel_port', '—')}` — {pp.get('rationale', '')}\n")
    lines.append(f"\n**Reserved ports (do not bind):** `{', '.join(str(p) for p in pp.get('reserved_ports', []))}`\n")
    return "".join(lines)


def _render_services(registry: dict) -> str:
    lines = ["## Services\n", "| Unit | Role | Purpose | Expected state | Critical |\n",
             "|------|------|---------|----------------|----------|\n"]
    for s in registry.get("services", []):
        lines.append(
            f"| `{s['unit']}` | {s.get('role','')} | "
            f"{_first_line(s.get('purpose'))} | "
            f"{s.get('expected_state','')} | "
            f"{'yes' if s.get('critical') else 'no'} |\n"
        )
    return "".join(lines)


def _render_schedules(registry: dict) -> str:
    systemd_lines = ["## Scheduled Automation\n\n### systemd timers\n",
                     "| Name | Cadence | Action | Expected state |\n",
                     "|------|---------|--------|----------------|\n"]
    cron_lines = ["### OpenClaw cron jobs\n",
                  "| Name | ID | Cadence | Action | Expected state |\n",
                  "|------|----|---------|--------|----------------|\n"]
    other_lines: list[str] = []
    for s in registry.get("schedules", []):
        mech = s.get("mechanism", "")
        action_short = _first_line(s.get("action"))
        row = (
            f"| {s['name']} | "
            + (f"`{s.get('id','')[:8]}` | " if mech == "openclaw-cron" else "")
            + f"{s.get('cadence','')} | "
            f"{action_short} | "
            f"{s.get('expected_state','')} |\n"
        )
        notes = s.get("notes")
        if notes:
            row = row.rstrip("\n") + f" *{_first_line(notes)}*\n"
        if mech == "systemd-timer":
            systemd_lines.append(row)
        elif mech == "openclaw-cron":
            cron_lines.append(row)
        else:
            other_lines.append(f"- **{s['name']}** ({mech}): {action_short}\n")
    return "".join(systemd_lines) + "\n" + "".join(cron_lines) + "\n" + "".join(other_lines)


def _render_backups(registry: dict) -> str:
    lines = ["## Backup and Recovery\n", "| Name | Mechanism | Schedule | Repository / Output | Verified |\n",
             "|------|-----------|----------|---------------------|----------|\n"]
    for b in registry.get("backups", []):
        loc = b.get("repository") or b.get("output") or "—"
        verified = "yes" if b.get("verified") else "partial" if b.get("restore") else "no"
        lines.append(
            f"| {b['name']} | {b['mechanism']} | {b.get('schedule','—')} | "
            f"{loc.splitlines()[0]} | {verified} |\n"
        )
    for b in registry.get("backups", []):
        lines.append(f"\n### {b['name']}\n")
        lines.append(f"- **Mechanism:** {b['mechanism']}\n")
        if b.get("driver"):
            lines.append(f"- **Driver:** `{b['driver']}`\n")
        if b.get("schedule"):
            lines.append(f"- **Schedule:** {b['schedule']}\n")
        if b.get("retention"):
            lines.append(f"- **Retention:** {b['retention']}\n")
        if b.get("covers"):
            lines.append("- **Covers:**\n")
            for item in b["covers"]:
                lines.append(f"  - {item}\n")
        if b.get("restore"):
            lines.append(f"- **Restore:** `{b['restore']}`\n")
        if b.get("notes"):
            lines.append(f"- **Notes:** {b['notes']}\n")
    return "".join(lines)


def _render_known_issues(registry: dict) -> str:
    ki = registry.get("known_issues", {})
    if not ki:
        return ""
    lines = ["## Known Issues\n"]
    for name, issue in ki.items():
        sev = issue.get("severity", "?")
        lines.append(f"### `{name}` — severity: {sev}\n")
        for key in ("summary", "evidence", "risk", "risk_if_changed_carelessly",
                    "mitigated", "mitigation", "rationale", "recommendation", "notes",
                    "status", "tracked_findings_by_family"):
            val = issue.get(key)
            if val:
                if isinstance(val, dict):
                    lines.append(f"**{key}:**\n")
                    for k2, v2 in val.items():
                        lines.append(f"  - `{k2}`: {v2}\n")
                else:
                    lines.append(f"**{key}:** {val}\n")
        lines.append("\n")
    return "".join(lines)


def render(registry: dict) -> str:
    version = registry.get("version")
    lines = [
        _md_frontmatter(version),
        f"# System Registry\n\n",
        f"> Auto-generated from `system_registry.yaml` v{version}.\n"
        "> Edit the YAML; run `just generate-docs` or `python scripts/generate_system_docs.py`.\n\n",
        _render_ports(registry),
        "\n",
        _render_services(registry),
        "\n",
        _render_schedules(registry),
        "\n",
        _render_backups(registry),
        "\n",
        _render_known_issues(registry),
    ]
    return "".join(lines)


def generate() -> str:
    registry = _load_registry()
    content = render(registry)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    return str(OUTPUT_PATH)


def check() -> bool:
    """Return True if the generated file is already up to date."""
    if not OUTPUT_PATH.exists():
        return False
    # Simple staleness check: regenerate and compare.
    new = render(_load_registry())
    existing = OUTPUT_PATH.read_text(encoding="utf-8")
    return new == existing


def main() -> None:
    ap = argparse.ArgumentParser(description="Render system_registry.yaml to docs/generated/*.md")
    ap.add_argument("--check", action="store_true", help="CI mode: exit 1 if stale, 0 if current")
    args = ap.parse_args()
    if args.check:
        if check():
            print(f"OK {OUTPUT_PATH}")
            sys.exit(0)
        print(f"STALE {OUTPUT_PATH} — run scripts/generate_system_docs.py", file=sys.stderr)
        sys.exit(1)
    path = generate()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
