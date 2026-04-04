from __future__ import annotations

import re
import smtplib
import socket
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage

from .models import AppConfig, Job, RunRecord
from .security import load_secret

DEFAULT_NOTIFICATION_TO = "adarnell@concepts2code.com"
CLOUD_SUMMARY_START = "[[CodexSchedulerCloudSummary:v1]]"
CLOUD_SUMMARY_END = "[[/CodexSchedulerCloudSummary]]"


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _action(action: str, label: str) -> dict[str, str]:
    return {"action": action, "label": label}


def _looks_like_email(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def _sanitize_text(value: str, limit: int = 2000) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0B-\x1F\x7F]", "", value or "")
    return cleaned.strip()[:limit]


def build_cloud_summary_prompt(prompt: str) -> str:
    if CLOUD_SUMMARY_START in prompt and CLOUD_SUMMARY_END in prompt:
        return prompt
    contract = (
        "\n\nScheduler contract (required when present):\n"
        f"Return a concise final summary block exactly once using these delimiters:\n"
        f"{CLOUD_SUMMARY_START}\n"
        "status: <completed|failed|timed_out>\n"
        "highlights: <short comma-separated summary>\n"
        "checks: <pass/fail notes>\n"
        "next_actions: <short actionable follow-up>\n"
        f"{CLOUD_SUMMARY_END}\n"
        "Keep the block under 1200 characters."
    )
    return f"{prompt}{contract}"


def extract_cloud_summary_block(raw_output: str | None) -> str | None:
    text = raw_output or ""
    pattern = re.escape(CLOUD_SUMMARY_START) + r"(.*?)" + re.escape(CLOUD_SUMMARY_END)
    matches = re.findall(pattern, text, flags=re.DOTALL)
    if not matches:
        return None
    summary = _sanitize_text(matches[-1], limit=1500)
    return summary or None


def resolve_notification_recipient(job: Job, config: AppConfig) -> str | None:
    candidate = (job.notify_email_to or config.default_notification_to or DEFAULT_NOTIFICATION_TO or "").strip()
    return candidate or None


def compute_notification_readiness(config: AppConfig, recipient: str | None = None) -> dict:
    if config.notifications_enabled is False:
        return {
            "ready": False,
            "category": "disabled",
            "summary": "Email notifications are disabled in settings.",
            "actions": [_action("enable_notifications", "Enable notifications")],
        }

    missing: list[str] = []
    if not (config.smtp_host or "").strip():
        missing.append("SMTP host")
    if not config.smtp_port:
        missing.append("SMTP port")
    if (config.smtp_security or "starttls") not in {"starttls", "ssl", "none"}:
        missing.append("SMTP security mode")
    if not _looks_like_email(config.smtp_from_email):
        missing.append("valid From email")

    if missing:
        return {
            "ready": False,
            "category": "config_missing",
            "summary": f"Email delivery setup incomplete: {', '.join(missing)}.",
            "actions": [_action("configure_smtp", "Configure SMTP settings")],
        }

    if (config.smtp_username or "").strip() and not (config.smtp_password_secret_ref or "").strip():
        return {
            "ready": False,
            "category": "auth_missing",
            "summary": "SMTP password is not configured.",
            "actions": [_action("set_smtp_password", "Set SMTP password")],
        }

    resolved_recipient = (recipient or config.default_notification_to or DEFAULT_NOTIFICATION_TO or "").strip()
    if not _looks_like_email(resolved_recipient):
        return {
            "ready": False,
            "category": "recipient_invalid",
            "summary": "Default notification recipient is missing or invalid.",
            "actions": [_action("set_recipient", "Set default recipient")],
        }

    return {
        "ready": True,
        "category": None,
        "summary": "Email delivery is ready.",
        "actions": [],
    }


