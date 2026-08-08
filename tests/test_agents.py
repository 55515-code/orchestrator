from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from substrate.agents import (
    AgentConfig,
    AgentConfigError,
    AgentStateStore,
    agent_branch_name,
    cadence_bucket,
    check_action_permission,
    cleanup_stale_agent_artifacts,
    evaluate_due_agents,
    load_agents_config,
    prepare_agent_worktree,
    run_agent,
    run_agent_cycle,
    run_command_bounded,
)
from substrate.cli import main
from substrate.orchestrator import Orchestrator
from substrate.registry import SubstrateRuntime

GIT_AVAILABLE = shutil.which("git") is not None


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=full_env,
        check=True,
    )


def _init_git_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "agent-test@example.com")
    _git(path, "config", "user.name", "Agent Test")
    (path / "README.md").write_text("# test repo\n\nTODO: improve docs\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "initial commit")


def _write_workspace_yaml(
    root: Path,
    *,
    require_source_facts: bool = False,
    include_site_repo: bool = False,
) -> None:
    repos = """
  - slug: test-repo
    path: .
    allow_mutations: true
    default_mode: observe
    tasks:
      test_suite:
        description: Run unit tests.
        mode: observe
        command:
          default:
            - python
            - -c
            - "print('tests ok')"
"""
    if include_site_repo:
        repos += """
  - slug: test-site
    path: site
    allow_mutations: true
    default_mode: observe
    tasks: {}
"""
    (root / "workspace.yaml").write_text(
        f"""
version: 1
policy:
  default_mode: observe
  require_source_facts_before_mutation: {'true' if require_source_facts else 'false'}
  enforce_stage_flow: false
  stage_sequence:
    - local
    - hosted_dev
    - production
  pass_sequence:
    - research
    - development
    - testing
  rc1_validation_max_attempts: 2
  rc1_validation_attempt_timeout_seconds: 10
  rc1_validation_deadline_seconds: 30
repositories:
{repos}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_agents_yaml(root: Path, agents_block: str) -> None:
    (root / "agents.yaml").write_text(
        f"version: 1\nagents:\n{agents_block}", encoding="utf-8"
    )


def _write_chain_fixture(root: Path) -> None:
    chains_dir = root / "chains"
    prompts_dir = root / "prompts"
    chains_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (chains_dir / "local-agent-chain.yaml").write_text(
        """
name: local-agent-chain
steps:
  - id: scope
    prompt: prompts/01_scope.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (prompts_dir / "01_scope.md").write_text(
        "Scope step for objective: {{ objective }}\n", encoding="utf-8"
    )


VALID_AGENTS_BLOCK = """
  - id: research-test
    role: research-agent
    repo_slug: test-repo
    pass: research
    cadence: daily
    autonomy_tier: 0
    provider: mock
    enabled: true
    command: substrate_cli.py agent-run --role research-agent --repo test-repo
  - id: moderator-test
    role: content-moderator
    repo_slug: test-site
    pass: research
    cadence: hourly
    autonomy_tier: 1
    provider: mock
    enabled: true
    command: substrate_cli.py agent-run --role content-moderator --repo test-site
""".strip(
    "\n"
)


class AgentConfigLoadingTest(unittest.TestCase):
    def test_loads_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_agents_yaml(root, VALID_AGENTS_BLOCK)
            agents = load_agents_config(root)
            self.assertEqual(2, len(agents))
            first = agents[0]
            self.assertEqual("research-test", first.id)
            self.assertEqual("research-agent", first.role)
            self.assertEqual("test-repo", first.repo_slug)
            self.assertEqual("research", first.pass_name)
            self.assertEqual("daily", first.cadence)
            self.assertEqual(0, first.autonomy_tier)
            self.assertTrue(first.enabled)

    def test_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], load_agents_config(Path(tmp)))

    def test_rejects_unknown_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_agents_yaml(
                root,
                VALID_AGENTS_BLOCK.replace("research-agent", "rogue-agent", 1),
            )
            with self.assertRaises(AgentConfigError):
                load_agents_config(root)

    def test_rejects_invalid_tier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            block = VALID_AGENTS_BLOCK.replace("autonomy_tier: 0", "autonomy_tier: 9", 1)
            _write_agents_yaml(root, block)
            with self.assertRaises(AgentConfigError):
                load_agents_config(root)

    def test_rejects_unknown_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            block = VALID_AGENTS_BLOCK.replace("cadence: daily", "cadence: minutely", 1)
            _write_agents_yaml(root, block)
            with self.assertRaises(AgentConfigError):
                load_agents_config(root)

    def test_rejects_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            block = VALID_AGENTS_BLOCK.replace("moderator-test", "research-test", 1)
            _write_agents_yaml(root, block)
            with self.assertRaises(AgentConfigError):
                load_agents_config(root)

    def test_rejects_unsupported_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            block = VALID_AGENTS_BLOCK.replace("provider: mock", "provider: not-real", 1)
            _write_agents_yaml(root, block)
            with self.assertRaises(AgentConfigError):
                load_agents_config(root)


