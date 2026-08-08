#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config="$root/fabric.json"
workspace_root="$(jq -r .workspace_root "$config")"

if (($# != 1)); then
  printf 'usage: %s WORKSPACE\n' "$0" >&2
  exit 2
fi

workspace="$(realpath -e "$1")"
[[ -d "$workspace" ]] ||
  { printf 'Workspace is not a directory: %s\n' "$workspace" >&2; exit 2; }

if [[ "$workspace" == "$workspace_root" ]]; then
  slug=codespace
elif [[ "$workspace" == "$workspace_root/"* ]]; then
  relative="${workspace#"$workspace_root/"}"
  slug="${relative//\//--}"
else
  slug="$(basename "$workspace")"
fi

host="$(jq -r '.profiles["vm-rootless"].ssh_host' "$config")"
port="$(jq -r '.profiles["vm-rootless"].ssh_port' "$config")"
user="$(jq -r '.profiles["vm-rootless"].ssh_user' "$config")"
identity="$(jq -r '.profiles["vm-rootless"].identity' "$config")"
remote_root="$(jq -r '.profiles["vm-rootless"].remote_root' "$config")"
known_hosts="$(dirname "$identity")/known_hosts"

# Starting through the fabric also waits for a verified SSH command channel and
# creates the deterministic remote workspace.
"$root/fabric.py" run --profile vm-rootless --workspace "$workspace" -- true

rsync \
  --archive \
  --human-readable \
  --info=stats1 \
  --exclude=/.git/ \
  --exclude=/.repo/ \
  --exclude=/.venv/ \
  --exclude=/node_modules/ \
  --exclude=/out/ \
  --exclude=/dist/ \
  --exclude=/build/ \
  -e "ssh -p $port -i $identity -o BatchMode=yes -o UserKnownHostsFile=$known_hosts" \
  "$workspace/" \
  "$user@$host:$remote_root/$slug/"

printf 'Synced %s to vm-rootless:%s/%s\n' "$workspace" "$remote_root" "$slug"
