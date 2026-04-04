from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="exec")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="cron")
    cron_expr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sandbox: Mapped[str] = mapped_column(String(32), nullable=False, default="read-only")
    repo_slug: Mapped[str] = mapped_column(String(120), nullable=False, default="substrate-core")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    requested_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mutate")
    allow_mutations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_stage_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    working_directory: Mapped[str] = mapped_column(String(512), nullable=False, default=".")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    cloud_env_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    codex_args: Mapped[str | None] = mapped_column(Text, nullable=True)
    env_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notify_email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_email_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    runs: Mapped[list["RunRecord"]] = relationship("RunRecord", back_populates="job", cascade="all, delete-orphan")


class RunRecord(Base):
    __tablename__ = "run_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stdout_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    stderr_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    diagnostic_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orchestrator_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    orchestrator_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    orchestrator_artifact: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="skipped")
    notification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_recipient: Mapped[str | None] = mapped_column(String(320), nullable=True)

    job: Mapped[Job] = relationship("Job", back_populates="runs")


class AppConfig(Base):
    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    codex_executable: Mapped[str] = mapped_column(String(512), nullable=False, default="codex")
    codex_home: Mapped[str | None] = mapped_column(String(512), nullable=True)
    default_working_directory: Mapped[str] = mapped_column(String(512), nullable=False, default=".")
    default_cloud_env_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key_env_var: Mapped[str] = mapped_column(String(128), nullable=False, default="OPENAI_API_KEY")
    api_key_secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    global_env_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployment_task_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deployment_host: Mapped[str] = mapped_column(String(64), nullable=False, default="127.0.0.1")
    deployment_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8787)
    deployment_user: Mapped[str | None] = mapped_column(String(256), nullable=True)
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="chatgpt_account")
    last_connection_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_connection_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auth_rate_limit_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_security: Mapped[str] = mapped_column(String(16), nullable=False, default="starttls")
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    smtp_password_secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_notification_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
