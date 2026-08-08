#!/usr/bin/env bash
# Substrate Infrastructure Health Check
# Validates critical files and dependencies exist
set -euo pipefail

ERRORS=0

check_file() {
    if [[ ! -f "$1" ]]; then
        echo "❌ MISSING: $1"
        ERRORS=$((ERRORS + 1))
    else
        echo "✅ EXISTS: $1"
    fi
}

check_dir() {
    if [[ ! -d "$1" ]]; then
        echo "❌ MISSING: $1"
        ERRORS=$((ERRORS + 1))
    else
        echo "✅ EXISTS: $1"
    fi
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ MISSING: $1"
        ERRORS=$((ERRORS + 1))
    else
        echo "✅ EXISTS: $1"
    fi
}

echo "=== Substrate Infrastructure Health Check ==="
echo ""

echo "--- Critical Files ---"
check_file "pyproject.toml"
check_file "uv.lock"
check_file "workspace.yaml"
check_file "AGENTS.md"
check_file "README.md"
echo ""

echo "--- Critical Directories ---"
check_dir "substrate"
check_dir "scripts"
check_dir "docs"
check_dir "tests"
check_dir "state"
echo ""

echo "--- Key Scripts ---"
check_file "scripts/substrate_cli.py"
check_file "scripts/probe_system.py"
check_file "scripts/package_substrate.py"
check_file "scripts/run_chain.py"
echo ""

echo "--- Tools ---"
check_command "uv"
check_command "python3"
check_command "git"
echo ""

echo "--- Python Syntax ---"
if uv run python -m compileall substrate scripts > /dev/null 2>&1; then
    echo "✅ compileall: PASS"
else
    echo "❌ compileall: FAIL"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo "--- Substrate Scan ---"
if uv run python scripts/substrate_cli.py scan > /dev/null 2>&1; then
    echo "✅ substrate scan: PASS"
else
    echo "❌ substrate scan: FAIL"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo "=== Summary ==="
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ All checks passed"
    exit 0
else
    echo "❌ $ERRORS check(s) failed"
    exit 1
fi
