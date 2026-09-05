"""Regression tests for policy loading in substrate/settings.py.

Background
----------
`workspace.yaml` declared ten policy keys (framework-first development, UX
accessibility, OpenClaw gateway baseline). `PolicyConfig` had matching fields
and `substrate/stats.py` + `substrate/orchestrator.py` read them. But
`load_workspace_config` never passed them to the constructor, so configured
`true` values silently resolved to the dataclass default `False`.

The class of bug is "dataclass field exists, config key exists, loader forgets
to wire them together" — invisible unless asserted. `test_every_policy_field_is_wired`
guards the whole surface so a newly added field cannot repeat it.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from substrate.models import PolicyConfig
from substrate.settings import WORKSPACE_FILE, load_workspace_config


def _write_workspace(tmp_path: Path, policy: dict) -> Path:
    """Write a minimal-but-valid workspace.yaml containing `policy`."""
    doc = {
        "policy": policy,
        "repositories": [],
        "tasks": [],
    }
    (tmp_path / WORKSPACE_FILE).write_text(yaml.safe_dump(doc), encoding="utf-8")
    return tmp_path


# Keys that were dropped by the loader, with a non-default value to prove they
# are actually read rather than coincidentally matching the default.
FRAMEWORK_POLICY_CASES = [
    ("framework_first_development", True, False),
    ("ux_accessibility_first", True, False),
    ("openclaw_gateway_baseline", True, False),
    ("openclaw_gateway_primary_ui", True, False),
    ("ux_screen_reader_support", False, True),
    ("ux_min_touch_target_px", 72, 44),
    ("default_agent_framework", "langchain", "smolagents"),
    ("default_orchestration_framework", "crewai", "langgraph"),
    ("default_web_framework", "starlette", "fastapi"),
    ("default_frontend_framework", "htmx", "vanilla_js_with_established_libs"),
]


@pytest.mark.parametrize("key,configured,default", FRAMEWORK_POLICY_CASES)
def test_policy_key_is_read_from_config(tmp_path, key, configured, default):
    """A configured value must reach the runtime, not fall back to the default."""
    assert configured != default, "test case must use a non-default value"

    _write_workspace(tmp_path, {"default_mode": "mutate", key: configured})
    policy = load_workspace_config(tmp_path).policy

    assert getattr(policy, key) == configured, (
        f"policy.{key} was declared as {configured!r} in workspace.yaml but the "
        f"loader produced {getattr(policy, key)!r}. The loader is dropping the key."
    )


@pytest.mark.parametrize("key,configured,default", FRAMEWORK_POLICY_CASES)
def test_policy_key_falls_back_to_default_when_absent(tmp_path, key, configured, default):
    """An absent key must yield the documented default."""
    _write_workspace(tmp_path, {"default_mode": "mutate"})
    policy = load_workspace_config(tmp_path).policy
    assert getattr(policy, key) == default


def test_every_policy_field_is_wired(tmp_path):
    """No PolicyConfig field may be silently ignored by the loader.

    Guards the whole surface: for each field, write a workspace.yaml that sets a
    value distinguishable from the default and assert the loader honours it.
    Fields needing structured values are covered by dedicated tests elsewhere
    and are listed here explicitly so additions are a deliberate decision.
    """
    structured_or_validated = {
        # Validated/normalised with their own dedicated handling.
        "default_mode",
        "stage_sequence",
        "pass_sequence",
        "restricted_terms",
        "rc1_openclaw_allowed_stages",
        "rc1_openclaw_allowed_passes",
        "rc1_openclaw_allowed_data_classes",
    }

    unwired: list[str] = []
    for f in dataclasses.fields(PolicyConfig):
        if f.name in structured_or_validated:
            continue

        default = getattr(PolicyConfig(), f.name)
        if isinstance(default, bool):
            probe = not default
        elif isinstance(default, int):
            probe = default + 7
        elif isinstance(default, float):
            probe = default + 1.5
        elif isinstance(default, str):
            probe = default + "-probe"
        else:  # pragma: no cover - defensive
            continue

        policy = load_workspace_config(
            _write_workspace(tmp_path, {"default_mode": "mutate", f.name: probe})
        ).policy
        if getattr(policy, f.name) != probe:
            unwired.append(f.name)

    assert not unwired, (
        "These PolicyConfig fields are declared and defaulted but never read by "
        f"load_workspace_config, so configuring them has no effect: {sorted(unwired)}"
    )


def test_real_workspace_yaml_policy_is_honoured():
    """The repo's own workspace.yaml must round-trip through the loader.

    This is the end-to-end assertion that the original bug is fixed: the shipped
    config sets these to `true`, so the runtime must see `True`.
    """
    policy = load_workspace_config(ROOT).policy
    raw = yaml.safe_load((ROOT / WORKSPACE_FILE).read_text()).get("policy", {})

    for key in (
        "framework_first_development",
        "ux_accessibility_first",
        "openclaw_gateway_baseline",
        "openclaw_gateway_primary_ui",
    ):
        if key in raw:
            assert getattr(policy, key) == raw[key], (
                f"workspace.yaml declares policy.{key}={raw[key]!r} but the "
                f"runtime resolved {getattr(policy, key)!r}"
            )
