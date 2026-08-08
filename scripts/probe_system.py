#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_COMMAND_TIMEOUT_SECONDS = 8


def run_text(command: list[str], *, timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1, int(timeout_seconds)),
        )
    except subprocess.TimeoutExpired:
        return f"timeout({max(1, int(timeout_seconds))}s)"
    except OSError as exc:
        return f"unavailable: {exc}"
    output = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 and output:
        return f"error({completed.returncode}): {output}"
    return output or "ok"


def _format_bytes(value: int) -> str:
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    for suffix in suffixes:
        if amount < 1024 or suffix == suffixes[-1]:
            return f"{amount:.1f}{suffix}"
        amount /= 1024
    return f"{value}B"


def _detect_nvidia_gpu() -> dict[str, Any]:
    gpu_info: dict[str, Any] = {"vendor": "nvidia", "available": False}
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return gpu_info
    raw = run_text([nvidia_smi, "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], timeout_seconds=10)
    if raw.startswith("error") or raw.startswith("unavailable") or raw.startswith("timeout"):
        gpu_info["error"] = raw
        return gpu_info
    gpus = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "memory_total_mb": int(parts[2]),
                "memory_used_mb": int(parts[3]),
                "memory_free_mb": int(parts[4]),
                "utilization_pct": int(parts[5]),
            })
        except (ValueError, IndexError):
            continue
    if gpus:
        gpu_info["available"] = True
        gpu_info["gpus"] = gpus
        total = sum(g["memory_total_mb"] for g in gpus)
        free = sum(g["memory_free_mb"] for g in gpus)
        gpu_info["vram_total_mb"] = total
        gpu_info["vram_free_mb"] = free
    return gpu_info


