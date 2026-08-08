#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_user="$(id -un)"

if ! command -v pkexec >/dev/null; then
  printf 'PolicyKit pkexec is not installed.\n' >&2
  exit 1
fi

# pkexec provides the graphical desktop authorization dialog. All privileged
# work stays in the narrowly scoped, auditable bootstrap script.
exec pkexec "$root/bootstrap-cachyos.sh" \
  --apply \
  --target-user "$target_user"
