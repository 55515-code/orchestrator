from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..learning import record_execution
from ..providers import SUPPORTED_PROVIDERS
from ..reliability import IdempotencyStore, make_idempotency_key

AGENT_ROLES = frozenset(
    {
        "research-agent",
        "dev-agent",
        "update-agent",
        "content-moderator",
        "community-manager",
        "market-research",
        "resource-generator",
        "creative-agent",
        "email-manager",
        "maintenance-agent",
    }
)
VALID_CADENCES = ("hourly", "every_4_hours", "daily", "weekly", "on_demand")
CADENCE_SECONDS: dict[str, int | None] = {
    "hourly": 3600,
    "every_4_hours": 4 * 3600,
    "daily": 86400,
    "weekly": 7 * 86400,
    "on_demand": None,
}
ALLOWED_AGENT_PROVIDERS = set(SUPPORTED_PROVIDERS)

TIER_AUTO = 0
TIER_AUTO_IF_GREEN = 1
TIER_HUMAN = 2

AGENT_BRANCH_PREFIX = "agent/"
BRANCH_MAX_AGE_DAYS = 30
AGENTS_FILE = "agents.yaml"


class AgentConfigError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class AgentConfig:
    id: str
    role: str
    repo_slug: str
    pass_name: str
    cadence: str
    autonomy_tier: int
    provider: str
    command: str
    enabled: bool = True
    model: str | None = None
    framework: str | None = None
    ux_principle: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AgentConfig:
        if not isinstance(raw, dict):
            raise AgentConfigError("Each agent entry must be a mapping.")
        try:
            agent_id = str(raw["id"]).strip()
            role = str(raw["role"]).strip()
            repo_slug = str(raw["repo_slug"]).strip()
            pass_name = str(raw["pass"]).strip().lower()
            cadence = str(raw["cadence"]).strip()
            autonomy_tier = int(raw["autonomy_tier"])
            provider = str(raw["provider"]).strip()
            command = str(raw.get("command") or "").strip()
            framework = str(raw.get("framework") or "").strip() or None
            ux_principle = str(raw.get("ux_principle") or "").strip() or None
        except KeyError as exc:
            raise AgentConfigError(f"Agent entry missing required field: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise AgentConfigError(
                f"Agent '{raw.get('id', '?')}' has invalid autonomy_tier."
            ) from exc

        if not agent_id:
            raise AgentConfigError("Agent id must not be empty.")
        if role not in AGENT_ROLES:
            raise AgentConfigError(
                f"Agent '{agent_id}' has unknown role '{role}'. "
                f"Expected one of {sorted(AGENT_ROLES)}."
            )
        if cadence not in VALID_CADENCES:
            raise AgentConfigError(
                f"Agent '{agent_id}' has unknown cadence '{cadence}'. "
                f"Expected one of {list(VALID_CADENCES)}."
            )
        if autonomy_tier not in (TIER_AUTO, TIER_AUTO_IF_GREEN, TIER_HUMAN):
            raise AgentConfigError(
                f"Agent '{agent_id}' autonomy_tier must be 0, 1, or 2."
            )
        if provider not in ALLOWED_AGENT_PROVIDERS:
            raise AgentConfigError(
                f"Agent '{agent_id}' provider '{provider}' is not supported. "
                f"Expected one of {sorted(ALLOWED_AGENT_PROVIDERS)}."
            )
        model = raw.get("model")
        framework = raw.get("framework")
        ux_principle = raw.get("ux_principle")
        return cls(
            id=agent_id,
            role=role,
            repo_slug=repo_slug,
            pass_name=pass_name,
            cadence=cadence,
            autonomy_tier=autonomy_tier,
            provider=provider,
            command=command,
            enabled=bool(raw.get("enabled", True)),
            model=str(model).strip() if model else None,
            framework=str(framework).strip() if framework else None,
            ux_principle=str(ux_principle).strip() if ux_principle else None,
        )


def agents_file_path(root: Path) -> Path:
    return root / AGENTS_FILE


def load_agents_config(root: Path) -> list[AgentConfig]:
    path = agents_file_path(root)
    if not path.exists():
        return []
    payload = _utils.load_yaml(path)
    version = payload.get("version", 1)
    if int(version) != 1:
        raise AgentConfigError(f"Unsupported agents.yaml version: {version}")
    raw_agents = payload.get("agents") or []
    if not isinstance(raw_agents, list):
        raise AgentConfigError("agents.yaml 'agents' must be a list.")
    agents = [AgentConfig.from_dict(raw) for raw in raw_agents]
    seen: set[str] = set()
    for agent in agents:
        if agent.id in seen:
            raise AgentConfigError(f"Duplicate agent id in agents.yaml: {agent.id}")
        seen.add(agent.id)
    return agents


