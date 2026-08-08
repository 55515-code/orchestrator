"""GitHub synchronization service.

Automatically syncs with GitHub repository to keep dashboard and pipelines
current with latest commits, branches, and release tags.
"""

from .sync import GitHubSyncService, SyncState

__all__ = ["GitHubSyncService", "SyncState"]
