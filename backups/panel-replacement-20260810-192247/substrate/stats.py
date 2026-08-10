from __future__ import annotations

from .config_sync import config_sync_payload
from .integrations import integrations_payload
from .learning import learning_payload
from .registry import SubstrateRuntime
from .standards import standards_payload
from .tooling import tooling_snapshot


def dashboard_payload(runtime: SubstrateRuntime) -> dict:
    standards = standards_payload(runtime)
    tooling = tooling_snapshot(runtime)
    integrations = integrations_payload(runtime)
    learning = learning_payload(runtime)
    config_sync = config_sync_payload(runtime)
    return {
        "environment": {
            "os": runtime.environment.os_name,
            "release": runtime.environment.os_release,
            "machine": runtime.environment.machine,
            "python": runtime.environment.python_version,
            "tags": runtime.environment.tags,
            "cwd": runtime.environment.cwd,
        },
        "metrics": runtime.db.dashboard_metrics(),
        "repositories": runtime.db.latest_repository_snapshots(),
        "sources": runtime.db.list_source_projects(),
        "runs": runtime.db.list_recent_runs(limit=30),
        "standards": standards["tracks"],
        "standards_summary": standards["summary"],
        "principles": standards["principles"],
        "tooling": tooling,
        "integrations": integrations,
        "learning": learning,
        "config_sync": config_sync,
        "dotfiles": config_sync,
    }