class AgentStateStore:
    """Persists per-agent run history used for cadence and status reporting."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"agents": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return {"agents": {}}
        if not isinstance(payload, dict):
            return {"agents": {}}
        agents = payload.get("agents")
        payload["agents"] = agents if isinstance(agents, dict) else {}
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        payload["updated_at"] = _utils.utc_now_iso()
        _utils.write_json(self.path, payload)

    def record_run(
        self,
        agent_id: str,
        *,
        status: str,
        run_id: str,
        outputs: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        payload = self._load()
        entry = payload["agents"].get(agent_id, {})
        entry["last_run_at"] = _utils.utc_now_iso()
        entry["last_status"] = status
        entry["last_run_id"] = run_id
        entry["last_note"] = note
        entry["run_count"] = int(entry.get("run_count", 0)) + 1
        recent = entry.get("recent_outputs") or []
        if not isinstance(recent, list):
            recent = []
        recent.extend(outputs or [])
        entry["recent_outputs"] = recent[-20:]
        payload["agents"][agent_id] = entry
        self._save(payload)
        return entry

    def get(self, agent_id: str) -> dict[str, Any] | None:
        entry = self._load()["agents"].get(agent_id)
        return entry if isinstance(entry, dict) else None

    def all(self) -> dict[str, Any]:
        return self._load()["agents"]


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def evaluate_due_agents(
    agents: list[AgentConfig],
    store: AgentStateStore,
    *,
    now: datetime | None = None,
) -> list[AgentConfig]:
    current = now or datetime.now(UTC)
    due: list[AgentConfig] = []
    for agent in agents:
        if not agent.enabled:
            continue
        window = CADENCE_SECONDS.get(agent.cadence)
        if window is None:
            continue
        entry = store.get(agent.id)
        if entry is None:
            due.append(agent)
            continue
        last_run = _parse_iso(str(entry.get("last_run_at") or ""))
        if last_run is None:
            due.append(agent)
            continue
        if (current - last_run).total_seconds() >= window:
            due.append(agent)
    return due


def cadence_bucket(agent: AgentConfig, *, now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    if agent.cadence == "hourly":
        return current.strftime("%Y-%m-%dT%H")
    if agent.cadence == "every_4_hours":
        return f"{current.date().isoformat()}:{current.hour // 4}"
    if agent.cadence == "weekly":
        iso = current.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if agent.cadence == "daily":
        return current.date().isoformat()
    return current.isoformat()


def check_action_permission(
    *,
    agent_tier_cap: int,
    action_tier: int,
    tests_green: bool = True,
    directive: str = "",
) -> tuple[bool, str]:
    """Decide whether an agent may perform an action under the autonomy model.

    Tier 0 actions are always automatic. Tier 1 actions are automatic only when
    validation is green and the agent cap allows them. Tier 2 actions always
    require an explicit human directive.
    """
    if action_tier not in (TIER_AUTO, TIER_AUTO_IF_GREEN, TIER_HUMAN):
        raise ValueError("action_tier must be 0, 1, or 2")
    if agent_tier_cap not in (TIER_AUTO, TIER_AUTO_IF_GREEN, TIER_HUMAN):
        raise ValueError("agent_tier_cap must be 0, 1, or 2")
    if action_tier == TIER_HUMAN:
        if directive.strip():
            return True, "human_directive"
        return False, "tier2_requires_directive"
    if action_tier > agent_tier_cap:
        return False, "exceeds_agent_tier_cap"
    if action_tier == TIER_AUTO_IF_GREEN and not tests_green:
        return False, "validation_not_green"
    return True, "allowed"


def bounded_validation_limits(runtime: Any) -> dict[str, Any]:
    policy = runtime.workspace.policy
    return {
        "max_attempts": max(1, int(policy.rc1_validation_max_attempts)),
        "attempt_timeout_seconds": max(1, int(policy.rc1_validation_attempt_timeout_seconds)),
        "deadline_seconds": max(1, int(policy.rc1_validation_deadline_seconds)),
    }


def run_command_bounded(
    command: list[str],
    *,
    workdir: Path,
    max_attempts: int,
    attempt_timeout_seconds: int,
    deadline_seconds: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a command with bounded-validation semantics (bounded attempts + deadline)."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    import os
    import time

    if env is None:
        env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}

    deadline = time.monotonic() + deadline_seconds
    attempts = 0
    last_stdout = ""
    last_stderr = ""
    last_returncode: int | None = None
    while attempts < max_attempts:
        attempts += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "ok": False,
                "attempts": attempts,
                "reason": "deadline_exceeded",
                "returncode": last_returncode,
                "stdout": last_stdout,
                "stderr": last_stderr or "bounded validation deadline exceeded",
                "command": list(command),
                "workdir": str(workdir),
            }
        timeout = min(attempt_timeout_seconds, remaining)
        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
            last_returncode = completed.returncode
            last_stdout = completed.stdout
            last_stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            last_returncode = None
            last_stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            last_stderr = f"attempt timed out after {timeout:.1f}s"
        if last_returncode == 0:
            return {
                "ok": True,
                "attempts": attempts,
                "reason": "ok",
                "returncode": 0,
                "stdout": last_stdout,
                "stderr": last_stderr,
            }
    return {
        "ok": False,
        "attempts": attempts,
        "reason": "attempts_exhausted",
        "returncode": last_returncode,
        "stdout": last_stdout,
        "stderr": last_stderr,
        "command": list(command),
        "workdir": str(workdir),
    }


def _git(
    repo_path: Path, *args: str, timeout: float = 30.0
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def ensure_python_env(work_root: Path, *, timeout: float = 600.0) -> bool:
    """Best-effort warm-up of the uv-managed environment inside a worktree.

    Environment preparation happens outside bounded validation so that the
    bounded test attempts start with a ready interpreter. Returns True when
    the environment is usable (or nothing needs doing).
    """
    import shutil

    if not (work_root / "pyproject.toml").exists():
        return True
    if not shutil.which("uv"):
        return True
    if (work_root / ".venv").exists():
        return True
    try:
        completed = subprocess.run(
            ["uv", "sync", "--quiet"],
            cwd=work_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def is_git_repo(path: Path) -> bool:
    if not path.exists():
        return False
    completed = _git(path, "rev-parse", "--show-toplevel")
    return bool(completed and completed.returncode == 0)


def agent_branch_name(
    repo_slug: str, role: str, date_str: str, *, suffix: str = ""
) -> str:
    role_token = role.replace("_", "-").strip("-")
    branch = f"{AGENT_BRANCH_PREFIX}{repo_slug}/{role_token}-{date_str}"
    if suffix:
        branch = f"{branch}-{suffix}"
    return branch


def prepare_agent_worktree(
    repo_path: Path, worktrees_root: Path, branch_name: str, *, base_ref: str = "HEAD"
) -> Path | None:
    """Create (or reuse) an isolated git worktree for an agent branch.

    Returns the worktree path, or None when the repository is not git-managed.
    """
    if not is_git_repo(repo_path):
        return None
    worktrees_root.mkdir(parents=True, exist_ok=True)
    worktree_path = (worktrees_root / branch_name.replace("/", "-")).resolve()
    if worktree_path.exists():
        return worktree_path

    branch_ref = f"refs/heads/{branch_name}"
    exists = _git(repo_path, "show-ref", "--verify", "--quiet", branch_ref)
    if exists is not None and exists.returncode == 0:
        completed = _git(
            repo_path, "worktree", "add", str(worktree_path), branch_name, timeout=120.0
        )
    else:
        completed = _git(
            repo_path,
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            base_ref,
            timeout=120.0,
        )
    if completed is None or completed.returncode != 0:
        return None
    return worktree_path


def _branch_committer_epoch(repo_path: Path, branch_name: str) -> int | None:
    completed = _git(
        repo_path, "log", "-1", "--format=%ct", branch_name, timeout=30.0
    )
    if completed is None or completed.returncode != 0:
        return None
    try:
        return int(completed.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def cleanup_stale_agent_artifacts(
    repo_path: Path,
    worktrees_root: Path,
    *,
    max_age_days: int = BRANCH_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Remove agent worktrees and local agent branches older than max_age_days."""
    removed_worktrees: list[str] = []
    removed_branches: list[str] = []
    current = now or datetime.now(UTC)
    cutoff_epoch = int(current.timestamp()) - max_age_days * 86400

    if not is_git_repo(repo_path):
        return {"removed_worktrees": [], "removed_branches": []}

    listing = _git(repo_path, "worktree", "list", "--porcelain")
    if listing is not None and listing.returncode == 0:
        worktree_path: str | None = None
        worktree_branch: str | None = None
        entries: list[tuple[str, str]] = []
        for line in listing.stdout.splitlines():
            if line.startswith("worktree "):
                if worktree_path and worktree_branch:
                    entries.append((worktree_path, worktree_branch))
                worktree_path = line[len("worktree ") :].strip()
                worktree_branch = None
            elif line.startswith("branch refs/heads/"):
                worktree_branch = line[len("branch refs/heads/") :].strip()
        if worktree_path and worktree_branch:
            entries.append((worktree_path, worktree_branch))

        resolved_root = worktrees_root.resolve()
        for path_text, branch_name in entries:
            if not branch_name.startswith(AGENT_BRANCH_PREFIX):
                continue
            entry_path = Path(path_text)
            try:
                entry_path.resolve().relative_to(resolved_root)
            except (ValueError, OSError):
                continue
            epoch = _branch_committer_epoch(repo_path, branch_name)
            if epoch is None or epoch > cutoff_epoch:
                continue
            _git(repo_path, "worktree", "remove", "--force", path_text, timeout=60.0)
            removed_worktrees.append(branch_name)

    completed = _git(
        repo_path,
        "for-each-ref",
        "refs/heads/agent",
        "--format=%(refname:short) %(committerdate:unix)",
    )
    if completed is not None and completed.returncode == 0:
        for line in completed.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            branch_name, epoch_raw = parts
            try:
                epoch = int(epoch_raw)
            except ValueError:
                continue
            if epoch > cutoff_epoch:
                continue
            _git(repo_path, "branch", "-D", branch_name)
            removed_branches.append(branch_name)

    return {"removed_worktrees": removed_worktrees, "removed_branches": removed_branches}


