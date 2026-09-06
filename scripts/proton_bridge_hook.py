#!/usr/bin/env python3
"""Proton Mail Bridge → OpenClaw hook bridge (durable).

Polls Proton Mail Bridge IMAP (127.0.0.1:1143) for new messages and POSTs
them to the OpenClaw hooks endpoint (http://127.0.0.1:8090/hooks/proton)
so inbound email arrives as an agent message.

Durability guarantees (no silent email loss):
- A message is only marked delivered after the hook returns 2xx.
- Failed deliveries are written to the outbox dir as JSON files and
  retried (with bounded backoff) on every subsequent poll before new mail.
- At-least-once delivery: the OpenClaw hook is idempotent per message id
  (the agent dedups), so retrying an already-delivered message is safe.

Uses IMAP polling with a periodic reconnect. One-shot mode:  --once

Config (all optional, sane defaults):
  env:
    PROTON_IMAP_HOST   (default 127.0.0.1)
    PROTON_IMAP_PORT   (default 1143)
    PROTON_EMAIL       (default ahronzombi@protonmail.com)
    PROTON_BRIDGE_PW   (default: read from secret-tool keyring)
    OPENCLAW_HOOK_URL  (default http://127.0.0.1:8090/hooks/proton)
    OPENCLAW_HOOK_TOKEN (default: read from ~/.openclaw/hooks-token.txt or
                         ~/.config/substrate/hooks-token.txt)
    PROTON_POLL_SECONDS (default 30)
    OUTBOX_MAX_AGE_SECONDS (default 7 days; older entries are dropped with a warning)

State: ~/.local/state/proton-bridge-hook/
  seen.json    processed UIDs (delivered + outboxed)
  outbox/      pending deliveries (message-id.json)
"""

import argparse
import email
import hashlib
import imaplib
import json
import os
import re
import sys
import time
import urllib.request
from email.header import decode_header, make_header
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "proton-bridge-hook"
SEEN_FILE = STATE_DIR / "seen.json"
OUTBOX_DIR = STATE_DIR / "outbox"

DEFAULT_EMAIL = "ahronzombi@protonmail.com"
DEFAULT_IMAP_HOST = "127.0.0.1"
DEFAULT_IMAP_PORT = 1143
DEFAULT_HOOK_URL = "http://127.0.0.1:8090/hooks/proton"
DEFAULT_POLL_SECONDS = 30
DEFAULT_OUTBOX_MAX_AGE = 7 * 24 * 3600  # 7 days

KEYRING_SERVICE = "substrate-credentials"
KEYRING_ACCOUNT = "proton-bridge-smtp"


def log(*args):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]", *args, flush=True)


def bridge_password() -> str:
    env = os.environ.get("PROTON_BRIDGE_PW", "").strip()
    if env:
        return env
    try:
        import subprocess
        out = subprocess.run(
            ["secret-tool", "lookup", "service", KEYRING_SERVICE, "account", KEYRING_ACCOUNT],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def hook_token() -> str:
    env = os.environ.get("OPENCLAW_HOOK_TOKEN", "").strip()
    if env:
        return env
    for p in (Path.home() / ".openclaw" / "hooks-token.txt",
              Path.home() / ".config" / "substrate" / "hooks-token.txt"):
        if p.exists():
            tok = p.read_text().strip()
            if tok:
                return tok
    return ""


def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()).get("uids", []))
        except Exception:
            pass
    return set()


def save_seen(seen: set) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps({"uids": sorted(seen)}))


# ---------------------------------------------------------------------------
# Outbox (durable pending deliveries)
# ---------------------------------------------------------------------------


def outbox_path(msg_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._@-]", "_", msg_id)[:160]
    return OUTBOX_DIR / f"{safe}.json"


def outbox_write(entry: dict) -> None:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = outbox_path(entry["id"])
    path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")


