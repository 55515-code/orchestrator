# Standards and Tool Profiles

The substrate now keeps two explicit catalogs in the workspace root:

- `standards.yaml`: trusted community formats and source projects.
- `tool_profiles.yaml`: optional binaries/tooling that should be assembled on first use.

This keeps the shipped package lean while preserving a reproducible way to expand capabilities when needed.

## 3x3 Lifecycle Matrix

Each standards entry is expanded against the workspace policy matrix:

- stages: `local -> hosted_dev -> production`
- passes: `research -> development -> testing`

The dashboard and API expose this as execution guidance so implementation stays aligned with local-first discipline and staged promotion.

## Included Tracks

- Device-inspired operations:
  - Hak5 USB Rubber Ducky (DuckyScript)
  - Flipper Zero BadUSB/Sub-GHz formats
- Distro baselines:
  - Kali metapackages and tool lifecycle practices
  - Parrot signed mirror model
- Threat research formats:
  - MITRE ATT&CK
  - Atomic Red Team
  - Sigma
  - Nuclei templates
- Android security operations:
  - Android platform-tools (`adb`, `fastboot`)
  - Apktool
  - JADX
  - MobSF
  - Frida
  - OWASP MASVS/MASTG alignment

## CLI Usage

```bash
# full standards catalog
uv run python scripts/substrate_cli.py standards

# single track
uv run python scripts/substrate_cli.py standards --track android_security_ops

# check optional tool readiness
uv run python scripts/substrate_cli.py deps-status

# check one profile
uv run python scripts/substrate_cli.py deps-status --profile android_lab

# preview install plan
uv run python scripts/substrate_cli.py deps-ensure --profile android_lab

# apply install plan
uv run python scripts/substrate_cli.py deps-ensure --profile android_lab --apply
```

## Web API Usage

- `GET /api/standards`
- `GET /api/tooling`
- `POST /api/actions/deps-ensure`
- `GET /api/payloads`
- `POST /api/actions/run-payload`
- `GET /api/payload-jobs/{job_id}`

## Scope and Authorization

These catalogs are intended for authorized security testing and engineering workflows only. Keep usage constrained to environments where you have explicit permission.
