"""Email-manager agent — daily email digest via Proton Mail Bridge + WhatsApp.

Tier 1 autonomy: reads mailbox via IMAP, classifies messages, writes a digest
note to ``.research/email-digest/``. Sending the WhatsApp digest is a Tier 2
action that requires the WhatsApp plugin to be configured; when it is, the
agent sends the digest automatically (Tier 1 with green validation).

Classification strategy:
  - Spam folder messages are skipped (Proton's filter already caught them).
  - Messages from List-Id headers (GitHub, mailing lists) are classified as
    "notifications".
  - Senders in a configurable allowlist are "important".
  - Known newsletter/marketing patterns are "promotions".
  - Everything else is "inbox" (normal personal email).
  - A simple keyword score adjusts classification for financial/security emails.

The agent runs daily and produces a compact digest of the last 24h of email.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

IMAP_HOST = "127.0.0.1"
IMAP_PORT = 1143
SMTP_HOST = "127.0.0.1"
SMTP_PORT = 1025

KEYRING_SERVICE = "substrate-credentials"
KEYRING_ACCOUNT = "proton-bridge-smtp"

EMAIL_FROM_CANDIDATES = [
    "ahronzombi@protonmail.com",
    "ahronzombi@proton.me",
]

# Folders to scan (Proton Bridge exposes these).
SCAN_FOLDERS = ["INBOX", "Spam"]

# Senders that are always "important" (personal, financial, security).
IMPORTANT_SENDERS = {
    "ahronzombi@protonmail.com",
    "ahronzombi@proton.me",
    # Financial
    "notifications@sezzle.com",
    "invoice+statements+acct_1R1ePOJ7A6SsvrfS@stripe.com",
    "hi@app.kilocode.ai",
    # Add more as needed
}

# Patterns that indicate newsletter/marketing/promotional email.
PROMO_PATTERNS = [
    r"unsubscribe",
    r"manage.*preferences",
    r"this.*email.*was.*sent.*because",
    r"you.*subscribed",
    r"view.*in.*browser",
    r"bulk.*buy",
    r"sale",
    r"discount",
    r"deal",
    r"limited.*time",
    r"order.*now",
    r"special.*offer",
]
PROMO_RE = re.compile("|".join(PROMO_PATTERNS), re.IGNORECASE)

# Patterns that elevate priority.
PRIORITY_KEYWORDS = [
    "security",
    "alert",
    "urgent",
    "action required",
    "verify",
    "password",
    "breach",
    "invoice",
    "receipt",
    "payment",
    "failed",
    "ci",
    "run failed",
]
PRIORITY_RE = re.compile("|".join(PRIORITY_KEYWORDS), re.IGNORECASE)

# List-Id senders that are "notifications" not "promotions".
NOTIFICATION_LIST_IDS = {
    "github.com",
}

# Maximum number of messages to fetch headers for per folder.
MAX_FETCH = 500


# ---------------------------------------------------------------------------
# Bridge credentials
# ---------------------------------------------------------------------------


def _bridge_password() -> str:
    """Read the Proton Mail Bridge password from the OS keyring."""
    env = os.environ.get("PROTON_BRIDGE_PW", "").strip()
    if env:
        return env
    # fallback: credentials file written by scripts/bridge_setup.py
    for p in (Path.home() / ".config/substrate/credentials.json",
              Path.home() / ".config/substrate/bridge-credentials.txt"):
        try:
            if p.suffix == ".json":
                data = json.loads(p.read_text())
                pw = data.get("proton_bridge_pw") or data.get("bridge_password") or ""
            else:
                pw = p.read_text().strip().splitlines()[0]
            if pw:
                return pw
        except Exception:
            pass
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "service", KEYRING_SERVICE,
             "account", KEYRING_ACCOUNT],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _decode_header(raw: str) -> str:
    """Decode an RFC 2047-encoded email header."""
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


# ---------------------------------------------------------------------------
# IMAP reader
# ---------------------------------------------------------------------------


class EmailSummary:
    """Lightweight representation of a single email for digest purposes."""

    __slots__ = (
        "category",
        "date",
        "folder",
        "from_addr",
        "from_name",
        "list_id",
        "priority",
        "snippet",
        "subject",
        "uid",
    )

    def __init__(
        self,
        uid: str,
        folder: str,
        from_addr: str,
        from_name: str,
        subject: str,
        date: datetime | None,
        list_id: str,
        snippet: str,
    ) -> None:
        self.uid = uid
        self.folder = folder
        self.from_addr = from_addr
        self.from_name = from_name
        self.subject = subject
        self.date = date
        self.list_id = list_id
        self.snippet = snippet
        self.category = "inbox"
        self.priority = 0

    def classify(self) -> None:
        """Assign category and priority score based on headers and content."""
        addr_lower = self.from_addr.lower()
        subject_lower = (self.subject or "").lower()
        snippet_lower = (self.snippet or "").lower()
        combined = f"{subject_lower} {snippet_lower}"

        # Spam folder = spam, period.
        if self.folder.lower() == "spam":
            self.category = "spam"
            self.priority = 0
            return

        # Important sender allowlist.
        if addr_lower in IMPORTANT_SENDERS:
            self.category = "important"
            self.priority = 10
            return

        # GitHub / notification list emails.
        if self.list_id:
            list_lower = self.list_id.lower()
            if any(domain in list_lower for domain in NOTIFICATION_LIST_IDS):
                self.category = "notification"
                self.priority = 3
                # CI failures get elevated.
                if "run failed" in combined or "ci" in combined:
                    self.priority = 5
                return
            # Other lists are lower priority.
            self.category = "notification"
            self.priority = 2
            return

        # Promotional patterns.
        if PROMO_RE.search(combined):
            self.category = "promotion"
            self.priority = 1
            return

        # Priority keywords bump.
        if PRIORITY_RE.search(combined):
            self.category = "important"
            self.priority = 7
            return

        # Default: normal inbox.
        self.category = "inbox"
        self.priority = 4

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "folder": self.folder,
            "from_addr": self.from_addr,
            "from_name": self.from_name,
            "subject": self.subject,
            "date": self.date.isoformat() if self.date else None,
            "category": self.category,
            "priority": self.priority,
            "list_id": self.list_id,
            "snippet": self.snippet[:200],
        }


def _fetch_folder(
    conn: imaplib.IMAP4,
    folder: str,
    *,
    since: datetime,
    password: str,
) -> list[EmailSummary]:
    """Fetch email summaries from a folder since *since*."""
    conn.select(folder, readonly=True)
    # IMAP date search: SINCE is day-level granularity.
    date_str = since.strftime("%d-%b-%Y")
    typ, data = conn.search(None, f'SINCE {date_str}')
    if typ != "OK" or not data[0]:
        return []

    all_ids = data[0].split()
    # Limit to most recent MAX_FETCH to avoid huge fetches.
    ids = all_ids[-MAX_FETCH:]

    summaries: list[EmailSummary] = []
    for uid in ids:
        typ, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-ID)] BODY.PEEK[TEXT]<0.500>)")
        if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue

        raw_headers = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
        headers = raw_headers.decode(errors="replace") if isinstance(raw_headers, bytes) else str(raw_headers)

        # Parse headers
        msg = email.message_from_string(headers)
        from_raw = msg.get("From", "")
        # Extract email address and name
        from_match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', from_raw)
        if from_match:
            from_name = _decode_header(from_match.group(1).strip())
            from_addr = from_match.group(2).strip()
        else:
            from_name = ""
            from_addr = from_raw.strip()

        subject = _decode_header(msg.get("Subject", ""))
        date_raw = msg.get("Date", "")
        list_id = msg.get("List-Id", "")

        date_obj: datetime | None = None
        if date_raw:
            try:
                date_obj = parsedate_to_datetime(date_raw)
                if date_obj and date_obj.tzinfo is None:
                    date_obj = date_obj.replace(tzinfo=UTC)
            except Exception:
                pass

        # Extract snippet from text body
        snippet = ""
        for item in msg_data:
            if isinstance(item, tuple) and isinstance(item[1], bytes):
                body = item[1].decode(errors="replace")
                # Strip HTML tags crudely
                clean = re.sub(r"<[^>]+>", " ", body)
                clean = re.sub(r"\s+", " ", clean).strip()
                snippet = clean[:300]
                break

        summary = EmailSummary(
            uid=uid.decode() if isinstance(uid, bytes) else str(uid),
            folder=folder,
            from_addr=from_addr,
            from_name=from_name,
            subject=subject,
            date=date_obj,
            list_id=list_id,
            snippet=snippet,
        )
        summary.classify()
        summaries.append(summary)

    return summaries


def fetch_recent_emails(hours: int = 24) -> dict[str, Any]:
    """Fetch and classify emails from the last *hours* hours.

    Returns a dict with:
      - summaries: list of EmailSummary dicts
      - counts: per-category counts
      - folders_scanned: list of folder names
    """
    password = _bridge_password()
    if not password:
        return {
            "error": "No bridge password found in keyring",
            "summaries": [],
            "counts": {},
            "folders_scanned": [],
        }

    since = datetime.now(UTC) - timedelta(hours=hours)
    all_summaries: list[EmailSummary] = []
    folders_scanned: list[str] = []

    try:
        conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        conn.starttls()
        conn.login(EMAIL_FROM_CANDIDATES[0], password)

        for folder in SCAN_FOLDERS:
            try:
                summaries = _fetch_folder(conn, folder, since=since, password=password)
                all_summaries.extend(summaries)
                folders_scanned.append(folder)
            except imaplib.IMAP4.error as exc:
                folders_scanned.append(f"{folder} (error: {exc})")

        conn.logout()
    except Exception as exc:
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "summaries": [],
            "counts": {},
            "folders_scanned": [],
        }

    # Filter to only messages within the time window (IMAP SINCE is day-level).
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    filtered = [s for s in all_summaries if s.date is None or s.date >= cutoff]

    # Sort by date descending.
    filtered.sort(key=lambda s: s.date or datetime.min.replace(tzinfo=UTC), reverse=True)

    # Counts per category.
    counts: dict[str, int] = {}
    for s in filtered:
        counts[s.category] = counts.get(s.category, 0) + 1

    return {
        "summaries": [s.to_dict() for s in filtered],
        "counts": counts,
        "folders_scanned": folders_scanned,
        "total": len(filtered),
    }


# ---------------------------------------------------------------------------
# Digest formatting
# ---------------------------------------------------------------------------


def build_digest(data: dict[str, Any]) -> str:
    """Build a human-readable digest from fetch_recent_emails() output."""
    if data.get("error"):
        return f"❌ Email fetch failed: {data['error']}"

    summaries: list[dict[str, Any]] = data.get("summaries", [])
    counts: dict[str, int] = data.get("counts", {})
    total = data.get("total", 0)

    now_str = datetime.now(UTC).strftime("%a %b %d, %Y %H:%M UTC")
    lines = [
        f"📧 Daily Email Digest — {now_str}",
        f"Total: {total} messages in last 24h",
        "",
    ]

    if counts:
        parts = []
        for cat in ("important", "inbox", "notification", "promotion", "spam"):
            if cat in counts:
                emoji = {
                    "important": "🔴",
                    "inbox": "🔵",
                    "notification": "🟡",
                    "promotion": "🟢",
                    "spam": "⚫",
                }.get(cat, "⚪")
                parts.append(f"{emoji} {cat}: {counts[cat]}")
        if parts:
            lines.append(" | ".join(parts))
        lines.append("")

    # Important emails (show up to 10).
    important = [s for s in summaries if s["category"] == "important"]
    if important:
        lines.append("🔴 IMPORTANT:")
        for s in important[:10]:
            sender = s["from_name"] or s["from_addr"] or "?"
            subject = s["subject"][:80] if s["subject"] else "(no subject)"
            lines.append(f"  • {sender}: {subject}")
        if len(important) > 10:
            lines.append(f"  ... and {len(important) - 10} more")
        lines.append("")

    # Notifications (show up to 5).
    notifications = [s for s in summaries if s["category"] == "notification"]
    if notifications:
        lines.append("🟡 NOTIFICATIONS:")
        for s in notifications[:5]:
            sender = s["from_name"] or s["from_addr"] or "?"
            subject = s["subject"][:80] if s["subject"] else "(no subject)"
            lines.append(f"  • {sender}: {subject}")
        if len(notifications) > 5:
            lines.append(f"  ... and {len(notifications) - 5} more")
        lines.append("")

    # Normal inbox (show up to 5).
    inbox = [s for s in summaries if s["category"] == "inbox"]
    if inbox:
        lines.append("🔵 INBOX:")
        for s in inbox[:5]:
            sender = s["from_name"] or s["from_addr"] or "?"
            subject = s["subject"][:80] if s["subject"] else "(no subject)"
            lines.append(f"  • {sender}: {subject}")
        if len(inbox) > 5:
            lines.append(f"  ... and {len(inbox) - 5} more")
        lines.append("")

    # Promotions (just count).
    promos = [s for s in summaries if s["category"] == "promotion"]
    if promos:
        lines.append(f"🟢 PROMOTIONS: {len(promos)} filtered")

    # Spam (just count).
    spam = [s for s in summaries if s["category"] == "spam"]
    if spam:
        lines.append(f"⚫ SPAM: {len(spam)} in spam folder")

    if not summaries:
        lines.append("No emails in the last 24h. 🎉")

    return "\n".join(lines)


def build_whatsapp_digest(data: dict[str, Any]) -> str:
    """Build a compact WhatsApp-friendly digest (under 4096 chars)."""
    if data.get("error"):
        return f"📧 Email Digest: fetch failed — {data['error']}"

    summaries: list[dict[str, Any]] = data.get("summaries", [])
    counts: dict[str, int] = data.get("counts", {})
    total = data.get("total", 0)

    now_str = datetime.now(UTC).strftime("%a %b %d")
    lines = [f"📧 *Daily Email Digest — {now_str}*"]
    lines.append(f"_{total} messages in last 24h_")
    lines.append("")

    # Summary line
    parts = []
    for cat in ("important", "inbox", "notification", "promotion", "spam"):
        if cat in counts:
            emoji = {
                "important": "🔴",
                "inbox": "🔵",
                "notification": "🟡",
                "promotion": "🟢",
                "spam": "⚫",
            }.get(cat, "⚪")
            parts.append(f"{emoji}{counts[cat]}")
    if parts:
        lines.append(" ".join(parts))
        lines.append("")

    # Important (up to 8, compact)
    important = [s for s in summaries if s["category"] == "important"]
    if important:
        lines.append("*🔴 Important:*")
        for s in important[:8]:
            sender = (s["from_name"] or s["from_addr"] or "?")[:30]
            subject = (s["subject"] or "(no subject)")[:60]
            lines.append(f"• {sender}: {subject}")
        if len(important) > 8:
            lines.append(f"_+{len(important) - 8} more_")
        lines.append("")

    # Notifications (up to 4)
    notifications = [s for s in summaries if s["category"] == "notification"]
    if notifications:
        lines.append("*🟡 Notifications:*")
        for s in notifications[:4]:
            sender = (s["from_name"] or s["from_addr"] or "?")[:30]
            subject = (s["subject"] or "(no subject)")[:60]
            lines.append(f"• {sender}: {subject}")
        if len(notifications) > 4:
            lines.append(f"_+{len(notifications) - 4} more_")
        lines.append("")

    # Inbox (up to 3)
    inbox = [s for s in summaries if s["category"] == "inbox"]
    if inbox:
        lines.append("*🔵 Inbox:*")
        for s in inbox[:3]:
            sender = (s["from_name"] or s["from_addr"] or "?")[:30]
            subject = (s["subject"] or "(no subject)")[:60]
            lines.append(f"• {sender}: {subject}")
        if len(inbox) > 3:
            lines.append(f"_+{len(inbox) - 3} more_")
        lines.append("")

    # Promotions and spam counts only
    promos = counts.get("promotion", 0)
    spam = counts.get("spam", 0)
    if promos:
        lines.append(f"🟢 Promotions: {promos} (filtered)")
    if spam:
        lines.append(f"⚫ Spam: {spam} (in spam folder)")

    if not summaries:
        lines.append("No emails in the last 24h. 🎉")

    text = "\n".join(lines)
    # WhatsApp text limit is 4096 chars.
    if len(text) > 4090:
        text = text[:4080] + "\n…(truncated)"
    return text


# ---------------------------------------------------------------------------
# WhatsApp sending
# ---------------------------------------------------------------------------


def _whatsapp_recipient() -> str:
    """Read the configured WhatsApp recipient phone number."""
    cfg_path = Path.home() / ".config" / "substrate" / "approval_lane.json"
    try:
        cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError):
        return ""
    # Check for whatsapp config
    wa = cfg.get("whatsapp") or {}
    return wa.get("recipient") or ""


async def send_whatsapp_digest(text: str, recipient: str = "") -> dict[str, Any]:
    """Send the digest via WhatsApp Cloud API.

    Requires the WhatsApp plugin to be configured in state/gateway-whatsapp.json.
    Returns the send result or an error dict.
    """
    recipient = recipient or _whatsapp_recipient()
    if not recipient:
        return {
            "ok": False,
            "error": "No WhatsApp recipient configured (set whatsapp.recipient in ~/.config/substrate/approval_lane.json)",
        }

    # Load WhatsApp plugin config from state
    wa_state_path = Path("state/gateway-whatsapp.json")
    if not wa_state_path.exists():
        return {
            "ok": False,
            "error": "WhatsApp plugin not configured (state/gateway-whatsapp.json missing)",
        }

    try:
        wa_config = json.loads(wa_state_path.read_text())
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"WhatsApp config parse error: {exc}"}

    phone_number_id = wa_config.get("phone_number_id")
    access_token = wa_config.get("access_token")
    if not phone_number_id or not access_token:
        return {
            "ok": False,
            "error": "WhatsApp plugin missing phone_number_id or access_token",
        }

    try:
        from ..gateway.models import OutboundMessage
        from ..gateway.plugins.whatsapp import WhatsAppPlugin

        plugin = WhatsAppPlugin()
        plugin.initialize({
            "phone_number_id": phone_number_id,
            "access_token": access_token,
            "app_secret": wa_config.get("app_secret", ""),
            "verify_token": wa_config.get("verify_token", ""),
        })

        message = OutboundMessage.text(recipient, text)
        result = await plugin.send(message)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator, directive
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    # 1. Fetch and classify recent emails.
    email_data = fetch_recent_emails(hours=24)
    actions.append({
        "action": "fetch-emails",
        "tier": 0,
        "status": "failed" if email_data.get("error") else "success",
        "total": email_data.get("total", 0),
        "counts": email_data.get("counts", {}),
        "folders_scanned": email_data.get("folders_scanned", []),
        "error": email_data.get("error"),
    })

    # 2. Build digest text.
    digest_text = build_digest(email_data)
    whatsapp_text = build_whatsapp_digest(email_data)

    # 3. Write digest note to research dir.
    digest_dir = runtime.paths["research"] / "email-digest"
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / f"{date_str}-digest.md"
    digest_path.write_text(digest_text + "\n", encoding="utf-8")
    outputs.append(str(digest_path.relative_to(runtime.root)))

    # Also write the JSON data for programmatic access.
    json_path = digest_dir / f"{date_str}-digest.json"
    json_path.write_text(
        json.dumps(email_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    outputs.append(str(json_path.relative_to(runtime.root)))

    # 4. Attempt WhatsApp delivery (Tier 2 — requires configured plugin).
    wa_result: dict[str, Any] = {"skipped": True, "reason": "not configured"}
    wa_recipient = _whatsapp_recipient()
    wa_state_path = Path("state/gateway-whatsapp.json")
    if wa_recipient and wa_state_path.exists():
        import asyncio
        try:
            wa_result = asyncio.run(send_whatsapp_digest(whatsapp_text, wa_recipient))
        except Exception as exc:
            wa_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    actions.append({
        "action": "whatsapp-digest",
        "tier": 2,
        "status": "success" if wa_result.get("ok") else "skipped",
        "recipient": wa_recipient or "(not configured)",
        "detail": wa_result.get("error") or wa_result.get("reason") or "sent",
    })

    # 5. Summary line.
    counts = email_data.get("counts", {})
    total = email_data.get("total", 0)
    wa_status = "sent" if wa_result.get("ok") else "skipped (WA not configured)"

    return {
        "status": "failed" if email_data.get("error") else "success",
        "note": (
            f"{total} emails processed "
            f"(important: {counts.get('important', 0)}, "
            f"notifications: {counts.get('notification', 0)}, "
            f"promotions: {counts.get('promotion', 0)}, "
            f"spam: {counts.get('spam', 0)}); "
            f"WhatsApp: {wa_status}"
        ),
        "outputs": outputs,
        "actions": actions,
    }
