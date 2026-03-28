set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

bootstrap:
    bash scripts/bootstrap-local-agent-env.sh

probe:
    python scripts/probe_system.py docs/system-probe.md

sync:
    uv sync --python 3.12

chain objective="Repository audit":
    uv run python scripts/run_chain.py --objective "{{objective}}" --dry-run

scan:
    uv run python scripts/substrate_cli.py scan

polish:
    bash scripts/developer_polish.sh

polish-task:
    uv run python scripts/substrate_cli.py run-task --repo substrate-core --task developer_polish --stage local

polish-schedule:
    bash scripts/install_developer_polish_timer.sh

sources:
    uv run python scripts/substrate_cli.py sources-refresh

ops:
    uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090

community cycle="0" provider="mock":
    uv run python scripts/substrate_cli.py community-cycle --cycle "{{cycle}}" --agent-provider "{{provider}}"

package:
    uv run python scripts/package_substrate.py

docs:
    uv run mkdocs serve -a 127.0.0.1:8000
