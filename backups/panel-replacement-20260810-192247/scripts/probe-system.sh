#!/usr/bin/env bash
set -euo pipefail

OUT_FILE="${1:-docs/system-probe.md}"
python scripts/probe_system.py "${OUT_FILE}"