def _classify_send_exception(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth_failed", False
    if isinstance(exc, smtplib.SMTPResponseException):
        code = int(getattr(exc, "smtp_code", 0) or 0)
        if 400 <= code < 500:
            return "provider_transient", True
        return "send_failed", False
    if isinstance(exc, (socket.timeout, TimeoutError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError)):
        return "provider_transient", True
    return "unknown", False


def _smtp_send_once(
    *,
    host: str,
    port: int,
    security_mode: str,
    username: str | None,
    password: str | None,
    message: EmailMessage,
    timeout_seconds: int,
) -> None:
    ssl_ctx = ssl.create_default_context()
    if security_mode == "ssl":
        with smtplib.SMTP_SSL(host=host, port=port, timeout=timeout_seconds, context=ssl_ctx) as client:
            if username:
                client.login(username, password or "")
            client.send_message(message)
        return

    with smtplib.SMTP(host=host, port=port, timeout=timeout_seconds) as client:
        client.ehlo()
        if security_mode == "starttls":
            client.starttls(context=ssl_ctx)
            client.ehlo()
        if username:
            client.login(username, password or "")
        client.send_message(message)


def send_email_smtp(
    *,
    config: AppConfig,
    recipient: str,
    subject: str,
    body: str,
    timeout_seconds: int = 20,
    max_attempts: int = 2,
) -> dict:
    host = (config.smtp_host or "").strip()
    security_mode = (config.smtp_security or "starttls").strip().lower()
    username = (config.smtp_username or "").strip() or None
    from_email = (config.smtp_from_email or "").strip()

    password = None
    if config.smtp_password_secret_ref:
        password = load_secret(config.smtp_password_secret_ref)

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            _smtp_send_once(
                host=host,
                port=int(config.smtp_port or 587),
                security_mode=security_mode,
                username=username,
                password=password,
                message=message,
                timeout_seconds=timeout_seconds,
            )
            return {
                "ok": True,
                "category": None,
                "summary": "Email sent.",
            }
        except Exception as exc:  # pragma: no cover - exercised via tests with monkeypatch
            category, retryable = _classify_send_exception(exc)
            if retryable and attempt < attempts:
                time.sleep(2 * attempt)
                continue
            return {
                "ok": False,
                "category": category,
                "summary": _sanitize_text(str(exc), limit=400) or "Email delivery failed.",
            }

    return {
        "ok": False,
        "category": "unknown",
        "summary": "Email delivery failed.",
    }


def _build_run_subject(job: Job, run: RunRecord) -> str:
    return f"[Codex Scheduler] {job.name} - {run.status}"


def _build_run_body(job: Job, run: RunRecord, cloud_summary: str | None) -> str:
    started = run.started_at.isoformat() if run.started_at else "n/a"
    finished = run.finished_at.isoformat() if run.finished_at else "n/a"
    duration_seconds = None
    if run.started_at and run.finished_at:
        duration_seconds = max(0, int((run.finished_at - run.started_at).total_seconds()))

    parts = [
        "Codex Scheduler job status update",
        "",
        f"Job: {job.name}",
        f"Mode: {job.mode}",
        f"Status: {run.status}",
        f"Return code: {run.return_code if run.return_code is not None else 'n/a'}",
        f"Failure category: {run.failure_category or 'n/a'}",
        f"Retryable: {'yes' if run.retryable else 'no'}",
        f"Started (UTC): {started}",
        f"Finished (UTC): {finished}",
        f"Duration (s): {duration_seconds if duration_seconds is not None else 'n/a'}",
        "",
        "Message:",
        _sanitize_text(run.message or "n/a", limit=1200),
    ]

    if cloud_summary:
        parts.extend(["", "Cloud Summary:", cloud_summary])

    if run.stdout_path or run.stderr_path:
        parts.extend(
            [
                "",
                "Artifacts:",
                f"stdout: {run.stdout_path or 'n/a'}",
                f"stderr: {run.stderr_path or 'n/a'}",
                f"metadata: {run.metadata_path or 'n/a'}",
            ]
        )
    return "\n".join(parts)


def send_run_notification(
    *,
    config: AppConfig,
    job: Job,
    run: RunRecord,
    cloud_output: str | None = None,
) -> dict:
    if not bool(job.notify_email_enabled):
        return {
            "status": "skipped",
            "error": "job_notifications_disabled",
            "recipient": None,
            "sent_at": None,
        }
    if config.notifications_enabled is False:
        return {
            "status": "skipped",
            "error": "global_notifications_disabled",
            "recipient": None,
            "sent_at": None,
        }

    recipient = resolve_notification_recipient(job, config)
    readiness = compute_notification_readiness(config, recipient=recipient)
    if not readiness["ready"]:
        return {
            "status": "failed",
            "error": readiness["summary"],
            "recipient": recipient,
            "sent_at": None,
        }

    summary = extract_cloud_summary_block(cloud_output) if job.mode == "cloud_exec" else None
    subject = _build_run_subject(job, run)
    body = _build_run_body(job, run, summary)
    sent = send_email_smtp(
        config=config,
        recipient=recipient or DEFAULT_NOTIFICATION_TO,
        subject=subject,
        body=body,
        timeout_seconds=20,
        max_attempts=2,
    )
    if sent["ok"]:
        return {
            "status": "sent",
            "error": None,
            "recipient": recipient,
            "sent_at": utcnow_naive(),
        }
    return {
        "status": "failed",
        "error": sent["summary"],
        "recipient": recipient,
        "sent_at": None,
    }


def send_test_notification(*, config: AppConfig, recipient: str | None = None) -> dict:
    target = (recipient or config.default_notification_to or DEFAULT_NOTIFICATION_TO or "").strip()
    readiness = compute_notification_readiness(config, recipient=target)
    if not readiness["ready"]:
        return {
            "ok": False,
            "category": readiness["category"],
            "summary": readiness["summary"],
            "recipient": target or None,
        }

    body = (
        "Codex Scheduler Studio test notification\n\n"
        "If you received this email, SMTP delivery is configured and working."
    )
    sent = send_email_smtp(
        config=config,
        recipient=target,
        subject="[Codex Scheduler] Test notification",
        body=body,
        timeout_seconds=20,
        max_attempts=2,
    )
    return {
        "ok": bool(sent["ok"]),
        "category": sent["category"],
        "summary": "Test email sent." if sent["ok"] else sent["summary"],
        "recipient": target,
    }
