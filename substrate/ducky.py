from __future__ import annotations

import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from .orchestrator import Orchestrator
from .registry import SubstrateRuntime
from .research import refresh_upstreams

StepKind = Literal["scan", "refresh_sources", "run_task", "run_chain", "pinch_report"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class PayloadStep:
    id: str
    label: str
    kind: StepKind
    task_id: str | None = None
    objective_template: str | None = None
    dry_run: bool = True
    optional: bool = False


@dataclass(frozen=True, slots=True)
class PayloadDefinition:
    id: str
    name: str
    description: str
    requires_repo: bool
    steps: tuple[PayloadStep, ...]
    tags: tuple[str, ...] = ("safe", "devops")


DEFAULT_PAYLOADS: tuple[PayloadDefinition, ...] = (
    PayloadDefinition(
        id="ducky_quick_recon",
        name="Quick Recon",
        description="Refresh local repo intelligence: inventory, upstream facts, and pinch report.",
        requires_repo=False,
        tags=("safe", "inventory", "research"),
        steps=(
            PayloadStep(
                id="scan",
                label="Scan repositories",
                kind="scan",
            ),
            PayloadStep(
                id="refresh_sources",
                label="Refresh upstream source facts",
                kind="refresh_sources",
            ),
            PayloadStep(
                id="pinch_report",
                label="Write pinch-mode command report",
                kind="pinch_report",
            ),
        ),
    ),
    PayloadDefinition(
        id="ducky_repo_triage",
        name="Repo Triage",
        description="Run practical triage loop for a repository: inventory, host probe, and chain dry-run.",
        requires_repo=True,
        tags=("safe", "triage", "automation"),
        steps=(
            PayloadStep(
                id="scan",
                label="Scan repositories",
                kind="scan",
            ),
            PayloadStep(
                id="probe",
                label="Run probe_system task",
                kind="run_task",
                task_id="probe_system",
                optional=True,
            ),
            PayloadStep(
                id="chain",
                label="Run triage chain dry-run",
                kind="run_chain",
                objective_template="Ducky triage for {repo_slug}",
                dry_run=True,
            ),
        ),
    ),
    PayloadDefinition(
        id="ducky_stage_gate",
        name="Stage Gate Check",
        description="Exercise stage-aware chain flow with a deterministic dry-run objective.",
        requires_repo=True,
        tags=("safe", "lifecycle", "gates"),
        steps=(
            PayloadStep(
                id="chain_gate",
                label="Run lifecycle gate dry-run",
                kind="run_chain",
                objective_template="Lifecycle gate validation for {repo_slug}",
                dry_run=True,
            ),
            PayloadStep(
                id="pinch_report",
                label="Write pinch-mode command report",
                kind="pinch_report",
            ),
        ),
    ),
)


class DuckyPayloadEngine:
    def __init__(self, runtime: SubstrateRuntime, orchestrator: Orchestrator) -> None:
        self.runtime = runtime
        self.orchestrator = orchestrator
        self._payloads = {payload.id: payload for payload in DEFAULT_PAYLOADS}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)

    def _tool_presence(self) -> dict[str, str | None]:
        return {
            "cloudflared": shutil.which("cloudflared"),
            "tailscale": shutil.which("tailscale"),
            "ssh": shutil.which("ssh"),
        }

    def _payload_artifacts_dir(self) -> Path:
        path = self.runtime.paths["memory"] / "payloads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _find_repo(self, repo_slug: str | None):
        if not repo_slug:
            return None
        try:
            return self.runtime.resolve_repo(repo_slug)
        except KeyError:
            return None

    def list_payloads(self, repo_slug: str | None = None) -> list[dict[str, Any]]:
        repo = self._find_repo(repo_slug)
        items: list[dict[str, Any]] = []
        for payload in self._payloads.values():
            available = True
            unavailable_reason: str | None = None
            if payload.requires_repo and repo is None:
                available = False
                unavailable_reason = "Repository is required."
            items.append(
                {
                    "id": payload.id,
                    "name": payload.name,
                    "description": payload.description,
                    "requires_repo": payload.requires_repo,
                    "available": available,
                    "unavailable_reason": unavailable_reason,
                    "tags": list(payload.tags),
                    "steps": [step.label for step in payload.steps],
                }
            )
        return items

    def submit(
        self,
        *,
        payload_id: str,
        repo_slug: str | None,
        stage: str,
        allow_stage_skip: bool = False,
        port: int = 8090,
    ) -> str:
        if payload_id not in self._payloads:
            raise KeyError(f"Unknown payload: {payload_id}")
        payload = self._payloads[payload_id]
        if payload.requires_repo and not repo_slug:
            raise ValueError(f"Payload '{payload_id}' requires repo_slug.")
        if repo_slug is not None:
            self.runtime.resolve_repo(repo_slug)

        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "payload_id": payload.id,
            "payload_name": payload.name,
            "repo_slug": repo_slug,
            "stage": stage,
            "status": "queued",
            "created_at": _utc_now(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "artifact_path": None,
            "steps": [
                {
                    "id": step.id,
                    "label": step.label,
                    "kind": step.kind,
                    "status": "pending",
                    "details": None,
                    "run_id": None,
                }
                for step in payload.steps
            ],
        }
        with self._lock:
            self._jobs[job_id] = job
        future = self._executor.submit(
            self._run_job,
            job_id,
            payload,
            repo_slug,
            stage,
            allow_stage_skip,
            port,
        )
        future.add_done_callback(lambda _: None)
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            copied = {
                **job,
                "steps": [dict(step) for step in job["steps"]],
            }
        return copied

    def _set_job(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(updates)

    def _set_step(self, job_id: str, index: int, **updates: Any) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            step = self._jobs[job_id]["steps"][index]
            step.update(updates)

    def _render_pinch_report(self, *, repo_slug: str | None, port: int) -> str:
        base_url = f"http://127.0.0.1:{port}"
        tools = self._tool_presence()
        lines = [
            "# Ducky Pinch Report",
            "",
            f"- Generated (UTC): {_utc_now()}",
            f"- Base URL: {base_url}",
            f"- Repository: {repo_slug or '(not set)'}",
            "",
            "## Access Fallbacks",
            "",
            f"- cloudflared: {'available' if tools['cloudflared'] else 'missing'}",
            f"  command: `cloudflared tunnel --url {base_url}`",
            f"- tailscale: {'available' if tools['tailscale'] else 'missing'}",
            f"  command: `tailscale serve localhost:{port}`",
            f"- ssh: {'available' if tools['ssh'] else 'missing'}",
            f"  command: `ssh -N -R {port}:127.0.0.1:{port} user@remote-host`",
            "",
            "## Diagnostics",
            "",
            f"- `curl -fsS {base_url}/healthz`",
            "- `uv run python scripts/substrate_cli.py runs`",
            "- `uv run python scripts/substrate_cli.py scan`",
        ]
        if repo_slug:
            lines.extend(
                [
                    "- `uv run python scripts/substrate_cli.py run-chain "
                    f'--repo {repo_slug} --objective "Recovery check" --stage local --dry-run`',
                ]
            )
        lines.append("")
        return "\n".join(lines)

    def _write_job_artifact(self, job_id: str) -> str:
        job = self.get_job(job_id)
        if job is None:
            raise RuntimeError("Unknown job state while writing artifact.")
        artifact_dir = self._payload_artifacts_dir()
        artifact_path = artifact_dir / f"{job_id}.md"
        lines = [
            f"# Payload Job {job['job_id']}",
            "",
            f"- Payload: {job['payload_name']} (`{job['payload_id']}`)",
            f"- Repository: {job['repo_slug'] or '(none)'}",
            f"- Stage: {job['stage']}",
            f"- Status: {job['status']}",
            f"- Started: {job['started_at']}",
            f"- Finished: {job['finished_at']}",
            "",
            "## Steps",
            "",
        ]
        for step in job["steps"]:
            lines.append(f"- `{step['id']}` {step['label']} -> **{step['status']}**")
            if step.get("details"):
                lines.append(f"  - details: {step['details']}")
            if step.get("run_id"):
                lines.append(f"  - run_id: `{step['run_id']}`")
        if job.get("error"):
            lines.extend(["", "## Error", "", f"```\n{job['error']}\n```"])
        artifact_path.write_text("\n".join(lines), encoding="utf-8")
        return str(artifact_path)

    def _run_job(
        self,
        job_id: str,
        payload: PayloadDefinition,
        repo_slug: str | None,
        stage: str,
        allow_stage_skip: bool,
        port: int,
    ) -> None:
        self._set_job(job_id, status="running", started_at=_utc_now())
        try:
            for index, step in enumerate(payload.steps):
                self._set_step(job_id, index, status="running", details=None)
                if step.kind == "scan":
                    snapshots = self.runtime.scan_repositories(persist=True)
                    self._set_step(
                        job_id,
                        index,
                        status="success",
                        details=f"{len(snapshots)} repositories scanned",
                    )
                    continue

                if step.kind == "refresh_sources":
                    refreshed = refresh_upstreams(self.runtime)
                    self._set_step(
                        job_id,
                        index,
                        status="success",
                        details=f"{len(refreshed)} source projects refreshed",
                    )
                    continue

                if step.kind == "run_task":
                    if repo_slug is None:
                        raise ValueError("Task step requires a repository.")
                    repo = self.runtime.resolve_repo(repo_slug)
                    if step.task_id is None:
                        raise ValueError("Task step missing task_id.")
                    if step.task_id not in repo.tasks:
                        if step.optional:
                            self._set_step(
                                job_id,
                                index,
                                status="skipped",
                                details=f"Task '{step.task_id}' not found in repo '{repo_slug}'",
                            )
                            continue
                        raise ValueError(
                            f"Task '{step.task_id}' not found in repo '{repo_slug}'"
                        )
                    run_id = self.orchestrator.run_task(
                        repo_slug=repo_slug,
                        task_id=step.task_id,
                        stage=stage,
                        requested_mode="observe",
                        allow_mutations=False,
                        allow_stage_skip=allow_stage_skip,
                    )
                    self._set_step(
                        job_id,
                        index,
                        status="success",
                        run_id=run_id,
                        details=f"Task run completed ({run_id[:10]})",
                    )
                    continue

                if step.kind == "run_chain":
                    if repo_slug is None:
                        raise ValueError("Chain step requires a repository.")
                    objective = (
                        step.objective_template or "Payload chain for {repo_slug}"
                    ).format(repo_slug=repo_slug)
                    run_id = self.orchestrator.run_chain(
                        repo_slug=repo_slug,
                        objective=objective,
                        stage=stage,
                        provider="mock",
                        model="mock-model",
                        dry_run=step.dry_run,
                        requested_mode="observe",
                        allow_mutations=False,
                        allow_stage_skip=allow_stage_skip,
                    )
                    self._set_step(
                        job_id,
                        index,
                        status="success",
                        run_id=run_id,
                        details=f"Chain run completed ({run_id[:10]})",
                    )
                    continue

                if step.kind == "pinch_report":
                    artifact_dir = self._payload_artifacts_dir()
                    report_path = artifact_dir / f"{job_id}-pinch.md"
                    report = self._render_pinch_report(repo_slug=repo_slug, port=port)
                    report_path.write_text(report, encoding="utf-8")
                    self._set_step(
                        job_id,
                        index,
                        status="success",
                        details=f"Wrote {report_path}",
                    )
                    continue

                raise ValueError(f"Unsupported payload step kind: {step.kind}")

            self._set_job(job_id, status="success")
        except Exception as exc:  # noqa: BLE001
            self._set_job(job_id, status="failed", error=str(exc))
            for index, step in enumerate(self.get_job(job_id)["steps"]):  # type: ignore[index]
                if step["status"] == "running":
                    self._set_step(job_id, index, status="failed", details=str(exc))
                    break
        finally:
            artifact = self._write_job_artifact(job_id)
            self._set_job(job_id, artifact_path=artifact, finished_at=_utc_now())