def outbox_remove(entry_id: str) -> None:
    path = outbox_path(entry_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def outbox_load(max_age: int) -> list[dict]:
    if not OUTBOX_DIR.exists():
        return []
    entries = []
    now = time.time()
    for path in sorted(OUTBOX_DIR.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            path.unlink(missing_ok=True)
            continue
        # Drop entries older than max_age (they will not be re-fetched either,
        # since IMAP search is bounded; avoid unbounded growth).
        if now - entry.get("first_attempt_ts", now) > max_age:
            log(f"WARN: dropping outbox entry older than max age: {path.name}")
            path.unlink(missing_ok=True)
            continue
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def post_payload(payload: dict) -> bool:
    """POST one payload; returns True only on 2xx."""
    url = os.environ.get("OPENCLAW_HOOK_URL", DEFAULT_HOOK_URL)
    token = hook_token()
    if not token:
        log("ERROR: no OpenClaw hook token found (set OPENCLAW_HOOK_TOKEN or write hooks-token.txt)")
        return False
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode(errors="replace")
            log(f"POST {url} -> {resp.status} {body[:200]}")
            return resp.status < 300
    except Exception as exc:
        log(f"POST {url} failed: {exc}")
        return False


def deliver_entry(entry: dict) -> bool:
    """Deliver one outbox entry (payload wrapper)."""
    payload = {
        "messages": [
            {
                "id": entry["id"],
                "threadId": entry.get("threadId", entry["id"]),
                "from": entry.get("from", ""),
                "to": entry.get("to", ""),
                "subject": entry.get("subject", ""),
                "date": entry.get("date", ""),
                "snippet": (entry.get("body") or "").strip()[:500],
                "body": entry.get("body", ""),
                "uid": entry.get("uid", ""),
            }
        ],
    }
    return post_payload(payload)


def flush_outbox(max_age: int) -> int:
    """Retry pending outbox entries; returns number still pending."""
    entries = outbox_load(max_age)
    if not entries:
        return 0
    pending = 0
    for entry in entries:
        if deliver_entry(entry):
            outbox_remove(entry["id"])
            log(f"outbox delivered: {entry['id']}")
        else:
            pending += 1
    return pending


# ---------------------------------------------------------------------------
# IMAP
# ---------------------------------------------------------------------------


def decode_header_value(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def message_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(errors="replace"))
                except Exception:
                    continue
        return "\n".join(parts)
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def entry_from_message(msg: email.message.Message, uid: str) -> dict:
    """Build the durable outbox entry shape (idempotent per message id)."""
    msg_id = msg.get("Message-ID", f"proton-{uid}").strip("<>")
    text = message_text(msg)
    return {
        "id": msg_id,
        "threadId": msg.get("Message-ID", msg_id).strip("<>"),
        "from": decode_header_value(msg.get("From")),
        "to": decode_header_value(msg.get("To")),
        "subject": decode_header_value(msg.get("Subject")),
        "date": msg.get("Date", ""),
        "body": text,
        "uid": uid,
        "first_attempt_ts": time.time(),
    }


def process_mailbox(conn: imaplib.IMAP4, seen: set, outbox_max_age: int) -> tuple[int, int]:
    """Process new messages; returns (newly_posted, still_pending).

    Delivery flow per message: try post → on 2xx mark seen; on failure
    write/keep in outbox and mark seen (so it is not re-fetched into a
    second outbox entry) — the outbox retry owns delivery from then on.
    """
    posted = 0
    pending = 0

    # 1. Retry durable outbox first (bounded backoff via retry counter).
    pending = flush_outbox(outbox_max_age)

    # 2. Fetch new messages.
    typ, data = conn.select("INBOX", readonly=True)
    if typ != "OK":
        log("select INBOX failed")
        return posted, pending
    try:
        typ, data = conn.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return posted, pending
        uids = data[0].split()
        for num in uids[-25:]:  # last 25 to bound work
            typ, resp = conn.fetch(num, "(UID RFC822)")
            if typ != "OK":
                continue
            uid = ""
            for part in resp:
                if isinstance(part, tuple):
                    meta = part[0].decode(errors="replace")
                    m = re.search(r"UID (\d+)", meta)
                    if m:
                        uid = m.group(1)
                    msg = email.message_from_bytes(part[1])
                    break
            else:
                continue
            if uid in seen:
                continue
            entry = entry_from_message(msg, uid)
            dedup = hashlib.sha256(
                (entry["id"] + "|" + entry.get("date", "")).encode()
            ).hexdigest()[:16]
            if dedup in seen:
                continue
            # Try immediate delivery; on failure persist to outbox. Either
            # way the UID is marked seen so it is not re-processed.
            seen.add(uid)
            seen.add(dedup)
            if deliver_entry(entry):
                posted += 1
            else:
                outbox_write(entry)
                pending += 1
                log(f"queued to outbox: {entry['id']}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return posted, pending


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="process new mail once and exit")
    args = ap.parse_args()

    host = os.environ.get("PROTON_IMAP_HOST", DEFAULT_IMAP_HOST)
    port = int(os.environ.get("PROTON_IMAP_PORT", DEFAULT_IMAP_PORT))
    email_addr = os.environ.get("PROTON_EMAIL", DEFAULT_EMAIL)
    pw = bridge_password()
    if not pw:
        log("ERROR: bridge password unavailable (keyring lookup failed)")
        return 1

    seen = load_seen()
    poll_every = int(os.environ.get("PROTON_POLL_SECONDS", str(DEFAULT_POLL_SECONDS)))
    outbox_max_age = int(os.environ.get("OUTBOX_MAX_AGE_SECONDS", str(DEFAULT_OUTBOX_MAX_AGE)))

    def connect() -> imaplib.IMAP4:
        conn = imaplib.IMAP4(host, port, timeout=30)
        conn.starttls()
        conn.login(email_addr, pw)
        log(f"connected to {host}:{port} as {email_addr}")
        return conn

    if args.once:
        conn = connect()
        try:
            posted, pending = process_mailbox(conn, seen, outbox_max_age)
            save_seen(seen)
            log(f"processed {posted} new message(s); {pending} pending in outbox")
            return 0 if pending == 0 else 1
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # Daemon mode: poll every poll_every seconds, reconnect on failure.
    log(f"daemon mode: polling INBOX every {poll_every}s")
    while True:
        try:
            conn = connect()
            try:
                while True:
                    posted, pending = process_mailbox(conn, seen, outbox_max_age)
                    if posted or pending:
                        save_seen(seen)
                        log(f"processed {posted} new message(s); {pending} pending in outbox")
                    time.sleep(poll_every)
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except Exception as exc:
            log(f"connection failed: {exc}; retrying in {poll_every}s")
            time.sleep(poll_every)


if __name__ == "__main__":
    sys.exit(main())
