from __future__ import annotations

from datetime import datetime
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: str = Field(default="exec")
    enabled: bool = True
    schedule_type: str = Field(default="cron")
    cron_expr: str | None = None
    interval_minutes: int | None = None
    prompt: str = Field(min_length=1)
    sandbox: str = "read-only"
    repo_slug: str = Field(default="substrate-core", min_length=1, max_length=120)
    stage: str = Field(default="local")
    requested_mode: str = Field(default="mutate")
    allow_mutations: bool = True
    allow_stage_skip: bool = False
    working_directory: str = "."
    timeout_seconds: int = Field(default=1800, ge=30, le=86400)
    cloud_env_id: str | None = None
    attempts: int = Field(default=1, ge=1, le=4)
    codex_args: str | None = None
    env_json: str | None = None
    notify_email_enabled: bool = False
    notify_email_to: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def validate_schedule(self) -> "JobBase":
        if self.schedule_type == "cron" and not self.cron_expr:
            raise ValueError("cron_expr is required for cron schedules.")
        if self.schedule_type == "interval" and not self.interval_minutes:
            raise ValueError("interval_minutes is required for interval schedules.")
        if self.schedule_type not in {"cron", "interval"}:
            raise ValueError("schedule_type must be cron or interval.")
        if self.mode not in {"exec", "cloud_exec"}:
            raise ValueError("mode must be exec or cloud_exec.")
        if self.requested_mode not in {"observe", "mutate"}:
            raise ValueError("requested_mode must be observe or mutate.")
        if self.stage not in {"local", "hosted_dev", "production"}:
            raise ValueError("stage must be local, hosted_dev, or production.")
        if self.env_json:
            try:
                parsed_env = json.loads(self.env_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"env_json must be valid JSON object: {exc}") from exc
            if not isinstance(parsed_env, dict):
                raise ValueError("env_json must be a JSON object.")
        if self.codex_args:
            try:
                parsed_args = json.loads(self.codex_args)
                if not isinstance(parsed_args, list):
                    raise ValueError("codex_args JSON must be an array.")
            except json.JSONDecodeError:
                pass
        return self


class JobCreate(JobBase):
    pass


class JobUpdate(JobBase):
    pass


class JobOut(JobBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RunOut(BaseModel):
    id: int
    job_id: int
    status: str
    return_code: int | None
    command: str
    started_at: datetime
    finished_at: datetime | None
    stdout_path: str | None
    stderr_path: str | None
    metadata_path: str | None
    message: str | None
    failure_category: str | None = None
    diagnostic_code: str | None = None
    retryable: bool = False
    orchestrator_run_id: str | None = None
    orchestrator_status: str | None = None
    orchestrator_artifact: str | None = None
    notification_status: str | None = "skipped"
    notification_error: str | None = None
    notification_sent_at: datetime | None = None
    notification_recipient: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    codex_executable: str = "codex"
    codex_home: str | None = None
    default_working_directory: str = "."
    default_cloud_env_id: str | None = None
    api_key_env_var: str = "OPENAI_API_KEY"
    global_env_json: str | None = None
    deployment_task_name: str | None = None
    deployment_host: str = "127.0.0.1"
    deployment_port: int = Field(default=8787, ge=1, le=65535)
    deployment_user: str | None = None
    auth_mode: str = "chatgpt_account"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: str = "starttls"
    smtp_username: str | None = None
    smtp_from_email: str | None = None
    notifications_enabled: bool = True
    default_notification_to: str | None = Field(default="adarnell@concepts2code.com", max_length=320)

    @model_validator(mode="after")
    def validate_auth_mode(self) -> "SettingsUpdate":
        if self.auth_mode not in {"chatgpt_account", "api_key"}:
            raise ValueError("auth_mode must be chatgpt_account or api_key.")
        if self.smtp_security not in {"starttls", "ssl", "none"}:
            raise ValueError("smtp_security must be starttls, ssl, or none.")
        return self


class SettingsOut(SettingsUpdate):
    api_key_configured: bool = False
    smtp_password_configured: bool = False
    last_connection_status: str | None = None
    last_connection_message: str | None = None
    auth_rate_limited_until: datetime | None = None
    auth_rate_limit_hits: int = 0


class ApiKeyPayload(BaseModel):
    api_key: str = Field(min_length=10)


class SmtpPasswordPayload(BaseModel):
    password: str = Field(min_length=1)


class DeploymentInstallPayload(BaseModel):
    task_name: str = Field(min_length=1, max_length=128)
    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    python_path: str = "python"
    user: str = Field(min_length=1)
    logon_type: str = "interactive"
    password: str | None = None
    run_level: str = "limited"
    codex_scheduler_db: str | None = None
    codex_scheduler_disable_autostart: bool = False


class ConnectionModePayload(BaseModel):
    auth_mode: str


class ConnectionStatusOut(BaseModel):
    installed: bool
    resolved_executable: str | None = None
    version: str | None = None
    auth_file_exists: bool
    auth_file_path: str
    error: str | None = None
    auth_mode: str
    api_key_configured: bool
    rate_limited: bool = False
    retry_after_seconds: int = 0
    rate_limited_until: datetime | None = None


class DeviceAuthStartOut(BaseModel):
    ok: bool
    verification_url: str | None = None
    user_code: str | None = None
    raw_output: str | None = None
    error: str | None = None
    rate_limited: bool = False
    retry_after_seconds: int | None = None


class PreflightCheckOut(BaseModel):
    name: str
    status: str
    detail: str


class PreflightOut(BaseModel):
    status: str
    checks: list[PreflightCheckOut]


class CloudActionOut(BaseModel):
    action: str
    label: str


class NotificationActionOut(BaseModel):
    action: str
    label: str


class NotificationReadinessOut(BaseModel):
    ready: bool
    category: str | None = None
    summary: str
    actions: list[NotificationActionOut] = Field(default_factory=list)


class NotificationTestPayload(BaseModel):
    recipient: str | None = Field(default=None, max_length=320)


class NotificationTestOut(BaseModel):
    ok: bool
    category: str | None = None
    summary: str
    recipient: str | None = None


class SystemRuntimeOut(BaseModel):
    mode: str
    channel: str
    version: str
    update_capable: bool = False
    bundled_codex_cli: bool = False
    data_dir: str | None = None
    packaged_backend_status: str = "unavailable"
    diagnostic_code: str | None = None


class SystemUpdateStatusOut(BaseModel):
    channel: str
    enabled: bool = False
    update_base_url: str | None = None
    last_check_at: str | None = None
    last_result: str | None = None
    last_error: str | None = None


class CloudTargetOut(BaseModel):
    id: str
    label: str
    repo: str | None = None
    detail: str | None = None
    is_recommended: bool = False


class CloudTargetsOut(BaseModel):
    ok: bool = True
    category: str | None = None
    summary: str | None = None
    targets: list[CloudTargetOut] = Field(default_factory=list)


class CloudReadinessOut(BaseModel):
    ready: bool
    category: str | None = None
    summary: str
    retryable: bool = False
    diagnostic_code: str | None = None
    env_source: str | None = None
    resolved_cloud_env_id: str | None = None
    actions: list[CloudActionOut] = Field(default_factory=list)
