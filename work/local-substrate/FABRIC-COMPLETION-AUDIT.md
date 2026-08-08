# Codespace workload fabric completion audit

Audited against the live host and provisioned guest on 2026-07-29.

| Objective requirement | Authoritative evidence | Result |
|---|---|---|
| Full codespace organization | Discovery returns 10 bounded project units; Android repo components are not misclassified as independent workloads | Complete |
| Flexible, repurposable configuration | `fabric.json` separates policy, project overrides, execution profiles, and MCP definitions from dispatcher code | Complete |
| Local execution | `local-light` executes in a resource-controlled systemd user scope | Complete |
| Container offload | Rootless Podman execution enforces CPU, memory, PID, network, privilege, and workspace policies | Complete |
| Usable general container | Pinned toolbox image contains Python, Git, GCC, Make, jq, curl, rsync, and SSH; real 16-GiB cgroup limit verified | Complete |
| Build and KVM containers | Digest-pinned Arch build and LuigiOS QEMU images have dedicated high-compute profiles | Complete |
| Rootless VM offload | Ubuntu guest provisions from a checksum-verified official image, starts on demand, accepts SSH commands, and runs Podman/Git/GCC/Python | Complete |
| Project transfer to VM | Additive rsync uses deterministic paths and excludes Git/repo metadata plus common generated outputs; no implicit deletion | Complete |
| VM resource hygiene | Guest is non-autostarting and can be stopped through the fabric; tests restore an initially stopped VM | Complete |
| MCP isolation | Roo Context7 routes through the fabric into a constrained disposable container; real MCP initialize handshake passes | Complete |
| MCP repurposing | Declarative MCP entries support pinned images/commands, stdio transport, resource limits, network policy, and named environment passthrough | Complete |
| Supply-chain drift control | Config validation rejects mutable remote container tags; Context7 package is pinned to 3.2.5 | Complete |
| Host stability | Four CPU threads, 8 GiB RAM, and 80 GiB free disk are reserved; dispatch refuses policy violations | Complete |
| Privilege policy | Containers, MCPs, and normal VMs are rootless; unavoidable host setup is isolated behind graphical PolicyKit | Complete |
| Regression gate | `completion-audit.sh` composes host, container, KVM, fabric, MCP, VM, pinning, and toolbox tests | Complete |

The workload fabric is complete when `completion-audit.sh` reports
`SUMMARY failures=0` and restores transient VM state.
