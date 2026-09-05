"""Tests for the GitHub sync module."""

from __future__ import annotations

import asyncio
from datetime import datetime

from substrate.gh_sync import GitHubSyncService, SyncState


class TestSyncState:
    """Test sync state model."""

    def test_sync_state_initialization(self):
        """Test initializing sync state."""
        state = SyncState()
        assert state.last_sync_at is None
        assert state.last_commit_sha is None
        assert state.last_tag is None
        assert len(state.branches) == 0
        assert len(state.tags) == 0
        assert len(state.recent_commits) == 0
        assert len(state.sync_errors) == 0

    def test_sync_state_to_dict(self):
        """Test converting sync state to dictionary."""
        state = SyncState(
            last_sync_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc),
            last_commit_sha="abc123",
            last_tag="v1.0.0",
            branches=["main", "develop"],
            tags=["v1.0.0", "v0.9.0"],
            recent_commits=[
                {"sha": "abc123", "message": "Test commit"},
            ],
            sync_errors=["Error 1", "Error 2"],
        )

        data = state.to_dict()
        assert data["last_sync_at"] == "2024-01-01T12:00:00+00:00"
        assert data["last_commit_sha"] == "abc123"
        assert data["last_tag"] == "v1.0.0"
        assert len(data["branches"]) == 2
        assert len(data["tags"]) == 2
        assert len(data["recent_commits"]) == 1
        assert len(data["sync_errors"]) == 2


class TestGitHubSyncService:
    """Test GitHub sync service."""

    def test_service_initialization(self):
        """Test initializing the sync service."""
        service = GitHubSyncService(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            sync_interval_seconds=600,
        )
        assert service.owner == "test-owner"
        assert service.repo == "test-repo"
        assert service.token == "test-token"
        assert service.sync_interval == 600
        assert service.state is not None

    def test_service_without_token(self):
        """Test initializing service without token."""
        service = GitHubSyncService(
            owner="test-owner",
            repo="test-repo",
        )
        assert service.token is None

    def test_get_state(self):
        """Test getting the sync state."""
        service = GitHubSyncService(
            owner="test-owner",
            repo="test-repo",
        )
        state = service.get_state()
        assert state is not None
        assert isinstance(state, SyncState)

    def test_close_without_client(self):
        """Test closing service without client."""
        service = GitHubSyncService(
            owner="test-owner",
            repo="test-repo",
        )
        asyncio.run(service.close())
        # Should not raise

    def test_stop_without_start(self):
        """Test stopping service without starting."""
        service = GitHubSyncService(
            owner="test-owner",
            repo="test-repo",
        )
        asyncio.run(service.stop())
        # Should not raise

    def test_start_and_stop(self):
        """Test starting and stopping the service."""
        service = GitHubSyncService(
            owner="test-owner",
            repo="test-repo",
            sync_interval_seconds=3600,  # Long interval to avoid actual syncs
        )

        async def _run():
            await service.start()
            assert service._running is True
            assert service._sync_task is not None

            await service.stop()
            assert service._running is False
            assert service._sync_task is None

            await service.close()

        asyncio.run(_run())
