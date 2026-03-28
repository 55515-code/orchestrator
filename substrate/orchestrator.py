from __future__ import annotations

import json
import os
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml
from langchain_core.prompts import ChatPromptTemplate

from .environment import platform_key
from .learning import record_execution
from .reliability import (
    CheckpointStore,
    ExecutionTarget,
    IdempotencyStore,
    ProviderFailoverHook,
    RetryPolicy,
    TaskLifecycleState,
    classify_failure,
    decide_restart_action,
    execute_with_retry,
    make_idempotency_key,
)
from .registry import SubstrateRuntime
from .resource_orchestration import (
    ElasticScaleHooks,
    WorkloadPressure,
    WorkloadRequest,
    scheduler_from_chain_defaults,
)
from .research import run_openclaw_research_assist, source_facts_ready


_BOUNDED_VALIDATION_HINTS = (
    "probe",
    "hardware",
    "stress",
    "benchmark",
    "validate",
    "validation",
)


def _build_model(provider: str, model: str):
    if provider == "local":
        pass  # using local router

        return None  # delegated to local roo-router
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=0)
    if provider == "mock":
        return None
    raise ValueError(f"Unsupported provider: {provider}")


def _render_prompt(template_path: Path, state: dict[str, Any]) -> str:
    prompt_template = ChatPromptTemplate.from_template(
        template_path.read_text(encoding="utf-8")
    )
    outputs = state.get("outputs", {})
    previous_outputs = "\n\n".join(
        f"### {step_id}\n{content}" for step_id, content in outputs.items()
    ).strip()
    return prompt_template.format(
        objective=state.get("objective", ""),
        context=state.get("context", ""),
        previous_outputs=previous_outputs or "(none yet)",
        outputs_json=json.dumps(outputs, indent=2, ensure_ascii=False),
    )


