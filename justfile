set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

bootstrap:
    bash scripts/bootstrap-local-agent-env.sh

probe:
    python scripts/probe_system.py docs/system-probe.md

generate-docs:
    uv run python scripts/generate_system_docs.py

validate-docs:
    uv run python scripts/validate_docs.py

validate-registry:
    uv run python scripts/validate_system_registry.py

docs-check: generate-docs validate-docs validate-registry
    @echo "All docs/generator checks passed"

sync:
    uv sync --python 3.12 --extra dev

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

# Ops panel: OpenClaw Gateway owns 8090. Use 8096 for ad-hoc local dev
# to avoid a collision. See system_registry.yaml -> port_policy.
ops:
    uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8096

community cycle="0" provider="mock":
    uv run python scripts/substrate_cli.py community-cycle --cycle "{{cycle}}" --agent-provider "{{provider}}"

package:
    uv run python scripts/package_substrate.py

docs:
    uv run mkdocs serve -a 127.0.0.1:8000

container-up:
    bash scripts/run_local_container.sh up

container-down:
    bash scripts/run_local_container.sh down

container-logs:
    bash scripts/run_local_container.sh logs