class AutonomyTierTest(unittest.TestCase):
    def test_tier0_always_automatic(self) -> None:
        allowed, reason = check_action_permission(agent_tier_cap=0, action_tier=0)
        self.assertTrue(allowed)
        self.assertEqual("allowed", reason)

    def test_tier1_requires_green(self) -> None:
        allowed, _ = check_action_permission(
            agent_tier_cap=1, action_tier=1, tests_green=True
        )
        self.assertTrue(allowed)
        blocked, reason = check_action_permission(
            agent_tier_cap=1, action_tier=1, tests_green=False
        )
        self.assertFalse(blocked)
        self.assertEqual("validation_not_green", reason)

    def test_tier1_blocked_when_agent_cap_is_zero(self) -> None:
        allowed, reason = check_action_permission(
            agent_tier_cap=0, action_tier=1, tests_green=True
        )
        self.assertFalse(allowed)
        self.assertEqual("exceeds_agent_tier_cap", reason)

    def test_tier2_blocked_without_directive(self) -> None:
        allowed, reason = check_action_permission(
            agent_tier_cap=2, action_tier=2, tests_green=True, directive=""
        )
        self.assertFalse(allowed)
        self.assertEqual("tier2_requires_directive", reason)

    def test_tier2_allowed_with_directive(self) -> None:
        allowed, reason = check_action_permission(
            agent_tier_cap=2, action_tier=2, directive="human: approve submission x"
        )
        self.assertTrue(allowed)
        self.assertEqual("human_directive", reason)

    def test_invalid_tiers_raise(self) -> None:
        with self.assertRaises(ValueError):
            check_action_permission(agent_tier_cap=1, action_tier=5)
        with self.assertRaises(ValueError):
            check_action_permission(agent_tier_cap=7, action_tier=1)


