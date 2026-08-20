# Agent Hybrid Report

- Generated at: 2026-08-20T03:57:55.916743+00:00
- Session: `20260820-c4b97d9`
- Mode: `deep`
- Loop count: `6`
- Route: `cloud_agent`
- Target branch: `main`
- Allow write: `True`

## Repo health + failing surfaces

- Loop 1: 1 command(s) failed during mode 'deep'.
- Loop 1: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)
- Loop 2: 1 command(s) failed during mode 'deep'.
- Loop 2: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)
- Loop 3: 1 command(s) failed during mode 'deep'.
- Loop 3: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)
- Loop 4: 1 command(s) failed during mode 'deep'.
- Loop 4: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)
- Loop 5: 1 command(s) failed during mode 'deep'.
- Loop 5: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)

## Deep research findings with sources/risks

- Source anchors reviewed: `README.md`, `docs/community-cycle.md`, `docs/lifecycle.md`, `CONTRIBUTING.md`.
- Strategic direction reviewed: `docs/security-toolkit-roadmap.md`.
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
| 1 | partial_failure | deterministic | 1 | pr_create_failed |
| 2 | partial_failure | deterministic | 1 | pr_create_failed |
| 3 | partial_failure | deterministic | 1 | pr_create_failed |
| 4 | partial_failure | deterministic | 1 | pr_create_failed |
| 5 | partial_failure | deterministic | 1 | n/a |

- Loop 1 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 2 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 3 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 4 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0
- Loop 5 test `uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py` -> ok=True rc=0

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

## Compatibility notes

- Existing CLI/API compatibility remains required; no direct-merge-to-main bypass is used.
- Safe-gate merge requires clean rebase/push and successful loop checks.

## Unresolved questions

- None recorded by this automated cycle.

## Git sync posture summary

- Current branch: `agent/swarm-20260820-c4b97d9`
- Target branch: `main`
- Ahead: `4` | Behind: `0` | Diverged: `False`
- PR URL: `n/a`
- Final merge state: `not_attempted`

## Raw summary JSON

