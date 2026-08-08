# Substrate completion audit

Audited on 2026-07-28 against the live CachyOS host.

| Requirement | Evidence | Status |
|---|---|---|
| Rootless container runtime | Podman 6, `crun`, cgroup v2, overlay, netavark; constrained offline smoke test passes | Complete |
| Docker-compatible automation API | User `podman.socket` enabled and `_ping` returns `OK` | Complete |
| Automation resource isolation | `container-run.sh` enforces CPU, RAM, PID, network, privilege, workspace, and optional KVM policy | Complete |
| Hardware virtualization | VT-x/EPT present and `/dev/kvm` read/write; LuigiOS QEMU runner uses KVM inside Podman | Complete |
| Emulator acceleration | KVM, TUN, GPU render nodes, 62 GiB RAM, and zram verified | Complete |
| Native VM lifecycle | QEMU 11 and libvirt 12.5 installed; rootless user session and modular system sockets verified | Complete |
| Firmware and TPM simulation | OVMF 202605 and swtpm 0.10 installed and detected | Complete |
| Image/container construction utilities | Podman, Buildah, Skopeo, and podman-compose installed and version-checked | Complete |
| Storage headroom | Removed 31,652,671,280 bytes of verified temporary Git pack garbage; 113 GiB free, 77% used | Complete |
| Workspace scan safety | Local exclusions reduced root untracked scan from 1,176,627 paths to 282; status completes in about 0.01 seconds | Complete |
| Non-destructive cleanup policy | Audit detects active Git writers and temporary packs; no images, volumes, caches, refs, or worktree content pruned | Complete |
| Reproducible host setup | CachyOS bootstrap applied through PolicyKit; reruns use a graphical authorization window and noninteractive package transaction | Complete |

## Final gate

`audit.sh` reports zero failures and zero warnings. `smoke-test.sh` passes
shell validation, Podman API, constrained offline container execution, and a
real host QEMU process using KVM acceleration.
