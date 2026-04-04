# Deployment

This control panel is designed to run without owning an official domain and to remain deployable anywhere Codex can access.

## Profile A: Local secure only

```bash
uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090
```

Use this for personal/local ops with no public exposure.

Pinch-mode shortcut:

```bash
uv run python scripts/substrate_cli.py pinch --port 8090
```

## Profile B: Secure no-domain remote access

- Run the app locally on `127.0.0.1`.
- Expose using secure tunnel tools such as:
  - `cloudflared`
  - `tailscale`
  - `ssh` reverse tunnels

These options can provide encrypted access without purchasing or managing a domain. Provider plan limits can change, so validate current pricing/policies before production use.

## Profile C: Traditional hosting

- Deploy app with `uvicorn` on VPS/container.
- Put behind reverse proxy (`caddy` or `nginx`) with TLS.
- Keep auth/network restrictions in front of ops routes.
- Do not bind directly to `0.0.0.0` on an exposed host unless it is already behind a trusted proxy, tunnel, or VPN.

Container path:

```bash
docker compose -f deploy/compose.yaml up --build -d
```

Local helper (auto-detects docker/docker-compose/podman and runs smoke checks):

```bash
bash scripts/run_local_container.sh up
```

Reference files:

- `deploy/Dockerfile`
- `deploy/compose.yaml`
- `deploy/Caddyfile.example`
- `deploy/cloudflared.config.example.yml`

## Git-host and Codex-friendly deployment

The project is repo-native:

- Works directly from a Git checkout with `uv run ...`.
- Can be copied into other repos and run with local config (`workspace.yaml`, `upstreams.yaml`).
- Supports Codex-accessible environments (local workspaces, hosted dev repos, CI runners).

## Redistributable maintained zip

Build a portable release bundle with manifest and checksum:

```bash
uv run python scripts/package_substrate.py
```

Artifacts are written under `generated/releases/`:

- `<name>-<timestamp>.zip`
- `<name>-<timestamp>.manifest.json`
- `SHA256SUMS`

The zip includes runtime, docs, and `deploy/` templates so redistribution works across Git hosts and non-Git deployments.

Recovery flow when the normal path is broken:

```bash
uv run python scripts/substrate_cli.py pinch --repo substrate-core
curl -fsS http://127.0.0.1:8090/api/hints
curl -fsS http://127.0.0.1:8090/api/hints/diagnostics
```
