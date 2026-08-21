# Portable Gateway Capsule Strategy

## Objective

Create a rootless, reproducible **Gateway Capsule** containing OpenClaw,
Substrate control services, and Kilo execution adapters. The capsule must be
deployable on another Linux host, snapshot-able as one release, independently
upgradeable, and quickly reversible without granting container workloads
unrestricted control over the root operating system.

The recommended implementation is **rootless Podman + systemd user Quadlets +
Btrfs snapshots + verified application backups**. This matches the installed
tooling and OpenClaw's supported container model while minimizing new host
dependencies.

## Design principles

1. **The host is substrate, not application state.** Keep only the kernel,
   Btrfs, rootless Podman, systemd user manager, Tailscale/network ingress,
   hardware drivers, and optional host model runtimes on the host.
2. **Images are immutable; state is explicit.** Never store durable state in a
   container writable layer. Pin images by digest and replace containers.
3. **Application control is not root control.** The capsule may fully manage
   its Gateway and Kilo workers, but it receives no Podman socket, host root
   filesystem mount, or broad privileged capabilities.
4. **Every mutation has evidence and a rollback point.** Preserve Substrate's
   research -> development -> testing and local -> hosted_dev -> production
   gates.
5. **Sessions are portable records, not process-local accidents.** Normalize
   local Kilo, attached daemon, cloud, and OpenClaw sessions behind one registry.
6. **Secrets are restored separately.** Snapshot manifests may name required
   secret references, but source control and routine telemetry never contain
   secret values.

## Target architecture

```text
Host substrate (small, stable, rootless)
├── Btrfs subvolumes + snapshot/restore broker
├── rootless Podman + systemd user Quadlets
├── Tailscale Serve or loopback-only ingress
├── optional Ollama/LM Studio/GPU runtimes
└── allowlisted host-ops broker (no arbitrary shell)
        │
        ▼
Gateway Capsule (replaceable release)
├── openclaw-gateway       Gateway, Control UI, channels, hooks
├── substrate-control      policy, panel, workflows, deployment controller
├── kilo-executor          local/daemon/cloud session adapter
├── router-registry        local and hosted model health/cost/capability data
└── telemetry-exporter     redacted events, metrics, traces (optional)
        │
        ▼
Explicit persistent volumes / bind mounts
├── openclaw-state         config, auth profiles, channels, sessions
├── substrate-state        SQLite, agent state, learning index
├── substrate-memory       run logs and durable execution records
├── kilo-state             config, session exports, adapter registry
├── workspace              checked-out source and operator context
└── artifacts              reports, bundles, SBOMs, backup manifests
```

Run the services on a private Podman network. Publish only the Gateway ingress
to `127.0.0.1`; use host-managed Tailscale Serve for remote access. Bind the
Gateway to `lan` *inside* the container, as required for published container
ports, while retaining loopback-only host exposure.

Do not enable trusted-proxy authentication in the first migration. Continue
token/device authentication. If a reverse proxy is later introduced, make it
the only network path, configure exact trusted proxy addresses and allowed
origins, and test bypass resistance before promotion.

## State and snapshot contract

### Subvolume layout

Create independent Btrfs subvolumes under a capsule root, for example:

```text
~/gateway-capsule/
  releases/       # manifests and Quadlet definitions; CoW, Git-managed
  workspace/      # CoW, compressed
  openclaw/       # CoW; native backup is the consistency authority
  substrate-state/# WAL-heavy; application backup before FS snapshot
  memory/         # durable logs; independently retainable
  kilo/           # Kilo config and sanitized session exports
  artifacts/      # backup archives, SBOMs, test evidence
  secrets/        # mode 0700; excluded from Git and ordinary exports
```

Avoid blanket `nodatacow` for state that must participate in atomic Btrfs
snapshots. Measure SQLite write amplification first; if `nodatacow` remains
necessary, rely on application-consistent SQLite backups rather than claiming
filesystem-level atomicity.

### Release manifest

Every deployable release gets a signed or checksummed manifest containing:

- Git commit and dirty-tree status.
- OpenClaw, Substrate, Kilo, and schema versions.
- OCI image names, immutable digests, SBOM paths, and build provenance.
- Quadlet/Compose configuration checksum.
- Required volume schema and migration version.
- Secret *names* and optional-provider requirements, never values.
- Pre-deploy backup IDs and Btrfs snapshot IDs.
- Test evidence, health results, promotion stage, and prior release ID.

### Consistent snapshot sequence

