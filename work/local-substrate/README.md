# Local development substrate

This kit keeps the workstation optimized around two complementary layers:

- **Rootless Podman** for routine builds, disposable toolchains, CI parity, and
  automation. The user API socket is enabled so Docker-compatible clients can
  use `DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock` when needed.
- **QEMU/KVM and libvirt** for full operating-system simulation, firmware/TPM
  testing, and guests that need isolation stronger than a container.

Normal VM commands default to `qemu:///session`, keeping VM lifecycle and disk
management unprivileged. Use `qemu:///system` explicitly only when a VM needs
the privileged libvirt NAT/bridge network or another host-level facility.

The scripts are deliberately idempotent and do not prune data or modify
project checkouts.

## Workload fabric

`fabric.py` is the shared entry point for organizing and offloading codespace
work. Its versioned contract is `fabric.json`; profiles can be copied, renamed,
and adjusted without changing the dispatcher.

Build the pinned general-purpose toolbox after changing its package set:

```bash
./work/local-substrate/build-images.sh
```

Remote base images are digest-pinned. The fabric rejects newly added mutable
remote tags during configuration loading, and the completion audit verifies
that MCP package commands are version-pinned as well.

Inspect capacity and discovered project units:

```bash
./work/local-substrate/fabric.py status
./work/local-substrate/fabric.py projects
./work/local-substrate/fabric.py profiles
```

Preview or run a workload:

```bash
./work/local-substrate/fabric.py run \
  --profile container-arch-build \
  --workspace ./batocera-steamdeck-upstream \
  --dry-run -- make help

./work/local-substrate/fabric.py run \
  --profile local-light \
  --workspace ./open-provenance-knowledge \
  -- python -m pytest
```

Projects can be addressed by their discovered name. The fabric then applies
the versioned override or recommendation:

```bash
./work/local-substrate/fabric.py run \
  --project LuigiOS \
  --dry-run -- ./tools/ci-check
```

The fabric reserves 4 CPU threads, 8 GiB of RAM, and 80 GiB of free disk for
host stability. It refuses a profile that would violate those reserves.

MCP servers use the same resource contract. Roo's Context7 entry now invokes
`fabric.py mcp-run context7`, which runs Node/npm and the server inside a
2-CPU/2-GiB disposable container instead of modifying host Node state. Add or
repurpose MCPs by copying an entry under `mcps` in `fabric.json`.

Provision the reusable rootless Ubuntu VM:

```bash
./work/local-substrate/vm-provision.sh --apply
```

The official released cloud image is SHA-256 verified, and each guest uses a
sparse overlay. The VM does not autostart and consume 16 GiB continuously;
fabric dispatch starts it on demand. Synchronize only the project needed:

```bash
./work/local-substrate/vm-sync.sh ./open-provenance-knowledge
./work/local-substrate/fabric.py run \
  --profile vm-rootless \
  --workspace ./open-provenance-knowledge \
  -- python3 -m pytest
./work/local-substrate/fabric.py vm stop
```

Sync is additive and excludes Git metadata and common build outputs. It never
uses `--delete`, so guest-side artifacts are not removed implicitly.

Validation:

```bash
./work/local-substrate/fabric-test.sh
./work/local-substrate/mcp-smoke.sh
./work/local-substrate/vm-smoke.sh
./work/local-substrate/completion-audit.sh
```

## Current host profile

- CachyOS/Arch, kernel 7.1.5, Intel i7-12800H (20 threads), 62 GiB RAM.
- VT-x/EPT and `/dev/kvm` are available; nested QEMU inside rootless Podman is
  already used successfully by LuigiOS.
- Podman 6 uses rootless `crun`, cgroup v2, netavark/aardvark, and native
  overlay on Btrfs.
- Root Btrfs has about 84 GiB free and is the limiting resource. Do not
  schedule automatic pruning: the checkout contains large Android and LuigiOS
  build state, and active image/volume ownership must be reviewed first.
- A 62 GiB zram swap device is active. The existing `vm.max_map_count` and
  inotify values are already suitable for large IDE/container workloads.

## Usage

Run the read-only audit at any time:

```bash
./work/local-substrate/audit.sh
```

Preview privileged changes:

```bash
./work/local-substrate/bootstrap-cachyos.sh
```

Apply unavoidable host changes through the graphical PolicyKit prompt:

```bash
./work/local-substrate/gui-bootstrap.sh
```

Daily builds and tests should use `container-run.sh` or project VM runners and
therefore need no root access. Do not run the bootstrap through a terminal
`sudo` prompt; `gui-bootstrap.sh` is the supported authorization path.

After applying, log out and back in if group membership changed, then rerun the
audit. The bootstrap installs the local virtualization/container toolchain,
enables modular libvirt sockets, and creates the conventional default libvirt
network. It does not enable Docker, prune Podman, delete caches, or configure
cluster software.

## Operational policy

- Prefer rootless containers and pinned image tags/digests.
- For Docker-compatible tools, export
  `DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock` in that tool's
  service environment rather than globally. Native Podman and
  `podman-compose` do not need this variable.
- Pass `/dev/kvm` only to trusted VM-runner containers and use
  `--network=none` for offline image construction.
- Prefer `virsh`, `virt-install`, and virt-manager on the default rootless
  `qemu:///session` connection. The `default` user storage pool lives under
  `~/.local/share/libvirt/images`.
- Put explicit CPU/memory limits on long-running automation; reserve at least
  4 CPU threads and 8 GiB RAM for the desktop.
- Keep VM disks and container volumes out of Git. Use qcow2 for VM disks and
  raw files only when performance measurements justify the space cost.
- Review `podman system df -v` before manual cleanup. Never automate
  `podman system prune --volumes`.
- Keep Kubernetes local clusters optional and project-scoped. Install `kind`
  or `k3d` only for a project that actually exercises Kubernetes APIs.