class CadenceTest(unittest.TestCase):
    def _agent(self, cadence: str, enabled: bool = True) -> AgentConfig:
        return AgentConfig(
            id="x",
            role="research-agent",
            repo_slug="test-repo",
            pass_name="research",
            cadence=cadence,
            autonomy_tier=0,
            provider="mock",
            command="",
            enabled=enabled,
        )

    def test_bucket_formats(self) -> None:
        now = datetime(2026, 8, 8, 9, 30, tzinfo=timezone.utc)
        self.assertEqual(
            "2026-08-08T09", cadence_bucket(self._agent("hourly"), now=now)
        )
        self.assertEqual(
            "2026-08-08:2", cadence_bucket(self._agent("every_4_hours"), now=now)
        )
        self.assertEqual("2026-08-08", cadence_bucket(self._agent("daily"), now=now))
        weekly = cadence_bucket(self._agent("weekly"), now=now)
        self.assertTrue(weekly.startswith("2026-W"))

    def test_due_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentStateStore(Path(tmp) / "agent-state.json")
            now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
            never_run = self._agent("daily")
            never_run = AgentConfig(
                id="never-run",
                role=never_run.role,
                repo_slug=never_run.repo_slug,
                pass_name=never_run.pass_name,
                cadence="daily",
                autonomy_tier=0,
                provider="mock",
                command="",
            )
            fresh = AgentConfig(
                id="fresh",
                role="research-agent",
                repo_slug="test-repo",
                pass_name="research",
                cadence="daily",
                autonomy_tier=0,
                provider="mock",
                command="",
            )
            stale = AgentConfig(
                id="stale",
                role="research-agent",
                repo_slug="test-repo",
                pass_name="research",
                cadence="hourly",
                autonomy_tier=0,
                provider="mock",
                command="",
            )
            disabled = AgentConfig(
                id="disabled",
                role="research-agent",
                repo_slug="test-repo",
                pass_name="research",
                cadence="daily",
                autonomy_tier=0,
                provider="mock",
                command="",
                enabled=False,
            )
            on_demand = AgentConfig(
                id="on-demand",
                role="research-agent",
                repo_slug="test-repo",
                pass_name="research",
                cadence="on_demand",
                autonomy_tier=0,
                provider="mock",
                command="",
            )
            store.record_run(
                "fresh",
                status="success",
                run_id="r1",
            )
            old_time = (now - timedelta(hours=3)).isoformat()
            payload = store._load()
            payload["agents"]["stale"] = {
                "last_run_at": old_time,
                "last_status": "success",
                "run_count": 1,
            }
            store._save(payload)

            due = evaluate_due_agents(
                [never_run, fresh, stale, disabled, on_demand], store, now=now
            )
            due_ids = {agent.id for agent in due}
            self.assertIn("never-run", due_ids)
            self.assertIn("stale", due_ids)
            self.assertNotIn("fresh", due_ids)
            self.assertNotIn("disabled", due_ids)
            self.assertNotIn("on-demand", due_ids)


