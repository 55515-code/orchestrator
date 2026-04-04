from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def normalize_sqlite_url(raw_url: str) -> str:
    if raw_url.startswith("sqlite:///"):
        return raw_url
    if raw_url.endswith(".db"):
        return f"sqlite:///{raw_url}"
    return raw_url


def init_database(db_url: str) -> tuple[sessionmaker[Session], object]:
    url = normalize_sqlite_url(db_url)
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if db_path.parent and str(db_path.parent) != ".":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(url)

    Base.metadata.create_all(bind=engine)
    _run_migrations(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return factory, engine


def _run_migrations(engine: object) -> None:
    with engine.begin() as conn:
        try:
            rows = conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
            cols = {row[1] for row in rows}
        except Exception:
            return

        if "codex_args" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN codex_args TEXT"))
        if "env_json" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN env_json TEXT"))
        if "notify_email_enabled" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN notify_email_enabled BOOLEAN DEFAULT 0"))
        if "notify_email_to" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN notify_email_to VARCHAR(320)"))
        if "repo_slug" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE jobs ADD COLUMN repo_slug VARCHAR(120) DEFAULT 'substrate-core'"
                )
            )
        if "stage" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN stage VARCHAR(32) DEFAULT 'local'"))
        if "requested_mode" not in cols:
            conn.execute(
                text("ALTER TABLE jobs ADD COLUMN requested_mode VARCHAR(16) DEFAULT 'mutate'")
            )
        if "allow_mutations" not in cols:
            conn.execute(
                text("ALTER TABLE jobs ADD COLUMN allow_mutations BOOLEAN DEFAULT 1")
            )
        if "allow_stage_skip" not in cols:
            conn.execute(
                text("ALTER TABLE jobs ADD COLUMN allow_stage_skip BOOLEAN DEFAULT 0")
            )
        run_rows = conn.execute(text("PRAGMA table_info(run_records)")).fetchall()
        run_cols = {row[1] for row in run_rows}
        if "failure_category" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN failure_category VARCHAR(32)"))
        if "diagnostic_code" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN diagnostic_code VARCHAR(64)"))
        if "retryable" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN retryable BOOLEAN DEFAULT 0"))
        if "orchestrator_run_id" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN orchestrator_run_id VARCHAR(64)"))
        if "orchestrator_status" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN orchestrator_status VARCHAR(32)"))
        if "orchestrator_artifact" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN orchestrator_artifact VARCHAR(1024)"))
        if "notification_status" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN notification_status VARCHAR(16) DEFAULT 'skipped'"))
        if "notification_error" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN notification_error TEXT"))
        if "notification_sent_at" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN notification_sent_at DATETIME"))
        if "notification_recipient" not in run_cols:
            conn.execute(text("ALTER TABLE run_records ADD COLUMN notification_recipient VARCHAR(320)"))

        try:
            config_rows = conn.execute(text("PRAGMA table_info(app_config)")).fetchall()
            config_cols = {row[1] for row in config_rows}
        except Exception:
            config_cols = set()

        if config_cols:
            if "auth_mode" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN auth_mode VARCHAR(32) DEFAULT 'chatgpt_account'"))
            if "default_cloud_env_id" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN default_cloud_env_id VARCHAR(128)"))
            if "last_connection_status" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN last_connection_status VARCHAR(32)"))
            if "last_connection_message" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN last_connection_message TEXT"))
            if "auth_rate_limited_until" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN auth_rate_limited_until DATETIME"))
            if "auth_rate_limit_hits" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN auth_rate_limit_hits INTEGER DEFAULT 0"))
            if "smtp_host" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN smtp_host VARCHAR(255)"))
            if "smtp_port" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN smtp_port INTEGER DEFAULT 587"))
            if "smtp_security" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN smtp_security VARCHAR(16) DEFAULT 'starttls'"))
            if "smtp_username" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN smtp_username VARCHAR(255)"))
            if "smtp_from_email" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN smtp_from_email VARCHAR(320)"))
            if "smtp_password_secret_ref" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN smtp_password_secret_ref VARCHAR(256)"))
            if "notifications_enabled" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN notifications_enabled BOOLEAN DEFAULT 1"))
            if "default_notification_to" not in config_cols:
                conn.execute(text("ALTER TABLE app_config ADD COLUMN default_notification_to VARCHAR(320)"))