1. Stop accepting new workflow mutations; allow active jobs a bounded drain.
2. Run `openclaw backup create --verify --no-include-workspace` into artifacts.
   This is the canonical OpenClaw state backup because it safely handles its
   SQLite databases and omits volatile files.
3. Use SQLite's backup API for `state/orchestrator.db`; checkpoint WAL only
   through the application-aware backup routine.
4. Export newly changed Kilo sessions with `kilo export --sanitize`; preserve
   provider/session references separately for resumable authorized sessions.
5. Create read-only Btrfs snapshots of each persistent subvolume and record
   their UUIDs in the release manifest.
6. Send encrypted deduplicated copies through restic. Apply daily/weekly/monthly
   retention independently from local instant-rollback snapshots.
7. Perform a scheduled restore drill into a disposable capsule; a backup is not
   considered healthy solely because creation succeeded.

Secrets require a separate encrypted recovery bundle and a documented re-key
procedure. Restores should work in a degraded, offline/read-only mode before
secrets are supplied.

## Deployment and rollback

### Blue/green promotion

Use two local capsule slots rather than updating the live container in place:

1. Build or pull the candidate image and verify its digest/SBOM.
2. Restore a sanitized recent state copy into the **green** slot.
3. Run config validation, `doctor`, migrations, `/healthz`, `/readyz`, deep
   health, panel API smoke tests, and one non-destructive Kilo session probe.
4. Run Substrate bounded validation and security audit. No production secrets
   are given to research or untrusted test tasks.
5. Snapshot live state and drain active jobs.
6. Start green against the live volumes, keeping blue stopped but intact.
7. Switch the loopback ingress only after readiness succeeds; monitor a short
   canary window.
8. Mark the release current. Retain blue and the pre-deploy snapshots until the
   rollback window closes.

Rollback reverses ingress, restores the previous image digest, and restores
state only when a migration is not backward-compatible. Never blindly roll an
old binary onto newly migrated writable state.

### Health gates

Required gates are:

- Image starts as a non-root UID with dropped capabilities and seccomp active.
- `/healthz` and `/readyz` pass.
- Authenticated Gateway deep health passes and configured channels retain their
  expected state.
- Substrate `/healthz`, connection status, scan, compile, and focused tests pass.
- Kilo can create a local JSON-stream session and resume it by session ID.
- Router endpoints are reachable only from intended namespaces.
- `openclaw security audit` has no new critical finding or unwaived warning.
- Restore drill verifies manifest checksums and starts a disposable read-only
  capsule.

## Kilo and router integration

### Provider-neutral execution model

Add a Substrate `ExecutionSpec` and `SessionRef` rather than adding more CLI
conditionals directly to the panel:

```text
ExecutionSpec
  objective, repository, ref, workspace, stage, pass, mode
  backend: local_process | local_daemon | cloud_agent
  model_policy, capability_set, budget, timeout, data_class
  continuation: new | resume | fork | cloud_fork

SessionRef
  substrate_run_id, backend, provider, external_session_id
  repository, commit, container_release, status, parent_session
  created_at, last_event_at, sanitized_export, artifact_refs
```

Implement adapters for:

- **Local process:** existing `kilo run --format json` path.
- **Local daemon:** `kilo serve`/daemon plus `kilo run --attach`, allowing a
  stable execution service and lower startup overhead.
- **Session movement:** resume/fork and `--cloud-fork` where Kilo supports it.
- **Cloud Agent:** start/send/status/result with repository, branch, model, and
  organization references captured in `SessionRef`.

Cloud execution is opt-in per task. Apply the existing data-class policy:
synthetic or redacted research may leave the host; private repository contents,
credentials, and unrestricted workspace context may not be sent without an
explicit directive.

### Router registry

Create one registry consumed by OpenClaw, Kilo, and the panel. Each route should
report capability, context size, locality, health, queue depth, latency, cost,
privacy class, and supported tools. Populate it from Kilo model/usage data,
OpenClaw usage snapshots, and active probes of local endpoints.

Routing order should be policy-driven:

1. A healthy local model that satisfies context/tool/quality requirements.
2. Kilo's selected router for ordinary development.
3. A pinned hosted model for tasks that need higher capability and permit the
   relevant data class.
4. Cloud Agent only for repository-scoped asynchronous work with a branch and
   bounded budget.

Record metadata and aggregate usage by default, not prompts or tool payloads.
Deduplicate retries with the existing task-cache/idempotency mechanisms.

### Control panel movement

Extend the existing Kilo Code page with:

