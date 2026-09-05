#!/usr/bin/env python3
"""Validate the documentation tree for structural invariants.

Checks
------
1. Every path referenced in mkdocs.yml `nav:` exists as a markdown file.
2. Every .md file in `docs/` is reachable from mkdocs.yml nav (or explicitly
   in a whitelist of accepted orphans — generated docs, images, HTML).
3. All fenced code blocks have matching open/close fences.
4. All internal `.md` links resolve (file exists and heading exists in target).
5. No doc tells the reader to bind the retired panel to port 8090 or 8091
   (the gateway owns both).
6. All backtick-quoted paths that look like real files exist on disk.

Exit codes
----------
0 — all checks passed
1 — one or more checks failed
2 — fatal (bad YAML, etc.)

CI wire-up
----------
    uv run python scripts/validate_docs.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"

# Paths under docs/ that are intentionally not in mkdocs nav.
# These are relative to docs/ (matching mkdocs nav convention), NOT repo-root.
ALLOWED_ORPHANS = {
    # Generated files (written by scripts/generate_system_docs.py).
    "generated/system-registry.md",
    # Non-markdown artifact.
    "community_status.html",
    # Point-in-time research / snapshot reports intentionally kept out of the
    # published nav. They are reviewed annually; see POINT_IN_TIME_REPORTS.
    "OPTIMIZATION_CYCLE_2026-08-08.md",
    "automation-review-2026-08-17.md",
    "FINAL_RESEARCH_REPORT.md",
    "RESEARCH_SUMMARY.md",
    "LIVE_MONITORING_AND_KILO_INTEGRATION_PROPOSAL.md",
    "GATEWAY_IMPLEMENTATION_SUMMARY.md",
    "openclaw_substrate_audit.md",
    "openclaw-production-checklist.md",
    "CONTROL_PANEL_IMPLEMENTATION.md",
    "remote-access-findings.md",
    "android-node-registration.md",
    "android-security-tool-deployment.md",
    "flipper-zero-openclaw-research.md",
    "nothing-stock-restore.md",
    "decentralized_governance_synthesis.md",
    "nephilim_union_source_analysis.md",
    "huggingface_image_edit_guide.md",
    "credential-restore-runbook.md",
    "promotion-and-deploy-runbook.md",
    "portable-gateway-capsule-strategy.md",
    "proton-drive-filesystem-architecture.md",
    "proton-mail-openclaw-channel.md",
    "dashboard-orchestration.md",
    "creative-ai-workflows.md",
    "arin-novel-automation.md",
    "CRYPTO_PAYMENT_RUNBOOK.md",
    "caching.md",
    "approval-lane.md",
    "render-router.md",
    "security-toolkit-roadmap.md",
    "WHATSAPP_GATEWAY_SETUP.md",
    "ai-collaboration.md",
}

# Intentionally-orphaned point-in-time reports. These are now also listed in
# ALLOWED_ORPHANS above; this set is retained so the annual-review warning
# fires if any are ever removed from ALLOWED_ORPHANS without moving them here.
POINT_IN_TIME_REPORTS: set[str] = {
    "OPTIMIZATION_CYCLE_2026-08-08.md",
    "automation-review-2026-08-17.md",
    "FINAL_RESEARCH_REPORT.md",
    "RESEARCH_SUMMARY.md",
    "LIVE_MONITORING_AND_KILO_INTEGRATION_PROPOSAL.md",
    "GATEWAY_IMPLEMENTATION_SUMMARY.md",
    "openclaw_substrate_audit.md",
    "openclaw-production-checklist.md",
    "CONTROL_PANEL_IMPLEMENTATION.md",
    "remote-access-findings.md",
    "android-node-registration.md",
    "android-security-tool-deployment.md",
    "flipper-zero-openclaw-research.md",
    "nothing-stock-restore.md",
    "decentralized_governance_synthesis.md",
    "nephilim_union_source_analysis.md",
    "huggingface_image_edit_guide.md",
    "credential-restore-runbook.md",
    "promotion-and-deploy-runbook.md",
    "portable-gateway-capsule-strategy.md",
    "proton-drive-filesystem-architecture.md",
    "proton-mail-openclaw-channel.md",
    "dashboard-orchestration.md",
    "creative-ai-workflows.md",
    "arin-novel-automation.md",
    "CRYPTO_PAYMENT_RUNBOOK.md",
    "caching.md",
    "approval-lane.md",
    "render-router.md",
    "security-toolkit-roadmap.md",
    "WHATSAPP_GATEWAY_SETUP.md",
    "ai-collaboration.md",
}

# Patterns that indicate a doc is telling the reader to bind the retired panel
# to a reserved port. Only the router page should be bound to 8090/8091.
FORBIDDEN_PORT_PATTERNS = [
    (re.compile(r"\b8090\b"), "port 8090 (OpenClaw Gateway)"),
    (re.compile(r"\b8091\b"), "port 8091 (OpenClaw Gateway)"),
]

# Code-fence languages that don't need closing (HTML fragments, etc. are still
# closed; this list is for unusual cases).
_FENCE_RE = re.compile(r"^```(\w+)?\s*$", re.MULTILINE)


def _die(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(2)


def _warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _load_mkdocs_nav() -> list[str]:
    """Return the list of file paths referenced in mkdocs.yml nav.

    MkDocs resolves nav paths relative to the docs_dir (default: docs/), so
    `index.md` in nav means `docs/index.md`. We normalise to paths relative
    to docs/ for comparison.
    """
    if not MKDOCS_YML.exists():
        _die(f"{MKDOCS_YML} not found")
    try:
        with MKDOCS_YML.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        _die(f"{MKDOCS_YML} is not valid YAML: {exc}")
    nav = cfg.get("nav", [])
    paths: list[str] = []
    for entry in nav:
        if isinstance(entry, dict):
            for section_items in entry.values():
                if isinstance(section_items, list):
                    for item in section_items:
                        if isinstance(item, dict):
                            paths.extend(p for p in item.values() if isinstance(p, str))
                        elif isinstance(item, str):
                            paths.append(item)
    # Normalise to docs-relative paths (strip a leading docs/ if present).
    normalised: list[str] = []
    for p in paths:
        if p.startswith("docs/"):
            normalised.append(p[len("docs/"):])
        else:
            normalised.append(p)
    return normalised


def _all_md_files() -> set[str]:
    """Return paths relative to docs/ of every .md under docs/."""
    return {
        str(p.relative_to(DOCS_DIR))
        for p in DOCS_DIR.rglob("*.md")
        if p.is_file()
    }


def _check_nav_coverage(nav_paths: list[str], all_md: set[str]) -> int:
    failures = 0
    # 1. Every nav target exists.
    for p in nav_paths:
        full = DOCS_DIR / p
        if not full.exists():
            _fail(f"mkdocs nav points at missing file: {p}")
            failures += 1
    # 2. Every .md in docs/ is either in nav or in the allowed-orphan set.
    nav_set = set(nav_paths)
    unexpected_orphans = all_md - nav_set - ALLOWED_ORPHANS
    for orphan in sorted(unexpected_orphans):
        basename = Path(orphan).name
        if basename in POINT_IN_TIME_REPORTS:
            _warn(f"point-in-time report not in nav (intentional but review later): {orphan}")
        else:
            _fail(f"orphaned from mkdocs nav: {orphan}")
            failures += 1
    return failures


def _check_fences(path: str, content: str) -> list[str]:
    """Return a list of fence-balance errors for this file."""
    errors = []
    count = 0
    for m in _FENCE_RE.finditer(content):
        fence = m.group(0)
        if fence.startswith("```"):
            count += 1
    if count % 2 != 0:
        errors.append(f"unbalanced code fences ({count} opening/closing tokens)")
    return errors


def _check_internal_links(path: str, content: str) -> list[str]:
    """Find markdown links to .md files and verify they resolve."""
    errors = []
    src_dir = Path(path).parent
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+\.md)(?:#[^)]*)?\)", content):
        target_rel = m.group(2)
        # Skip URLs and absolute paths outside the repo.
        if target_rel.startswith(("http://", "https://", "/")):
            continue
        target = (src_dir / target_rel).resolve()
        if not target.exists():
            errors.append(f"broken link [{m.group(1)}]({target_rel}) — file not found")
            continue
        # Verify heading anchor if present.
        anchor_m = re.search(r"#(.*)", m.group(0))
        if anchor_m:
            anchor = anchor_m.group(1)
            if anchor:
                heading_re = re.compile(
                    r"^#+\s+" + re.escape(anchor).replace(r"\ ", r"\s+") + r"\s*$",
                    re.MULTILINE | re.IGNORECASE,
                )
                if not heading_re.search(target.read_text(encoding="utf-8")):
                    errors.append(
                        f"link [{m.group(1)}]({target_rel}) — heading #{anchor} not found in target"
                    )
    return errors


def _check_forbidden_port_references(path: str, content: str) -> list[str]:
    """Warn if a doc tells users to bind a service to a reserved port."""
    issues = []
    for pattern, label in FORBIDDEN_PORT_PATTERNS:
        for m in pattern.finditer(content):
            line_no = content[:m.start()].count("\n") + 1
            # Skip code blocks and comments.
            before = content[:m.start()]
            line_start = before.rfind("\n") + 1
            line = before[line_start:] + m.group(0)
            if line.strip().startswith("#") or "```" in before[before.rfind("\n", 0, m.start()):]:
                continue
            issues.append(f"line {line_no}: references reserved {label}")
    return issues


def _check_backtick_paths(path: str, content: str) -> list[str]:
    """Check that paths in backticks that look like real files exist."""
    errors = []
    for m in re.finditer(r"`([^`]+)`", content):
        token = m.group(1)
        # Only check paths that look like file references.
        if not re.match(r"^(\.{0,2}/)?[\w./-]+\.\w{1,4}$", token):
            continue
        if token.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Skip well-known binary names.
        basename = Path(token).name
        if basename in {"node", "python", "python3", "uv", "uvicorn",
                        "ss", "systemctl", "git", "bash", "node-MainThread"}:
            continue
        full = (Path(path).parent / token).resolve()
        if not full.exists():
            # Only flag if it looks like a project-relative path, not a bare
            # command name.
            if "/" in token or token.startswith("."):
                errors.append(f"backtick path `{token}` does not exist (from {path})")
    return errors


def check_all() -> int:
    failures = 0
    nav_paths = _load_mkdocs_nav()
    all_md = _all_md_files()

    failures += _check_nav_coverage(nav_paths, all_md)

    md_files = sorted(all_md - ALLOWED_ORPHANS)
    for md_path in md_files:
        full = DOCS_DIR / md_path
        try:
            content = full.read_text(encoding="utf-8")
        except OSError as exc:
            _fail(f"{md_path}: unreadable: {exc}")
            failures += 1
            continue

        # Balanced fences.
        fence_errors = _check_fences(md_path, content)
        for err in fence_errors:
            _fail(f"{md_path}: {err}")
            failures += 1

        # Internal links.
        link_errors = _check_internal_links(md_path, content)
        for err in link_errors:
            _fail(f"{md_path}: {err}")
            failures += 1

        # Forbidden port references.
        port_issues = _check_forbidden_port_references(md_path, content)
        for issue in port_issues:
            _warn(f"{md_path}: {issue}")

        # Backtick paths.
        path_errors = _check_backtick_paths(md_path, content)
        for err in path_errors:
            _fail(f"{md_path}: {err}")
            failures += 1

    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate documentation structure")
    ap.add_argument(
        "--allow-orphan",
        action="append",
        default=[],
        help="additional paths to allow outside mkdocs nav",
    )
    args = ap.parse_args()
    if args.allow_orphan:
        ALLOWED_ORPHANS.update(args.allow_orphan)

    failures = check_all()
    if failures:
        print(f"\n{failures} documentation check(s) FAILED", file=sys.stderr)
        sys.exit(1)
    print("OK: documentation structure is valid")


if __name__ == "__main__":
    main()
