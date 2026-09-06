# Agent Hybrid Report

- Generated at: 2026-09-06T07:53:43.131687+00:00
- Session: `20260906-9109e4c`
- Mode: `deep`
- Loop count: `6`
- Route: `cloud_agent`
- Target branch: `main`
- Allow write: `True`

## Repo health + failing surfaces

- Loop 1: All deterministic checks in this loop succeeded.
- Loop 2: All deterministic checks in this loop succeeded.
- Loop 3: All deterministic checks in this loop succeeded.
- Loop 4: All deterministic checks in this loop succeeded.
- Loop 5: All deterministic checks in this loop succeeded.
- Loop 6: All deterministic checks in this loop succeeded.

## Deep research findings with sources/risks

- Source anchors reviewed: `README.md`, `docs/community-cycle.md`, `docs/lifecycle.md`, `CONTRIBUTING.md`.
- Strategic direction reviewed: `docs/security-toolkit-roadmap.md`.
- Risk: AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.
- Risk: AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.
- Risk: AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.
- Risk: AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.
- Risk: AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.
- Risk: AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.

## Development plan with prioritized tasks

- P1 | qa_release | Investigate failing command surfaces and publish deterministic repro notes. | Acceptance: Each failure has a reproducible command and captured stdout/stderr evidence path.
- P1 | core_reliability | Translate validated findings into minimal, test-backed reliability patches. | Acceptance: Patches include targeted tests and preserve stage/policy safeguards.
- P2 | docs_community | Update collaboration queue with owner-tagged next tasks. | Acceptance: At least 3 queued tasks include owner, priority, and labels.
- P1 | security_tooling | Prioritize sanctioned defensive tool integrations and normalized evidence output. | Acceptance: Top adapters include maintenance status and risk notes.
- P1 | ux_operator | Improve explainable security-run UX and learner-safe remediation guidance. | Acceptance: Operator flow clearly shows finding, confidence, and next safe step.

## Implemented changes + test evidence

- Changed files detected in runner workspace: `0`
- Session summary is included in the raw JSON section below.

### Loop execution table

| Loop | Status | Route | Failing commands | Merge action |
| --- | --- | --- | --- | --- |
| 1 | success | deterministic | 0 | pr_create_failed |
| 2 | success | deterministic | 0 | pr_create_failed |
| 3 | success | deterministic | 0 | pr_create_failed |
| 4 | success | deterministic | 0 | pr_create_failed |
| 5 | success | deterministic | 0 | pr_create_failed |
| 6 | success | deterministic | 0 | n/a |

- Loop 1 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 2 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 3 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 4 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 5 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 6 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0

## Collaboration tasks for external bots (issues/labels/entry points)

- Label recommendations: `ai-ready`, `help-wanted`, `good-first-task`, `needs-repro`, `research-needed`.
- Primary entry points: `docs/ai-collaboration.md`, `prompts/cloud_agent_hybrid_operator.md`, and the pinned collaboration issue.
- Queue updates should include owner, priority, and acceptance criteria.

## Command transcript summary

- Loop 1 executed 3 commands.
- Loop 2 executed 3 commands.
- Loop 3 executed 3 commands.
- Loop 4 executed 3 commands.
- Loop 5 executed 3 commands.
- Loop 6 executed 3 commands.

## Compatibility notes

- Existing CLI/API compatibility remains required; no direct-merge-to-main bypass is used.
- Safe-gate merge requires clean rebase/push and successful loop checks.

## Unresolved questions

- None recorded by this automated cycle.

## Git sync posture summary

- Current branch: `agent/swarm-20260906-9109e4c`
- Target branch: `main`
- Ahead: `5` | Behind: `0` | Diverged: `False`
- PR URL: `n/a`
- Final merge state: `not_attempted`

## Raw summary JSON