- backend/model/privacy selectors with safe defaults;
- local, attached, cloud, and fork badges;
- session lineage and repository/commit association;
- pause/cancel/resume/fork/cloud-fork controls;
- streaming normalized events and artifact links;
- health, budget, cache-hit, and route-explanation summaries;
- deployment readiness and rollback controls gated by autonomy tier.

The panel calls Substrate APIs, not shell strings. All command arguments remain
argv-safe, operations are auditable, and Tier 2 actions (production promotion,
external writes, secret changes) continue to require explicit authorization.

## Automated lifecycle

Preserve the enforced 3x3 sequence:

| Stage/pass | Automated outcome |
|---|---|
| local/research | probes, upstream facts, threat model, state inventory |
| local/development | adapter code, manifests, Quadlets, backup APIs |
| local/testing | unit/integration tests, disposable Podman restore, security audit |
| hosted_dev/research | host capability and ingress discovery, no mutation |
| hosted_dev/development | deploy green capsule with redacted/synthetic state |
| hosted_dev/testing | E2E Kilo/Gateway/panel tests and rollback drill |
| production/research | live drift, capacity, backup, and release-readiness report |
| production/development | blue/green promotion after snapshot and drain |
| production/testing | canary, channel checks, telemetry, automatic rollback gate |

Use current Substrate tooling as the control surface: `scan`, `agent-status`,
`runs`, `snapshot`, `storage-status`, `storage-validate`, `run-chain`,
`record-test`, and `swarm-control`. Add capsule-specific commands behind that
CLI rather than introducing an unrelated deployment script collection:

- `capsule probe|plan|build|backup|restore|deploy|rollback|status`
- `router probe|routes|explain`
- `kilo-sessions list|resume|fork|cloud-fork|export`

All mutating commands should support a dry-run plan, emit structured JSON, use
idempotency keys, and write evidence into the orchestrator run record.

## Phased implementation

### Phase 0 — repair and inventory

- Fix the current panel container's 8080/8090 mismatch and avoid collision with
  the live Gateway.
- Inventory state and secret references; add OpenClaw and Kilo to the encrypted
  backup scope.
- Disable or constrain request-selected hook session keys after compatibility
  testing.
- Add capsule schema, release manifest, and read-only `capsule probe/plan`.

### Phase 1 — disposable local capsule

- Build rootless Podman images and Quadlet templates.
- Run on alternate loopback ports with copied/sanitized state.
- Add deterministic health, backup, restore, and migration tests.
- Keep the native Gateway untouched as the rollback path.

### Phase 2 — Kilo execution plane

- Introduce `ExecutionSpec`, `SessionRef`, adapter interfaces, and normalized
  events.
- Migrate existing panel chat to the local-process adapter without behavior
  loss; then add daemon attachment and explicit forks.
- Add Cloud Agent support only after repository/data-class/budget gates exist.

### Phase 3 — blue/green local production

- Snapshot and drain the native Gateway.
- Promote the Podman capsule through loopback ingress.
- Keep the native systemd unit disabled but immediately recoverable during the
  acceptance window; remove it only after repeated restore drills.

### Phase 4 — portable hosted deployment

- Deploy the same digest and manifest to hosted development.
- Restore non-secret state, inject destination-specific secrets, and run E2E
  tests before production promotion.
- Support air-gapped image export/import and offline degraded operation.

## Acceptance criteria

- A fresh compatible Linux host can restore a capsule from documented host
  prerequisites, OCI images, release manifest, application backup, and secrets.
- Local deployment and rollback are one Substrate operation each and never
  require editing live container files.
- Recovery point objective is at most one scheduled snapshot interval; local
  rollback target is under five minutes after state compatibility is confirmed.
- Destruction and recreation of every container preserves Gateway, Substrate,
  Kilo session references, and workspace state.
- A failed health gate cannot switch ingress or delete the previous release.
- The container cannot obtain root host control through mounted sockets,
  privileged mode, or unrestricted host paths.
- The panel can create, resume, fork, inspect, and cancel supported Kilo session
  types while showing route, privacy, cost, and deployment evidence.

## Current recommendation

Proceed with **rootless Podman/Quadlet**, separate service containers in one
capsule release, host-loopback ingress, OpenClaw native verified backups plus
Btrfs/restic, and a provider-neutral Kilo session registry. Do not use a single
privileged “everything container,” mount the Podman socket into the Gateway, or
move directly from the current native service to an in-place container cutover.

No operator decision is required to begin Phases 0 and 1. Cloud credentials,
remote ingress, and production promotion remain explicit later-stage gates.
