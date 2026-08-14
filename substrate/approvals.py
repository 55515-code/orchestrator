"""Approval lane subsystem for the Local Agent Substrate.

Automation that requires a human input does not have to wait for the operator
to log in. This module provides a *primary approval lane*: a verified
communication channel (email, and provider-based SMS when configured) through
which the substrate

1. sends a verification-coded test message,
2. confirms the operator controls the channel when the matching code comes
   back through the same platform,
3. promotes the verified channel to the permanent primary approval lane, and
4. dispatches and resolves approval requests for directive-gated actions.

The lane never auto-approves anything: a pending approval is only resolved by
the operator's reply carrying the single-use code. This preserves the substrate
autonomy-tier rule that Tier 2 actions always require an explicit human
directive - the verified reply *is* that directive.

Channels
--------
* ``email``      - Proton Mail Bridge SMTP relay (127.0.0.1:1025, STARTTLS,
                   unauthenticated local). Sends to the configured address.
* ``sms:<num>``  - provider-based SMS (e.g. Twilio). Requires provider
                   credentials in the lane config; reports precisely when the
                   provider is not configured.

Delivery status
---------------
The Proton Mail Bridge on this host currently loads *zero* accounts (the v2->v3
migration failed with "failed to create keychain: no keychain"), so the SMTP
relay rejects every sender with "The account is not available in Bridge".
The lane therefore reports the exact failure and stays ``ready``-pending
verification until the bridge account is re-added. SMS requires an external
provider subscription. Neither is fabricatable from inside the substrate -
credentials are operator-supplied secrets.

Stdlib only.
"""

from __future__ import annotations

import email
import imaplib
import json
import re
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .learning import record_execution

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_FILENAME = "approval-lane.json"

# Channel keys seeded into the lane on first load.
DEFAULT_CHANNELS: dict[str, dict[str, Any]] = {
    "email": {
        "label": "Email",
        "address": "ahronzombi@protonmail.com",
        "backend": "proton_bridge",
        "enabled": True,
    },
    "sms:7163528536": {
        "label": "SMS 716-352-8536",
        "address": "7163528536",
        "backend": "provider",
        "provider": None,
        "enabled": True,
    },
    "sms:7162666606": {
        "label": "SMS 716-266-6606",
        "address": "7162666606",
        "backend": "provider",
        "provider": None,
        "enabled": True,
    },
}

# Primary approval lane configuration (operator-supplied secrets live here).
CONFIG_PATH = Path.home() / ".config" / "substrate" / "approval_lane.json"

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
CODE_LEN = 6
CODE_TTL_MINUTES = 60 * 24 * 3  # 72h to reply before a code expires
MAX_VERIFY_ATTEMPTS = 5

EMAIL_FROM_CANDIDATES = [
    "ahronzombi@protonmail.com",
    "ahronzombi@proton.me",
]
SMTP_HOST = "127.0.0.1"
SMTP_PORT = 1025
IMAP_HOST = "127.0.0.1"
IMAP_PORT = 1143

# Bridge v3 requires SMTP AUTH with the per-account password it generates.
# That password lives in the OS keyring (secret-service), labeled:
#   service=substrate-credentials account=proton-bridge-smtp
# It can also be supplied via config:  smtp.username / smtp.password
KEYRING_SERVICE = "substrate-credentials"
KEYRING_ACCOUNT = "proton-bridge-smtp"

CODE_RE = re.compile(rf"\b[{CODE_ALPHABET}]{{{CODE_LEN}}}\b")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def lane_path(runtime: Any) -> Path:
    paths = getattr(runtime, "paths", None)
    if isinstance(paths, dict) and paths.get("approval_lane"):
        return Path(paths["approval_lane"])
    return Path(getattr(runtime, "root", Path("."))) / "state" / STATE_FILENAME