@dataclass(slots=True)
class AgentRunResult:
    agent_id: str
    role: str
    repo_slug: str
    status: str
    run_id: str
    note: str = ""
    outputs: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "repo_slug": self.repo_slug,
            "status": self.status,
            "run_id": self.run_id,
            "note": self.note,
            "outputs": self.outputs,
            "actions": self.actions,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _agent_idempotency_store(runtime: Any) -> IdempotencyStore:
    return IdempotencyStore(runtime.paths["state"] / "agent-idempotency")


def run_agent(
    runtime: Any,
    orchestrator: Any,
    agent: AgentConfig,
    *,
    directive: str = "",
    force: bool = False,
    now: datetime | None = None,
) -> AgentRunResult:
    """Execute a single agent with idempotency, learning, and state recording."""
    from . import community as community_role
    from . import creative as creative_role
    from . import development as development_role
    from . import email_manager as email_manager_role
    from . import maintenance as maintenance_role
    from . import market_research as market_research_role
    from . import moderation as moderation_role
    from . import research as research_role
    from . import resource_gen as resource_gen_role
    from . import update as update_role

    handlers: dict[str, Callable[..., dict[str, Any]]] = {
        "research-agent": research_role.run,
        "dev-agent": development_role.run,
        "update-agent": update_role.run,
        "content-moderator": moderation_role.run,
        "community-manager": community_role.run,
        "market-research": market_research_role.run,
        "resource-generator": resource_gen_role.run,
        "creative-agent": creative_role.run,
        "email-manager": email_manager_role.run,
        "maintenance-agent": maintenance_role.run,
    }
    handler = handlers.get(agent.role)
    if handler is None:
        raise AgentConfigError(f"No handler registered for role '{agent.role}'.")

    runtime.resolve_repo(agent.repo_slug)
    run_id = uuid.uuid4().hex
    started_at = _utils.utc_now_iso()
    store = _agent_idempotency_store(runtime)
    bucket = cadence_bucket(agent, now=now)
    idempotency_key = make_idempotency_key(agent.id, agent.cadence, bucket)

    if not force:
        existing = store.get(agent.id, idempotency_key)
        if existing is not None and existing.status == "completed":
            return AgentRunResult(
                agent_id=agent.id,
                role=agent.role,
                repo_slug=agent.repo_slug,
                status="skipped",
                run_id=run_id,
                note="already completed for this cadence window",
                started_at=started_at,
                finished_at=_utils.utc_now_iso(),
            )
        store.begin(agent.id, idempotency_key, payload={"run_id": run_id})

    state_store = AgentStateStore(runtime.paths["state"] / "agent-state.json")
    status = "success"
    note = ""
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []
    try:
        payload = handler(runtime, orchestrator, agent, directive=directive)
        status = str(payload.get("status") or "success")
        note = str(payload.get("note") or "")
        outputs = [str(item) for item in payload.get("outputs") or []]
        actions = list(payload.get("actions") or [])
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        note = f"{type(exc).__name__}: {exc}"

    finished_at = _utils.utc_now_iso()
    record_execution(
        runtime,
        run_type="agent",
        run_id=run_id,
        repo_slug=agent.repo_slug,
        stage="local",
        command=agent.command or f"agent-run --role {agent.role} --repo {agent.repo_slug}",
        status="success" if status == "success" else "error",
        exit_code=0 if status == "success" else 1,
        stdout="\n".join(outputs[-5:]),
        stderr=note if status != "success" else None,
        note=f"agent:{agent.id}",
    )
    state_store.record_run(
        agent.id, status=status, run_id=run_id, outputs=outputs, note=note
    )
    if not force:
        store.mark_completed(
            agent.id,
            idempotency_key,
            payload={"run_id": run_id, "status": status},
        )
    return AgentRunResult(
        agent_id=agent.id,
        role=agent.role,
        repo_slug=agent.repo_slug,
        status=status,
        run_id=run_id,
        note=note,
        outputs=outputs,
        actions=actions,
        started_at=started_at,
        finished_at=finished_at,
    )