```json
{
  "status": "success",
  "mode": "deep",
  "route": "cloud_agent",
  "target_branch": "main",
  "allow_write": true,
  "session_id": "20260906-9109e4c",
  "loop_count": 6,
  "generated_at": "2026-09-06T07:53:43.131687+00:00",
  "started_at": "2026-09-06T07:53:11.488048+00:00",
  "findings": [
    "Loop 1: All deterministic checks in this loop succeeded.",
    "Loop 2: All deterministic checks in this loop succeeded.",
    "Loop 3: All deterministic checks in this loop succeeded.",
    "Loop 4: All deterministic checks in this loop succeeded.",
    "Loop 5: All deterministic checks in this loop succeeded.",
    "Loop 6: All deterministic checks in this loop succeeded."
  ],
  "risks": [
    "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.",
    "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.",
    "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.",
    "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.",
    "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent.",
    "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
  ],
  "tasks": [
    {
      "priority": "P1",
      "owner": "qa_release",
      "task": "Investigate failing command surfaces and publish deterministic repro notes.",
      "acceptance_criteria": "Each failure has a reproducible command and captured stdout/stderr evidence path."
    },
    {
      "priority": "P1",
      "owner": "core_reliability",
      "task": "Translate validated findings into minimal, test-backed reliability patches.",
      "acceptance_criteria": "Patches include targeted tests and preserve stage/policy safeguards."
    },
    {
      "priority": "P2",
      "owner": "docs_community",
      "task": "Update collaboration queue with owner-tagged next tasks.",
      "acceptance_criteria": "At least 3 queued tasks include owner, priority, and labels."
    },
    {
      "priority": "P1",
      "owner": "security_tooling",
      "task": "Prioritize sanctioned defensive tool integrations and normalized evidence output.",
      "acceptance_criteria": "Top adapters include maintenance status and risk notes."
    },
    {
      "priority": "P1",
      "owner": "ux_operator",
      "task": "Improve explainable security-run UX and learner-safe remediation guidance.",
      "acceptance_criteria": "Operator flow clearly shows finding, confidence, and next safe step."
    }
  ],
  "changed_files": [],
  "test_results": [
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 4.388,
      "loop": 1
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.213,
      "loop": 2
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.154,
      "loop": 3
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.177,
      "loop": 4
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.151,
      "loop": 5
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.151,
      "loop": 6
    }
  ],
  "assumptions": [
    "Target merge branch defaults to main.",
    "Rolling PR model uses one branch and one PR for the full session.",
    "Safe gate merge requires loop checks and rebase/push success."
  ],
  "next_cycle_focus": [
    "Increase cloud execution reliability and Kilo/OpenClaw readiness.",
    "Expand defensive-tool evidence normalization coverage.",
    "Improve UX explainability for learner-safe security runs."
  ],
  "loop_results": [
    {
      "loop_index": 1,
      "started_at": "2026-09-06T07:53:11.944802+00:00",
      "generated_at": "2026-09-06T07:53:17.504326+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "All deterministic checks in this loop succeeded."
      ],
      "risks": [
        "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
      ],
      "command_results": [
        {
          "command": [
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "substrate",
            "scripts",
            "tests"
          ],
          "command_text": "uv run --with ruff ruff check substrate scripts tests",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.755,
          "stdout_tail": "All checks passed!\n",
          "stderr_tail": "Downloading ruff (10.9MiB)\n Downloaded ruff\nInstalled 1 package in 1ms\n"
        },
        {
          "command": [
            "uv",
            "run",
            "python",
            "-m",
            "compileall",
            "substrate",
            "scripts"
          ],
          "command_text": "uv run python -m compileall substrate scripts",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.417,
          "stdout_tail": "ubstrate/pipelines'...\nCompiling 'substrate/pipelines/__init__.py'...\nCompiling 'substrate/pipelines/api.py'...\nCompiling 'substrate/pipelines/engine.py'...\nCompiling 'substrate/pipelines/expansion_trigger.py'...\nCompiling 'substrate/pipelines/models.py'...\nCompiling 'substrate/pipelines/quality_gate.py'...\nCompiling 'substrate/pipelines/registry.py'...\nCompiling 'substrate/pipelines/resource_pipeline.py'...\nCompiling 'substrate/pipelines/triggers.py'...\nCompiling 'substrate/prefill_proxy.py'...\nCompiling 'substrate/proton_support.py'...\nCompiling 'substrate/providers.py'...\nCompiling 'substrate/registry.py'...\nCompiling 'substrate/reliability.py'...\nCompiling 'substrate/render.py'...\nListing 'substrate/render_engines'...\nCompiling 'substrate/render_engines/__init__.py'...\nCompiling 'substrate/render_engines/base.py'...\nCompiling 'substrate/render_engines/hosted.py'...\nCompiling 'substrate/render_engines/local_diffusers.py'...\nCompiling 'substrate/research.py'...\nCompiling 'substrate/resource_orchestration.py'...\nListing 'substrate/resources'...\nCompiling 'substrate/resources/__init__.py'...\nCompiling 'substrate/resources/api_access.py'...\nListing 'substrate/security'...\nCompiling 'substrate/security/__init__.py'...\nCompiling 'substrate/security/abuse_detection.py'...\nCompiling 'substrate/security/audit_trail.py'...\nCompiling 'substrate/settings.py'...\nCompiling 'substrate/site_content.py'...\nCompiling 'substrate/snapshots.py'...\nCompiling 'substrate/standards.py'...\nListing 'substrate/static'...\nCompiling 'substrate/stats.py'...\nCompiling 'substrate/swarm_control.py'...\nCompiling 'substrate/task_cache.py'...\nListing 'substrate/templates'...\nCompiling 'substrate/tooling.py'...\nCompiling 'substrate/vault.py'...\nListing 'substrate/watchdog'...\nCompiling 'substrate/watchdog/__init__.py'...\nCompiling 'substrate/watchdog/gateway_watchdog.py'...\nCompiling 'substrate/web.py'...\nListing 'scripts'...\nCompiling 'scripts/agent_hybrid_runner.py'...\nCompiling 'scripts/approval_lane_watch.py'...\nCompiling 'scripts/bridge_fix_login.py'...\nCompiling 'scripts/bridge_login.py'...\nCompiling 'scripts/bridge_login_gui.py'...\nCompiling 'scripts/bridge_setup.py'...\nCompiling 'scripts/chat_image_edit.py'...\nCompiling 'scripts/chat_image_edit_local.py'...\nCompiling 'scripts/chatbot.py'...\nCompiling 'scripts/credential_snapshots.py'...\nListing 'scripts/crypto'...\nCompiling 'scripts/crypto/backup_proton.py'...\nCompiling 'scripts/crypto/create_cf_dns_token.py'...\nCompiling 'scripts/crypto/export_site_data.py'...\nCompiling 'scripts/crypto/publish_custom_domain.py'...\nCompiling 'scripts/crypto/wallet_gen.py'...\nCompiling 'scripts/da_cookies.py'...\nCompiling 'scripts/daily_security_report.py'...\nCompiling 'scripts/ensure_agency.py'...\nCompiling 'scripts/generate_cosmic_wallpapers.py'...\nCompiling 'scripts/generate_status_page.py'...\nCompiling 'scripts/generate_system_docs.py'...\nCompiling 'scripts/inject_foundation_archive.py'...\nCompiling 'scripts/kilo_proxy.py'...\nCompiling 'scripts/original_render.py'...\nCompiling 'scripts/original_render_xl.py'...\nCompiling 'scripts/package_substrate.py'...\nCompiling 'scripts/probe_system.py'...\nCompiling 'scripts/proton_bridge_hook.py'...\nCompiling 'scripts/proton_connect.py'...\nCompiling 'scripts/remaster_pipeline.py'...\nCompiling 'scripts/run_chain.py'...\nCompiling 'scripts/send_research_report.py'...\nCompiling 'scripts/serve_dashboard.py'...\nCompiling 'scripts/serve_pipelines.py'...\nCompiling 'scripts/setup_gmail_lane.py'...\nCompiling 'scripts/site_content.py'...\nCompiling 'scripts/snapshot_guard.py'...\nCompiling 'scripts/substrate_cli.py'...\nCompiling 'scripts/substrate_lister.py'...\nListing 'scripts/templates'...\nCompiling 'scripts/test_gateway.py'...\nCompiling 'scripts/test_openclaw_ui.py'...\nCompiling 'scripts/test_openclaw_ui_exec.py'...\nCompiling 'scripts/unlock_bridge.py'...\nCompiling 'scripts/validate_docs.py'...\nCompiling 'scripts/validate_system_registry.py'...\nCompiling 'scripts/wait_for_mail_sync.py'...\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "httpx",
            "pytest",
            "-q",
            "tests/test_decentralized_governance.py"
          ],
          "command_text": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 4.388,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.78s\n",
          "stderr_tail": "Installed 12 packages in 16ms\n"
        }
      ],
      "failing_count": 0,
      "loop_status": "success",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 4.388
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260906-9109e4c",
        "pr_number": 0,
        "pr_url": "",
        "merge_attempted": false,
        "merged": false,
        "merge_attempts": 0,
        "message": "Failed to create PR from rolling branch.",
        "rebase_ok": true,
        "push_ok": true,
        "loop_index": 1
      }
    },
    {
      "loop_index": 2,
      "started_at": "2026-09-06T07:53:21.527205+00:00",
      "generated_at": "2026-09-06T07:53:22.829558+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "All deterministic checks in this loop succeeded."
      ],
      "risks": [
        "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
      ],
      "command_results": [
        {
          "command": [
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "substrate",
            "scripts",
            "tests"
          ],
          "command_text": "uv run --with ruff ruff check substrate scripts tests",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.03,
          "stdout_tail": "All checks passed!\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "python",
            "-m",
            "compileall",
            "substrate",
            "scripts"
          ],
          "command_text": "uv run python -m compileall substrate scripts",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.06,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/boot'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'substrate/watchdog'...\nListing 'scripts'...\nListing 'scripts/crypto'...\nListing 'scripts/templates'...\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "httpx",
            "pytest",
            "-q",
            "tests/test_decentralized_governance.py"
          ],
          "command_text": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 1.213,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.30s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 0,
      "loop_status": "success",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.213
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260906-9109e4c",
        "pr_number": 0,
        "pr_url": "",
        "merge_attempted": false,
        "merged": false,
        "merge_attempts": 0,
        "message": "Failed to create PR from rolling branch.",
        "rebase_ok": true,
        "push_ok": true,
        "loop_index": 2
      }
    },
    {
      "loop_index": 3,
      "started_at": "2026-09-06T07:53:26.594014+00:00",
      "generated_at": "2026-09-06T07:53:27.836885+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "All deterministic checks in this loop succeeded."
      ],
      "risks": [
        "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
      ],
      "command_results": [
        {
          "command": [
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "substrate",
            "scripts",
            "tests"
          ],
          "command_text": "uv run --with ruff ruff check substrate scripts tests",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.029,
          "stdout_tail": "All checks passed!\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "python",
            "-m",
            "compileall",
            "substrate",
            "scripts"
          ],
          "command_text": "uv run python -m compileall substrate scripts",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.06,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/boot'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'substrate/watchdog'...\nListing 'scripts'...\nListing 'scripts/crypto'...\nListing 'scripts/templates'...\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "httpx",
            "pytest",
            "-q",
            "tests/test_decentralized_governance.py"
          ],
          "command_text": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 1.154,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.29s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 0,
      "loop_status": "success",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.154
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260906-9109e4c",
        "pr_number": 0,
        "pr_url": "",
        "merge_attempted": false,
        "merged": false,
        "merge_attempts": 0,
        "message": "Failed to create PR from rolling branch.",
        "rebase_ok": true,
        "push_ok": true,
        "loop_index": 3
      }
    },
    {
      "loop_index": 4,
      "started_at": "2026-09-06T07:53:31.468044+00:00",
      "generated_at": "2026-09-06T07:53:32.734888+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "All deterministic checks in this loop succeeded."
      ],
      "risks": [
        "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
      ],
      "command_results": [
        {
          "command": [
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "substrate",
            "scripts",
            "tests"
          ],
          "command_text": "uv run --with ruff ruff check substrate scripts tests",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.029,
          "stdout_tail": "All checks passed!\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "python",
            "-m",
            "compileall",
            "substrate",
            "scripts"
          ],
          "command_text": "uv run python -m compileall substrate scripts",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.06,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/boot'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'substrate/watchdog'...\nListing 'scripts'...\nListing 'scripts/crypto'...\nListing 'scripts/templates'...\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "httpx",
            "pytest",
            "-q",
            "tests/test_decentralized_governance.py"
          ],
          "command_text": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 1.177,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.29s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 0,
      "loop_status": "success",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.177
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260906-9109e4c",
        "pr_number": 0,
        "pr_url": "",
        "merge_attempted": false,
        "merged": false,
        "merge_attempts": 0,
        "message": "Failed to create PR from rolling branch.",
        "rebase_ok": true,
        "push_ok": true,
        "loop_index": 4
      }
    },
    {
      "loop_index": 5,
      "started_at": "2026-09-06T07:53:36.551589+00:00",
      "generated_at": "2026-09-06T07:53:37.792451+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "All deterministic checks in this loop succeeded."
      ],
      "risks": [
        "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
      ],
      "command_results": [
        {
          "command": [
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "substrate",
            "scripts",
            "tests"
          ],
          "command_text": "uv run --with ruff ruff check substrate scripts tests",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.031,
          "stdout_tail": "All checks passed!\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "python",
            "-m",
            "compileall",
            "substrate",
            "scripts"
          ],
          "command_text": "uv run python -m compileall substrate scripts",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.06,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/boot'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'substrate/watchdog'...\nListing 'scripts'...\nListing 'scripts/crypto'...\nListing 'scripts/templates'...\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "httpx",
            "pytest",
            "-q",
            "tests/test_decentralized_governance.py"
          ],
          "command_text": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 1.151,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.28s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 0,
      "loop_status": "success",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.151
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260906-9109e4c",
        "pr_number": 0,
        "pr_url": "",
        "merge_attempted": false,
        "merged": false,
        "merge_attempts": 0,
        "message": "Failed to create PR from rolling branch.",
        "rebase_ok": true,
        "push_ok": true,
        "loop_index": 5
      }
    },
    {
      "loop_index": 6,
      "started_at": "2026-09-06T07:53:41.531447+00:00",
      "generated_at": "2026-09-06T07:53:42.771260+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "All deterministic checks in this loop succeeded."
      ],
      "risks": [
        "AGENT_CLOUD_COMMAND is not set; deep mode ran without cloud agent."
      ],
      "command_results": [
        {
          "command": [
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "substrate",
            "scripts",
            "tests"
          ],
          "command_text": "uv run --with ruff ruff check substrate scripts tests",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.029,
          "stdout_tail": "All checks passed!\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "python",
            "-m",
            "compileall",
            "substrate",
            "scripts"
          ],
          "command_text": "uv run python -m compileall substrate scripts",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 0.059,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/boot'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'substrate/watchdog'...\nListing 'scripts'...\nListing 'scripts/crypto'...\nListing 'scripts/templates'...\n",
          "stderr_tail": ""
        },
        {
          "command": [
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "httpx",
            "pytest",
            "-q",
            "tests/test_decentralized_governance.py"
          ],
          "command_text": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "return_code": 0,
          "ok": true,
          "duration_seconds": 1.151,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.29s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 0,
      "loop_status": "success",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.151
        }
      ]
    }
  ],
  "merge_history": [
    {
      "action": "pr_create_failed",
      "ok": false,
      "branch": "agent/swarm-20260906-9109e4c",
      "pr_number": 0,
      "pr_url": "",
      "merge_attempted": false,
      "merged": false,
      "merge_attempts": 0,
      "message": "Failed to create PR from rolling branch.",
      "rebase_ok": true,
      "push_ok": true,
      "loop_index": 1
    },
    {
      "action": "pr_create_failed",
      "ok": false,
      "branch": "agent/swarm-20260906-9109e4c",
      "pr_number": 0,
      "pr_url": "",
      "merge_attempted": false,
      "merged": false,
      "merge_attempts": 0,
      "message": "Failed to create PR from rolling branch.",
      "rebase_ok": true,
      "push_ok": true,
      "loop_index": 2
    },
    {
      "action": "pr_create_failed",
      "ok": false,
      "branch": "agent/swarm-20260906-9109e4c",
      "pr_number": 0,
      "pr_url": "",
      "merge_attempted": false,
      "merged": false,
      "merge_attempts": 0,
      "message": "Failed to create PR from rolling branch.",
      "rebase_ok": true,
      "push_ok": true,
      "loop_index": 3
    },
    {
      "action": "pr_create_failed",
      "ok": false,
      "branch": "agent/swarm-20260906-9109e4c",
      "pr_number": 0,
      "pr_url": "",
      "merge_attempted": false,
      "merged": false,
      "merge_attempts": 0,
      "message": "Failed to create PR from rolling branch.",
      "rebase_ok": true,
      "push_ok": true,
      "loop_index": 4
    },
    {
      "action": "pr_create_failed",
      "ok": false,
      "branch": "agent/swarm-20260906-9109e4c",
      "pr_number": 0,
      "pr_url": "",
      "merge_attempted": false,
      "merged": false,
      "merge_attempts": 0,
      "message": "Failed to create PR from rolling branch.",
      "rebase_ok": true,
      "push_ok": true,
      "loop_index": 5
    }
  ],
  "final_pr_url": "",
  "final_merge_state": "not_attempted",
  "git_context": {
    "current_branch": "agent/swarm-20260906-9109e4c",
    "target_branch": "main",
    "head_sha": "c184a437a5e27c849eb132402fc95f1deee63458",
    "target_sha": "9109e4cb087fd8ad49c86e867817f8dfa84ce158",
    "ahead_count": 5,
    "behind_count": 0,
    "diverged": false,
    "working_tree_clean_start": true,
    "working_tree_clean_end": true
  },
  "git_actions": [
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.404,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "main\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "0\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.044,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.421,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "main\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "0\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.006,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "bash",
        "scripts/agent_hybrid_publish.sh",
        "true",
        "main",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md",
        "1",
        "6",
        "20260906-9109e4c",
        "safe_gate",
        "1",
        "true"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 1 6 20260906-9109e4c safe_gate 1 true",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.582,
      "stdout_tail": "[agent/swarm-20260906-9109e4c 4dda28e] chore(agent): swarm loop 1/6 session 20260906-9109e4c\n 2 files changed, 786 insertions(+)\n create mode 100644 artifacts/agent-hybrid/agent_report.md\n create mode 100644 artifacts/agent-hybrid/agent_summary.json\nCurrent branch agent/swarm-20260906-9109e4c is up to date.\nbranch 'agent/swarm-20260906-9109e4c' set up to track 'origin/agent/swarm-20260906-9109e4c'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260906-9109e4c\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nSwitched to a new branch 'agent/swarm-20260906-9109e4c'\nremote: \nremote: Create a pull request for 'agent/swarm-20260906-9109e4c' on GitHub by visiting:        \nremote:      https://github.com/55515-code/orchestrator/pull/new/agent/swarm-20260906-9109e4c        \nremote: \nTo https://github.com/55515-code/orchestrator\n * [new branch]      agent/swarm-20260906-9109e4c -> agent/swarm-20260906-9109e4c\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
    },
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.354,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "agent/swarm-20260906-9109e4c\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "4dda28ee19018cb461f4994cc25560fa9e6f018e\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "1\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.005,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "bash",
        "scripts/agent_hybrid_publish.sh",
        "true",
        "main",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md",
        "2",
        "6",
        "20260906-9109e4c",
        "safe_gate",
        "1",
        "true"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 2 6 20260906-9109e4c safe_gate 1 true",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.389,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260906-9109e4c'.\n[agent/swarm-20260906-9109e4c 8cf0ea8] chore(agent): swarm loop 2/6 session 20260906-9109e4c\n 2 files changed, 495 insertions(+), 18 deletions(-)\nCurrent branch agent/swarm-20260906-9109e4c is up to date.\nbranch 'agent/swarm-20260906-9109e4c' set up to track 'origin/agent/swarm-20260906-9109e4c'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260906-9109e4c\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260906-9109e4c'\nTo https://github.com/55515-code/orchestrator\n   4dda28e..8cf0ea8  agent/swarm-20260906-9109e4c -> agent/swarm-20260906-9109e4c\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
    },
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.374,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "agent/swarm-20260906-9109e4c\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "8cf0ea8843bb679fd4d77e088019be99cc978f9c\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "2\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.006,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "bash",
        "scripts/agent_hybrid_publish.sh",
        "true",
        "main",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md",
        "3",
        "6",
        "20260906-9109e4c",
        "safe_gate",
        "1",
        "true"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 3 6 20260906-9109e4c safe_gate 1 true",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.236,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260906-9109e4c'.\n[agent/swarm-20260906-9109e4c 73c002b] chore(agent): swarm loop 3/6 session 20260906-9109e4c\n 2 files changed, 486 insertions(+), 11 deletions(-)\nCurrent branch agent/swarm-20260906-9109e4c is up to date.\nbranch 'agent/swarm-20260906-9109e4c' set up to track 'origin/agent/swarm-20260906-9109e4c'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260906-9109e4c\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260906-9109e4c'\nTo https://github.com/55515-code/orchestrator\n   8cf0ea8..73c002b  agent/swarm-20260906-9109e4c -> agent/swarm-20260906-9109e4c\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
    },
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.357,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "agent/swarm-20260906-9109e4c\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "73c002be06c3bf8bbf5475f9844e417a1a47d4eb\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "3\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.006,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "bash",
        "scripts/agent_hybrid_publish.sh",
        "true",
        "main",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md",
        "4",
        "6",
        "20260906-9109e4c",
        "safe_gate",
        "1",
        "true"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 4 6 20260906-9109e4c safe_gate 1 true",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.438,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260906-9109e4c'.\n[agent/swarm-20260906-9109e4c 08bba83] chore(agent): swarm loop 4/6 session 20260906-9109e4c\n 2 files changed, 486 insertions(+), 11 deletions(-)\nCurrent branch agent/swarm-20260906-9109e4c is up to date.\nbranch 'agent/swarm-20260906-9109e4c' set up to track 'origin/agent/swarm-20260906-9109e4c'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260906-9109e4c\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260906-9109e4c'\nTo https://github.com/55515-code/orchestrator\n   73c002b..08bba83  agent/swarm-20260906-9109e4c -> agent/swarm-20260906-9109e4c\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
    },
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.378,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "agent/swarm-20260906-9109e4c\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "08bba833b8d876d37184bc1036d3e39b77f23b20\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "4\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.006,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "bash",
        "scripts/agent_hybrid_publish.sh",
        "true",
        "main",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json",
        "/home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md",
        "5",
        "6",
        "20260906-9109e4c",
        "safe_gate",
        "1",
        "true"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 5 6 20260906-9109e4c safe_gate 1 true",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.338,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260906-9109e4c'.\n[agent/swarm-20260906-9109e4c c184a43] chore(agent): swarm loop 5/6 session 20260906-9109e4c\n 2 files changed, 486 insertions(+), 11 deletions(-)\nCurrent branch agent/swarm-20260906-9109e4c is up to date.\nbranch 'agent/swarm-20260906-9109e4c' set up to track 'origin/agent/swarm-20260906-9109e4c'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260906-9109e4c\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260906-9109e4c'\nTo https://github.com/55515-code/orchestrator\n   08bba83..c184a43  agent/swarm-20260906-9109e4c -> agent/swarm-20260906-9109e4c\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
    },
    {
      "command": [
        "git",
        "rev-parse",
        "--is-inside-work-tree"
      ],
      "command_text": "git rev-parse --is-inside-work-tree",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "true\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "fetch",
        "--all",
        "--prune"
      ],
      "command_text": "git fetch --all --prune",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.34,
      "stdout_tail": "",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "branch",
        "--show-current"
      ],
      "command_text": "git branch --show-current",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "agent/swarm-20260906-9109e4c\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "HEAD"
      ],
      "command_text": "git rev-parse HEAD",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "c184a437a5e27c849eb132402fc95f1deee63458\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-parse",
        "origin/main"
      ],
      "command_text": "git rev-parse origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.001,
      "stdout_tail": "9109e4cb087fd8ad49c86e867817f8dfa84ce158\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main"
      ],
      "command_text": "git rev-list --left-right --count HEAD...origin/main",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.002,
      "stdout_tail": "5\t0\n",
      "stderr_tail": ""
    },
    {
      "command": [
        "git",
        "status",
        "--porcelain"
      ],
      "command_text": "git status --porcelain",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 0.006,
      "stdout_tail": "",
      "stderr_tail": ""
    }
  ]
}
```
