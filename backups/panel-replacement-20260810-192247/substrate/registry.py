from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import OrchestratorDB
from .environment import detect_environment
from .models import RepositoryConfig, WorkspaceConfig
from .settings import (
    discover_workspace_root,
    ensure_runtime_dirs,
    load_workspace_config,
    workspace_paths,
)


class SubstrateRuntime:
    def __init__(self, root: Path | None = None) -> None:
        self.root = discover_workspace_root(root)
        ensure_runtime_dirs(self.root)
        self.paths = workspace_paths(self.root)
        self.workspace: WorkspaceConfig = load_workspace_config(self.root)
        self.environment = detect_environment(self.root)
        self.db = OrchestratorDB(self.paths["db"])

    def _slug_for_path(self, path: Path) -> str:
        rel = path.relative_to(self.root) if path.is_relative_to(self.root) else path
        slug = re.sub(r"[^a-z0-9-]+", "-", str(rel).lower()).strip("-")
        return slug or "workspace"

    def _is_ignored(self, path: Path) -> bool:
        ignored = set(self.workspace.ignored_paths)
        if path.name in ignored:
            return True
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            rel = path
        return any(part in ignored for part in rel.parts)

    def _discover_git_repositories(self) -> dict[str, RepositoryConfig]:
        discovered: dict[str, RepositoryConfig] = {}
        if not self.workspace.auto_discovery_enabled:
            return discovered

        explicit_paths = {
            (self.root / repo.path).resolve()
            for repo in self.workspace.repositories.values()
        }

        for configured_root in self.workspace.auto_discovery_roots:
            scan_root = (self.root / configured_root).resolve()
            if not scan_root.exists() or not scan_root.is_dir():
                continue

            for current, dirnames, filenames in os.walk(scan_root):
                current_path = Path(current)
                depth = len(current_path.relative_to(scan_root).parts)
                if depth > self.workspace.auto_discovery_max_depth:
                    dirnames[:] = []
                    continue

                dirnames[:] = [
                    name
                    for name in dirnames
                    if not self._is_ignored(current_path / name)
                ]

                is_git = ".git" in dirnames or ".git" in filenames
                if not is_git:
                    continue

                resolved = current_path.resolve()
                if resolved in explicit_paths:
                    dirnames[:] = []
                    continue
                slug = self._slug_for_path(resolved)
                discovered[slug] = RepositoryConfig(
                    slug=slug,
                    path=resolved.relative_to(self.root)
                    if resolved.is_relative_to(self.root)
                    else resolved,
                    allow_mutations=False,
                    default_mode="observe",
                    tasks={},
                )
                dirnames[:] = []
        return discovered

    def repositories(self) -> dict[str, RepositoryConfig]:
        merged = dict(self.workspace.repositories)
        for slug, repo in self._discover_git_repositories().items():
            if slug not in merged:
                merged[slug] = repo
        return merged

    def resolve_repo(self, slug: str) -> RepositoryConfig:
        repositories = self.repositories()
        if slug not in repositories:
            raise KeyError(f"Unknown repository slug: {slug}")
        return repositories[slug]

    def _git_output(self, repo_path: Path, args: list[str]) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    def inspect_repository(self, repo: RepositoryConfig) -> dict[str, Any]:
        repo_path = (self.root / repo.path).resolve()
        snapshot: dict[str, Any] = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "repo_slug": repo.slug,
            "repo_path": str(repo_path),
            "is_git_repo": False,
            "details": {},
        }
        if not repo_path.exists():
            snapshot["details"] = {"status": "missing"}
            return snapshot

        if not self.environment.git_available:
            snapshot["details"] = {"status": "git_unavailable"}
            return snapshot

        if not ((repo_path / ".git").exists() or (repo_path / ".git").is_file()):
            if self._git_output(repo_path, ["rev-parse", "--show-toplevel"]) is None:
                snapshot["details"] = {"status": "not_git"}
                return snapshot

        snapshot["is_git_repo"] = True
        snapshot["branch"] = self._git_output(
            repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]
        )
        status_output = self._git_output(repo_path, ["status", "--porcelain"]) or ""
        snapshot["dirty"] = bool(status_output.strip())
        snapshot["last_commit_at"] = self._git_output(
            repo_path, ["log", "-1", "--format=%cI"]
        )
        snapshot["remote_url"] = self._git_output(
            repo_path, ["config", "--get", "remote.origin.url"]
        )
        default_ref = self._git_output(
            repo_path, ["symbolic-ref", "refs/remotes/origin/HEAD"]
        )
        if default_ref:
            snapshot["default_branch"] = default_ref.rsplit("/", maxsplit=1)[-1]
        snapshot["details"] = {
            "allow_mutations": repo.allow_mutations,
            "default_mode": repo.default_mode,
            "tasks": sorted(repo.tasks.keys()),
        }
        return snapshot

    def scan_repositories(self, persist: bool = True) -> list[dict[str, Any]]:
        snapshots = [
            self.inspect_repository(self.resolve_repo(slug))
            for slug in sorted(self.repositories().keys())
        ]
        if persist:
            for snapshot in snapshots:
                self.db.record_repository_snapshot(snapshot)
        return snapshots

    def effective_mode(
        self,
        *,
        requested_mode: str | None,
        repo: RepositoryConfig,
        allow_mutations: bool,
    ) -> str:
        mode = requested_mode or repo.default_mode or self.workspace.policy.default_mode
        if mode not in {"observe", "mutate"}:
            mode = "observe"
        if mode == "mutate":
            if not allow_mutations:
                raise PermissionError(
                    "Mutation mode requested but --allow-mutations was not provided."
                )
            if not repo.allow_mutations:
                raise PermissionError(
                    f"Repository '{repo.slug}' disallows mutations in workspace.yaml."
                )
        return mode

    def evaluate_openclaw_policy(
        self,
        *,
        stage: str,
        pass_name: str,
        manual_trigger: bool,
        data_class: str,
    ) -> tuple[bool, str]:
        policy = self.workspace.policy
        normalized_stage = stage.strip().lower()
        normalized_pass = pass_name.strip().lower()
        normalized_data_class = data_class.strip().lower()

        if not policy.rc1_openclaw_internal_assist_enabled:
            return False, "feature_disabled"
        if not policy.rc1_openclaw_revetting_required:
            return False, "revetting_required"
        if policy.rc1_openclaw_manual_trigger_required and not manual_trigger:
            return False, "manual_trigger_required"
        if normalized_stage == "production":
            return False, "stage_production_blocked"
        if normalized_stage not in set(policy.rc1_openclaw_allowed_stages):
            return False, "stage_not_allowed"
        if normalized_pass not in set(policy.rc1_openclaw_allowed_passes):
            return False, "pass_not_allowed"
        if normalized_data_class not in set(policy.rc1_openclaw_allowed_data_classes):
            return False, "data_class_not_allowed"
        return True, "allowed"