class BoundedCommandTest(unittest.TestCase):
    def test_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_command_bounded(
                ["python", "-c", "print('ok')"],
                workdir=Path(tmp),
                max_attempts=2,
                attempt_timeout_seconds=10,
                deadline_seconds=30,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(1, result["attempts"])

    def test_failure_respects_max_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "counter.txt"
            code = (
                "from pathlib import Path\n"
                f"p = Path({str(counter)!r})\n"
                "n = int(p.read_text()) if p.exists() else 0\n"
                "p.write_text(str(n + 1))\n"
                "raise SystemExit(1)\n"
            )
            result = run_command_bounded(
                ["python", "-c", code],
                workdir=Path(tmp),
                max_attempts=2,
                attempt_timeout_seconds=10,
                deadline_seconds=30,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(2, result["attempts"])
            self.assertEqual(2, int(counter.read_text()))


@unittest.skipUnless(GIT_AVAILABLE, "git is required")
class BranchWorktreeTest(unittest.TestCase):
    def test_branch_naming(self) -> None:
        self.assertEqual(
            "agent/test-repo/dev-2026-08-08",
            agent_branch_name("test-repo", "dev", "2026-08-08"),
        )
        self.assertEqual(
            "agent/test-repo/dev-2026-08-08-gh-6",
            agent_branch_name("test-repo", "dev", "2026-08-08", suffix="gh-6"),
        )

    def test_worktree_creation_and_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            _init_git_repo(root)
            worktrees_root = Path(tmp) / "worktrees"
            branch = agent_branch_name("test-repo", "dev", "2026-08-08")

            worktree = prepare_agent_worktree(root, worktrees_root, branch)
            self.assertIsNotNone(worktree)
            assert worktree is not None
            self.assertTrue(worktree.exists())
            self.assertTrue((worktree / "README.md").exists())

            branch_check = _git(root, "show-ref", "--verify", f"refs/heads/{branch}")
            self.assertEqual(0, branch_check.returncode)

            reused = prepare_agent_worktree(root, worktrees_root, branch)
            self.assertEqual(worktree, reused)

    def test_cleanup_removes_stale_branches_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            _init_git_repo(root)
            worktrees_root = Path(tmp) / "worktrees"

            stale_branch = "agent/test-repo/dev-2020-01-01"
            _git(root, "branch", stale_branch)
            _git(root, "checkout", "-q", stale_branch)
            (root / "stale.txt").write_text("stale\n", encoding="utf-8")
            _git(root, "add", "-A")
            old_date = "2020-01-01T00:00:00Z"
            _git(
                root,
                "commit",
                "-q",
                "-m",
                "stale commit",
                env={"GIT_COMMITTER_DATE": old_date, "GIT_AUTHOR_DATE": old_date},
            )
            _git(root, "checkout", "-q", "master" if self._has_master(root) else "main")

            fresh_branch = agent_branch_name("test-repo", "dev", "2026-08-08")
            worktree = prepare_agent_worktree(root, worktrees_root, fresh_branch)
            self.assertIsNotNone(worktree)

            removed = cleanup_stale_agent_artifacts(root, worktrees_root)
            self.assertIn(stale_branch, removed["removed_branches"])
            self.assertNotIn(fresh_branch, removed["removed_branches"])
            self.assertEqual([], removed["removed_worktrees"])

            refs = _git(root, "for-each-ref", "refs/heads/agent", "--format=%(refname:short)")
            self.assertIn(fresh_branch, refs.stdout)
            self.assertNotIn(stale_branch, refs.stdout)

    def test_cleanup_removes_stale_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            _init_git_repo(root)
            worktrees_root = Path(tmp) / "worktrees"
            branch = "agent/test-repo/dev-2020-02-02"
            worktree = prepare_agent_worktree(root, worktrees_root, branch)
            self.assertIsNotNone(worktree)
            assert worktree is not None
            (worktree / "old.txt").write_text("old\n", encoding="utf-8")
            _git(worktree, "add", "-A")
            old_date = "2020-02-02T00:00:00Z"
            _git(
                worktree,
                "commit",
                "-q",
                "-m",
                "old worktree commit",
                env={"GIT_COMMITTER_DATE": old_date, "GIT_AUTHOR_DATE": old_date},
            )

            removed = cleanup_stale_agent_artifacts(root, worktrees_root)
            self.assertIn(branch, removed["removed_worktrees"])
            self.assertFalse(worktree.exists())

    def _has_master(self, root: Path) -> bool:
        result = _git(root, "branch", "--list", "master")
        return bool(result.stdout.strip())


class ResearchAgentRunTest(unittest.TestCase):
    def test_research_agent_writes_note_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_agents_yaml(
                root,
                """
  - id: research-test
    role: research-agent
    repo_slug: test-repo
    pass: research
    cadence: daily
    autonomy_tier: 0
    provider: mock
    command: agent-run --role research-agent --repo test-repo
""".strip(
                    "\n"
                ),
            )
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agents = load_agents_config(root)
            self.assertEqual(1, len(agents))

            result = run_agent(runtime, orchestrator, agents[0])
            self.assertEqual("success", result.status)
            notes = list((root / ".research" / "test-repo").glob("*-upstream-research.md"))
            self.assertEqual(1, len(notes))
            content = notes[0].read_text(encoding="utf-8")
            self.assertIn("Research note", content)

            state = AgentStateStore(root / "state" / "agent-state.json")
            entry = state.get("research-test")
            self.assertIsNotNone(entry)
            self.assertEqual(1, entry.get("run_count"))

            learning = json.loads(
                (root / "state" / "learning-index.json").read_text(encoding="utf-8")
            )
            self.assertTrue(learning["known_good"])

            rerun = run_agent(runtime, orchestrator, agents[0])
            self.assertEqual("skipped", rerun.status)

            forced = run_agent(runtime, orchestrator, agents[0], force=True)
            self.assertEqual("success", forced.status)
            entry = state.get("research-test")
            assert entry is not None
            self.assertEqual(2, entry.get("run_count"))


class DevAgentPolicyGateTest(unittest.TestCase):
    def test_dev_agent_blocked_without_source_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root, require_source_facts=True)
            _write_agents_yaml(
                root,
                """
  - id: dev-test
    role: dev-agent
    repo_slug: test-repo
    pass: development
    cadence: daily
    autonomy_tier: 1
    provider: mock
    command: agent-run --role dev-agent --repo test-repo
""".strip(
                    "\n"
                ),
            )
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agents = load_agents_config(root)
            result = run_agent(runtime, orchestrator, agents[0])
            self.assertEqual("failed", result.status)
            self.assertIn("source facts", result.note)
            blocked_reports = list((root / ".research" / "test-repo").glob("*dev-blocked*"))
            self.assertEqual(1, len(blocked_reports))

    def test_dev_agent_mock_chain_no_patch_path(self) -> None:
        if not GIT_AVAILABLE:
            self.skipTest("git is required")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_chain_fixture(root)
            _write_agents_yaml(
                root,
                """
  - id: dev-test
    role: dev-agent
    repo_slug: test-repo
    pass: development
    cadence: daily
    autonomy_tier: 1
    provider: mock
    command: agent-run --role dev-agent --repo test-repo
""".strip(
                    "\n"
                ),
            )
            _init_git_repo(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agents = load_agents_config(root)
            result = run_agent(runtime, orchestrator, agents[0])
            self.assertEqual("success", result.status)
            self.assertIn("no file changes", result.note)
            self.assertTrue(result.outputs)

    def test_update_agent_no_changes_path(self) -> None:
        if not GIT_AVAILABLE:
            self.skipTest("git is required")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_agents_yaml(
                root,
                """
  - id: update-test
    role: update-agent
    repo_slug: test-repo
    pass: development
    cadence: weekly
    autonomy_tier: 1
    provider: mock
    command: agent-run --role update-agent --repo test-repo
""".strip(
                    "\n"
                ),
            )
            _init_git_repo(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agents = load_agents_config(root)
            result = run_agent(runtime, orchestrator, agents[0])
            self.assertEqual("success", result.status)
            self.assertIn("no changes", result.note)


class ContentModeratorTest(unittest.TestCase):
    def _build_site(self, root: Path) -> Path:
        site_root = root / "site"
        inbox = site_root / ".content-queue" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "clean-post.md").write_text(
            "---\ntitle: A Clean Community Post\n"
            "description: A perfectly reasonable community contribution about local tooling.\n"
            "pubDate: 2026-08-01\n---\nThis is the body of a clean post.\n",
            encoding="utf-8",
        )
        (inbox / "broken-post.md").write_text(
            "---\ntitle: Ab\ndescription: too short\npubDate: 2026-08-01\n---\nBody.\n",
            encoding="utf-8",
        )
        (inbox / "spam-post.md").write_text(
            "---\ntitle: Amazing Opportunity Now\n"
            "description: A totally legitimate offer that you should absolutely accept today.\n"
            "pubDate: 2026-08-01\n---\n"
            "Win big at our casino! Free money for everyone, act now, winner guaranteed!\n",
            encoding="utf-8",
        )
        (inbox / "iffy-post.md").write_text(
            "---\ntitle: Somewhat Promotional Post\n"
            "description: A post that mentions one promotional phrase in the body text.\n"
            "pubDate: 2026-08-01\n---\nCheck out this limited time offer we have.\n",
            encoding="utf-8",
        )
        return site_root

    def test_classification_and_marks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root, include_site_repo=True)
            _write_agents_yaml(
                root,
                """
  - id: moderator-test
    role: content-moderator
    repo_slug: test-site
    pass: research
    cadence: hourly
    autonomy_tier: 1
    provider: mock
    command: agent-run --role content-moderator --repo test-site
""".strip(
                    "\n"
                ),
            )
            self._build_site(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agents = load_agents_config(root)
            result = run_agent(runtime, orchestrator, agents[0])
            self.assertEqual("success", result.status)
            self.assertEqual(4, len(result.outputs))

            classifications = {
                action["action"].split(":", 1)[1]: action["classification"]
                for action in result.actions
                if action["action"].startswith("classify:")
            }
            self.assertEqual("approve-recommend", classifications["clean-post"])
            self.assertEqual("needs-changes", classifications["broken-post"])
            self.assertEqual("reject-recommend", classifications["spam-post"])
            self.assertEqual("hold", classifications["iffy-post"])

            for action in result.actions:
                if not action["action"].startswith("classify:"):
                    continue
                if action["classification"] in {"hold", "needs-changes"}:
                    self.assertEqual(1, action["tier"])
                    self.assertEqual("applied", action["status"])
                else:
                    self.assertEqual(2, action["tier"])
                    self.assertEqual("recommendation", action["status"])

            queue_state = json.loads(
                (root / "state" / "content-queue.json").read_text(encoding="utf-8")
            )
            marks = queue_state["moderation_marks"]
            self.assertIn("broken-post.md", marks)
            self.assertIn("iffy-post.md", marks)
            self.assertNotIn("clean-post.md", marks)
            self.assertNotIn("spam-post.md", marks)

            decisions_path = root / "state" / "moderation-decisions.json"
            decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
            self.assertEqual(4, len(decisions["decisions"]))

            rationale_files = list((root / ".research" / "site-moderation").glob("*.md"))
            self.assertEqual(4, len(rationale_files))

            inbox = root / "site" / ".content-queue" / "inbox"
            self.assertEqual(4, len(list(inbox.glob("*.md"))))


class AgentCycleTest(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        _write_workspace_yaml(root)
        _write_agents_yaml(
            root,
            """
  - id: research-test
    role: research-agent
    repo_slug: test-repo
    pass: research
    cadence: daily
    autonomy_tier: 0
    provider: mock
    command: agent-run --role research-agent --repo test-repo
""".strip(
                "\n"
            ),
        )

    def test_cycle_runs_due_agents_then_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)

            first = run_agent_cycle(runtime, orchestrator)
            self.assertEqual(["research-test"], first["agents_due"])
            self.assertEqual(1, len(first["results"]))
            self.assertEqual("success", first["results"][0]["status"])
            self.assertIn("test-repo", first["cleanup"])

            second = run_agent_cycle(runtime, orchestrator)
            self.assertEqual([], second["agents_due"])
            self.assertEqual([], second["results"])

    def test_cycle_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            payload = run_agent_cycle(runtime, orchestrator, dry_run=True)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(["research-test"], payload["agents_due"])
            self.assertEqual([], payload["results"])
            self.assertFalse((root / ".research" / "test-repo").exists())

    def test_cycle_unknown_agent_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            with self.assertRaises(AgentConfigError):
                run_agent_cycle(runtime, orchestrator, only_ids=["nope"])


class CliCommandsTest(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        _write_workspace_yaml(root)
        _write_agents_yaml(
            root,
            """
  - id: research-test
    role: research-agent
    repo_slug: test-repo
    pass: research
    cadence: daily
    autonomy_tier: 0
    provider: mock
    command: agent-run --role research-agent --repo test-repo
""".strip(
                "\n"
            ),
        )

    def test_agent_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            exit_code = main(["--root", str(root), "agent-status"])
            self.assertEqual(0, exit_code)

    def test_agent_cycle_dry_run_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            exit_code = main(["--root", str(root), "agent-cycle", "--dry-run"])
            self.assertEqual(0, exit_code)

    def test_agent_run_unknown_role_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            with self.assertRaises(SystemExit):
                main(
                    [
                        "--root",
                        str(root),
                        "agent-run",
                        "--role",
                        "nonexistent-role",
                        "--repo",
                        "test-repo",
                    ]
                )

    def test_agent_run_executes_selected_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            exit_code = main(
                [
                    "--root",
                    str(root),
                    "agent-run",
                    "--role",
                    "research-agent",
                    "--repo",
                    "test-repo",
                ]
            )
            self.assertEqual(0, exit_code)
            state = json.loads(
                (root / "state" / "agent-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(1, state["agents"]["research-test"]["run_count"])


if __name__ == "__main__":
    unittest.main()