```json
{
  "status": "partial_failure",
  "mode": "deep",
  "route": "cloud_agent",
  "target_branch": "main",
  "allow_write": true,
  "session_id": "20260820-c4b97d9",
  "loop_count": 6,
  "generated_at": "2026-08-20T03:57:55.916743+00:00",
  "started_at": "2026-08-20T03:57:28.946594+00:00",
  "findings": [
    "Loop 1: 1 command(s) failed during mode 'deep'.",
    "Loop 1: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)",
    "Loop 2: 1 command(s) failed during mode 'deep'.",
    "Loop 2: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)",
    "Loop 3: 1 command(s) failed during mode 'deep'.",
    "Loop 3: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)",
    "Loop 4: 1 command(s) failed during mode 'deep'.",
    "Loop 4: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)",
    "Loop 5: 1 command(s) failed during mode 'deep'.",
    "Loop 5: Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)"
  ],
  "risks": [
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
      "duration_seconds": 3.532,
      "loop": 1
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.191,
      "loop": 2
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.183,
      "loop": 3
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.176,
      "loop": 4
    },
    {
      "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
      "ok": true,
      "return_code": 0,
      "duration_seconds": 1.189,
      "loop": 5
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
      "started_at": "2026-08-20T03:57:29.383397+00:00",
      "generated_at": "2026-08-20T03:57:33.762128+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "1 command(s) failed during mode 'deep'.",
        "Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)"
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
          "return_code": 1,
          "ok": false,
          "duration_seconds": 0.471,
          "stdout_tail": "yield f\"data: {json.dumps(payload)}\\n\\n\"\n1841 |                 await asyncio.sleep(2)  # Update every 2 seconds\n1842 |             except Exception as e:\n     |                    ^^^^^^^^^\n1843 |                 print(f\"Error in metrics stream: {e}\")\n1844 |                 await asyncio.sleep(5)\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1913:12\n     |\n1911 |     try:\n1912 |         payload = await request.json()\n1913 |     except Exception as e:\n     |            ^^^^^^^^^\n1914 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1936:16\n     |\n1934 |             else:\n1935 |                 responses.append({\"message_id\": message.message_id, \"status\": \"processed\"})\n1936 |         except Exception as e:\n     |                ^^^^^^^^^\n1937 |             logger.error(f\"Error processing message {message.message_id}: {e}\")\n1938 |             responses.append({\"message_id\": message.message_id, \"status\": \"error\", \"error\": str(e)})\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1956:12\n     |\n1954 |     try:\n1955 |         body = await request.json()\n1956 |     except Exception as e:\n     |            ^^^^^^^^^\n1957 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1970:12\n     |\n1968 |         append_log(RUNTIME.root, \"send\", f\"outbound message to {user_id} via {service_id}\")\n1969 |         return JSONResponse({\"status\": \"sent\", \"result\": result})\n1970 |     except Exception as e:\n     |            ^^^^^^^^^\n1971 |         logger.error(f\"Error sending message: {e}\")\n1972 |         raise HTTPException(status_code=500, detail=f\"Failed to send message: {e}\")\n     |\n\nS110 `try`-`except`-`pass` detected, consider logging the exception\n    --> substrate/web.py:2175:5\n     |\n2173 |       try:\n2174 |           message_id = result[\"messages\"][0][\"id\"]\n2175 | /     except Exception:  # noqa: BLE001\n2176 | |         pass\n     | |____________^\n2177 |       return JSONResponse(\n2178 |           {\"status\": \"success\", \"message\": \"Test message sent\", \"message_id\": message_id}\n     |\n\nI001 [*] Import block is un-sorted or un-formatted\n --> tests/test_crypto_backup.py:1:1\n  |\n1 | / from pathlib import Path\n2 | | import tempfile\n3 | | import unittest\n4 | |\n5 | | from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir\n  | |________________________________________________________________________________^\n6 |\n7 |   DIRECTIVE = \"human: test backup\"\n  |\nhelp: Organize imports\n  |\n  - from pathlib import Path\n1 | import tempfile\n2 | import unittest\n3 + from pathlib import Path\n4 |\n  |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:13:8\n   |\n11 | try:\n12 |     from mnemonic import Mnemonic\n13 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n14 |     Mnemonic = None  # type: ignore[assignment,misc]\n   |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:19:8\n   |\n17 | try:\n18 |     from eth_account import Account\n19 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n20 |     Account = None  # type: ignore[assignment,misc]\n   |\n\nDTZ001 `datetime.datetime()` called without a `tzinfo` argument\n  --> tests/test_gh_sync.py:28:26\n   |\n26 |         \"\"\"Test converting sync state to dictionary.\"\"\"\n27 |         state = SyncState(\n28 |             last_sync_at=datetime(2024, 1, 1, 12, 0, 0),\n   |                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n29 |             last_commit_sha=\"abc123\",\n30 |             last_tag=\"v1.0.0\",\n   |\nhelp: Pass a `datetime.timezone` object to the `tzinfo` parameter\n\nFound 308 errors.\n[*] 35 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).\n",
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
          "duration_seconds": 0.375,
          "stdout_tail": "y'...\nCompiling 'substrate/integrations.py'...\nCompiling 'substrate/iphone_panel.py'...\nCompiling 'substrate/learning.py'...\nCompiling 'substrate/models.py'...\nListing 'substrate/monitoring'...\nCompiling 'substrate/monitoring/__init__.py'...\nCompiling 'substrate/monitoring/crypto_alerts.py'...\nCompiling 'substrate/orchestrator.py'...\nCompiling 'substrate/panel_settings.py'...\nListing 'substrate/pipelines'...\nCompiling 'substrate/pipelines/__init__.py'...\nCompiling 'substrate/pipelines/api.py'...\nCompiling 'substrate/pipelines/engine.py'...\nCompiling 'substrate/pipelines/expansion_trigger.py'...\nCompiling 'substrate/pipelines/models.py'...\nCompiling 'substrate/pipelines/quality_gate.py'...\nCompiling 'substrate/pipelines/registry.py'...\nCompiling 'substrate/pipelines/resource_pipeline.py'...\nCompiling 'substrate/pipelines/triggers.py'...\nCompiling 'substrate/prefill_proxy.py'...\nCompiling 'substrate/proton_support.py'...\nCompiling 'substrate/providers.py'...\nCompiling 'substrate/registry.py'...\nCompiling 'substrate/reliability.py'...\nCompiling 'substrate/render.py'...\nListing 'substrate/render_engines'...\nCompiling 'substrate/render_engines/__init__.py'...\nCompiling 'substrate/render_engines/base.py'...\nCompiling 'substrate/render_engines/hosted.py'...\nCompiling 'substrate/render_engines/local_diffusers.py'...\nCompiling 'substrate/research.py'...\nCompiling 'substrate/resource_orchestration.py'...\nListing 'substrate/resources'...\nCompiling 'substrate/resources/__init__.py'...\nCompiling 'substrate/resources/api_access.py'...\nListing 'substrate/security'...\nCompiling 'substrate/security/__init__.py'...\nCompiling 'substrate/security/abuse_detection.py'...\nCompiling 'substrate/security/audit_trail.py'...\nCompiling 'substrate/settings.py'...\nCompiling 'substrate/site_content.py'...\nCompiling 'substrate/snapshots.py'...\nCompiling 'substrate/standards.py'...\nListing 'substrate/static'...\nCompiling 'substrate/stats.py'...\nCompiling 'substrate/swarm_control.py'...\nCompiling 'substrate/task_cache.py'...\nListing 'substrate/templates'...\nCompiling 'substrate/tooling.py'...\nCompiling 'substrate/vault.py'...\nCompiling 'substrate/web.py'...\nListing 'scripts'...\nCompiling 'scripts/agent_hybrid_runner.py'...\nCompiling 'scripts/approval_lane_watch.py'...\nCompiling 'scripts/bridge_fix_login.py'...\nCompiling 'scripts/bridge_login.py'...\nCompiling 'scripts/bridge_login_gui.py'...\nCompiling 'scripts/bridge_setup.py'...\nCompiling 'scripts/chat_image_edit.py'...\nCompiling 'scripts/chat_image_edit_local.py'...\nCompiling 'scripts/chatbot.py'...\nListing 'scripts/crypto'...\nCompiling 'scripts/crypto/backup_proton.py'...\nCompiling 'scripts/crypto/create_cf_dns_token.py'...\nCompiling 'scripts/crypto/export_site_data.py'...\nCompiling 'scripts/crypto/publish_custom_domain.py'...\nCompiling 'scripts/crypto/wallet_gen.py'...\nCompiling 'scripts/da_cookies.py'...\nCompiling 'scripts/daily_security_report.py'...\nCompiling 'scripts/ensure_agency.py'...\nCompiling 'scripts/generate_cosmic_wallpapers.py'...\nCompiling 'scripts/generate_status_page.py'...\nCompiling 'scripts/inject_foundation_archive.py'...\nCompiling 'scripts/kilo_proxy.py'...\nCompiling 'scripts/original_render.py'...\nCompiling 'scripts/original_render_xl.py'...\nCompiling 'scripts/package_substrate.py'...\nCompiling 'scripts/probe_system.py'...\nCompiling 'scripts/proton_bridge_hook.py'...\nCompiling 'scripts/proton_connect.py'...\nCompiling 'scripts/remaster_pipeline.py'...\nCompiling 'scripts/run_chain.py'...\nCompiling 'scripts/send_research_report.py'...\nCompiling 'scripts/serve_dashboard.py'...\nCompiling 'scripts/serve_pipelines.py'...\nCompiling 'scripts/setup_gmail_lane.py'...\nCompiling 'scripts/site_content.py'...\nCompiling 'scripts/substrate_cli.py'...\nCompiling 'scripts/substrate_lister.py'...\nCompiling 'scripts/test_gateway.py'...\nCompiling 'scripts/test_openclaw_ui.py'...\nCompiling 'scripts/test_openclaw_ui_exec.py'...\nCompiling 'scripts/unlock_bridge.py'...\nCompiling 'scripts/wait_for_mail_sync.py'...\n",
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
          "duration_seconds": 3.532,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.80s\n",
          "stderr_tail": "Installed 12 packages in 10ms\n"
        }
      ],
      "failing_count": 1,
      "loop_status": "partial_failure",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 3.532
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260820-c4b97d9",
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
      "started_at": "2026-08-20T03:57:38.260372+00:00",
      "generated_at": "2026-08-20T03:57:39.572824+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "1 command(s) failed during mode 'deep'.",
        "Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)"
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
          "return_code": 1,
          "ok": false,
          "duration_seconds": 0.065,
          "stdout_tail": "yield f\"data: {json.dumps(payload)}\\n\\n\"\n1841 |                 await asyncio.sleep(2)  # Update every 2 seconds\n1842 |             except Exception as e:\n     |                    ^^^^^^^^^\n1843 |                 print(f\"Error in metrics stream: {e}\")\n1844 |                 await asyncio.sleep(5)\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1913:12\n     |\n1911 |     try:\n1912 |         payload = await request.json()\n1913 |     except Exception as e:\n     |            ^^^^^^^^^\n1914 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1936:16\n     |\n1934 |             else:\n1935 |                 responses.append({\"message_id\": message.message_id, \"status\": \"processed\"})\n1936 |         except Exception as e:\n     |                ^^^^^^^^^\n1937 |             logger.error(f\"Error processing message {message.message_id}: {e}\")\n1938 |             responses.append({\"message_id\": message.message_id, \"status\": \"error\", \"error\": str(e)})\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1956:12\n     |\n1954 |     try:\n1955 |         body = await request.json()\n1956 |     except Exception as e:\n     |            ^^^^^^^^^\n1957 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1970:12\n     |\n1968 |         append_log(RUNTIME.root, \"send\", f\"outbound message to {user_id} via {service_id}\")\n1969 |         return JSONResponse({\"status\": \"sent\", \"result\": result})\n1970 |     except Exception as e:\n     |            ^^^^^^^^^\n1971 |         logger.error(f\"Error sending message: {e}\")\n1972 |         raise HTTPException(status_code=500, detail=f\"Failed to send message: {e}\")\n     |\n\nS110 `try`-`except`-`pass` detected, consider logging the exception\n    --> substrate/web.py:2175:5\n     |\n2173 |       try:\n2174 |           message_id = result[\"messages\"][0][\"id\"]\n2175 | /     except Exception:  # noqa: BLE001\n2176 | |         pass\n     | |____________^\n2177 |       return JSONResponse(\n2178 |           {\"status\": \"success\", \"message\": \"Test message sent\", \"message_id\": message_id}\n     |\n\nI001 [*] Import block is un-sorted or un-formatted\n --> tests/test_crypto_backup.py:1:1\n  |\n1 | / from pathlib import Path\n2 | | import tempfile\n3 | | import unittest\n4 | |\n5 | | from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir\n  | |________________________________________________________________________________^\n6 |\n7 |   DIRECTIVE = \"human: test backup\"\n  |\nhelp: Organize imports\n  |\n  - from pathlib import Path\n1 | import tempfile\n2 | import unittest\n3 + from pathlib import Path\n4 |\n  |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:13:8\n   |\n11 | try:\n12 |     from mnemonic import Mnemonic\n13 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n14 |     Mnemonic = None  # type: ignore[assignment,misc]\n   |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:19:8\n   |\n17 | try:\n18 |     from eth_account import Account\n19 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n20 |     Account = None  # type: ignore[assignment,misc]\n   |\n\nDTZ001 `datetime.datetime()` called without a `tzinfo` argument\n  --> tests/test_gh_sync.py:28:26\n   |\n26 |         \"\"\"Test converting sync state to dictionary.\"\"\"\n27 |         state = SyncState(\n28 |             last_sync_at=datetime(2024, 1, 1, 12, 0, 0),\n   |                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n29 |             last_commit_sha=\"abc123\",\n30 |             last_tag=\"v1.0.0\",\n   |\nhelp: Pass a `datetime.timezone` object to the `tzinfo` parameter\n\nFound 308 errors.\n[*] 35 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).\n",
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
          "duration_seconds": 0.057,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'scripts'...\nListing 'scripts/crypto'...\n",
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
          "duration_seconds": 1.191,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.30s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 1,
      "loop_status": "partial_failure",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.191
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260820-c4b97d9",
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
      "started_at": "2026-08-20T03:57:43.458373+00:00",
      "generated_at": "2026-08-20T03:57:44.759392+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "1 command(s) failed during mode 'deep'.",
        "Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)"
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
          "return_code": 1,
          "ok": false,
          "duration_seconds": 0.061,
          "stdout_tail": "yield f\"data: {json.dumps(payload)}\\n\\n\"\n1841 |                 await asyncio.sleep(2)  # Update every 2 seconds\n1842 |             except Exception as e:\n     |                    ^^^^^^^^^\n1843 |                 print(f\"Error in metrics stream: {e}\")\n1844 |                 await asyncio.sleep(5)\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1913:12\n     |\n1911 |     try:\n1912 |         payload = await request.json()\n1913 |     except Exception as e:\n     |            ^^^^^^^^^\n1914 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1936:16\n     |\n1934 |             else:\n1935 |                 responses.append({\"message_id\": message.message_id, \"status\": \"processed\"})\n1936 |         except Exception as e:\n     |                ^^^^^^^^^\n1937 |             logger.error(f\"Error processing message {message.message_id}: {e}\")\n1938 |             responses.append({\"message_id\": message.message_id, \"status\": \"error\", \"error\": str(e)})\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1956:12\n     |\n1954 |     try:\n1955 |         body = await request.json()\n1956 |     except Exception as e:\n     |            ^^^^^^^^^\n1957 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1970:12\n     |\n1968 |         append_log(RUNTIME.root, \"send\", f\"outbound message to {user_id} via {service_id}\")\n1969 |         return JSONResponse({\"status\": \"sent\", \"result\": result})\n1970 |     except Exception as e:\n     |            ^^^^^^^^^\n1971 |         logger.error(f\"Error sending message: {e}\")\n1972 |         raise HTTPException(status_code=500, detail=f\"Failed to send message: {e}\")\n     |\n\nS110 `try`-`except`-`pass` detected, consider logging the exception\n    --> substrate/web.py:2175:5\n     |\n2173 |       try:\n2174 |           message_id = result[\"messages\"][0][\"id\"]\n2175 | /     except Exception:  # noqa: BLE001\n2176 | |         pass\n     | |____________^\n2177 |       return JSONResponse(\n2178 |           {\"status\": \"success\", \"message\": \"Test message sent\", \"message_id\": message_id}\n     |\n\nI001 [*] Import block is un-sorted or un-formatted\n --> tests/test_crypto_backup.py:1:1\n  |\n1 | / from pathlib import Path\n2 | | import tempfile\n3 | | import unittest\n4 | |\n5 | | from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir\n  | |________________________________________________________________________________^\n6 |\n7 |   DIRECTIVE = \"human: test backup\"\n  |\nhelp: Organize imports\n  |\n  - from pathlib import Path\n1 | import tempfile\n2 | import unittest\n3 + from pathlib import Path\n4 |\n  |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:13:8\n   |\n11 | try:\n12 |     from mnemonic import Mnemonic\n13 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n14 |     Mnemonic = None  # type: ignore[assignment,misc]\n   |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:19:8\n   |\n17 | try:\n18 |     from eth_account import Account\n19 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n20 |     Account = None  # type: ignore[assignment,misc]\n   |\n\nDTZ001 `datetime.datetime()` called without a `tzinfo` argument\n  --> tests/test_gh_sync.py:28:26\n   |\n26 |         \"\"\"Test converting sync state to dictionary.\"\"\"\n27 |         state = SyncState(\n28 |             last_sync_at=datetime(2024, 1, 1, 12, 0, 0),\n   |                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n29 |             last_commit_sha=\"abc123\",\n30 |             last_tag=\"v1.0.0\",\n   |\nhelp: Pass a `datetime.timezone` object to the `tzinfo` parameter\n\nFound 308 errors.\n[*] 35 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).\n",
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
          "duration_seconds": 0.057,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'scripts'...\nListing 'scripts/crypto'...\n",
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
          "duration_seconds": 1.183,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.29s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 1,
      "loop_status": "partial_failure",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.183
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260820-c4b97d9",
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
      "started_at": "2026-08-20T03:57:48.721076+00:00",
      "generated_at": "2026-08-20T03:57:50.016876+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "1 command(s) failed during mode 'deep'.",
        "Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)"
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
          "return_code": 1,
          "ok": false,
          "duration_seconds": 0.063,
          "stdout_tail": "yield f\"data: {json.dumps(payload)}\\n\\n\"\n1841 |                 await asyncio.sleep(2)  # Update every 2 seconds\n1842 |             except Exception as e:\n     |                    ^^^^^^^^^\n1843 |                 print(f\"Error in metrics stream: {e}\")\n1844 |                 await asyncio.sleep(5)\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1913:12\n     |\n1911 |     try:\n1912 |         payload = await request.json()\n1913 |     except Exception as e:\n     |            ^^^^^^^^^\n1914 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1936:16\n     |\n1934 |             else:\n1935 |                 responses.append({\"message_id\": message.message_id, \"status\": \"processed\"})\n1936 |         except Exception as e:\n     |                ^^^^^^^^^\n1937 |             logger.error(f\"Error processing message {message.message_id}: {e}\")\n1938 |             responses.append({\"message_id\": message.message_id, \"status\": \"error\", \"error\": str(e)})\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1956:12\n     |\n1954 |     try:\n1955 |         body = await request.json()\n1956 |     except Exception as e:\n     |            ^^^^^^^^^\n1957 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1970:12\n     |\n1968 |         append_log(RUNTIME.root, \"send\", f\"outbound message to {user_id} via {service_id}\")\n1969 |         return JSONResponse({\"status\": \"sent\", \"result\": result})\n1970 |     except Exception as e:\n     |            ^^^^^^^^^\n1971 |         logger.error(f\"Error sending message: {e}\")\n1972 |         raise HTTPException(status_code=500, detail=f\"Failed to send message: {e}\")\n     |\n\nS110 `try`-`except`-`pass` detected, consider logging the exception\n    --> substrate/web.py:2175:5\n     |\n2173 |       try:\n2174 |           message_id = result[\"messages\"][0][\"id\"]\n2175 | /     except Exception:  # noqa: BLE001\n2176 | |         pass\n     | |____________^\n2177 |       return JSONResponse(\n2178 |           {\"status\": \"success\", \"message\": \"Test message sent\", \"message_id\": message_id}\n     |\n\nI001 [*] Import block is un-sorted or un-formatted\n --> tests/test_crypto_backup.py:1:1\n  |\n1 | / from pathlib import Path\n2 | | import tempfile\n3 | | import unittest\n4 | |\n5 | | from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir\n  | |________________________________________________________________________________^\n6 |\n7 |   DIRECTIVE = \"human: test backup\"\n  |\nhelp: Organize imports\n  |\n  - from pathlib import Path\n1 | import tempfile\n2 | import unittest\n3 + from pathlib import Path\n4 |\n  |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:13:8\n   |\n11 | try:\n12 |     from mnemonic import Mnemonic\n13 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n14 |     Mnemonic = None  # type: ignore[assignment,misc]\n   |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:19:8\n   |\n17 | try:\n18 |     from eth_account import Account\n19 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n20 |     Account = None  # type: ignore[assignment,misc]\n   |\n\nDTZ001 `datetime.datetime()` called without a `tzinfo` argument\n  --> tests/test_gh_sync.py:28:26\n   |\n26 |         \"\"\"Test converting sync state to dictionary.\"\"\"\n27 |         state = SyncState(\n28 |             last_sync_at=datetime(2024, 1, 1, 12, 0, 0),\n   |                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n29 |             last_commit_sha=\"abc123\",\n30 |             last_tag=\"v1.0.0\",\n   |\nhelp: Pass a `datetime.timezone` object to the `tzinfo` parameter\n\nFound 308 errors.\n[*] 35 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).\n",
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
          "duration_seconds": 0.057,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'scripts'...\nListing 'scripts/crypto'...\n",
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
          "duration_seconds": 1.176,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.30s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 1,
      "loop_status": "partial_failure",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.176
        }
      ],
      "publish_result": {
        "action": "pr_create_failed",
        "ok": false,
        "branch": "agent/swarm-20260820-c4b97d9",
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
      "started_at": "2026-08-20T03:57:54.004193+00:00",
      "generated_at": "2026-08-20T03:57:55.315436+00:00",
      "route": "deterministic",
      "cloud_attempted": false,
      "cloud_success": false,
      "cloud_note": "Cloud command not configured; skipping cloud route.",
      "findings": [
        "1 command(s) failed during mode 'deep'.",
        "Failed: uv run --with ruff ruff check substrate scripts tests (rc=1)"
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
          "return_code": 1,
          "ok": false,
          "duration_seconds": 0.065,
          "stdout_tail": "yield f\"data: {json.dumps(payload)}\\n\\n\"\n1841 |                 await asyncio.sleep(2)  # Update every 2 seconds\n1842 |             except Exception as e:\n     |                    ^^^^^^^^^\n1843 |                 print(f\"Error in metrics stream: {e}\")\n1844 |                 await asyncio.sleep(5)\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1913:12\n     |\n1911 |     try:\n1912 |         payload = await request.json()\n1913 |     except Exception as e:\n     |            ^^^^^^^^^\n1914 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1936:16\n     |\n1934 |             else:\n1935 |                 responses.append({\"message_id\": message.message_id, \"status\": \"processed\"})\n1936 |         except Exception as e:\n     |                ^^^^^^^^^\n1937 |             logger.error(f\"Error processing message {message.message_id}: {e}\")\n1938 |             responses.append({\"message_id\": message.message_id, \"status\": \"error\", \"error\": str(e)})\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1956:12\n     |\n1954 |     try:\n1955 |         body = await request.json()\n1956 |     except Exception as e:\n     |            ^^^^^^^^^\n1957 |         raise HTTPException(status_code=400, detail=f\"Invalid JSON: {e}\")\n     |\n\nBLE001 Do not catch blind exception: `Exception`\n    --> substrate/web.py:1970:12\n     |\n1968 |         append_log(RUNTIME.root, \"send\", f\"outbound message to {user_id} via {service_id}\")\n1969 |         return JSONResponse({\"status\": \"sent\", \"result\": result})\n1970 |     except Exception as e:\n     |            ^^^^^^^^^\n1971 |         logger.error(f\"Error sending message: {e}\")\n1972 |         raise HTTPException(status_code=500, detail=f\"Failed to send message: {e}\")\n     |\n\nS110 `try`-`except`-`pass` detected, consider logging the exception\n    --> substrate/web.py:2175:5\n     |\n2173 |       try:\n2174 |           message_id = result[\"messages\"][0][\"id\"]\n2175 | /     except Exception:  # noqa: BLE001\n2176 | |         pass\n     | |____________^\n2177 |       return JSONResponse(\n2178 |           {\"status\": \"success\", \"message\": \"Test message sent\", \"message_id\": message_id}\n     |\n\nI001 [*] Import block is un-sorted or un-formatted\n --> tests/test_crypto_backup.py:1:1\n  |\n1 | / from pathlib import Path\n2 | | import tempfile\n3 | | import unittest\n4 | |\n5 | | from substrate.crypto import WalletManager, backup_wallet_seeds, proton_sync_dir\n  | |________________________________________________________________________________^\n6 |\n7 |   DIRECTIVE = \"human: test backup\"\n  |\nhelp: Organize imports\n  |\n  - from pathlib import Path\n1 | import tempfile\n2 | import unittest\n3 + from pathlib import Path\n4 |\n  |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:13:8\n   |\n11 | try:\n12 |     from mnemonic import Mnemonic\n13 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n14 |     Mnemonic = None  # type: ignore[assignment,misc]\n   |\n\nBLE001 Do not catch blind exception: `Exception`\n  --> tests/test_crypto_backup.py:19:8\n   |\n17 | try:\n18 |     from eth_account import Account\n19 | except Exception:  # pragma: no cover - optional crypto extra\n   |        ^^^^^^^^^\n20 |     Account = None  # type: ignore[assignment,misc]\n   |\n\nDTZ001 `datetime.datetime()` called without a `tzinfo` argument\n  --> tests/test_gh_sync.py:28:26\n   |\n26 |         \"\"\"Test converting sync state to dictionary.\"\"\"\n27 |         state = SyncState(\n28 |             last_sync_at=datetime(2024, 1, 1, 12, 0, 0),\n   |                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n29 |             last_commit_sha=\"abc123\",\n30 |             last_tag=\"v1.0.0\",\n   |\nhelp: Pass a `datetime.timezone` object to the `tzinfo` parameter\n\nFound 308 errors.\n[*] 35 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).\n",
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
          "duration_seconds": 0.057,
          "stdout_tail": "Listing 'substrate'...\nListing 'substrate/agents'...\nListing 'substrate/assets'...\nListing 'substrate/chatbot'...\nListing 'substrate/chatbot/static'...\nListing 'substrate/credentials'...\nListing 'substrate/crypto'...\nListing 'substrate/dashboard'...\nListing 'substrate/gateway'...\nListing 'substrate/gateway/plugins'...\nListing 'substrate/gh_sync'...\nListing 'substrate/monitoring'...\nListing 'substrate/pipelines'...\nListing 'substrate/render_engines'...\nListing 'substrate/resources'...\nListing 'substrate/security'...\nListing 'substrate/static'...\nListing 'substrate/templates'...\nListing 'scripts'...\nListing 'scripts/crypto'...\n",
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
          "duration_seconds": 1.189,
          "stdout_tail": ".............                                                            [100%]\n13 passed in 0.30s\n",
          "stderr_tail": ""
        }
      ],
      "failing_count": 1,
      "loop_status": "partial_failure",
      "test_results": [
        {
          "command": "uv run --with pytest --with httpx pytest -q tests/test_decentralized_governance.py",
          "ok": true,
          "return_code": 0,
          "duration_seconds": 1.189
        }
      ]
    }
  ],
  "merge_history": [
    {
      "action": "pr_create_failed",
      "ok": false,
      "branch": "agent/swarm-20260820-c4b97d9",
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
      "branch": "agent/swarm-20260820-c4b97d9",
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
      "branch": "agent/swarm-20260820-c4b97d9",
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
      "branch": "agent/swarm-20260820-c4b97d9",
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
  ],
  "final_pr_url": "",
  "final_merge_state": "not_attempted",
  "git_context": {
    "current_branch": "agent/swarm-20260820-c4b97d9",
    "target_branch": "main",
    "head_sha": "5c668c4b7985c17c713ca8b47480d5c5a5509d8a",
    "target_sha": "c4b97d903f437ac9b3f4fb22de536c9efd59217d",
    "ahead_count": 4,
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
      "duration_seconds": 0.001,
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
      "duration_seconds": 0.39,
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
      "duration_seconds": 0.039,
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
      "duration_seconds": 0.388,
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
        "1",
        "6",
        "20260820-c4b97d9",
        "safe_gate",
        "1",
        "false"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 1 6 20260820-c4b97d9 safe_gate 1 false",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 4.093,
      "stdout_tail": "[agent/swarm-20260820-c4b97d9 6a8d2e9] chore(agent): swarm loop 1/6 session 20260820-c4b97d9\n 2 files changed, 791 insertions(+)\n create mode 100644 artifacts/agent-hybrid/agent_report.md\n create mode 100644 artifacts/agent-hybrid/agent_summary.json\nCurrent branch agent/swarm-20260820-c4b97d9 is up to date.\nbranch 'agent/swarm-20260820-c4b97d9' set up to track 'origin/agent/swarm-20260820-c4b97d9'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260820-c4b97d9\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nSwitched to a new branch 'agent/swarm-20260820-c4b97d9'\nremote: \nremote: Create a pull request for 'agent/swarm-20260820-c4b97d9' on GitHub by visiting:        \nremote:      https://github.com/55515-code/orchestrator/pull/new/agent/swarm-20260820-c4b97d9        \nremote: \nTo https://github.com/55515-code/orchestrator\n * [new branch]      agent/swarm-20260820-c4b97d9 -> agent/swarm-20260820-c4b97d9\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
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
      "duration_seconds": 0.399,
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
      "stdout_tail": "agent/swarm-20260820-c4b97d9\n",
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
      "stdout_tail": "6a8d2e90c5294a1712326f7e33d656a96223f8d0\n",
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
        "20260820-c4b97d9",
        "safe_gate",
        "1",
        "false"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 2 6 20260820-c4b97d9 safe_gate 1 false",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.467,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260820-c4b97d9'.\n[agent/swarm-20260820-c4b97d9 0b17e21] chore(agent): swarm loop 2/6 session 20260820-c4b97d9\n 2 files changed, 498 insertions(+), 16 deletions(-)\nCurrent branch agent/swarm-20260820-c4b97d9 is up to date.\nbranch 'agent/swarm-20260820-c4b97d9' set up to track 'origin/agent/swarm-20260820-c4b97d9'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260820-c4b97d9\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260820-c4b97d9'\nTo https://github.com/55515-code/orchestrator\n   6a8d2e9..0b17e21  agent/swarm-20260820-c4b97d9 -> agent/swarm-20260820-c4b97d9\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
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
      "stdout_tail": "agent/swarm-20260820-c4b97d9\n",
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
      "stdout_tail": "0b17e21162c35a65850fb0df3c17ae383be5d2b1\n",
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
        "3",
        "6",
        "20260820-c4b97d9",
        "safe_gate",
        "1",
        "false"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 3 6 20260820-c4b97d9 safe_gate 1 false",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.539,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260820-c4b97d9'.\n[agent/swarm-20260820-c4b97d9 d841420] chore(agent): swarm loop 3/6 session 20260820-c4b97d9\n 2 files changed, 491 insertions(+), 11 deletions(-)\nCurrent branch agent/swarm-20260820-c4b97d9 is up to date.\nbranch 'agent/swarm-20260820-c4b97d9' set up to track 'origin/agent/swarm-20260820-c4b97d9'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260820-c4b97d9\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260820-c4b97d9'\nTo https://github.com/55515-code/orchestrator\n   0b17e21..d841420  agent/swarm-20260820-c4b97d9 -> agent/swarm-20260820-c4b97d9\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
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
      "duration_seconds": 0.387,
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
      "stdout_tail": "agent/swarm-20260820-c4b97d9\n",
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
      "stdout_tail": "d841420d2f93faa28daa5e181de4874f0d80cbcb\n",
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
        "4",
        "6",
        "20260820-c4b97d9",
        "safe_gate",
        "1",
        "false"
      ],
      "command_text": "bash scripts/agent_hybrid_publish.sh true main /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md 4 6 20260820-c4b97d9 safe_gate 1 false",
      "return_code": 0,
      "ok": true,
      "duration_seconds": 3.58,
      "stdout_tail": "M\tartifacts/agent-hybrid/agent_report.md\nM\tartifacts/agent-hybrid/agent_summary.json\nYour branch is up to date with 'origin/agent/swarm-20260820-c4b97d9'.\n[agent/swarm-20260820-c4b97d9 5c668c4] chore(agent): swarm loop 4/6 session 20260820-c4b97d9\n 2 files changed, 491 insertions(+), 11 deletions(-)\nCurrent branch agent/swarm-20260820-c4b97d9 is up to date.\nbranch 'agent/swarm-20260820-c4b97d9' set up to track 'origin/agent/swarm-20260820-c4b97d9'.\nAGENT_PUBLISH_ACTION=pr_create_failed\nAGENT_PUBLISH_OK=false\nAGENT_PUBLISH_BRANCH=agent/swarm-20260820-c4b97d9\nAGENT_PUBLISH_PR_NUMBER=\nAGENT_PUBLISH_PR_URL=\nAGENT_PUBLISH_MERGE_ATTEMPTED=false\nAGENT_PUBLISH_MERGED=false\nAGENT_PUBLISH_MERGE_ATTEMPTS=0\nAGENT_PUBLISH_REBASE_OK=true\nAGENT_PUBLISH_PUSH_OK=true\nAGENT_PUBLISH_MESSAGE=Failed to create PR from rolling branch.\n",
      "stderr_tail": "From https://github.com/55515-code/orchestrator\n * branch            main       -> FETCH_HEAD\nAlready on 'agent/swarm-20260820-c4b97d9'\nTo https://github.com/55515-code/orchestrator\n   d841420..5c668c4  agent/swarm-20260820-c4b97d9 -> agent/swarm-20260820-c4b97d9\nscripts/agent_hybrid_publish.sh: line 64: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_summary.json\\: No such file or directory\nscripts/agent_hybrid_publish.sh: line 65: /home/runner/work/orchestrator/orchestrator/artifacts/agent-hybrid/agent_report.md\\: No such file or directory\npull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)\n"
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
      "duration_seconds": 0.582,
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
      "stdout_tail": "agent/swarm-20260820-c4b97d9\n",
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
      "stdout_tail": "5c668c4b7985c17c713ca8b47480d5c5a5509d8a\n",
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
      "stdout_tail": "c4b97d903f437ac9b3f4fb22de536c9efd59217d\n",
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
      "duration_seconds": 0.007,
      "stdout_tail": "",
      "stderr_tail": ""
    }
  ]
}
```