def run_agent_cycle(
    runtime: Any,
    orchestrator: Any,
    *,
    only_ids: list[str] | None = None,
    dry_run: bool = False,
    directive: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    agents = load_agents_config(runtime.root)
    state_store = AgentStateStore(runtime.paths["state"] / "agent-state.json")
    if only_ids:
        wanted = set(only_ids)
        unknown = wanted - {agent.id for agent in agents}
        if unknown:
            raise AgentConfigError(f"Unknown agent ids: {sorted(unknown)}")
        agents = [agent for agent in agents if agent.id in wanted]
    due = evaluate_due_agents(agents, state_store, now=now)
    cycle_started_at = _utils.utc_now_iso()

    results: list[dict[str, Any]] = []
    if not dry_run:
        for agent in due:
            result = run_agent(runtime, orchestrator, agent, directive=directive)
            results.append(result.to_dict())

    cleanup: dict[str, Any] = {}
    if not dry_run:
        worktrees_root = runtime.paths["state"] / "agent-worktrees"
        seen_repos: set[str] = set()
        for agent in agents:
            if agent.repo_slug in seen_repos:
                continue
            seen_repos.add(agent.repo_slug)
            try:
                repo = runtime.resolve_repo(agent.repo_slug)
            except KeyError:
                continue
            repo_path = (runtime.root / repo.path).resolve()
            cleanup[agent.repo_slug] = cleanup_stale_agent_artifacts(
                repo_path, worktrees_root
            )

    return {
        "cycle_started_at": cycle_started_at,
        "agents_configured": len(agents),
        "agents_due": [agent.id for agent in due],
        "dry_run": dry_run,
        "results": results,
        "cleanup": cleanup,
    }


def agent_status_payload(runtime: Any, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    agents = load_agents_config(runtime.root)
    state_store = AgentStateStore(runtime.paths["state"] / "agent-state.json")
    rows: list[dict[str, Any]] = []
    for agent in agents:
        entry = state_store.get(agent.id) or {}
        window = CADENCE_SECONDS.get(agent.cadence)
        next_due_at: str | None = None
        last_run_at = str(entry.get("last_run_at") or "")
        last_dt = _parse_iso(last_run_at)
        if not agent.enabled or window is None:
            next_due_at = None
        elif last_dt is None:
            next_due_at = current.isoformat()
        else:
            from datetime import timedelta

            next_due_at = (last_dt + timedelta(seconds=window)).isoformat()
        rows.append(
            {
                "agent_id": agent.id,
                "role": agent.role,
                "repo_slug": agent.repo_slug,
                "cadence": agent.cadence,
                "autonomy_tier": agent.autonomy_tier,
                "provider": agent.provider,
                "framework": agent.framework,
                "ux_principle": agent.ux_principle,
                "enabled": agent.enabled,
                "due_now": (
                    agent.id in {item.id for item in evaluate_due_agents(agents, state_store, now=current)}
                ),
                "last_run_at": last_run_at or None,
                "last_status": entry.get("last_status"),
                "run_count": entry.get("run_count", 0),
                "next_due_at": next_due_at,
                "recent_outputs": entry.get("recent_outputs", [])[-5:],
            }
        )
    return {
        "generated_at": current.isoformat(),
        "agents_file": str(agents_file_path(runtime.root)),
        "agents": rows,
    }