def load_lane(runtime: Any) -> dict[str, Any]:
    """Load the lane state, seeding default channels on first use."""
    path = lane_path(runtime)
    lane: dict[str, Any] = {
        "version": 1,
        "primary": None,
        "primary_confirmed_at": None,
        "channels": {},
        "pending_approvals": [],
        "resolved_approvals": [],
        "log": [],
    }
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                lane.update({k: v for k, v in loaded.items() if k in lane})
                lane["channels"] = dict(loaded.get("channels") or {})
                lane["pending_approvals"] = list(loaded.get("pending_approvals") or [])
                lane["resolved_approvals"] = list(loaded.get("resolved_approvals") or [])
                lane["log"] = list(loaded.get("log") or [])
        except (OSError, ValueError):
            # Corrupt state: fall back to defaults without clobbering on save.
            lane["_corrupt"] = True
    for key, cfg in DEFAULT_CHANNELS.items():
        lane["channels"].setdefault(key, dict(cfg))
        lane["channels"][key].setdefault("status", "unconfigured")
        lane["channels"][key].setdefault("last_error", "")
        lane["channels"][key].setdefault("verification_code", None)
        lane["channels"][key].setdefault("code_expires_at", None)
        lane["channels"][key].setdefault("last_probe_at", None)
        lane["channels"][key].setdefault("verified_at", None)
    return lane


def save_lane(runtime: Any, lane: dict[str, Any]) -> None:
    path = lane_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": lane.get("version", 1),
        "primary": lane.get("primary"),
        "primary_confirmed_at": lane.get("primary_confirmed_at"),
        "channels": lane["channels"],
        "pending_approvals": lane["pending_approvals"],
        "resolved_approvals": lane["resolved_approvals"],
        "log": lane["log"][-200:],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    path.chmod(0o600)


def _log(lane: dict[str, Any], event: str, **detail: Any) -> None:
    lane.setdefault("log", []).append(
        {"ts": utc_now(), "event": event, **detail}
    )


def _load_operator_config() -> dict[str, Any]:
    """Load operator-supplied lane config (credentials live here, never in state)."""
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _channel_config(channel: str) -> dict[str, Any]:
    cfg = _load_operator_config()
    channels = cfg.get("channels") or {}
    return channels.get(channel) or {}


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------