def _detect_amd_gpu() -> dict[str, Any]:
    gpu_info: dict[str, Any] = {"vendor": "amd", "available": False}
    rocm_smi = shutil.which("rocm-smi")
    if not rocm_smi:
        return gpu_info
    raw = run_text([rocm_smi, "--showallinfo", "--csv"], timeout_seconds=10)
    if raw.startswith("error") or raw.startswith("unavailable") or raw.startswith("timeout"):
        gpu_info["error"] = raw
        return gpu_info
    gpus = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("GPU") or line.startswith("Device"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            total_mb = int(parts[3])
            used_mb = int(parts[4]) if len(parts) > 4 else 0
            free_mb = max(0, total_mb - used_mb)
            gpus.append({
                "index": len(gpus),
                "name": parts[1],
                "memory_total_mb": total_mb,
                "memory_used_mb": used_mb,
                "memory_free_mb": free_mb,
                "utilization_pct": int(parts[2]) if len(parts) > 2 else 0,
            })
        except (ValueError, IndexError):
            continue
    if gpus:
        gpu_info["available"] = True
        gpu_info["gpus"] = gpus
        total = sum(g["memory_total_mb"] for g in gpus)
        free = sum(g["memory_free_mb"] for g in gpus)
        gpu_info["vram_total_mb"] = total
        gpu_info["vram_free_mb"] = free
    return gpu_info


def _detect_intel_gpu() -> dict[str, Any]:
    gpu_info: dict[str, Any] = {"vendor": "intel", "available": False}
    intel_gpu_top = shutil.which("intel_gpu_top")
    if intel_gpu_top:
        raw = run_text([intel_gpu_top, "-L"], timeout_seconds=10)
        if "error" not in raw and "unavailable" not in raw:
            gpu_info["available"] = True
            gpu_info["top_output"] = raw[:2000]
            return gpu_info
    glxinfo = shutil.which("glxinfo")
    if glxinfo:
        raw = run_text([glxinfo, "|", "grep", "-i", "renderer"], timeout_seconds=10)
        if "Intel" in raw:
            gpu_info["available"] = True
            gpu_info["renderer"] = raw.strip()
    return gpu_info


def _detect_vulkan_gpus() -> list[dict[str, str]]:
    vulkaninfo = shutil.which("vulkaninfo")
    if not vulkaninfo:
        return []
    raw = run_text([vulkaninfo], timeout_seconds=10)
    gpus = []
    for line in raw.splitlines():
        if "deviceName" in line or "GPU" in line:
            gpus.append({"vulkan": line.strip()})
    return gpus


def _detect_apple_silicon() -> dict[str, Any]:
    info: dict[str, Any] = {"available": False}
    if platform.system().lower() != "darwin":
        return info
    brand = run_text(["sysctl", "-n", "machdep.cpu.brand_string"])
    if "Apple" in brand:
        info["available"] = True
        info["chip"] = brand.strip()
        cores = run_text(["sysctl", "-n", "hw.physicalcpu"])
        mem = run_text(["sysctl", "-n", "hw.memsize"])
        try:
            info["physical_cores"] = int(cores)
        except (ValueError, TypeError):
            info["physical_cores"] = None
        try:
            info["memory_bytes"] = int(mem)
        except (ValueError, TypeError):
            info["memory_bytes"] = None
        gpu_cores = run_text(["sysctl", "-n", "hw.perflevel0.physicalcpu"])
        try:
            info["performance_cores"] = int(gpu_cores)
        except (ValueError, TypeError):
            info["performance_cores"] = None
        info["metal"] = run_text(["system_profiler", "SPDisplaysDataType", "-json"]).startswith("{")
    return info


def _detect_npu() -> dict[str, Any]:
    info: dict[str, Any] = {"available": False}
    accel_paths = list(Path("/dev").glob("accel*"))
    if accel_paths:
        info["available"] = True
        info["devices"] = [str(p) for p in accel_paths]
    try:
        lsmod = run_text(["lsmod"])
        if "npu" in lsmod.lower() or "habanalabs" in lsmod.lower():
            info["available"] = True
            info["kernel_modules"] = [line for line in lsmod.splitlines() if "npu" in line.lower() or "habanalabs" in line.lower()]
    except Exception:  # noqa: BLE001
        pass
    if platform.system().lower() == "darwin":
        brand = run_text(["sysctl", "-n", "machdep.cpu.brand_string"])
        if "Apple" in brand and info.get("available") is False:
            info["available"] = "unknown"
            info["note"] = "Apple Silicon Neural Engine not directly enumerable via /dev/accel"
    return info


def _detect_memory() -> dict[str, Any]:
    info: dict[str, Any] = {}
    total = shutil.disk_usage(Path.cwd())
    info["disk_total"] = total.total
    info["disk_free"] = total.free
    info["disk_used"] = total.used
    cpu_count = os.cpu_count() or 0
    info["cpu_count"] = cpu_count
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    info["ram_total_kb"] = int(line.split()[1])
                    break
    except OSError:
        info["ram_total_kb"] = None
    if platform.system().lower() == "darwin":
        mem = run_text(["sysctl", "-n", "hw.memsize"])
        try:
            info["ram_total_kb"] = int(mem) // 1024
        except (ValueError, TypeError):
            pass
    if info.get("ram_total_kb"):
        info["ram_total_gb"] = round(info["ram_total_kb"] / 1024 / 1024, 1)
    return info


def write_probe(out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host = socket.gethostname()
    user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    os_release = platform.platform()
    python_version = platform.python_version()
    machine = platform.machine()
    processor = platform.processor()

    network_info = (
        run_text(["ip", "-brief", "addr"])
        if os.name != "nt"
        else run_text(["ipconfig"])
    )
    tooling = []
    for tool in ["git", "rg", "uv", "mise", "direnv", "just", "node", "pnpm", "python"]:
        path = shutil.which(tool)
        if path is None:
            tooling.append(f"{tool:12}missing")
        else:
            version = run_text([tool, "--version"]).splitlines()[0]
            tooling.append(f"{tool:12}{version}")

    nvidia = _detect_nvidia_gpu()
    amd = _detect_amd_gpu()
    intel_gpu = _detect_intel_gpu()
    vulkan_gpus = _detect_vulkan_gpus()
    apple = _detect_apple_silicon()
    npu = _detect_npu()
    memory = _detect_memory()

    accelerators = []
    if nvidia.get("available"):
        accelerators.append(f"nvidia:{nvidia.get('vram_total_mb', 0)}MB")
    if amd.get("available"):
        accelerators.append(f"amd:{amd.get('vram_total_mb', 0)}MB")
    if intel_gpu.get("available"):
        accelerators.append("intel:igpu")
    if apple.get("available"):
        accelerators.append(f"apple-silicon:{apple.get('chip', 'unknown')}")
    if npu.get("available") is True:
        accelerators.append("npu:available")

    sections = [
        "# System Probe",
        "",
        f"- Generated (UTC): {timestamp}",
        f"- Host: {host}",
        f"- User: {user}",
        f"- Working directory: {Path.cwd()}",
        "",
        "## OS and Runtime",
        "```text",
        f"OS: {os_release}",
        f"Machine: {machine}",
        f"Processor: {processor}",
        f"Python: {python_version}",
        "```",
        "",
        "## CPU and Memory",
        "```text",
        f"CPU count: {memory.get('cpu_count', 0)}",
        f"RAM total: {_format_bytes((memory.get('ram_total_kb') or 0) * 1024)}",
        "```",
        "",
        "## Disk",
        "```text",
        f"Disk total: {_format_bytes(memory.get('disk_total', 0))}",
        f"Disk used: {_format_bytes(memory.get('disk_used', 0))}",
        f"Disk free: {_format_bytes(memory.get('disk_free', 0))}",
        "```",
        "",
        "## Network",
        "```text",
        network_info[:4000],
        "```",
        "",
        "## Accelerators",
        "```text",
        f"Detected: {', '.join(accelerators) if accelerators else 'none'}",
        "",
    ]

    if nvidia.get("available"):
        sections.append("### NVIDIA GPUs")
        sections.append("```text")
        for gpu in nvidia.get("gpus", []):
            sections.append(
                f"  [{gpu['index']}] {gpu['name']} | "
                f"VRAM {gpu['memory_total_mb']}MB (free {gpu['memory_free_mb']}MB) | "
                f"util {gpu['utilization_pct']}%"
            )
        sections.append("```")
        sections.append("")

    if amd.get("available"):
        sections.append("### AMD GPUs")
        sections.append("```text")
        for gpu in amd.get("gpus", []):
            sections.append(
                f"  [{gpu['index']}] {gpu['name']} | "
                f"VRAM {gpu['memory_total_mb']}MB (free {gpu['memory_free_mb']}MB) | "
                f"util {gpu['utilization_pct']}%"
            )
        sections.append("```")
        sections.append("")

    if intel_gpu.get("available"):
        sections.append("### Intel GPU")
        sections.append("```text")
        if intel_gpu.get("renderer"):
            sections.append(f"  Renderer: {intel_gpu['renderer']}")
        if intel_gpu.get("top_output"):
            sections.append(f"  Top: {intel_gpu['top_output']}")
        sections.append("```")
        sections.append("")

    if apple.get("available"):
        sections.append("### Apple Silicon")
        sections.append("```text")
        sections.append(f"  Chip: {apple.get('chip')}")
        sections.append(f"  Cores: {apple.get('physical_cores')}")
        sections.append(f"  Performance cores: {apple.get('performance_cores')}")
        sections.append(f"  RAM: {_format_bytes((apple.get('memory_bytes') or 0))}")
        sections.append("```")
        sections.append("")

    if npu.get("available") is True:
        sections.append("### NPU")
        sections.append("```text")
        if npu.get("devices"):
            sections.append(f"  Devices: {', '.join(npu['devices'])}")
        if npu.get("kernel_modules"):
            sections.append(f"  Modules: {', '.join(npu['kernel_modules'])}")
        sections.append("```")
        sections.append("")

    if vulkan_gpus:
        sections.append("### Vulkan Devices")
        sections.append("```text")
        for entry in vulkan_gpus:
            sections.append(f"  {entry.get('vulkan', 'unknown')}")
        sections.append("```")
        sections.append("")

    sections.extend([
        "## Core Tooling Snapshot",
        "```text",
        *tooling,
        "```",
        "",
    ])

    content = "\n".join(sections)
    out_file.write_text(content, encoding="utf-8")


def main() -> int:
    out_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/system-probe.md")
    write_probe(out_file)
    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
