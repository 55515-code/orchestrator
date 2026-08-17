#!/usr/bin/env python3
"""Daily security report for the Substrate host.

Checks:
  1. Local system  — listeners, firewall, sshd, pending updates, service state,
                     tailscale exposure, disk/load, user-journal errors
  2. Code          — per-repo secret scan (working tree + new commits since last
                     run, using a value-aware pattern set), git hygiene
  3. Public sites  — HTTP status, TLS expiry, security headers (HSTS)
  4. Public repos  — GitHub API visibility + latest commit per repo

Writes a plain-text report to STATE_DIR/YYYY-MM-DD.txt and emails it via the
ProtonMail Bridge SMTP relay (127.0.0.1:1025, STARTTLS, unauthenticated local).

Stdlib only. Run manually or via systemd user timer.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import socket
import ssl
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

CODESPACE = Path(os.environ.get("SUBSTRATE_ROOT", "/home/ahron/codespace"))
STATE_DIR = Path(os.environ.get("SECURITY_REPORT_DIR", str(CODESPACE / "memory" / "security-reports")))
STATE_FILE = STATE_DIR / "state.json"

EMAIL_TO = os.environ.get("SECURITY_REPORT_TO", "ahronzombi@protonmail.com")
EMAIL_FROM_CANDIDATES = [
    os.environ.get("SECURITY_REPORT_FROM", ""),
    "ahronzombi@protonmail.com",
    "ahronzombi@proton.me",
]
SMTP_HOST = os.environ.get("SECURITY_REPORT_SMTP_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("SECURITY_REPORT_SMTP_PORT", "1025"))

# Email is opt-in via ~/.config/substrate/security_report.json:
#   {"email": {"enabled": true, "to": "...", "from": "...",
#              "smtp_host": "127.0.0.1", "smtp_port": 1025}}
CONFIG_PATH = Path(os.environ.get("SECURITY_REPORT_CONFIG", str(Path.home() / ".config/substrate/security_report.json")))

REPOS = [
    ("orchestrator", CODESPACE),
    ("ahrondarnell-site", CODESPACE / "ahrondarnell-site"),
    ("dotfiles", Path.home() / ".local/share/chezmoi"),
]

PUBLIC_REPOS = [
    "55515-code/orchestrator",
    "55515-code/ahrondarnell-site",
    "55515-code/dotfiles",
]

SITES = [
    "https://1pointo.com",
    "https://1pointo.com/blog/",
    "https://1pointo.com/rss.xml",
    "https://1pointo.com/sitemap-index.xml",
]

SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"cf[Tu]_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY-----"),
    re.compile(r"postgres(ql)?://[^\s@:]+:[^\s@]+@"),
    re.compile(r"redis://[^\s@:]+:[^\s@]+@"),
    re.compile(r"mongodb(\+srv)?://[^\s@:]+:[^\s@]+@"),
    re.compile(r"\b(token|password|api[_-]?key|secret)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?", re.IGNORECASE),
]

PLACEHOLDER_RE = re.compile(
    r"(your|example|sample|placeholder|xxx+|<[^>]*>|changeme|demo|test)[_-]?|\.{2,}|\*{2,}",
    re.IGNORECASE,
)

TIMEOUT = 8


def run(cmd: list[str], timeout: int = TIMEOUT) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return out.strip()
    except subprocess.TimeoutExpired:
        return f"(timeout after {timeout}s)"
    except FileNotFoundError:
        return "(not found)"


def run_sudo(cmd: list[str], timeout: int = TIMEOUT) -> str:
    return run(["sudo", "-n"] + cmd, timeout=timeout)


def mask(value: str, keep: int = 4) -> str:
    return value[:keep] + "***" if len(value) > keep else "***"


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text))


def scan_lines(lines: list[str]) -> list[str]:
    hits: list[str] = []
    for line in lines:
        low = line.strip()
        if not low or low.startswith(("+", "-")):
            body = low[1:].strip()
        else:
            body = low
        if is_placeholder(body):
            continue
        for pat in SECRET_PATTERNS:
            m = pat.search(line)
            if m:
                secret = m.group(0)
                key = secret.split("=")[0].split(":")[0]
                hits.append(f"  {mask(secret, 8)} ({key})")
                break
    return hits


# ---------------- system ----------------


def system_section() -> list[str]:
    lines: list[str] = []
    lines.append("## Local system")
    listeners = run(["ss", "-tulpn"]).splitlines()[1:]
    SAFE_UDP_PORTS = {"5353", "5355", "41641", "5353:*", "5355:*", "41641:*"}
    exposed = []
    for line in listeners:
        cols = line.split()
        if len(cols) < 5:
            continue
        local = cols[3]
        if local.startswith(("0.0.0.0:", "[::]:", "192.168.")):
            port = local.split(":")[-1]
            if cols[0] == "udp" and port in SAFE_UDP_PORTS:
                continue
            exposed.append(line.strip())
    lines.append(f"- Exposed listeners (non-loopback): {len(exposed)}")
    for listener in exposed[:8]:
        lines.append(f"  `{listener}`")
    if not exposed:
        lines.append("  none - all services loopback/tailnet only")

    lines.append(f"- Host firewall (ufw active): {run(['systemctl', 'is-active', 'ufw'])}")
    lines.append(f"- sshd: enabled={run(['systemctl', 'is-enabled', 'sshd'])} active={run(['systemctl', 'is-active', 'sshd'])}")

    updates = run(["checkupdates"]).splitlines()
    if updates and not updates[0].startswith("(") and "::" not in updates[0]:
        lines.append(f"- Pending OS updates: {len(updates)}")
        lines.append(f"  {', '.join(sorted({u.split()[0] for u in updates if u.split()})[:12])}")
    else:
        lines.append("- Pending OS updates: 0 (or checkupdates unavailable)")

    svcs = {}
    for s in ("openclaw-gateway.service", "ttyd.service", "kilo-remote.service",
              "protonmail-bridge.service", "ollama.service", "tailscaled.service"):
        user = run(["systemctl", "--user", "is-active", s])
        svcs[s] = user if user in ("active", "failed") else run(["systemctl", "is-active", s])
    bad = {k: v for k, v in svcs.items() if v != "active"}
    lines.append(f"- Services: {len(svcs) - len(bad)}/{len(svcs)} active")
    for k, v in bad.items():
        lines.append(f"  ! {k}: {v}")

    ts = run(["tailscale", "status", "--json"], timeout=6)
    try:
        td = json.loads(ts)
        self_ = td.get("SelfNode") or td.get("Self") or {}
        peers = td.get("Peers") or []
        lines.append(f"- Tailscale: online={self_.get('Online')} peers={len(peers)} host={self_.get('HostName', '?')}")
    except Exception:
        lines.append(f"- Tailscale: status unavailable ({mask(ts[:80])})")

    serve = run(["tailscale", "serve", "status"], timeout=6)
    lines.append(f"- Tailscale serve entries: {len([entry for entry in serve.splitlines() if 'https://' in entry])}")

    disk = run(["df", "-h", "/home"]).splitlines()
    if len(disk) > 1:
        parts = disk[1].split()
        if len(parts) >= 5:
            lines.append(f"- Disk /home: {parts[4]} used ({parts[2]} of {parts[1]})")
    load = run(["cat", "/proc/loadavg"]).split()
    if load:
        lines.append(f"- Load avg: {', '.join(load[:3])}")

    jerr = run(["journalctl", "--user", "-p", "err", "--since", "24 hours ago", "--no-pager"]).splitlines()
    jerr = [e for e in jerr if not re.search(r"cosmic-comp|cosmic-launcher|CosmicTheme|com\.system76|shortcuts custom config|EGL|eglInitialize|Failed to create watcher", e)]
    if jerr:
        lines.append(f"- User-journal errors (24h, cosmic/EGL noise filtered): {len(jerr)}")
        for e in jerr[:3]:
            lines.append(f"  {e[:160]}")
    else:
        lines.append("- User-journal errors (24h): 0")
    return lines


# ---------------- code ----------------


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def code_section(state: dict) -> list[str]:
    lines: list[str] = []
    lines.append("## Code")
    for name, path in REPOS:
        if not (path / ".git").exists():
            lines.append(f"- {name}: not a repo")
            continue
        head = run(["git", "-C", str(path), "rev-parse", "HEAD"])
        branch = run(["git", "-C", str(path), "branch", "--show-current"])
        dirty = run(["git", "-C", str(path), "status", "--porcelain"]).splitlines()
        unpushed = run(["git", "-C", str(path), "log", "@{u}..HEAD", "--oneline"]).splitlines()
        status = ["ok"] if not dirty else [f"{len(dirty)} uncommitted files"]
        if unpushed:
            status.append(f"{len(unpushed)} unpushed commits")
        lines.append(f"- {name} [{branch}]: {', '.join(status)}")
        if not dirty:
            # value-aware secret scan on working tree
            scan = run(["bash", str(CODESPACE / "scripts" / "scan_secrets.sh")], timeout=30)
            if scan.strip():
                lines.append(f"  ! secret scan findings: {len(scan.splitlines())}")
                for s in scan.splitlines()[:6]:
                    lines.append(f"    {s[:160]}")
            else:
                lines.append("  secret scan: clean")
        # new-commit delta scan
        last = state.get(name, {}).get("last_checked")
        if last and last != head:
            added = run(["git", "-C", str(path), "log", "-p", f"{last}..{head}", "--",
                         ".", ":!*.pyc", ":!dist", ":!node_modules"], timeout=60)
            hits = scan_lines(added.splitlines())
            if hits:
                lines.append(f"  ! secrets in {len(hits)} new commits:")
                lines.extend(hits[:8])
            else:
                lines.append(f"  new commits ({last[:8]}..{head[:8]}): no secrets")
        else:
            lines.append(f"  history baseline: {head[:8]} (clean baseline set)")
        state.setdefault(name, {})["last_checked"] = head
    return lines


# ---------------- sites ----------------


def tls_expiry(host: str, port: int = 443) -> str:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days = (not_after.replace(tzinfo=UTC) - datetime.now(UTC)).days
        return f"{days}d"
    except Exception as e:
        return f"err:{type(e).__name__}"


def site_section() -> list[str]:
    lines: list[str] = []
    lines.append("## Public sites")
    for url in SITES:
        host = url.split("/")[2]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "security-report/1.0"})
            start = datetime.now()
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                code = r.status
                elapsed = (datetime.now() - start).total_seconds()
                hsts = bool(r.headers.get("Strict-Transport-Security"))
            lines.append(f"- {url}: HTTP {code} in {elapsed:.2f}s | TLS {tls_expiry(host)} | HSTS {'yes' if hsts else 'no'}")
        except urllib.error.HTTPError as e:
            lines.append(f"- {url}: HTTP {e.code}")
        except Exception as e:
            lines.append(f"- {url}: UNREACHABLE ({type(e).__name__})")
    return lines


# ---------------- public repos ----------------


def github_repo_section() -> list[str]:
    lines: list[str] = []
    lines.append("## Public repos (GitHub API)")
    for repo in PUBLIC_REPOS:
        try:
            with urllib.request.urlopen(
                f"https://api.github.com/repos/{repo}", timeout=TIMEOUT
            ) as r:
                d = json.loads(r.read())
            vis = d.get("visibility", "?")
            lines.append(f"- {repo}: {vis} | default={d.get('default_branch')} | pushed_at={d.get('pushed_at', '?')[:10]}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                lines.append(f"- {repo}: 404 anonymously - private or not publicly visible")
            else:
                lines.append(f"- {repo}: API HTTP {e.code}")
        except Exception as e:
            lines.append(f"- {repo}: API error ({type(e).__name__})")
    lines.append("  (Dependabot alerts require an authenticated token - not checked)")
    return lines


# ---------------- compose + send ----------------


def compose(state: dict) -> str:
    sections = [system_section(), code_section(state), site_section(), github_repo_section()]
    now = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    header = [
        f"Substrate Daily Security Report - {now}",
        f"Host: {socket.gethostname()}",
        "=" * 60,
    ]
    body = "\n\n".join("\n".join(s) for s in sections)
    footer = ["=" * 60, "Automated report - generated by scripts/daily_security_report.py"]
    return "\n".join(header + [body] + footer)


def send_email(report: str) -> str:
    cfg: dict = {}
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    email_cfg = cfg.get("email", {})
    if not email_cfg.get("enabled", False):
        return ("email disabled in ~/.config/substrate/security_report.json "
                "(enable with {\"email\": {\"enabled\": true}}); report written locally")

    to = email_cfg.get("to") or EMAIL_TO
    smtp_host = email_cfg.get("smtp_host", SMTP_HOST)
    smtp_port = int(email_cfg.get("smtp_port", SMTP_PORT))
    from_candidates = [
        email_cfg.get("from", ""),
        *[f for f in EMAIL_FROM_CANDIDATES if f and f != email_cfg.get("from", "")],
    ]
    msg = (
        "From: Substrate Security <{frm}>\n"
        "To: {to}\n"
        "Subject: Substrate Daily Security Report\n"
        "Date: {date}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "{body}"
    )
    for frm in [f for f in from_candidates if f]:
        try:
            s = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.sendmail(
                frm,
                [to],
                msg.format(frm=frm, to=to, date=datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z"), body=report),
            )
            s.quit()
            return f"email sent from {frm} via bridge"
        except smtplib.SMTPDataError as e:
            last = f"from={frm} bridge rejected: {e.smtp_error.decode()[:80]}"
        except Exception as e:
            last = f"from={frm} failed: {type(e).__name__}: {str(e)[:80]}"
    return "email FAILED: " + last


def main() -> int:
    state = load_state()
    report = compose(state)
    save_state(state)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    date_file = STATE_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.txt"
    date_file.write_text(report)
    print(report)
    result = send_email(report)
    print("\n== " + result)
    if "FAILED" in result:
        # Email is broken (Proton Bridge has no account) — fall back to
        # WhatsApp so the daily report still reaches the operator.
        wa = send_whatsapp(report)
        print("== " + wa)
    return 0


def send_whatsapp(report: str) -> str:
    """Deliver the report via OpenClaw's built-in WhatsApp channel.

    Used as a fallback when the Proton Bridge SMTP relay cannot send
    (e.g. bridge has no account loaded). Targets the operator's number
    from ~/.config/substrate/security_report.json (whatsapp.target).
    """
    cfg = {}
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    wa = cfg.get("whatsapp", {})
    if not wa.get("enabled", False):
        return "whatsapp disabled in ~/.config/substrate/security_report.json"
    target = wa.get("target", "")
    if not target:
        return "whatsapp target missing in security_report.json"
    try:
        subprocess.run(
            ["openclaw", "message", "send", "--channel", "whatsapp",
             "--target", target, "--media", str(STATE_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.txt"),
             "-m", "📋 Substrate Daily Security Report — " + datetime.now().strftime("%Y-%m-%d"),
             "--json"],
            capture_output=True, text=True, timeout=120,
        )
        return f"whatsapp sent to {target}"
    except Exception as e:
        return f"whatsapp FAILED: {type(e).__name__}: {str(e)[:120]}"


if __name__ == "__main__":
    sys.exit(main())
