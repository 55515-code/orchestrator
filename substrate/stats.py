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
    policy = runtime.workspace.policy
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
        "framework_policy": {
            "framework_first_development": getattr(policy, 'framework_first_development', False),
            "default_agent_framework": getattr(policy, 'default_agent_framework', 'smolagents'),
            "default_orchestration_framework": getattr(policy, 'default_orchestration_framework', 'langgraph'),
            "default_web_framework": getattr(policy, 'default_web_framework', 'fastapi'),
            "default_frontend_framework": getattr(policy, 'default_frontend_framework', 'vanilla_js_with_established_libs'),
            "ux_accessibility_first": getattr(policy, 'ux_accessibility_first', False),
            "openclaw_gateway_baseline": getattr(policy, 'openclaw_gateway_baseline', False),
            "openclaw_gateway_primary_ui": getattr(policy, 'openclaw_gateway_primary_ui', False),
        },
    }
