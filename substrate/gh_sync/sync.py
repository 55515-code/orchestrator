"""GitHub synchronization service.

Syncs repository state (commits, branches, tags) from GitHub API
to keep the dashboard and pipelines up-to-date.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx


@dataclass
class SyncState:
    """Tracks the state of GitHub synchronization."""

    last_sync_at: datetime | None = None
    last_commit_sha: str | None = None
    last_tag: str | None = None
    branches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    recent_commits: list[dict[str, Any]] = field(default_factory=list)
    sync_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_commit_sha": self.last_commit_sha,
            "last_tag": self.last_tag,
            "branches": self.branches,
            "tags": self.tags,
            "recent_commits": self.recent_commits[:10],
            "sync_errors": self.sync_errors[-5:],
        }


class GitHubSyncService:
    """Service for synchronizing with GitHub repository.

    Periodically fetches repository state from GitHub API and
    updates the sync state for use by dashboard and pipelines.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str | None = None,
        sync_interval_seconds: int = 300,
    ) -> None:
        """Initialize the sync service.

        Args:
            owner: GitHub repository owner.
            repo: GitHub repository name.
            token: GitHub API token (optional, for higher rate limits).
            sync_interval_seconds: Interval between sync operations.
        """
        self.owner = owner
        self.repo = repo
        self.token = token
        self.sync_interval = sync_interval_seconds
        self.state = SyncState()
        self._client: httpx.AsyncClient | None = None
        self._sync_task: asyncio.Task | None = None
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            headers = {"Accept": "application/vnd.github.v3+json"}
            if self.token:
                headers["Authorization"] = f"token {self.token}"
            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def _fetch_branches(self) -> list[str]:
        """Fetch all branches from the repository.

        Returns:
            List of branch names.
        """
        client = await self._get_client()
        branches: list[str] = []
        page = 1

        while True:
            response = await client.get(
                f"/repos/{self.owner}/{self.repo}/branches",
                params={"page": page, "per_page": 100},
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            branches.extend(branch["name"] for branch in data)
            page += 1

        return branches

    async def _fetch_tags(self) -> list[str]:
        """Fetch all tags from the repository.

        Returns:
            List of tag names.
        """
        client = await self._get_client()
        tags: list[str] = []
        page = 1

        while True:
            response = await client.get(
                f"/repos/{self.owner}/{self.repo}/tags",
                params={"page": page, "per_page": 100},
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            tags.extend(tag["name"] for tag in data)
            page += 1

        return tags

    async def _fetch_commits(self, branch: str = "main", limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent commits from a branch.

        Args:
            branch: Branch name.
            limit: Maximum number of commits to fetch.

        Returns:
            List of commit dictionaries.
        """
        client = await self._get_client()
        response = await client.get(
            f"/repos/{self.owner}/{self.repo}/commits",
            params={"sha": branch, "per_page": limit},
        )
        response.raise_for_status()
        data = response.json()

        commits = []
        for commit_data in data:
            commit = {
                "sha": commit_data["sha"],
                "message": commit_data["commit"]["message"],
                "author": commit_data["commit"]["author"]["name"],
                "date": commit_data["commit"]["author"]["date"],
                "url": commit_data["html_url"],
            }
            commits.append(commit)

        return commits

    async def sync(self) -> SyncState:
        """Perform a single synchronization.

        Fetches current repository state from GitHub and updates
        the sync state.

        Returns:
            Updated sync state.
        """
        try:
            # Fetch branches, tags, and commits concurrently
            branches, tags, commits = await asyncio.gather(
                self._fetch_branches(),
                self._fetch_tags(),
                self._fetch_commits(),
            )

            # Update state
            self.state.last_sync_at = datetime.utcnow()
            self.state.branches = branches
            self.state.tags = tags
            self.state.recent_commits = commits

            if commits:
                self.state.last_commit_sha = commits[0]["sha"]

            if tags:
                self.state.last_tag = tags[0]

            # Clear errors on successful sync
            self.state.sync_errors.clear()

        except Exception as exc:
            error_msg = f"{datetime.utcnow().isoformat()}: {exc}"
            self.state.sync_errors.append(error_msg)

        return self.state

    async def start(self) -> None:
        """Start the periodic sync service."""
        if self._running:
            return

        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def _sync_loop(self) -> None:
        """Background sync loop."""
        while self._running:
            try:
                await self.sync()
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                # Continue loop even on errors
                await asyncio.sleep(self.sync_interval)

    async def stop(self) -> None:
        """Stop the periodic sync service."""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.stop()
        if self._client:
            await self._client.aclose()
            self._client = None

    def get_state(self) -> SyncState:
        """Get the current sync state.

        Returns:
            Current sync state.
        """
        return self.state
