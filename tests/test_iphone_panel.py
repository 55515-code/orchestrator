"""Security tests for the iPhone panel automations (shell injection)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import substrate.iphone_panel as iphone_panel
from substrate.web import app

CLIENT_KWARGS = {"base_url": "http://127.0.0.1:8090"}


def test_automation_prompt_passed_as_argv_not_shell_code(
    tmp_path: Path, monkeypatch
) -> None:
    """A hostile prompt must reach the wrapper verbatim, never executed."""
    log = tmp_path / "args.log"
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            {
                "actions": {
                    "echo_agent": {
                        "command": 'echo "%PROMPT%"',
                        "cwd": ".",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'%s\\n\' "$@" > {log}\n'
        "exit 0\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    monkeypatch.setattr(iphone_panel, "ACTIONS_FILE", actions)
    monkeypatch.setattr(iphone_panel, "WRAPPER", wrapper)

    probe = tmp_path / "pwned-probe"
    prompt = f"clean'; touch {probe}; echo '$(id)"
    with TestClient(app, **CLIENT_KWARGS) as client:
        resp = client.post(
            "/api/iphone/automations/echo_agent",
            json={"prompt": prompt},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True, body

    recorded = log.read_text(encoding="utf-8").splitlines()
    assert recorded[0] == "echo_agent"
    assert recorded[1] == prompt, (
        "prompt must be forwarded verbatim as a single argv element"
    )
    assert not probe.exists(), "shell metacharacters must never be executed"
