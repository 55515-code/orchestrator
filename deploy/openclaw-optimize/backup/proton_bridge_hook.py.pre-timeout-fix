#!/usr/bin/env python3
"""Proton Mail Bridge → OpenClaw hook bridge.

Polls Proton Mail Bridge IMAP (127.0.0.1:1143) for new messages and POSTs
them to the OpenClaw hooks endpoint (http://127.0.0.1:18789/hooks/proton)
so inbound email arrives as an agent message.

Uses IMAP IDLE when available (bridge supports it) with a periodic
reconnect/poll fallback. One-shot mode:  --once

Config (all optional, sane defaults):
  env:
    PROTON_IMAP_HOST   (default 127.0.0.1)
    PROTON_IMAP_PORT   (default 1143)
    PROTON_EMAIL       (default ahronzombi@protonmail.com)
    PROTON_BRIDGE_PW   (default: read from secret-tool keyring)
    OPENCLAW_HOOK_URL  (default http://127.0.0.1:18789/hooks/proton)
    OPENCLAW_HOOK_TOKEN (default: read from ~/.openclaw/hooks-token.txt or
                         ~/.config/substrate/hooks-token.txt)
    PROTON_POLL_SECONDS (default 60; used when IDLE is unavailable)

State: ~/.local/state/proton-bridge-hook/seen.json  (processed UIDs)
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

DEFAULT_EMAIL = "ahronzombi@protonmail.com"
DEFAULT_IMAP_HOST = "127.0.0.1"
DEFAULT_IMAP_PORT = 1143
DEFAULT_HOOK_URL = "http://127.0.0.1:8090/hooks/proton"

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


def email_payload(msg: email.message.Message, msg_id: str, uid: str) -> dict:
    """Normalize a message into the OpenClaw hook payload shape."""
    subject = decode_header_value(msg.get("Subject"))
    from_ = decode_header_value(msg.get("From"))
    to = decode_header_value(msg.get("To"))
    date = msg.get("Date", "")
    text = message_text(msg)

    # Match the Gmail preset shape: messages[] with from/subject/snippet/id
    return {
        "messages": [
            {
                "id": msg_id,
                "threadId": msg.get("Message-ID", msg_id).strip("<>"),
                "from": from_,
                "to": to,
                "subject": subject,
                "date": date,
                "snippet": text.strip()[:500],
                "body": text,
                "uid": uid,
            }
        ],
    }


def post_to_openclaw(payload: dict) -> bool:
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode(errors="replace")
            log(f"POST {url} -> {resp.status} {body[:200]}")
            return resp.status < 300
    except Exception as exc:
        log(f"POST {url} failed: {exc}")
        return False


def process_mailbox(conn: imaplib.IMAP4, seen: set) -> int:
    """Process unseen/new messages; returns number of messages posted."""
    typ, data = conn.select("INBOX", readonly=True)
    if typ != "OK":
        log("select INBOX failed")
        return 0
    posted = 0
    try:
        typ, data = conn.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return 0
        uids = data[0].split()
        for num in uids[-25:]:  # last 25 to bound work
            # Use UID for dedup
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
            msg_id = msg.get("Message-ID", f"proton-{uid}").strip("<>")
            dedup = hashlib.sha256(
                (msg_id + "|" + msg.get("Date", "")).encode()
            ).hexdigest()[:16]
            if dedup in seen:
                continue
            payload = email_payload(msg, msg_id, uid)
            if post_to_openclaw(payload):
                seen.add(uid)
                seen.add(dedup)
                posted += 1
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return posted



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
    poll_every = int(os.environ.get("PROTON_POLL_SECONDS", "30"))

    def connect() -> imaplib.IMAP4:
        conn = imaplib.IMAP4(host, port, timeout=30)
        conn.starttls()
        conn.login(email_addr, pw)
        log(f"connected to {host}:{port} as {email_addr}")
        return conn

    if args.once:
        conn = connect()
        try:
            n = process_mailbox(conn, seen)
            save_seen(seen)
            log(f"processed {n} new message(s)")
            return 0
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # Daemon mode: poll every poll_every seconds, reconnect on failure
    log(f"daemon mode: polling INBOX every {poll_every}s")
    while True:
        try:
            conn = connect()
            try:
                while True:
                    n = process_mailbox(conn, seen)
                    if n:
                        save_seen(seen)
                        log(f"processed {n} new message(s)")
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
