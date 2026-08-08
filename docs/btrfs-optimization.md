# Btrfs Storage Optimization for the Local Agent Substrate

Production-tested Btrfs configuration that maximizes deduplication efficiency
and minimizes snapshot overhead, aligned with the substrate's existing tooling
stack (SQLite state, git worktrees, `uv` environments, Docker services, JSON/JSONL
logs, systemd timers) and the underlying compute/storage substrate.

The guidance in this document is enforced and validated by:

| Tool | Purpose |
|------|---------|
| `uv run python scripts/substrate_cli.py storage-status` | Filesystem facts + recommended plan (read-only) |
| `uv run python scripts/substrate_cli.py storage-validate` | Compatibility check vs. tooling stack |
| `uv run python scripts/substrate_cli.py storage-maintenance` | Dedup/defrag maintenance (dry-run by default) |
| `bash scripts/btrfs_setup.sh` | One-shot provisioning (dry-run by default; `--apply` to mutate) |
| `bash scripts/btrfs_maintenance.sh` | status / defrag / dedup / snapshot |
| `substrate/btrfs.py` | Python API backing all of the above |

All mutations require an explicit `--apply` flag, matching the substrate's
Tier 2 autonomy rule (explicit human directive required).

---

## 1. Filesystem Creation Parameters

Apply these at `mkfs.btrfs` time. The substrate's workload is a mix of frequent
small-file writes (state JSON, learning JSONL, SQLite WAL), moderate git churn
(agent worktrees/branches), compressible text, and regenerable artifacts.

```bash
mkfs.btrfs -f -m dup -d single -n 16384 -s \
    -O extref,skinny-metadata,no-holes /dev/<device>
```

| Parameter | Value | Rationale | Tradeoff |
|-----------|-------|-----------|----------|
| `-m dup` | metadata profile | Duplicates metadata across two locations on a single device. Protects the substrate's SQLite databases and git object metadata from single-sector loss. | Costs ~10–15% extra space. If space-constrained on NVMe, `-m single` is acceptable at higher metadata-loss risk. |
| `-d single` | data profile | Data extents (cache blobs, artifacts, worktrees) are regenerable; no need to mirror. | No data redundancy. Use RAID profiles only when the device pool provides them. |
| `-n 16384` | nodesize | 16 KiB nodes keep inode density high for the substrate's many small files (`state/`, `memory/`, `.venv/`, chat sessions). | Larger nodes (32 KiB) reduce metadata overhead slightly but waste more space on tiny files. |
| `-s` | SSD mode | Optimizes block layout for SSD/NVMe — the typical substrate compute substrate. | Not harmful on HDD; omit for spinning disks. |
| `-O extref,skinny-metadata,no-holes` | features | `extref` hardens link counting (git worktrees); `skinny-metadata` shrinks metadata for high inode counts; `no-holes` makes `du`/`btrfs filesystem df` accurate and reduces future defrag work. | Requires kernel ≥ 5.10 and `btrfs-progs` ≥ 5.15. |

**Required dependencies:** `btrfs-progs` ≥ 5.15; kernel ≥ 5.10. Verify with
`storage-validate`, which hard-fails on older kernels/progs.

**Necessary substrate change:** none for creation itself — but see §5 for the
SQLite WAL pairing that the substrate already applies.

---

## 2. Mount Option Tuning

Reference fstab entry for the workspace root (CoW-enabled):

```
UUID=<fs-uuid> / btrfs defaults,ssd,space_cache=v2,noatime,compress=zstd:1,autodefrag,discard=async 0 1
```

| Option | Value | Why / Tradeoff |
|--------|-------|----------------|
| `space_cache` | `v2` | Faster mount after unclean shutdown; reduces ops-panel startup latency. Older kernels require fallback. |
| `noatime` | on | Eliminates metadata write amplification on every file access — critical for `state/learning-index.jsonl`, `memory/dev-history.jsonl`, and SQLite. |
| `compress` | `zstd:1` | Substrate state is overwhelmingly compressible text (JSON, YAML, source). ~15–25% space savings at <3% CPU. `zstd:3` for more savings on CPU-idle hosts; avoid `zstd:9`. |
| `autodefrag` | on | Btrfs doesn't merge extents on sequential writes; git worktrees and SQLite WAL files fragment under CoW. `autodefrag` merges in the background. |
| `ssd` | on | Optimizes for low-latency SSDs. `ssd_spread` only if you observe TRIM/GC issues on lower-end NVMe. |
| `discard` | `async` | Asynchronous TRIM avoids TRIM storms during batch snapshot creation. Never use synchronous discard on production databases. |