def new_code() -> str:
    """Generate a single-use verification code (no ambiguous characters)."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


def _code_valid(channel_cfg: dict[str, Any], code: str) -> tuple[bool, str]:
    expected = channel_cfg.get("verification_code")
    if not expected:
        return False, "no verification code issued for this channel"
    if expected != (code or "").strip().upper():
        return False, "verification code does not match"
    expires = channel_cfg.get("code_expires_at")
    if expires:
        try:
            expiry = datetime.fromisoformat(expires)
            if datetime.now(UTC) > expiry:
                return False, "verification code expired"
        except ValueError:
            pass
    return True, "ok"


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


def _bridge_smtp_password() -> str:
    """Read the Proton Mail Bridge SMTP password from the OS keyring.

    Falls back to the operator config (``approval_lane.json`` ->
    ``smtp.password``) when secret-tool is unavailable (e.g. headless
    containers). Never logs or echoes the secret.
    """
    try:
        import subprocess
        out = subprocess.run(
            ["secret-tool", "lookup", "service", KEYRING_SERVICE,
             "account", KEYRING_ACCOUNT],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    cfg = _load_operator_config()
    return (cfg.get("smtp") or {}).get("password") or ""


def email_backend_send(
    to: str,
    subject: str,
    body: str,
    *,
    from_candidates: list[str] | None = None,
    host: str = SMTP_HOST,
    port: int = SMTP_PORT,
) -> tuple[bool, str, str]:
    """Send an email via the Proton Mail Bridge SMTP relay.

    Returns ``(ok, from_address_used, detail)``. Failures are precise so the
    operator can act (the common one being a bridge with no loaded account).
    """
    from_candidates = list(from_candidates or EMAIL_FROM_CANDIDATES)
    if not from_candidates:
        return False, "", "no from-address candidates configured"
    msg_template = (
        "From: Substrate Approval Lane <{frm}>\n"
        "To: {to}\n"
        "Subject: {subject}\n"
        "Date: {date}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "{body}"
    )
    last = ""
    password = _bridge_smtp_password()
    for frm in from_candidates:
        if not frm:
            continue
        try:
            conn = smtplib.SMTP(host, port, timeout=10)
            conn.ehlo()
            try:
                conn.starttls()
                conn.ehlo()
            except smtplib.SMTPException:
                pass  # relay may not offer STARTTLS in some builds
            if password:
                try:
                    conn.login(frm, password)
                except smtplib.SMTPAuthenticationError:
                    last = f"from={frm} bridge SMTP auth rejected (check keyring proton-bridge-smtp)"
                    conn.quit()
                    continue
            conn.sendmail(
                frm,
                [to],
                msg_template.format(
                    frm=frm,
                    to=to,
                    subject=subject,
                    date=datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z"),
                    body=body,
                ),
            )
            conn.quit()
            return True, frm, "email accepted by bridge SMTP relay"
        except smtplib.SMTPDataError as exc:
            last = f"from={frm} bridge rejected: {exc.smtp_error.decode(errors='replace')[:120]}"
        except smtplib.SMTPServerDisconnected as exc:
            last = f"from={frm} server disconnected: {exc}"
        except OSError as exc:
            last = f"from={frm} connection failed: {exc}"
        except Exception as exc:  # noqa: BLE001 - report any backend error
            last = f"from={frm} failed: {type(exc).__name__}: {exc}"
    return False, "", last


def sms_backend_send(channel_cfg: dict[str, Any], to: str, body: str) -> tuple[bool, str]:
    """Send an SMS through a configured provider.

    No provider is bundled. When the operator adds provider credentials under
    ``~/.config/substrate/approval_lane.json`` (``channels.<key>.provider``,
    ``provider_api_key``), wire the provider SDK/HTTP call here. Until then the
    backend reports exactly what is missing - it never fabricates delivery.
    """
    provider = (channel_cfg.get("provider") or "").strip()
    if not provider:
        return (
            False,
            ("no SMS provider configured for this channel; add provider credentials "
            f"in {CONFIG_PATH} (channels.{channel_cfg.get('key', 'sms:<number>')}.provider)"),
        )
    return (
        False,
        (f"SMS provider '{provider}' is registered but not implemented; "
        "implement provider delivery in substrate/approvals.py sms_backend_send()"),
    )


def smtp_backend_send(to: str, subject: str, body: str, cfg: dict[str, Any]) -> tuple[bool, str]:
    """Send via a generic authenticated SMTP relay (e.g. Gmail app password).

    Config comes from the operator config ``~/.config/substrate/
    approval_lane.json`` -> ``smtp: {host, port, username, password, from}``.
    STARTTLS is used on port 587; TLS on 465.
    """
    host = cfg.get("host", "")
    if not host:
        return False, "generic SMTP backend not configured (add smtp.host in " + str(CONFIG_PATH) + ")"
    port = int(cfg.get("port", 587))
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    sender = cfg.get("from") or username
    msg_template = (
        "From: Substrate Approval Lane <{frm}>\n"
        "To: {to}\n"
        "Subject: {subject}\n"
        "Date: {date}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "{body}"
    )
    try:
        if port == 465:
            import ssl
            conn = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
        else:
            conn = smtplib.SMTP(host, port, timeout=15)
            conn.ehlo()
            conn.starttls()
            conn.ehlo()
        if username:
            conn.login(username, password)
        conn.sendmail(
            sender,
            [to],
            msg_template.format(
                frm=sender,
                to=to,
                subject=subject,
                date=datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z"),
                body=body,
            ),
        )
        conn.quit()
        return True, f"sent via SMTP {host}:{port}"
    except smtplib.SMTPAuthenticationError as exc:
        return False, f"SMTP auth failed ({host}): {exc.smtp_error.decode(errors='replace')[:80]}"
    except smtplib.SMTPDataError as exc:
        return False, f"SMTP {host} rejected: {exc.smtp_error.decode(errors='replace')[:120]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"SMTP {host} failed: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _dispatch(runtime: Any, channel: str, subject: str, body: str) -> dict[str, Any]:
    lane = load_lane(runtime)
    channel_cfg = lane["channels"].get(channel)
    if channel_cfg is None:
        return {"ok": False, "detail": f"unknown channel '{channel}'"}
    backend = channel_cfg.get("backend", "")
    if not channel_cfg.get("enabled", True):
        return {"ok": False, "detail": f"channel '{channel}' is disabled"}
    address = channel_cfg.get("address", "")
    if backend == "proton_bridge":
        ok, used, detail = email_backend_send(address, subject, body)
        return {"ok": ok, "detail": detail, "from": used, "backend": backend}
    if backend == "smtp":
        cfg = _load_operator_config().get("smtp") or {}
        ok, detail = smtp_backend_send(address, subject, body, cfg)
        return {"ok": ok, "detail": detail, "backend": backend}
    if backend == "provider":
        ok, detail = sms_backend_send(channel_cfg, address, body)
        return {"ok": ok, "detail": detail, "backend": backend}
    return {"ok": False, "detail": f"unknown backend '{backend}' for channel '{channel}'"}


# ---------------------------------------------------------------------------
# Test messages + verification
# ---------------------------------------------------------------------------


def send_test_message(runtime: Any, channel: str) -> dict[str, Any]:
    """Issue a verification code and dispatch a test message on *channel*."""
    lane = load_lane(runtime)
    channel_cfg = lane["channels"].get(channel)
    if channel_cfg is None:
        return {"ok": False, "detail": f"unknown channel '{channel}'. "
                f"Known channels: {', '.join(sorted(lane['channels']))}"}
    if not channel_cfg.get("enabled", True):
        return {"ok": False, "detail": f"channel '{channel}' is disabled"}

    code = new_code()
    channel_cfg["verification_code"] = code
    channel_cfg["code_expires_at"] = (
        datetime.now(UTC) + timedelta(minutes=CODE_TTL_MINUTES)
    ).isoformat(timespec="seconds")
    channel_cfg["verify_attempts"] = 0
    channel_cfg["status"] = "probe-sent"
    channel_cfg["last_probe_at"] = utc_now()
    channel_cfg["last_error"] = ""

    label = channel_cfg.get("label", channel)
    channel_cfg.get("address", "")
    body = (
        f"Substrate approval lane test message ({label}).\n\n"
        f"Verification code: {code}\n\n"
        f"Reply with this code through the same platform to verify this "
        f"channel. The code expires in {CODE_TTL_MINUTES // 60} days.\n"
        f"Sent by the Local Agent Substrate at {utc_now()}."
    )
    result = _dispatch(runtime, channel, f"Substrate approval lane test ({label})", body)
    channel_cfg["last_error"] = "" if result["ok"] else result["detail"]
    if not result["ok"]:
        channel_cfg["status"] = "error"
        # The code was never delivered; invalidate it so a stale code cannot
        # be used to verify the channel.
        channel_cfg["verification_code"] = None
        channel_cfg["code_expires_at"] = None
    _log(lane, "test_message", channel=channel, ok=result["ok"],
         detail=result["detail"], code=code)
    save_lane(runtime, lane)
    payload: dict[str, Any] = {
        "ok": result["ok"],
        "channel": channel,
        "detail": result["detail"],
        "status": channel_cfg["status"],
    }
    if result["ok"]:
        payload["verification_code"] = code
        payload["expires_at"] = channel_cfg["code_expires_at"]
    return payload


def verify_channel(runtime: Any, channel: str, code: str) -> dict[str, Any]:
    """Verify *channel* with its single-use code and promote to primary lane.

    The code must match and be unexpired. On success the channel becomes
    ``verified`` and - if no primary lane exists yet - the permanent primary
    approval lane. The channel address is fixed at verification time.
    """
    lane = load_lane(runtime)
    channel_cfg = lane["channels"].get(channel)
    if channel_cfg is None:
        return {"ok": False, "detail": f"unknown channel '{channel}'"}
    if channel_cfg.get("status") == "verified":
        return {"ok": False, "detail": f"channel '{channel}' is already verified"}

    attempts = int(channel_cfg.get("verify_attempts", 0))
    if attempts >= MAX_VERIFY_ATTEMPTS:
        channel_cfg["status"] = "error"
        save_lane(runtime, lane)
        return {"ok": False, "detail": "too many failed verification attempts; "
                                       "send a new test message to retry"}

    ok, reason = _code_valid(channel_cfg, code)
    if not ok:
        channel_cfg["verify_attempts"] = attempts + 1
        _log(lane, "verify_failed", channel=channel, reason=reason)
        save_lane(runtime, lane)
        return {"ok": False, "detail": reason}

    channel_cfg["status"] = "verified"
    channel_cfg["verified_at"] = utc_now()
    channel_cfg["verification_code"] = None
    channel_cfg["code_expires_at"] = None
    channel_cfg["last_error"] = ""
    was_primary = lane.get("primary")
    if not was_primary:
        lane["primary"] = channel
    _log(lane, "channel_verified", channel=channel, promoted=not was_primary)
    save_lane(runtime, lane)
    return {
        "ok": True,
        "channel": channel,
        "status": "verified",
        "promoted_to_primary": not bool(was_primary),
        "primary": lane["primary"],
    }


# ---------------------------------------------------------------------------
# Approval requests
# ---------------------------------------------------------------------------


def request_approval(
    runtime: Any,
    *,
    subject: str,
    body: str = "",
    channel: str | None = None,
) -> dict[str, Any]:
    """Dispatch an approval request through the lane and record it as pending.

    The operator's reply carrying the approval's single-use code (returned in
    ``verification_code``) resolves it via :func:`resolve_approval`. Nothing is
    ever auto-approved.
    """
    lane = load_lane(runtime)
    target = channel or lane.get("primary")
    if not target:
        return {
            "ok": False,
            "detail": "no primary approval channel verified; run "
                      "'approval-lane send-test' then 'approval-lane verify'",
        }
    channel_cfg = lane["channels"].get(target)
    if channel_cfg is None or channel_cfg.get("status") != "verified":
        return {
            "ok": False,
            "detail": f"channel '{target}' is not verified; "
                      "verify it before dispatching approval requests",
        }

    approval = {
        "id": f"apv-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}",
        "created_at": utc_now(),
        "subject": subject,
        "body": body,
        "channel": target,
        "code": new_code(),
        "code_expires_at": (
            datetime.now(UTC) + timedelta(minutes=CODE_TTL_MINUTES)
        ).isoformat(timespec="seconds"),
        "status": "pending",
        "decision": None,
        "resolved_at": None,
        "resolved_via": None,
    }
    message = (
        f"Approval required: {subject}\n\n"
        f"{body}\n\n"
        f"Reply with the approval code {approval['code']} to approve, or "
        f"'DENY {approval['code']}' to deny. Code expires "
        f"{CODE_TTL_MINUTES // 60} days after issuance.\n"
        f"Requested by the Local Agent Substrate at {approval['created_at']}."
    )
    result = _dispatch(runtime, target, f"Approval required: {subject}", message)
    approval["dispatch_ok"] = result["ok"]
    approval["dispatch_detail"] = result["detail"]
    lane["pending_approvals"].append(approval)
    _log(lane, "approval_requested", approval_id=approval["id"], channel=target,
         ok=result["ok"], detail=result["detail"])
    save_lane(runtime, lane)
    return {
        # The approval request is always recorded; dispatch_ok reports whether
        # the notification actually left through the channel.
        "ok": True,
        "approval_id": approval["id"],
        "channel": target,
        "dispatch_ok": result["ok"],
        "detail": result["detail"],
        "verification_code": approval["code"],
        "expires_at": approval["code_expires_at"],
    }


def resolve_approval(
    runtime: Any,
    approval_id: str,
    code: str,
    decision: str,
) -> dict[str, Any]:
    """Resolve a pending approval with its single-use code.

    ``decision`` is ``approve`` or ``deny``. Only the operator's code-verified
    reply resolves a pending approval; the lane never auto-approves.
    """
    lane = load_lane(runtime)
    approval = next(
        (a for a in lane["pending_approvals"] if a["id"] == approval_id), None
    )
    if approval is None:
        return {"ok": False, "detail": f"unknown approval id '{approval_id}'"}
    if approval["status"] != "pending":
        return {"ok": False, "detail": f"approval '{approval_id}' is already "
                                       f"{approval['status']}"}
    if (approval.get("code") or "").upper() != (code or "").strip().upper():
        return {"ok": False, "detail": "approval code does not match"}
    expires = approval.get("code_expires_at")
    if expires:
        try:
            if datetime.now(UTC) > datetime.fromisoformat(expires):
                approval["status"] = "expired"
                save_lane(runtime, lane)
                return {"ok": False, "detail": "approval code expired"}
        except ValueError:
            pass

    decision = decision.strip().lower()
    if decision not in {"approve", "deny"}:
        return {"ok": False, "detail": "decision must be 'approve' or 'deny'"}

    approval["status"] = "approved" if decision == "approve" else "denied"
    approval["decision"] = decision
    approval["resolved_at"] = utc_now()
    approval["resolved_via"] = lane.get("primary")
    lane["pending_approvals"] = [
        a for a in lane["pending_approvals"] if a["id"] != approval_id
    ]
    lane["resolved_approvals"].append(approval)
    _log(lane, "approval_resolved", approval_id=approval_id, decision=decision)
    save_lane(runtime, lane)
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": approval["status"],
        "decision": decision,
        "resolved_via": approval["resolved_via"],
    }


# ---------------------------------------------------------------------------
# Reply polling (IMAP)
# ---------------------------------------------------------------------------


def _imap_config() -> dict[str, Any]:
    cfg = _load_operator_config()
    return cfg.get("imap") or {}


def poll_for_replies(runtime: Any) -> list[dict[str, Any]]:
    """Poll the verified channel's mailbox for coded replies.

    Reads IMAP credentials from the operator config (``~/.config/substrate/
    approval_lane.json`` -> ``imap: {host, port, username, password}``), falling
    back to the Proton Mail Bridge account (ahronzombi@protonmail.com) and the
    bridge password from the OS keyring (service=substrate-credentials,
    account=proton-bridge-smtp).
    """
    lane = load_lane(runtime)
    primary = lane.get("primary")
    results: list[dict[str, Any]] = []
    if not primary:
        results.append({
            "ok": False, "detail": "no verified primary channel; nothing to poll",
        })
        return results

    cfg = _imap_config()
    username = cfg.get("username", "") or EMAIL_FROM_CANDIDATES[0]
    password = cfg.get("password", "") or _bridge_smtp_password()
    if not username or not password:
        results.append({
            "ok": False,
            "detail": "IMAP credentials not configured; add imap.username/"
                      "imap.password to " + str(CONFIG_PATH) +
                      " (or keyring proton-bridge-smtp)",
        })
        return results

    host = cfg.get("host", IMAP_HOST)
    port = int(cfg.get("port", IMAP_PORT))
    try:
        conn = imaplib.IMAP4(host, port)
        conn.starttls()
        conn.login(username, password)
        conn.select("INBOX")
        typ, data = conn.search(None, "UNSEEN")
        if typ != "OK":
            results.append({"ok": False, "detail": "IMAP search failed"})
            conn.logout()
            return results
        for num in (data[0] or b"").split():
            typ, msg_data = conn.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            text = _message_text(msg)
            results.extend(_scan_message_for_codes(runtime, lane, primary, text))
        conn.logout()
    except imaplib.IMAP4.error as exc:
        results.append({"ok": False, "detail": f"IMAP login failed: {exc}"})
    except OSError as exc:
        results.append({"ok": False, "detail": f"IMAP connection failed: {exc}"})
    except Exception as exc:  # noqa: BLE001
        results.append({"ok": False, "detail": f"IMAP poll failed: {exc}"})
    return results


def _message_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(errors="replace"))
                except Exception:  # noqa: BLE001
                    continue
        return "\n".join(parts)
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def _scan_message_for_codes(
    runtime: Any,
    lane: dict[str, Any],
    primary: str,
    text: str,
) -> list[dict[str, Any]]:
    """Match any active code in *text* and verify/resolve accordingly."""
    results: list[dict[str, Any]] = []
    channel_cfg = lane["channels"].get(primary, {})
    if channel_cfg.get("status") != "verified":
        code = channel_cfg.get("verification_code")
        if code and code in text:
            results.append(verify_channel(runtime, primary, code))
    for approval in lane["pending_approvals"]:
        code = approval.get("code", "")
        if not code or code not in text:
            continue
        upper = text.upper()
        decision = "deny" if f"DENY {code}" in upper or "DENY" in upper.split()[:3] else "approve"
        results.append(resolve_approval(runtime, approval["id"], code, decision))
    return results


# ---------------------------------------------------------------------------
# Gate hook + status
# ---------------------------------------------------------------------------


def notify_approval_gate(
    runtime: Any,
    *,
    action: str,
    detail: str = "",
) -> dict[str, Any]:
    """Dispatch an approval request when a directive-gated action is attempted.

    Never changes gate semantics: it only notifies through the primary lane and
    returns the dispatch outcome. Failures are recorded, never raised.
    """
    lane = load_lane(runtime)
    primary = lane.get("primary")
    if not primary:
        return {
            "dispatched": False,
            "reason": "no verified primary approval channel",
        }
    try:
        result = request_approval(
            runtime,
            subject=f"Approval required: {action}",
            body=detail,
            channel=primary,
        )
        return {
            "dispatched": bool(result.get("dispatch_ok")),
            "approval_id": result.get("approval_id"),
            "detail": result.get("detail", ""),
        }
    except Exception as exc:  # noqa: BLE001
        return {"dispatched": False, "reason": f"{type(exc).__name__}: {exc}"}


def approval_lane_status(runtime: Any) -> dict[str, Any]:
    """Status payload for the CLI and web panel (no secrets, no codes)."""
    lane = load_lane(runtime)
    channels = {}
    for key, cfg in lane["channels"].items():
        channels[key] = {
            "label": cfg.get("label", key),
            "address": cfg.get("address", ""),
            "backend": cfg.get("backend", ""),
            "enabled": cfg.get("enabled", True),
            "status": cfg.get("status", "unconfigured"),
            "last_error": cfg.get("last_error", ""),
            "last_probe_at": cfg.get("last_probe_at"),
            "verified_at": cfg.get("verified_at"),
        }
    pending = [
        {
            "id": a["id"],
            "subject": a["subject"],
            "channel": a["channel"],
            "status": a["status"],
            "created_at": a["created_at"],
            "dispatch_ok": a.get("dispatch_ok", False),
            "dispatch_detail": a.get("dispatch_detail", ""),
        }
        for a in lane["pending_approvals"]
    ]
    return {
        "primary": lane.get("primary"),
        "channels": channels,
        "pending_approvals": pending,
        "recent_events": lane.get("log", [])[-10:],
    }


# ---------------------------------------------------------------------------
# Watch pass (autonomous background operation)
# ---------------------------------------------------------------------------


def _code_expired(channel_cfg: dict[str, Any]) -> bool:
    expires = channel_cfg.get("code_expires_at")
    if not expires:
        return False
    try:
        return datetime.now(UTC) > datetime.fromisoformat(expires)
    except ValueError:
        return False


def watch_once(runtime: Any) -> dict[str, Any]:
    """One autonomous watch pass: retry channel delivery, poll for replies,
    auto-verify/promote, and confirm the primary lane.

    Called periodically (timer/background loop). Idempotent: it never re-sends
    a test message while a code is still awaiting reply, and it never verifies
    without a matching reply code.
    """
    lane = load_lane(runtime)
    summary: dict[str, Any] = {
        "test_sends": [],
        "verifications": [],
        "approval_resolutions": [],
        "notifications": [],
    }

    # 1. Retry test-message delivery for unverified channels.
    for key, cfg in lane["channels"].items():
        if cfg.get("status") == "verified":
            continue
        if not cfg.get("enabled", True):
            continue
        if cfg.get("status") == "probe-sent" and not _code_expired(cfg):
            continue  # awaiting the operator's reply; do not spam
        result = send_test_message(runtime, key)
        summary["test_sends"].append({
            "channel": key,
            "ok": result["ok"],
            "detail": result["detail"],
        })

    # 2. Poll the verified primary channel for coded replies.
    if lane.get("primary"):
        replies = poll_for_replies(runtime)
        summary["poll_replies"] = replies

    # 3. Confirm the primary lane once it is verified. Reload because the
    # helpers above persist their own state snapshots.
    lane = load_lane(runtime)
    if lane.get("primary") and not lane.get("primary_confirmed_at"):
        primary = lane["primary"]
        lane["primary_confirmed_at"] = utc_now()
        _log(lane, "primary_confirmed", channel=primary)
        confirmed = _dispatch(
            runtime,
            primary,
            "Substrate approval lane is live",
            (
                f"The {lane['channels'][primary].get('label', primary)} channel "
                f"is now the verified primary approval lane.\n"
                f"Future automation that requires input will route approval "
                f"requests here; reply with the code in each request to "
                f"approve, or 'DENY <code>' to deny.\n"
                f"Confirmed by the Local Agent Substrate at {utc_now()}."
            ),
        )
        summary["notifications"].append({
            "channel": primary,
            "ok": confirmed["ok"],
            "detail": confirmed["detail"],
        })
        save_lane(runtime, lane)

    return summary


def _audit(runtime: Any, run_type: str, command: str, status: str, note: str, stdout: str) -> None:
    try:
        record_execution(
            runtime,
            run_type=run_type,
            run_id=None,
            repo_slug=None,
            stage="local",
            command=command,
            status=status,
            exit_code=0 if status == "success" else 1,
            stdout=stdout,
            note=note,
        )
    except Exception:  # noqa: BLE001 - audit must never break the lane
        pass