def _read_context(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        if path.suffix not in {".md", ".txt", ".yaml", ".yml", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        chunks.append(f"## {path}\n\n{text}")
    return "\n\n".join(chunks).strip()


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round(0.95 * (len(ordered) - 1)))
    return float(ordered[index])


class Orchestrator:
    def __init__(
        self,
        runtime: SubstrateRuntime,
        *,
        scale_hooks: ElasticScaleHooks | None = None,
    ) -> None:
        self.runtime = runtime
        reliability_root = self.runtime.paths["memory"] / "reliability"
        self._checkpoint_store = CheckpointStore(reliability_root / "checkpoints")
        self._idempotency_store = IdempotencyStore(reliability_root / "idempotency")
        self._scale_hooks = scale_hooks or ElasticScaleHooks()

    def _new_run_id(self) -> str:
        return uuid.uuid4().hex

    def _assert_mutation_policy(self, mode: str) -> None:
        if mode != "mutate":
            return
        if self.runtime.workspace.policy.require_source_facts_before_mutation:
            if not source_facts_ready(self.runtime):
                raise PermissionError(
                    "Mutation mode blocked: refresh upstream source facts first."
                )

    def _assert_stage_policy(
        self, *, repo_slug: str, stage: str, allow_stage_skip: bool
    ) -> None:
        stage_sequence = self.runtime.workspace.policy.stage_sequence
        if stage not in stage_sequence:
            raise ValueError(
                f"Stage '{stage}' is not allowed. Expected one of {stage_sequence}."
            )
        if allow_stage_skip or not self.runtime.workspace.policy.enforce_stage_flow:
            return
        index = stage_sequence.index(stage)
        if index == 0:
            return
        prerequisite = stage_sequence[index - 1]
        if not self.runtime.db.has_successful_stage(repo_slug, prerequisite):
            raise PermissionError(
                f"Stage '{stage}' requires a successful '{prerequisite}' run first. "
                "Use --allow-stage-skip to bypass."
            )

    def _chain_retry_policy(self, defaults: dict[str, Any]) -> RetryPolicy:
        raw_retry = defaults.get("retry_policy", {})
        if not isinstance(raw_retry, dict):
            raw_retry = {}
        return RetryPolicy(
            max_attempts=int(raw_retry.get("max_attempts", 3)),
            base_delay_seconds=float(raw_retry.get("base_delay_seconds", 0.5)),
            max_delay_seconds=float(raw_retry.get("max_delay_seconds", 8.0)),
            jitter_ratio=float(raw_retry.get("jitter_ratio", 0.2)),
        )

    def _chain_failover_hook(
        self,
        defaults: dict[str, Any],
        *,
        primary_provider: str,
        primary_model: str,
        models: dict[str, Any],
        allow_terminal_failover: bool,
    ) -> ProviderFailoverHook:
        raw_order = defaults.get("failover_order", defaults.get("fallback_order", []))
        fallback_order: list[str] = []
        if isinstance(raw_order, list):
            fallback_order = [
                str(provider)
                for provider in raw_order
                if isinstance(provider, str) and provider.strip()
            ]
        if not fallback_order:
            fallback_order = [
                provider
                for provider in ["local", "anthropic", "ollama", "mock"]
                if provider != primary_provider
            ]

        provider_models = {
            str(provider): str(model)
            for provider, model in models.items()
            if isinstance(provider, str) and isinstance(model, str)
        }
        provider_models.setdefault(primary_provider, primary_model)
        provider_models.setdefault("mock", "mock-model")

        return ProviderFailoverHook(
            fallback_order=fallback_order,
            provider_models=provider_models,
            allow_terminal_failover=allow_terminal_failover,
        )

    def _message_to_text(self, message: Any) -> str:
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content
        return json.dumps(content, indent=2, ensure_ascii=False)

    def _is_bounded_validation_task(
        self,
        *,
        task_id: str,
        description: str,
        command: list[str],
    ) -> bool:
        policy = self.runtime.workspace.policy
        if not policy.rc1_bounded_validation_enabled:
            return False
        haystack = " ".join([task_id, description, *command]).lower()
        return any(hint in haystack for hint in _BOUNDED_VALIDATION_HINTS)

    def _run_optional_openclaw_side_lane(
        self,
        *,
        run_id: str,
        stage: str,
        pass_name: str,
        objective: str,
        context: str,
        manual_trigger: bool,
        data_class: str,
    ) -> tuple[str | None, dict[str, Any]]:
        result = run_openclaw_research_assist(
            self.runtime,
            run_id=run_id,
            stage=stage,
            pass_name=pass_name,
            objective=objective,
            context=context,
            manual_trigger=manual_trigger,
            data_class=data_class,
        )
        status = str(result.get("status") or "unknown")
        event_payload = {
            "status": status,
            "pass_name": pass_name,
            "stage": stage,
            "manual_trigger": manual_trigger,
            "data_class": data_class,
            "reason": result.get("reason"),
            "raw_artifact": result.get("raw_artifact"),
            "vetting_report_artifact": result.get("vetting_report_artifact"),
            "vetted_artifact": result.get("vetted_artifact"),
            "rejected_artifact": result.get("rejected_artifact"),
            "imported_insight_count": len(result.get("imported_insights") or []),
            "imported_insights": list(result.get("imported_insights") or [])[:5],
            "adoption_policy": "learn_and_adapt_never_trust_or_copy",
        }
        level = "info"
        if status in {"rejected", "blocked"}:
            level = "warning"
        elif status.startswith("degraded"):
            level = "warning"
        self.runtime.db.add_event(
            run_id=run_id,
            level=level,
            message=f"OpenClaw side-lane outcome ({status})",
            payload=event_payload,
        )
        if status == "accepted":
            insight_markdown = str(result.get("insight_markdown") or "").strip()
            if insight_markdown:
                return (
                    (
                        "## openclaw_internal_research_insights\n\n"
                        "Security mode: learn-and-adapt, never trust-or-copy.\n"
                        "Insights below are internally re-articulated and vetted.\n\n"
                        f"{insight_markdown}"
                    ).strip(),
                    result,
                )
        return None, result

    def _invoke_provider_with_recovery(
        self,
        *,
        run_id: str,
        stage: str,
        step_id: str,
        rendered_prompt: str,
        retry_policy: RetryPolicy,
        failover_hook: ProviderFailoverHook,
        idempotency_key: str,
        initial_target: ExecutionTarget,
    ) -> tuple[str, ExecutionTarget]:
        current_target = initial_target
        failover_attempt = 0
        while True:
            try:

                def _invoke() -> str:
                    llm = _build_model(current_target.provider, current_target.model)
                    if llm is None:
                        raise RuntimeError(
                            "Mock provider is not allowed for resilient provider invocation."
                        )
                    message = llm.invoke(rendered_prompt)
                    return self._message_to_text(message)

                response = execute_with_retry(
                    _invoke,
                    policy=retry_policy,
                    on_retry=lambda event: self.runtime.db.add_event(
                        run_id=run_id,
                        level="warning",
                        message=(
                            f"Retrying step '{step_id}' "
                            f"(attempt {event.attempt}/{event.max_attempts})"
                        ),
                        payload={
                            "step": step_id,
                            "attempt": event.attempt,
                            "max_attempts": event.max_attempts,
                            "delay_seconds": round(event.delay_seconds, 3),
                            "failure_kind": event.classification.kind,
                            "failure_reason": event.classification.reason,
                            "provider": current_target.provider,
                            "model": current_target.model,
                            "idempotency_key": idempotency_key,
                            "error": str(event.error),
                        },
                    ),
                )
                return response, current_target
            except Exception as exc:  # noqa: BLE001
                failure = classify_failure(exc)
                self._checkpoint_store.create_checkpoint(
                    run_id=run_id,
                    scope="recovery",
                    status="provider_failure",
                    stage=stage,
                    step_id=step_id,
                    idempotency_key=idempotency_key,
                    payload={
                        "provider": current_target.provider,
                        "model": current_target.model,
                        "failure_kind": failure.kind,
                        "failure_reason": failure.reason,
                        "error": str(exc),
                        "failover_attempt": failover_attempt,
                    },
                )
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="error",
                    message=(
                        f"Provider '{current_target.provider}' failed for step '{step_id}'."
                    ),
                    payload={
                        "step": step_id,
                        "provider": current_target.provider,
                        "model": current_target.model,
                        "failure_kind": failure.kind,
                        "failure_reason": failure.reason,
                        "error": str(exc),
                    },
                )
                next_target = failover_hook.next_target(
                    run_id=run_id,
                    step_id=step_id,
                    attempt=failover_attempt + 1,
                    current=current_target,
                    failure=failure,
                    error=exc,
                )
                if next_target is None:
                    raise
                failover_attempt += 1
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="warning",
                    message=f"Failover for step '{step_id}'",
                    payload={
                        "step": step_id,
                        "from_provider": current_target.provider,
                        "from_model": current_target.model,
                        "to_provider": next_target.provider,
                        "to_model": next_target.model,
                        "failover_attempt": failover_attempt,
                        "idempotency_key": idempotency_key,
                    },
                )
                current_target = next_target

    def _record_task_lifecycle_transition(
        self,
        *,
        run_id: str,
        stage: str,
        task_id: str,
        idempotency_key: str,
        state: TaskLifecycleState,
        transition_index: int,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        next_index = transition_index + 1
        transition_payload: dict[str, Any] = {
            "task": task_id,
            "state": state,
            "reason": reason,
            "transition_index": next_index,
        }
        if payload:
            transition_payload.update(payload)
        self.runtime.db.add_event(
            run_id=run_id,
            level="info",
            message=f"Task lifecycle transitioned to '{state}'",
            payload=transition_payload,
        )
        self._checkpoint_store.create_checkpoint(
            run_id=run_id,
            scope="recovery",
            status=f"task_state_{state}",
            stage=stage,
            step_id=task_id,
            idempotency_key=idempotency_key,
            payload=transition_payload,
        )
        return next_index

    def _run_with_watchdog(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float | None,
        heartbeat_timeout_seconds: float,
        stuck_confirmation_seconds: float,
        poll_interval_seconds: float,
        terminate_grace_seconds: float,
        on_transition: Any | None = None,
    ) -> dict[str, Any]:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        started_at = time.monotonic()
        suspect_since: float | None = None

        while True:
            elapsed = max(0.0, time.monotonic() - started_at)
            if timeout_seconds is not None and elapsed >= timeout_seconds:
                process.terminate()
                forced_kill = False
                try:
                    stdout, stderr = process.communicate(timeout=terminate_grace_seconds)
                except subprocess.TimeoutExpired:
                    forced_kill = True
                    process.kill()
                    stdout, stderr = process.communicate()
                timeout_error = subprocess.TimeoutExpired(
                    cmd=command,
                    timeout=timeout_seconds,
                    output=stdout,
                    stderr=stderr,
                )
                return {
                    "completed": None,
                    "timeout_error": timeout_error,
                    "stuck_detected": False,
                    "forced_kill": forced_kill,
                    "elapsed_seconds": elapsed,
                }

            wait_timeout = poll_interval_seconds
            if timeout_seconds is not None:
                remaining = max(0.01, timeout_seconds - elapsed)
                wait_timeout = min(wait_timeout, remaining)

            try:
                stdout, stderr = process.communicate(timeout=wait_timeout)
                return {
                    "completed": subprocess.CompletedProcess(
                        command,
                        process.returncode if process.returncode is not None else 1,
                        stdout=stdout or "",
                        stderr=stderr or "",
                    ),
                    "timeout_error": None,
                    "stuck_detected": False,
                    "forced_kill": False,
                    "elapsed_seconds": max(0.0, time.monotonic() - started_at),
                }
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                elapsed = max(0.0, now - started_at)
                if elapsed < heartbeat_timeout_seconds:
                    continue

                if suspect_since is None:
                    suspect_since = now
                    if on_transition is not None:
                        on_transition(
                            "suspect_stuck",
                            "heartbeat_timeout",
                            {
                                "elapsed_seconds": round(elapsed, 3),
                                "heartbeat_timeout_seconds": heartbeat_timeout_seconds,
                            },
                        )
                    continue

                suspect_elapsed = max(0.0, now - suspect_since)
                if suspect_elapsed < stuck_confirmation_seconds:
                    continue

                if on_transition is not None:
                    on_transition(
                        "stuck_confirmed",
                        "stuck_confirmation_elapsed",
                        {
                            "elapsed_seconds": round(elapsed, 3),
                            "suspect_seconds": round(suspect_elapsed, 3),
                            "stuck_confirmation_seconds": stuck_confirmation_seconds,
                        },
                    )
                    on_transition(
                        "terminate_requested",
                        "watchdog_terminate_requested",
                        {"terminate_grace_seconds": terminate_grace_seconds},
                    )

                process.terminate()
                forced_kill = False
                try:
                    stdout, stderr = process.communicate(timeout=terminate_grace_seconds)
                except subprocess.TimeoutExpired:
                    forced_kill = True
                    process.kill()
                    stdout, stderr = process.communicate()

                if on_transition is not None:
                    on_transition(
                        "terminated",
                        "watchdog_terminated",
                        {"forced_kill": forced_kill},
                    )

                timeout_error = subprocess.TimeoutExpired(
                    cmd=command,
                    timeout=elapsed,
                    output=stdout,
                    stderr=stderr,
                )
                return {
                    "completed": None,
                    "timeout_error": timeout_error,
                    "stuck_detected": True,
                    "forced_kill": forced_kill,
                    "elapsed_seconds": elapsed,
                }

    def run_chain(
        self,
        *,
        repo_slug: str,
        objective: str,
        chain_path: str = "chains/local-agent-chain.yaml",
        provider: str | None = None,
        model: str | None = None,
        dry_run: bool = False,
        stage: str = "local",
        requested_mode: str | None = None,
        allow_mutations: bool = False,
        allow_stage_skip: bool = False,
        extra_context_files: list[str] | None = None,
        openclaw_manual_trigger: bool = False,
        openclaw_data_class: str = "synthetic",
        run_id: str | None = None,
    ) -> str:
        repo = self.runtime.resolve_repo(repo_slug)
        self._assert_stage_policy(
            repo_slug=repo_slug, stage=stage, allow_stage_skip=allow_stage_skip
        )
        mode = self.runtime.effective_mode(
            requested_mode=requested_mode, repo=repo, allow_mutations=allow_mutations
        )
        self._assert_mutation_policy(mode)

        run_id = run_id or self._new_run_id()
        chain_file = (self.runtime.root / chain_path).resolve()
        cfg = yaml.safe_load(chain_file.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict) or "steps" not in cfg:
            raise ValueError(f"Invalid chain config: {chain_file}")

        defaults = cfg.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
        models = defaults.get("models", {})
        if not isinstance(models, dict):
            models = {}
        provider_name = provider or defaults.get("provider", "mock")
        model_name = model or models.get(provider_name, "mock-model")
        retry_policy = self._chain_retry_policy(defaults)
        raw_retry = defaults.get("retry_policy", {})
        if not isinstance(raw_retry, dict):
            raw_retry = {}
        failover_hook = self._chain_failover_hook(
            defaults,
            primary_provider=provider_name,
            primary_model=model_name,
            models=models,
            allow_terminal_failover=bool(raw_retry.get("allow_terminal_failover", False)),
        )
        scheduler = scheduler_from_chain_defaults(
            defaults=defaults,
            primary_target=ExecutionTarget(provider=provider_name, model=model_name),
            provider_models=failover_hook.provider_models,
            failover_order=failover_hook.fallback_order,
            scale_hooks=self._scale_hooks,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_dir = self.runtime.paths["memory"] / "runs" / f"{timestamp}-{run_id[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)
        chain_command = [
            "run-chain",
            f"--repo={repo_slug}",
            f"--chain={chain_path}",
            f"--stage={stage}",
            f"--provider={provider_name}",
            f"--model={model_name}",
            f"--dry-run={str(dry_run).lower()}",
            f"--mode={mode}",
            f"--openclaw-manual-trigger={str(openclaw_manual_trigger).lower()}",
            f"--openclaw-data-class={openclaw_data_class}",
        ]

        self.runtime.db.create_run(
            run_id=run_id,
            run_type="chain",
            repo_slug=repo_slug,
            task_id=None,
            objective=objective,
            stage=stage,
            mode=mode,
            provider=provider_name,
            model=model_name,
            chain_path=str(chain_file),
            metadata={
                "dry_run": dry_run,
                "environment_tags": self.runtime.environment.tags,
                "pass_sequence": self.runtime.workspace.policy.pass_sequence,
                "reliability": {
                    "retry_policy": {
                        "max_attempts": retry_policy.max_attempts,
                        "base_delay_seconds": retry_policy.base_delay_seconds,
                        "max_delay_seconds": retry_policy.max_delay_seconds,
                        "jitter_ratio": retry_policy.jitter_ratio,
                    },
                    "failover_order": list(failover_hook.fallback_order),
                },
                "resource_orchestration": scheduler.snapshot(),
                "openclaw": {
                    "manual_trigger": openclaw_manual_trigger,
                    "data_class": openclaw_data_class,
                    "enabled": self.runtime.workspace.policy.rc1_openclaw_internal_assist_enabled,
                },
            },
        )

        context_paths = [
            self.runtime.root / str(p) for p in cfg.get("context_files", [])
        ]
        if extra_context_files:
            context_paths.extend((self.runtime.root / p) for p in extra_context_files)
        context = _read_context(context_paths)
        repo_snapshot = self.runtime.inspect_repository(repo)
        context = (
            f"{context}\n\n## repository_snapshot\n\n"
            f"```json\n{json.dumps(repo_snapshot, indent=2, ensure_ascii=False)}\n```"
        ).strip()

        try:
            steps = cfg["steps"]
            for index, step in enumerate(steps, start=1):
                step.setdefault("order", index)
                if "id" not in step or "prompt" not in step:
                    raise ValueError("Each step must include 'id' and 'prompt'.")

            outputs: dict[str, str] = {}
            step_execution_targets: dict[str, dict[str, str]] = {}
            step_resource_decisions: dict[str, dict[str, Any]] = {}
            step_durations_seconds: list[float] = []
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="started",
                stage=stage,
                payload={
                    "repo_slug": repo_slug,
                    "chain_path": str(chain_file),
                    "provider": provider_name,
                    "model": model_name,
                },
            )
            self.runtime.db.add_event(
                run_id=run_id,
                level="info",
                message="Three-pass workflow loaded",
                payload={
                    "stage": stage,
                    "passes": self.runtime.workspace.policy.pass_sequence,
                },
            )
            self.runtime.db.add_event(
                run_id=run_id,
                level="info",
                message="Reliability policy attached",
                payload={
                    "retry_policy": {
                        "max_attempts": retry_policy.max_attempts,
                        "base_delay_seconds": retry_policy.base_delay_seconds,
                        "max_delay_seconds": retry_policy.max_delay_seconds,
                        "jitter_ratio": retry_policy.jitter_ratio,
                    },
                    "failover_order": list(failover_hook.fallback_order),
                },
            )
            self.runtime.db.add_event(
                run_id=run_id,
                level="info",
                message="Resource scheduling policy attached",
                payload=scheduler.snapshot(),
            )
            if openclaw_manual_trigger:
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="info",
                    message="OpenClaw manual trigger requested",
                    payload={
                        "stage": stage,
                        "requested_data_class": openclaw_data_class,
                        "policy_enabled": self.runtime.workspace.policy.rc1_openclaw_internal_assist_enabled,
                    },
                )
            for step_index, step in enumerate(steps, start=1):
                step_id = str(step["id"])
                step_order = int(step.get("order", 0))
                prompt_path = (self.runtime.root / str(step["prompt"])).resolve()
                output_path = run_dir / f"{step_order:02d}_{step_id}.md"
                idempotency_key = make_idempotency_key(
                    run_id,
                    "chain-step",
                    stage,
                    str(step_order),
                    step_id,
                )
                self._idempotency_store.begin(
                    run_id,
                    idempotency_key,
                    payload={"step": step_id, "stage": stage, "order": step_order},
                )

                if self._idempotency_store.is_completed(run_id, idempotency_key):
                    recovered_response: str | None = None
                    recovered_artifact: Path | None = None
                    idempotency_record = self._idempotency_store.get(
                        run_id, idempotency_key
                    )
                    recovered_provider = provider_name
                    recovered_model = model_name
                    if idempotency_record is not None:
                        payload_provider = idempotency_record.payload.get("provider")
                        payload_model = idempotency_record.payload.get("model")
                        if isinstance(payload_provider, str) and payload_provider:
                            recovered_provider = payload_provider
                        if isinstance(payload_model, str) and payload_model:
                            recovered_model = payload_model

                        payload_artifact = idempotency_record.payload.get("artifact")
                        if isinstance(payload_artifact, str) and payload_artifact:
                            recovered_artifact = Path(payload_artifact)

                    if output_path.exists():
                        recovered_response = output_path.read_text(encoding="utf-8")
                        recovered_artifact = output_path
                    else:
                        if recovered_artifact is not None and recovered_artifact.exists():
                            recovered_response = recovered_artifact.read_text(
                                encoding="utf-8"
                            )
                        checkpoint = self._checkpoint_store.latest_checkpoint(
                            run_id,
                            scope="step",
                            step_id=step_id,
                        )
                        artifact = None
                        if checkpoint is not None:
                            raw_artifact = checkpoint.payload.get("artifact")
                            if isinstance(raw_artifact, str):
                                artifact = Path(raw_artifact)
                        if artifact is not None and artifact.exists():
                            recovered_response = artifact.read_text(encoding="utf-8")
                            recovered_artifact = artifact

                    if recovered_response is not None:
                        output_path.write_text(recovered_response, encoding="utf-8")
                        recovered_artifact = output_path
                        outputs[step_id] = recovered_response
                        step_execution_targets[step_id] = {
                            "provider": recovered_provider,
                            "model": recovered_model,
                        }
                        step_resource_decisions[step_id] = {
                            "recovered": True,
                            "execution_target": {
                                "provider": recovered_provider,
                                "model": recovered_model,
                            },
                        }
                        self.runtime.db.add_event(
                            run_id=run_id,
                            level="info",
                            message=(
                                f"Recovered step '{step_id}' from idempotent state."
                            ),
                            payload={
                                "step": step_id,
                                "idempotency_key": idempotency_key,
                                "artifact": str(recovered_artifact or output_path),
                                "provider": recovered_provider,
                                "model": recovered_model,
                            },
                        )
                        continue

                    self.runtime.db.add_event(
                        run_id=run_id,
                        level="warning",
                        message=(
                            f"Idempotency key exists for step '{step_id}' but "
                            "artifact was unavailable; replaying step."
                        ),
                        payload={
                            "step": step_id,
                            "idempotency_key": idempotency_key,
                        },
                    )
                    self._checkpoint_store.create_checkpoint(
                        run_id=run_id,
                        scope="recovery",
                        status="replay_without_artifact",
                        stage=stage,
                        step_id=step_id,
                        idempotency_key=idempotency_key,
                    )

                step_started_at = perf_counter()
                scheduled_pool_name: str | None = None
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="info",
                    message=f"Starting step '{step_id}'",
                    payload={"step": step_id},
                )
                try:
                    self._checkpoint_store.create_checkpoint(
                        run_id=run_id,
                        scope="step",
                        status="started",
                        stage=stage,
                        step_id=step_id,
                        idempotency_key=idempotency_key,
                        payload={"order": step_order, "prompt": str(prompt_path)},
                    )
                    rendered_prompt = _render_prompt(
                        prompt_path,
                        {"objective": objective, "context": context, "outputs": outputs},
                    )
                    pass_name = str(step.get("pass") or step_id).strip().lower()
                    should_attempt_openclaw = bool(openclaw_manual_trigger)
                    if (
                        pass_name == "research"
                        and should_attempt_openclaw
                    ):
                        openclaw_context = (
                            f"Objective:\n{objective}\n\n"
                            f"Step prompt:\n{rendered_prompt[:4000]}\n\n"
                            f"Repository snapshot:\n{json.dumps(repo_snapshot, ensure_ascii=False)}"
                        )
                        openclaw_insight, openclaw_result = self._run_optional_openclaw_side_lane(
                            run_id=run_id,
                            stage=stage,
                            pass_name=pass_name,
                            objective=objective,
                            context=openclaw_context,
                            manual_trigger=openclaw_manual_trigger,
                            data_class=openclaw_data_class,
                        )
                        if openclaw_insight:
                            rendered_prompt = (
                                f"{rendered_prompt}\n\n{openclaw_insight}"
                            ).strip()
                        self._checkpoint_store.create_checkpoint(
                            run_id=run_id,
                            scope="recovery",
                            status=f"openclaw_{str(openclaw_result.get('status') or 'unknown')}",
                            stage=stage,
                            step_id=step_id,
                            idempotency_key=idempotency_key,
                            payload={
                                "pass_name": pass_name,
                                "reason": openclaw_result.get("reason"),
                                "vetted_artifact": openclaw_result.get("vetted_artifact"),
                                "vetting_report_artifact": openclaw_result.get(
                                    "vetting_report_artifact"
                                ),
                                "raw_artifact": openclaw_result.get("raw_artifact"),
                            },
                        )
                    raw_capability = str(
                        step.get("capability")
                        or step.get("resource_class")
                        or scheduler.infer_capability_for_provider(provider_name)
                    ).strip()
                    capability = (
                        raw_capability
                        if raw_capability in {"cpu", "gpu", "model", "api"}
                        else scheduler.infer_capability_for_provider(provider_name)
                    )
                    safety_tier = (
                        "strict" if bool(step.get("strict_safety", False)) else "standard"
                    )
                    allow_degrade = bool(step.get("allow_degrade", True))
                    pressure = WorkloadPressure(
                        queue_depth=max(0, len(steps) - step_index),
                        p95_latency_seconds=_p95(step_durations_seconds),
                        in_flight=1,
                    )
                    schedule_decision = scheduler.schedule(
                        workload=WorkloadRequest(
                            workload_id=f"{run_id}:{step_id}",
                            capability=capability,
                            safety_tier=safety_tier,
                            allow_degrade=allow_degrade,
                        ),
                        pressure=pressure,
                    )
                    scheduled_pool_name = schedule_decision.pool_name
                    step_resource_decisions[step_id] = schedule_decision.to_dict()
                    self.runtime.db.add_event(
                        run_id=run_id,
                        level="info",
                        message=f"Scheduled step '{step_id}'",
                        payload={
                            "step": step_id,
                            "requested_capability": capability,
                            "safety_tier": safety_tier,
                            "allow_degrade": allow_degrade,
                            "pressure": {
                                "queue_depth": pressure.queue_depth,
                                "p95_latency_seconds": pressure.p95_latency_seconds,
                                "in_flight": pressure.in_flight,
                            },
                            "decision": schedule_decision.to_dict(),
                        },
                    )
                    effective_target = schedule_decision.execution_target
                    if dry_run or provider_name == "mock":
                        response = (
                            f"# Mock Response: {step_id}\n\n"
                            f"Provider: `{effective_target.provider}`\n"
                            f"Model: `{effective_target.model}`\n\n"
                            "Rendered prompt preview:\n\n"
                            f"{rendered_prompt[:4000]}"
                        )
                    else:
                        response, effective_target = self._invoke_provider_with_recovery(
                            run_id=run_id,
                            stage=stage,
                            step_id=step_id,
                            rendered_prompt=rendered_prompt,
                            retry_policy=retry_policy,
                            failover_hook=failover_hook,
                            idempotency_key=idempotency_key,
                            initial_target=effective_target,
                        )

                    output_path.write_text(response, encoding="utf-8")
                    outputs[step_id] = response
                    step_execution_targets[step_id] = {
                        "provider": effective_target.provider,
                        "model": effective_target.model,
                    }
                    self._idempotency_store.mark_completed(
                        run_id,
                        idempotency_key,
                        payload={
                            "artifact": str(output_path),
                            "provider": effective_target.provider,
                            "model": effective_target.model,
                        },
                    )
                    self._checkpoint_store.create_checkpoint(
                        run_id=run_id,
                        scope="step",
                        status="completed",
                        stage=stage,
                        step_id=step_id,
                        idempotency_key=idempotency_key,
                        payload={
                            "order": step_order,
                            "artifact": str(output_path),
                            "provider": effective_target.provider,
                            "model": effective_target.model,
                            "resource_pool": schedule_decision.pool_name,
                            "resource_capability": schedule_decision.pool_capability,
                            "resource_degraded": schedule_decision.degraded,
                            "resource_pressure": schedule_decision.pressure_level,
                        },
                    )
                    self.runtime.db.add_event(
                        run_id=run_id,
                        level="info",
                        message=f"Completed step '{step_id}'",
                        payload={
                            "step": step_id,
                            "artifact": str(output_path),
                            "idempotency_key": idempotency_key,
                            "provider": effective_target.provider,
                            "model": effective_target.model,
                            "resource_pool": schedule_decision.pool_name,
                            "resource_capability": schedule_decision.pool_capability,
                            "resource_degraded": schedule_decision.degraded,
                        },
                    )
                finally:
                    if scheduled_pool_name is not None:
                        scheduler.release(scheduled_pool_name)
                    elapsed = max(0.0, perf_counter() - step_started_at)
                    step_durations_seconds.append(elapsed)

            summary = {
                "chain": cfg.get("name", "unnamed-chain"),
                "description": cfg.get("description", ""),
                "provider": provider_name,
                "model": model_name,
                "dry_run": dry_run,
                "mode": mode,
                "stage": stage,
                "objective": objective,
                "repo_slug": repo_slug,
                "steps": [step["id"] for step in steps],
                "output_files": [
                    f"{step['order']:02d}_{step['id']}.md" for step in steps
                ],
                "step_execution_targets": step_execution_targets,
                "step_resource_decisions": step_resource_decisions,
                "resource_scheduler_final_state": scheduler.snapshot(),
                "final_output_step": steps[-1]["id"],
                "final_output_preview": outputs.get(steps[-1]["id"], "")[:800],
            }
            (run_dir / "run.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="completed",
                stage=stage,
                payload={
                    "artifact": str(run_dir / "run.json"),
                    "final_output_step": steps[-1]["id"],
                },
            )
            self.runtime.db.complete_run(
                run_id=run_id, status="success", run_dir=str(run_dir), exit_code=0
            )
            record_execution(
                self.runtime,
                run_type="chain",
                run_id=run_id,
                repo_slug=repo_slug,
                stage=stage,
                command=chain_command,
                status="success",
                exit_code=0,
                stdout=json.dumps(summary, ensure_ascii=False),
                artifact=str(run_dir),
            )
        except Exception as exc:  # noqa: BLE001
            self.runtime.db.add_event(
                run_id=run_id,
                level="error",
                message="Chain run failed.",
                payload={"error": str(exc), "traceback": traceback.format_exc()},
            )
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="failed",
                stage=stage,
                payload={"error": str(exc)},
            )
            self.runtime.db.complete_run(
                run_id=run_id,
                status="failed",
                run_dir=str(run_dir),
                exit_code=1,
                error_text=str(exc),
            )
            record_execution(
                self.runtime,
                run_type="chain",
                run_id=run_id,
                repo_slug=repo_slug,
                stage=stage,
                command=chain_command,
                status="failed",
                exit_code=1,
                stderr=f"{exc}\n{traceback.format_exc()}",
                artifact=str(run_dir),
            )
            raise

        return run_id

    def run_task(
        self,
        *,
        repo_slug: str,
        task_id: str,
        stage: str = "local",
        requested_mode: str | None = None,
        allow_mutations: bool = False,
        allow_stage_skip: bool = False,
        run_id: str | None = None,
    ) -> str:
        repo = self.runtime.resolve_repo(repo_slug)
        self._assert_stage_policy(
            repo_slug=repo_slug, stage=stage, allow_stage_skip=allow_stage_skip
        )
        if task_id not in repo.tasks:
            raise KeyError(f"Unknown task '{task_id}' for repo '{repo_slug}'.")
        task = repo.tasks[task_id]

        mode = self.runtime.effective_mode(
            requested_mode=requested_mode or task.mode,
            repo=repo,
            allow_mutations=allow_mutations,
        )
        if task.mode == "mutate" and mode != "mutate":
            raise PermissionError(
                f"Task '{task_id}' requires mutate mode. Re-run with --mode mutate."
            )
        self._assert_mutation_policy(mode)

        command = task.command_for_platform(platform_key())
        command = [os.path.expandvars(token) for token in command]
        policy = self.runtime.workspace.policy
        bounded_validation = self._is_bounded_validation_task(
            task_id=task_id,
            description=task.description,
            command=command,
        )
        watchdog_enabled = bool(
            bounded_validation and policy.rc1_watchdog_enabled
        )
        respawn_enabled = bool(watchdog_enabled and policy.rc1_respawn_enabled)
        bounded_validation_policy: dict[str, Any] | None = None
        if bounded_validation:
            bounded_validation_policy = {
                "enabled": bool(policy.rc1_bounded_validation_enabled),
                "hardware_probe_enabled": bool(policy.rc1_hardware_probe_enabled),
                "max_attempts": int(policy.rc1_validation_max_attempts),
                "attempt_timeout_seconds": int(
                    policy.rc1_validation_attempt_timeout_seconds
                ),
                "deadline_seconds": int(policy.rc1_validation_deadline_seconds),
                "watchdog_enabled": watchdog_enabled,
                "respawn_enabled": respawn_enabled,
                "watchdog_max_respawns": int(policy.rc1_watchdog_max_respawns),
                "watchdog_heartbeat_timeout_seconds": float(
                    policy.rc1_watchdog_heartbeat_timeout_seconds
                ),
                "watchdog_stuck_confirmation_seconds": float(
                    policy.rc1_watchdog_stuck_confirmation_seconds
                ),
                "watchdog_poll_interval_seconds": float(
                    policy.rc1_watchdog_poll_interval_seconds
                ),
                "watchdog_terminate_grace_seconds": float(
                    policy.rc1_watchdog_terminate_grace_seconds
                ),
            }
        repo_root = (self.runtime.root / repo.path).resolve()
        run_workdir = (repo_root / task.workdir).resolve()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_id = run_id or self._new_run_id()
        log_dir = self.runtime.paths["memory"] / "task-runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{timestamp}-{run_id[:8]}.log"
        idempotency_key = make_idempotency_key(run_id, "task", stage, task_id)

        self.runtime.db.create_run(
            run_id=run_id,
            run_type="task",
            repo_slug=repo_slug,
            task_id=task_id,
            objective=task.description,
            stage=stage,
            mode=mode,
            provider=None,
            model=None,
            metadata={
                "command": command,
                "workdir": str(run_workdir),
                "pass_sequence": self.runtime.workspace.policy.pass_sequence,
                "bounded_validation": bounded_validation_policy,
            },
        )
        self.runtime.db.add_event(
            run_id=run_id,
            level="info",
            message=f"Executing task '{task_id}'",
            payload={"command": command, "workdir": str(run_workdir)},
        )
        if bounded_validation_policy is not None:
            self.runtime.db.add_event(
                run_id=run_id,
                level="info",
                message="Bounded validation policy attached",
                payload={"task": task_id, **bounded_validation_policy},
            )
            if watchdog_enabled:
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="info",
                    message="Watchdog policy attached",
                    payload={"task": task_id, **bounded_validation_policy},
                )
        self._idempotency_store.begin(
            run_id,
            idempotency_key,
            payload={"task": task_id, "stage": stage},
        )
        self._checkpoint_store.create_checkpoint(
            run_id=run_id,
            scope="run",
            status="started",
            stage=stage,
            step_id=task_id,
            idempotency_key=idempotency_key,
            payload={"command": command, "workdir": str(run_workdir)},
        )

        if bounded_validation and not policy.rc1_hardware_probe_enabled:
            skip_reason = "hardware_probe_disabled_by_default"
            skip_output = (
                f"Bounded validation skip for task '{task_id}'.\n"
                "Hardware probe paths are disabled by default.\n"
                "Enable policy.rc1_hardware_probe_enabled to run this task."
            )
            log_path.write_text(skip_output, encoding="utf-8")
            self.runtime.db.complete_run(
                run_id=run_id,
                status="success",
                run_dir=str(log_path),
                exit_code=0,
            )
            self.runtime.db.add_event(
                run_id=run_id,
                level="warning",
                message=f"Validation task '{task_id}' skipped by policy",
                payload={
                    "task": task_id,
                    "reason": skip_reason,
                    "artifact": str(log_path),
                },
            )
            record_execution(
                self.runtime,
                run_type="task",
                run_id=run_id,
                repo_slug=repo_slug,
                stage=stage,
                command=command,
                status="success",
                exit_code=0,
                stdout=skip_output,
                artifact=str(log_path),
                note=f"task_id={task_id};skipped={skip_reason}",
                classify_as_test=True,
            )
            self._idempotency_store.mark_completed(
                run_id,
                idempotency_key,
                payload={
                    "artifact": str(log_path),
                    "exit_code": 0,
                    "skipped": True,
                    "skip_reason": skip_reason,
                },
            )
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="skipped",
                stage=stage,
                step_id=task_id,
                idempotency_key=idempotency_key,
                payload={"artifact": str(log_path), "reason": skip_reason},
            )
            return run_id

        attempt_limit = (
            int(policy.rc1_validation_max_attempts) if bounded_validation else 1
        )
        per_attempt_timeout_seconds = (
            float(policy.rc1_validation_attempt_timeout_seconds)
            if bounded_validation
            else 0.0
        )
        deadline_at = (
            time.monotonic() + float(policy.rc1_validation_deadline_seconds)
            if bounded_validation
            else None
        )
        max_respawns = int(policy.rc1_watchdog_max_respawns) if respawn_enabled else 0
        heartbeat_timeout_seconds = float(policy.rc1_watchdog_heartbeat_timeout_seconds)
        stuck_confirmation_seconds = float(policy.rc1_watchdog_stuck_confirmation_seconds)
        poll_interval_seconds = float(policy.rc1_watchdog_poll_interval_seconds)
        terminate_grace_seconds = float(policy.rc1_watchdog_terminate_grace_seconds)

        completed: subprocess.CompletedProcess[str] | None = None
        timeout_error: subprocess.TimeoutExpired | None = None
        launch_error: OSError | None = None
        attempts_used = 0
        respawns_used = 0
        restart_events = 0
        transition_index = 0
        last_failure_state: TaskLifecycleState | None = None
        watchdog_stuck_detected = False
        watchdog_forced_kill = False

        transition_index = self._record_task_lifecycle_transition(
            run_id=run_id,
            stage=stage,
            task_id=task_id,
            idempotency_key=idempotency_key,
            state="queued",
            transition_index=transition_index,
            reason="task_enqueued",
            payload={
                "attempt_limit": attempt_limit,
                "max_respawns": max_respawns,
                "watchdog_enabled": watchdog_enabled,
                "respawn_enabled": respawn_enabled,
            },
        )

        while attempts_used < attempt_limit:
            attempt = attempts_used + 1
            timeout_budget: float | None = None
            if deadline_at is not None:
                remaining_deadline = max(0.0, deadline_at - time.monotonic())
                if remaining_deadline <= 0:
                    self.runtime.db.add_event(
                        run_id=run_id,
                        level="warning",
                        message="Validation deadline reached before next attempt",
                        payload={
                            "task": task_id,
                            "attempt": attempt,
                            "max_attempts": attempt_limit,
                            "deadline_seconds": int(
                                policy.rc1_validation_deadline_seconds
                            ),
                        },
                    )
                    last_failure_state = "failed_retryable"
                    break
                timeout_budget = min(per_attempt_timeout_seconds, remaining_deadline)
                if timeout_budget <= 0:
                    self.runtime.db.add_event(
                        run_id=run_id,
                        level="warning",
                        message="Validation deadline budget exhausted",
                        payload={
                            "task": task_id,
                            "attempt": attempt,
                            "max_attempts": attempt_limit,
                            "deadline_seconds": int(
                                policy.rc1_validation_deadline_seconds
                            ),
                        },
                    )
                    last_failure_state = "failed_retryable"
                    break

            attempts_used = attempt
            transition_index = self._record_task_lifecycle_transition(
                run_id=run_id,
                stage=stage,
                task_id=task_id,
                idempotency_key=idempotency_key,
                state="dispatched",
                transition_index=transition_index,
                reason="attempt_dispatch",
                payload={
                    "attempt": attempt,
                    "max_attempts": attempt_limit,
                    "respawns_used": respawns_used,
                },
            )
            transition_index = self._record_task_lifecycle_transition(
                run_id=run_id,
                stage=stage,
                task_id=task_id,
                idempotency_key=idempotency_key,
                state="running",
                transition_index=transition_index,
                reason="subprocess_start",
                payload={
                    "attempt": attempt,
                    "attempt_timeout_seconds": timeout_budget,
                },
            )
            if watchdog_enabled:
                transition_index = self._record_task_lifecycle_transition(
                    run_id=run_id,
                    stage=stage,
                    task_id=task_id,
                    idempotency_key=idempotency_key,
                    state="healthy",
                    transition_index=transition_index,
                    reason="watchdog_heartbeat_within_threshold",
                    payload={
                        "attempt": attempt,
                        "heartbeat_timeout_seconds": heartbeat_timeout_seconds,
                    },
                )
            if bounded_validation:
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="info",
                    message="Validation attempt started",
                    payload={
                        "task": task_id,
                        "attempt": attempt,
                        "max_attempts": attempt_limit,
                        "attempt_timeout_seconds": timeout_budget,
                        "remaining_deadline_seconds": (
                            max(0.0, (deadline_at or 0.0) - time.monotonic())
                            if deadline_at is not None
                            else None
                        ),
                    },
                )

            try:
                if watchdog_enabled:

                    def _on_watchdog_transition(
                        state: TaskLifecycleState,
                        reason: str,
                        payload: dict[str, Any] | None = None,
                    ) -> None:
                        nonlocal transition_index
                        transition_index = self._record_task_lifecycle_transition(
                            run_id=run_id,
                            stage=stage,
                            task_id=task_id,
                            idempotency_key=idempotency_key,
                            state=state,
                            transition_index=transition_index,
                            reason=reason,
                            payload={"attempt": attempt, **(payload or {})},
                        )

                    watchdog_result = self._run_with_watchdog(
                        command=command,
                        cwd=run_workdir,
                        env={
                            **os.environ,
                            "SUBSTRATE_MODE": mode,
                            "SUBSTRATE_REPO_SLUG": repo_slug,
                            "SUBSTRATE_RUN_ID": run_id,
                            "SUBSTRATE_VALIDATION_ATTEMPT": str(attempt),
                        },
                        timeout_seconds=timeout_budget,
                        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                        stuck_confirmation_seconds=stuck_confirmation_seconds,
                        poll_interval_seconds=poll_interval_seconds,
                        terminate_grace_seconds=terminate_grace_seconds,
                        on_transition=_on_watchdog_transition,
                    )
                    completed = watchdog_result["completed"]
                    timeout_error = watchdog_result["timeout_error"]
                    watchdog_stuck_detected = bool(
                        watchdog_result.get("stuck_detected", False)
                    )
                    watchdog_forced_kill = bool(
                        watchdog_result.get("forced_kill", False)
                    )
                else:
                    completed = subprocess.run(
                        command,
                        cwd=run_workdir,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=timeout_budget,
                        env={
                            **os.environ,
                            "SUBSTRATE_MODE": mode,
                            "SUBSTRATE_REPO_SLUG": repo_slug,
                            "SUBSTRATE_RUN_ID": run_id,
                            "SUBSTRATE_VALIDATION_ATTEMPT": str(attempt),
                        },
                    )
                    timeout_error = None
                    watchdog_stuck_detected = False
                    watchdog_forced_kill = False
            except subprocess.TimeoutExpired as exc:
                timeout_error = exc
                completed = None
                watchdog_stuck_detected = False
                watchdog_forced_kill = False
            except OSError as exc:
                launch_error = exc
                break

            if completed is not None and completed.returncode == 0:
                last_failure_state = None
                transition_index = self._record_task_lifecycle_transition(
                    run_id=run_id,
                    stage=stage,
                    task_id=task_id,
                    idempotency_key=idempotency_key,
                    state="succeeded",
                    transition_index=transition_index,
                    reason="subprocess_completed",
                    payload={
                        "attempt": attempt,
                        "exit_code": 0,
                        "respawns_used": respawns_used,
                    },
                )
                break

            if completed is None:
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="warning",
                    message="Validation attempt timed out",
                    payload={
                        "task": task_id,
                        "attempt": attempt,
                        "max_attempts": attempt_limit,
                        "attempt_timeout_seconds": timeout_budget,
                        "stuck_detected": watchdog_stuck_detected,
                        "forced_kill": watchdog_forced_kill,
                    },
                )
                if watchdog_stuck_detected:
                    last_failure_state = "terminated"
                else:
                    last_failure_state = "failed_retryable"
                    if watchdog_enabled:
                        transition_index = self._record_task_lifecycle_transition(
                            run_id=run_id,
                            stage=stage,
                            task_id=task_id,
                            idempotency_key=idempotency_key,
                            state="failed_retryable",
                            transition_index=transition_index,
                            reason="attempt_timeout_reached",
                            payload={
                                "attempt": attempt,
                                "attempt_timeout_seconds": timeout_budget,
                            },
                        )
            else:
                self.runtime.db.add_event(
                    run_id=run_id,
                    level="warning",
                    message="Validation attempt failed",
                    payload={
                        "task": task_id,
                        "attempt": attempt,
                        "max_attempts": attempt_limit,
                        "exit_code": completed.returncode,
                    },
                )
                last_failure_state = "failed_retryable"
                if watchdog_enabled:
                    transition_index = self._record_task_lifecycle_transition(
                        run_id=run_id,
                        stage=stage,
                        task_id=task_id,
                        idempotency_key=idempotency_key,
                        state="failed_retryable",
                        transition_index=transition_index,
                        reason="nonzero_exit_code",
                        payload={
                            "attempt": attempt,
                            "exit_code": completed.returncode,
                        },
                    )

            if not bounded_validation:
                break

            decision = decide_restart_action(
                attempts_used=attempt,
                max_attempts=attempt_limit,
                respawns_used=respawns_used,
                max_respawns=max_respawns,
                respawn_enabled=respawn_enabled,
                failure_state=last_failure_state or "failed_retryable",
            )
            restart_events += 1
            decision_payload = {
                "task": task_id,
                "attempt": attempt,
                "max_attempts": attempt_limit,
                "respawns_used": respawns_used,
                "max_respawns": max_respawns,
                "failure_state": last_failure_state,
                "decision_action": decision.action,
                "decision_next_state": decision.next_state,
                "decision_reason": decision.reason,
            }
            self.runtime.db.add_event(
                run_id=run_id,
                level="info",
                message="Validation recovery decision",
                payload=decision_payload,
            )
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="recovery",
                status="validation_recovery_decision",
                stage=stage,
                step_id=task_id,
                idempotency_key=idempotency_key,
                payload=decision_payload,
            )
            transition_index = self._record_task_lifecycle_transition(
                run_id=run_id,
                stage=stage,
                task_id=task_id,
                idempotency_key=idempotency_key,
                state=decision.next_state,
                transition_index=transition_index,
                reason=decision.reason,
                payload={
                    "attempt": attempt,
                    "action": decision.action,
                    "respawns_used": respawns_used,
                },
            )

            if decision.action == "respawn":
                respawns_used += 1
                continue
            if decision.action == "retry":
                continue
            break

        if launch_error is not None:
            exc = launch_error
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="failed",
                stage=stage,
                step_id=task_id,
                idempotency_key=idempotency_key,
                payload={"error": str(exc)},
            )
            self.runtime.db.complete_run(
                run_id=run_id, status="failed", exit_code=1, error_text=str(exc)
            )
            self.runtime.db.add_event(
                run_id=run_id,
                level="error",
                message=f"Task launch failed: {exc}",
            )
            record_execution(
                self.runtime,
                run_type="task",
                run_id=run_id,
                repo_slug=repo_slug,
                stage=stage,
                command=command,
                status="failed",
                exit_code=1,
                stderr=str(exc),
                note=f"Task launch failed: {task_id}",
            )
            raise

        if bounded_validation and completed is None:
            timeout_stdout = ""
            timeout_stderr = ""
            timeout_seconds: float | None = None
            if timeout_error is not None:
                timeout_seconds = (
                    float(timeout_error.timeout)
                    if timeout_error.timeout is not None
                    else None
                )
                if timeout_error.stdout is not None:
                    if isinstance(timeout_error.stdout, bytes):
                        timeout_stdout = timeout_error.stdout.decode(
                            "utf-8", errors="replace"
                        )
                    else:
                        timeout_stdout = str(timeout_error.stdout)
                if timeout_error.stderr is not None:
                    if isinstance(timeout_error.stderr, bytes):
                        timeout_stderr = timeout_error.stderr.decode(
                            "utf-8", errors="replace"
                        )
                    else:
                        timeout_stderr = str(timeout_error.stderr)

            timeout_note = (
                f"Task '{task_id}' timed out under bounded validation policy and was skipped."
            )
            combined_output = (
                f"$ {' '.join(command)}\n"
                f"(cwd={run_workdir})\n"
                f"(bounded_validation=true, attempts_used={attempts_used}, "
                f"max_attempts={attempt_limit}, timeout_seconds={timeout_seconds}, "
                f"respawns_used={respawns_used}, max_respawns={max_respawns}, "
                f"restart_events={restart_events})\n\n"
                f"--- stdout ---\n{timeout_stdout}\n\n"
                f"--- stderr ---\n{timeout_stderr}\n\n"
                f"--- note ---\n{timeout_note}\n"
            )
            log_path.write_text(combined_output, encoding="utf-8")
            self.runtime.db.complete_run(
                run_id=run_id,
                status="success",
                run_dir=str(log_path),
                exit_code=124,
                error_text="bounded_validation_timeout_skip",
            )
            self.runtime.db.add_event(
                run_id=run_id,
                level="warning",
                message=f"Validation task '{task_id}' timed out and was skipped",
                payload={
                    "task": task_id,
                    "attempts_used": attempts_used,
                    "max_attempts": attempt_limit,
                    "deadline_seconds": int(policy.rc1_validation_deadline_seconds),
                    "artifact": str(log_path),
                    "skip_reason": "timeout",
                    "respawns_used": respawns_used,
                    "max_respawns": max_respawns,
                    "restart_events": restart_events,
                    "last_failure_state": last_failure_state,
                    "watchdog_stuck_detected": watchdog_stuck_detected,
                    "watchdog_forced_kill": watchdog_forced_kill,
                },
            )
            record_execution(
                self.runtime,
                run_type="task",
                run_id=run_id,
                repo_slug=repo_slug,
                stage=stage,
                command=command,
                status="success",
                exit_code=124,
                stdout=timeout_stdout,
                stderr=timeout_stderr,
                artifact=str(log_path),
                note=f"task_id={task_id};skipped=bounded_validation_timeout",
                classify_as_test=True,
            )
            self._idempotency_store.mark_completed(
                run_id,
                idempotency_key,
                payload={
                    "artifact": str(log_path),
                    "exit_code": 124,
                    "skipped": True,
                    "skip_reason": "bounded_validation_timeout",
                    "attempts_used": attempts_used,
                    "max_attempts": attempt_limit,
                    "respawns_used": respawns_used,
                    "max_respawns": max_respawns,
                    "restart_events": restart_events,
                    "last_failure_state": last_failure_state,
                    "watchdog_stuck_detected": watchdog_stuck_detected,
                    "watchdog_forced_kill": watchdog_forced_kill,
                },
            )
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="skipped_timeout",
                stage=stage,
                step_id=task_id,
                idempotency_key=idempotency_key,
                payload={
                    "artifact": str(log_path),
                    "attempts_used": attempts_used,
                    "max_attempts": attempt_limit,
                    "deadline_seconds": int(policy.rc1_validation_deadline_seconds),
                    "respawns_used": respawns_used,
                    "max_respawns": max_respawns,
                    "restart_events": restart_events,
                    "last_failure_state": last_failure_state,
                    "watchdog_stuck_detected": watchdog_stuck_detected,
                    "watchdog_forced_kill": watchdog_forced_kill,
                },
            )
            return run_id

        if completed is None:
            raise RuntimeError(
                f"Task '{task_id}' did not produce an execution result under current policy."
            )

        combined_output = (
            f"$ {' '.join(command)}\n"
            f"(cwd={run_workdir})\n\n"
            f"--- stdout ---\n{completed.stdout}\n\n"
            f"--- stderr ---\n{completed.stderr}"
        )
        log_path.write_text(combined_output, encoding="utf-8")
        status = "success" if completed.returncode == 0 else "failed"
        self.runtime.db.complete_run(
            run_id=run_id,
            status=status,
            run_dir=str(log_path),
            exit_code=completed.returncode,
            error_text=completed.stderr.strip()[:4000]
            if completed.returncode
            else None,
        )
        self.runtime.db.add_event(
            run_id=run_id,
            level="info" if completed.returncode == 0 else "error",
            message=f"Task '{task_id}' finished with code {completed.returncode}",
            payload={
                "artifact": str(log_path),
                "attempts_used": attempts_used,
                "max_attempts": attempt_limit,
                "respawns_used": respawns_used,
                "max_respawns": max_respawns,
                "restart_events": restart_events,
            },
        )
        record_execution(
            self.runtime,
            run_type="task",
            run_id=run_id,
            repo_slug=repo_slug,
            stage=stage,
            command=command,
            status=status,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            artifact=str(log_path),
            note=f"task_id={task_id}",
            classify_as_test=True,
        )
        if completed.returncode != 0:
            self._checkpoint_store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="failed",
                stage=stage,
                step_id=task_id,
                idempotency_key=idempotency_key,
                payload={
                    "exit_code": completed.returncode,
                    "artifact": str(log_path),
                    "attempts_used": attempts_used,
                    "max_attempts": attempt_limit,
                    "respawns_used": respawns_used,
                    "max_respawns": max_respawns,
                    "restart_events": restart_events,
                    "last_failure_state": last_failure_state,
                },
            )
            raise RuntimeError(
                f"Task '{task_id}' failed with exit code {completed.returncode}. "
                f"See {log_path}"
            )
        self._idempotency_store.mark_completed(
            run_id,
            idempotency_key,
            payload={
                "artifact": str(log_path),
                "exit_code": completed.returncode,
                "attempts_used": attempts_used,
                "max_attempts": attempt_limit,
                "respawns_used": respawns_used,
                "max_respawns": max_respawns,
                "restart_events": restart_events,
            },
        )
        self._checkpoint_store.create_checkpoint(
            run_id=run_id,
            scope="run",
            status="completed",
            stage=stage,
            step_id=task_id,
            idempotency_key=idempotency_key,
            payload={
                "artifact": str(log_path),
                "exit_code": completed.returncode,
                "attempts_used": attempts_used,
                "max_attempts": attempt_limit,
                "respawns_used": respawns_used,
                "max_respawns": max_respawns,
                "restart_events": restart_events,
            },
        )
        return run_id