### Subvolume-level overrides (volatile state)

The substrate's `state/` and `memory/` directories hold SQLite databases and
high-frequency JSONL appends. CoW on those files causes fragmentation and
snapshot metadata explosion. Mount their subvolumes with `nodatacow`:

```
UUID=<fs-uuid> /home/ahron/codespace/state  btrfs subvol=@state,nodatacow,noatime 0 0
UUID=<fs-uuid> /home/ahron/codespace/memory btrfs subvol=@memory,nodatacow,noatime 0 0
```

**Tradeoffs of `nodatacow`:**
- **Loses** checksums, compression, dedup, and CoW snapshot sharing for those trees.
- **Gains** stable file layout for SQLite WAL and fast appends for JSONL logs.
- This matches the substrate's own separation: `state/` and `memory/` are
  already excluded from source backups (`backup_snapshot.sh`) and git.

**Necessary substrate change:** `substrate/db.py` and `substrate/cache_store.py`
now apply `PRAGMA synchronous=NORMAL;` + `busy_timeout=5000` on every connection
(alongside the existing WAL), which is the documented safe pairing with CoW
disabled filesystems. No further code change is required — paths are unchanged.

---

## 3. Deduplication Efficiency

Btrfs has no inline deduplication in the mainline kernel. Dedup must be offline.
The substrate tooling makes this safe and schedulable:

```bash
# Dry-run the planned commands first (always safe):
uv run python scripts/substrate_cli.py storage-maintenance

# Execute (explicit directive required, consistent with Tier 2):
uv run python scripts/substrate_cli.py storage-maintenance --apply

# Or via the shell wrapper (schedules cleanly from cron/systemd):
bash scripts/btrfs_maintenance.sh dedup --apply
```

What the maintenance run does:

1. **Defrag + compress** (`btrfs filesystem defrag -r -c zstd:1`) on the
   CoW-enabled trees only: `artifacts/`, `resources/`, `docs/`. It **never**
   touches `state/` or `memory/` (CoW-disabled volatile trees), and it never
   touches live SQLite databases.
2. **Offline dedup** (`duperemove -r -h --dedupe-options=hash`) against
   `artifacts/` — generated binaries, images, and downloaded tooling are the
   best dedup targets. The hashfile lives at `state/btrfs-dedup-hashes.db` so
   incremental runs are cheap.

**Required dependency:** `duperemove` (separate package on Debian/Ubuntu; part
of `btrfs-progs` on Arch/Fedora). `storage-validate` reports it as informational
when absent; `dedup` exits with an error until installed.

**Tradeoffs:**
- `duperemove` reads the whole target tree — schedule during low I/O windows.
- Dedup does not persist across new writes; rerun after agent/update cycles.
- Do **not** run `duperemove` on active SQLite databases (`state/orchestrator.db`,
  `state/cache/cache.db`, `state/studio_scheduler.db`). Back up, stop services,
  dedup, restart — the tooling above already excludes them by design.

---

## 4. Snapshot Overhead Minimization

The substrate's own "snapshot" vocabulary is in-memory/JSON state snapshots
(`repository_snapshots`, community sim, `system_snapshot` SSE events). This
section governs **filesystem** snapshots for backup/rollback of agent worktrees
and repo state.

Rules that keep filesystem snapshots cheap:

1. **Read-only snapshots only.** `btrfs subvolume snapshot -r` prevents
   accidental writes into snapshot space and keeps COW metadata bounded.
   `bash scripts/btrfs_maintenance.sh snapshot` defaults to `-r`.
2. **Exclude volatile paths.** The snapshot plan (`snapshot_plan` in
   `substrate/btrfs.py`) reuses the `workspace.yaml` `ignored_paths` list
   (`.git`, `.venv`, `node_modules`, `tmp`, `downloads`, `work`, `tools`,
   `site`) plus `state/**` and `memory/**` — volatile state lives on its own
   CoW-disabled subvolume, so workspace snapshots never double-store it.
3. **Per-subvolume isolation.** `@workspace`, `@state`, `@memory`,
   `@artifacts` enable independent snapshot/restore per concern, matching the
   multi-repo structure in `workspace.yaml`.
