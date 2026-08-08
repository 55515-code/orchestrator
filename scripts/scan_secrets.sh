#!/usr/bin/env bash
# scan_secrets.sh — pre-commit / pre-push / pre-sync secret scanner.
# Blocks commits or syncs that contain obvious secret material in added lines.
#
# Exit codes:
#   0 = clean (or nothing staged)
#   1 = secrets detected (or scan error)
#
# Usage:
#   scripts/scan_secrets.sh            # scan staged diff in cwd
#   scripts/scan_secrets.sh <repo_dir> # scan staged diff in given repo
set -uo pipefail

TARGET="${1:-$(pwd)}"
cd "$TARGET" 2>/dev/null || { echo "ERROR: cannot cd to $TARGET" >&2; exit 1; }

# Match added diff lines carrying obvious secret-like material.
PATTERN='^\+.*(password[[:space:]]*[:=]|passwd[[:space:]]*[:=]|token[[:space:]]*[:=]|api[_-]?key[[:space:]]*[:=]|client_secret[[:space:]]*[:=]|BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'

STAGED_FILES="$(git diff --cached --name-only 2>/dev/null)"
if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

if git diff --cached --text 2>/dev/null | grep -qE "$PATTERN"; then
    echo "SECRET SCAN FAILED: staged diff contains secret-like material." >&2
    echo "Review the following staged files:" >&2
    echo "$STAGED_FILES" >&2
    echo "Do not commit credentials. Use environment variables, keyring, or .env (ignored)." >&2
    exit 1
fi

exit 0