4. **Rotation.** `scripts/btrfs_maintenance.sh snapshot --apply` keeps the
   newest `KEEP_SNAPSHOTS` (default 7) and deletes older read-only snapshots.

**Recommended cadence (aligns with `agents.yaml`):**
- Daily: snapshot `@workspace` before the `dev-agent` and `update-agent` runs.
- Weekly: snapshot after `update-agent` validation succeeds.

**Tradeoff:** snapshots are nearly free with `nodatacow` state subvolumes
(shared extents), but every snapshot of a CoW-enabled tree retains changed
extents until rotated. Rotation bounds that growth.

---

## 5. Tooling Integration Adjustments

### SQLite (`state/orchestrator.db`, `state/cache/cache.db`, `state/studio_scheduler.db`)

- **Conflict:** CoW fragmentation on databases; journal-mode mismatch.
- **Resolution (already applied in this change):** every connection now runs
  `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;`.
  `synchronous=NORMAL` with WAL is the documented safe pairing (fsync only on
  checkpoint, not every commit) and the `busy_timeout` absorbs multi-process
  lock collisions between the ops panel, dashboard, pipelines, and agent cycle.
- **Additional hardening:** place these on the `nodatacow` `@state` subvolume.

### Git

- **Conflict:** none significant — Btrfs handles git well.
- **Optimization:** `git config --global core.preloadIndex true` and
  `core.fsmonitor true` reduce `git status` latency in agent worktrees.
- **Note:** keep `.git` directories on CoW-enabled subvolumes so Btrfs-level
  checksums still protect them.

### Docker (MobSF profile, container workflows)

- **Conflict:** Docker's legacy `btrfs` storage driver is deprecated and
  conflicts with CoW-heavy layouts.
- **Resolution:** use `overlay2` with a Btrfs backing store. `storage-validate`
  fails with an `error` if `docker info` reports the `btrfs` driver, directing
  you to set `"storage-driver": "overlay2"` in `/etc/docker/daemon.json`.

### `uv` / Python environments

- **Conflict:** `uv` creates many small files in `.venv/`; CoW fragmentation is
  managed by `autodefrag`.
- **Optimization:** keep shared `uv` caches on CoW-enabled subvolumes with
  `compress=zstd:1` so dedup applies across environments. Do **not** put them
  on `nodatacow`.

### systemd timers / journald

- **Conflict:** `journald` on a compressed CoW filesystem can grow if verbose.
- **Resolution:** set `SystemMaxUse=500M` in `/etc/systemd/journald.conf` and
  rely on journald's own `Compress=yes`; avoid double-compression debates.

### restic (`scripts/backup_snapshot.sh`)

- **Compatible.** restic already excludes `**/.git/**`, `node_modules`,
  `__pycache__`, `.venv`, `dist` — the same classes `snapshot_plan` excludes.
- **Note:** restic and Btrfs snapshots are complementary: Btrfs snapshots give
  fast point-in-time rollback; restic gives encrypted off-machine restore.

---

## 6. Reference: Compatibility Matrix

| Component | Required state | How it's enforced |
|-----------|---------------|-------------------|
| Kernel | ≥ 5.10 | `storage-validate` (error below minimum) |
| btrfs-progs | ≥ 5.15 | `storage-validate` (warning below minimum) |
| SQLite | WAL + synchronous=NORMAL | Applied by `substrate/db.py` / `cache_store.py`; validated by `storage-validate` |
| Docker | overlay2, not legacy btrfs | `storage-validate` (error on legacy driver) |
| duperemove | installed for dedup | `storage-validate` (info) / `dedup` (error when run) |
| Workspace FS | btrfs | `storage-validate` + all scripts guard on it |

## 7. Operational Runbook

```bash
# Inspect current state and plan (read-only, safe anytime):
uv run python scripts/substrate_cli.py storage-status

# Validate compatibility with the tooling stack:
uv run python scripts/substrate_cli.py storage-validate

# One-shot provisioning (dry-run first, then apply):
bash scripts/btrfs_setup.sh
bash scripts/btrfs_setup.sh --apply

# Recurring maintenance (schedule in crontab/systemd):
bash scripts/btrfs_maintenance.sh defrag     # safe; run weekly
bash scripts/btrfs_maintenance.sh dedup      # I/O heavy; run in low-window
bash scripts/btrfs_maintenance.sh snapshot   # daily before agent runs
```

All commands emit substrate-idiomatic JSON where applicable and record
`storage-maintenance` runs into the learning index/run ledger via
`record_execution`.
