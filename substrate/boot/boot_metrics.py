"""Boot Metrics Collector.

Collects granular end-to-end boot performance metrics on Linux systems
with systemd. Designed to run as a oneshot systemd service early in boot
to capture kernel initialization, service startup, and userspace timing.

Output: JSON file in state/boot/ with per-service timestamps, process
resource utilization, kernel phase timings, and total boot duration.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT_DIR = Path("/home/ahron/codespace")
STATE_DIR = ROOT_DIR / "state" / "boot"
DEFAULT_OUTPUT = STATE_DIR / "latest.json"
JOURNAL_BOOT_ID_FILE = "/proc/sys/kernel/random/boot_id"
BOOT_TIME_FILE = "/proc/stat"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def run(cmd: list[str], *, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def read_file(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Kernel / boot identification
# ---------------------------------------------------------------------------


def get_boot_id() -> str | None:
    """Return the current boot ID from /proc/1/boot_id."""
    text = read_file(JOURNAL_BOOT_ID_FILE)
    if text:
        return text.strip()
    return None


def get_kernel_version() -> str | None:
    """Return the running kernel version."""
    return read_file("/proc/version")


def get_kernel_cmdline() -> str | None:
    """Return the kernel command line."""
    return read_file("/proc/cmdline")


# ---------------------------------------------------------------------------
# Timing collection
# ---------------------------------------------------------------------------


def get_systemd_analyze() -> dict[str, Any]:
    """Collect systemd-analyze timing data."""
    result: dict[str, Any] = {
        "time": None,
        "blame": [],
        "critical_chain": None,
        "plot": None,
    }

    # Total timing breakdown
    proc = run(["systemd-analyze", "time"])
    if proc.returncode == 0:
        result["time"] = proc.stdout.strip()

    # Per-service blame
    proc = run(["systemd-analyze", "blame"])
    if proc.returncode == 0:
        lines = proc.stdout.strip().splitlines()
        result["blame"] = [
            {
                "time": line.split()[0] if line.split() else "",
                "unit": " ".join(line.split()[1:]) if len(line.split()) > 1 else "",
            }
            for line in lines[:50]  # top 50 slowest
        ]

    # Critical chain
    proc = run(["systemd-analyze", "critical-chain"])
    if proc.returncode == 0:
        result["critical_chain"] = proc.stdout.strip()

    return result


def get_journal_boot_events() -> dict[str, Any]:
    """Collect journal entries for the current boot with timing info."""
    result: dict[str, Any] = {
        "boot_id": get_boot_id(),
        "events": [],
        "service_timestamps": {},
    }

    # Get all journal entries for this boot, focusing on service boundaries
    proc = run([
        "journalctl",
        "--boot",
        "-o", "short-iso",
        "--no-pager",
        "-n", "5000",
    ], timeout=60)

    if proc.returncode != 0:
        return result

    # Parse service start/stop messages
    service_events: dict[str, dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        # Look for systemd service start/stop messages
        if (
            ": Starting " in line
            or ": Started " in line
            or ": Stopped " in line
            or ": Reached " in line
            or "timed out" in line.lower()
            or "timeout" in line.lower()
        ):
            result["events"].append(line)

        # Extract service timestamps
        if "]: " in line:
            parts = line.split("]: ", 1)
            if len(parts) == 2:
                ts = parts[0].strip()
                msg = parts[1].strip()
                # Match service names like: nginx.service, getty@tty1.service
                if ".service" in msg or "target" in msg:
                    import re
                    unit_match = re.search(r"([a-zA-Z0-9@._-]+\.(service|target|socket|mount|device))", msg)
                    if unit_match:
                        unit = unit_match.group(1)
                        if unit not in service_events:
                            service_events[unit] = {"timestamps": []}
                        service_events[unit]["timestamps"].append({"time": ts, "message": msg[:120]})

    # Convert to list format
    result["service_timestamps"] = [
        {"unit": unit, "events": data["timestamps"][:10]}
        for unit, data in service_events.items()
    ]

    return result


def get_process_stats() -> dict[str, Any]:
    """Snapshot of active processes during collection."""
    result: dict[str, Any] = {
        "snapshot_time": utc_now_iso(),
        "processes": [],
    }

    # Get process tree with resource usage
    proc = run(["ps", "aux", "--sort=-%cpu"], timeout=10)
    if proc.returncode == 0:
        lines = proc.stdout.strip().splitlines()[1:21]  # top 20
        for line in lines:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                result["processes"].append({
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu_percent": parts[2],
                    "memory_percent": parts[3],
                    "vsz": parts[4],
                    "rss": parts[5],
                    "tty": parts[6],
                    "stat": parts[7],
                    "start": parts[8],
                    "time": parts[9],
                    "command": parts[10][:200],
                })

    return result


def get_systemd_service_states() -> dict[str, Any]:
    """Get current state of all systemd services."""
    result: dict[str, Any] = {
        "snapshot_time": utc_now_iso(),
        "services": [],
    }

    proc = run(["systemctl", "list-units", "--type=service", "--all", "--no-pager", "-o", "json"], timeout=15)
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            for unit in data[:100]:  # limit output
                result["services"].append({
                    "name": unit.get("unit", ""),
                    "load": unit.get("load", ""),
                    "active": unit.get("active", ""),
                    "sub": unit.get("sub", ""),
                    "description": unit.get("description", "")[:100],
                })
        except (json.JSONDecodeError, KeyError):
            pass

    return result


# ---------------------------------------------------------------------------
# Kernel initialization phase timing
# ---------------------------------------------------------------------------


def get_kernel_boot_timing() -> dict[str, Any]:
    """Extract kernel boot timing from /proc/stat and dmesg."""
    result: dict[str, Any] = {
        "proc_stat": None,
        "dmesg_timestamps": [],
        "early_boot_msgs": [],
    }

    # /proc/stat gives btime (boot time in seconds since epoch)
    text = read_file("/proc/stat")
    if text:
        for line in text.splitlines():
            if line.startswith("btime "):
                btime = int(line.split()[1])
                result["proc_stat"] = {
                    "btime": btime,
                    "btime_iso": datetime.fromtimestamp(btime, tz=UTC).isoformat(),
                }
                break

    # dmesg timestamps (relative to boot)
    proc = run(["dmesg", "-T", "--level=emerg,alert,crit,err,warn,notice,info"], timeout=10)
    if proc.returncode == 0:
        lines = proc.stdout.strip().splitlines()
        # Capture early boot messages (first 100)
        result["early_boot_msgs"] = [
            {
                "timestamp": line.split("]")[0].strip() + "]" if "]" in line else "",
                "message": line.split("]")[1].strip() if "]" in line else line[:120],
            }
            for line in lines[:100]
        ]

    return result


# ---------------------------------------------------------------------------
# Bootloader-to-kernel handoff
# ---------------------------------------------------------------------------


def get_grub_timing() -> dict[str, Any]:
    """Extract GRUB-related timing from journal."""
    result: dict[str, Any] = {
        "grub_entries": [],
        "kernel_handoff": None,
    }

    # Look for GRUB and kernel handoff messages
    proc = run([
        "journalctl",
        "--boot",
        "-o", "short-iso",
        "--no-pager",
        "-g", "grub|kernel|linux|initrd|boot",
        "-n", "200",
    ], timeout=30)

    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if any(kw in line.lower() for kw in ["grub", "linux ", "initrd", "kernel", "boot"]):
                result["grub_entries"].append(line[:200])

    return result


# ---------------------------------------------------------------------------
# Display manager timing
# ---------------------------------------------------------------------------


def get_display_manager_timing() -> dict[str, Any]:
    """Capture display manager startup timing if present."""
    result: dict[str, Any] = {
        "dm_detected": False,
        "dm_service": None,
        "dm_start_time": None,
        "dm_ready_time": None,
        "login_prompt_time": None,
    }

    # Common display managers
    dm_services = ["gdm.service", "sddm.service", "lightdm.service", "getty@tty1.service"]

    for dm in dm_services:
        proc = run([
            "journalctl",
            "--boot",
            "-u", dm,
            "-o", "short-iso",
            "--no-pager",
            "-n", "50",
        ], timeout=15)

        if proc.returncode == 0 and proc.stdout.strip():
            result["dm_detected"] = True
            result["dm_service"] = dm
            lines = proc.stdout.strip().splitlines()
            if lines:
                result["dm_start_time"] = lines[0][:200]
            if len(lines) > 1:
                result["dm_ready_time"] = lines[-1][:200]
            break

    return result


# ---------------------------------------------------------------------------
# Main collection
# ---------------------------------------------------------------------------


def collect_boot_metrics(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Collect all boot metrics and write to output file."""
    metrics: dict[str, Any] = {
        "schema_version": "1.0.0",
        "collection_time": utc_now_iso(),
        "host": os.uname().nodename,
        "kernel": os.uname().release,
        "architecture": os.uname().machine,
        "boot_id": get_boot_id(),
        "kernel_version": get_kernel_version(),
        "kernel_cmdline": get_kernel_cmdline(),
        "kernel_timing": get_kernel_boot_timing(),
        "systemd_timing": get_systemd_analyze(),
        "journal_events": get_journal_boot_events(),
        "process_snapshot": get_process_stats(),
        "service_states": get_systemd_service_states(),
        "grub_timing": get_grub_timing(),
        "display_manager": get_display_manager_timing(),
    }

    write_json(output_path, metrics)
    return metrics


def print_summary(metrics: dict[str, Any]) -> None:
    """Print a human-readable summary of boot metrics."""
    print("=" * 60)
    print("BOOT METRICS SUMMARY")
    print("=" * 60)

    # Kernel timing
    kt = metrics.get("kernel_timing", {})
    ps = kt.get("proc_stat", {})
    if ps:
        print(f"Boot time (btime): {ps.get('btime_iso', 'unknown')}")

    # Systemd timing
    st = metrics.get("systemd_timing", {})
    if st.get("time"):
        print(f"systemd-analyze time: {st['time']}")

    # Slowest services
    if st.get("blame"):
        print("\nTop 5 slowest services:")
        for entry in st["blame"][:5]:
            print(f"  {entry.get('time', '?')} {entry.get('unit', '?')}")

    # Display manager
    dm = metrics.get("display_manager", {})
    if dm.get("dm_detected"):
        print(f"\nDisplay manager: {dm.get('dm_service')}")
    else:
        print("\nNo display manager detected")

    # Output file
    print(f"\nDetailed metrics written to: {DEFAULT_OUTPUT}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Boot Metrics Collector")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--summary", action="store_true", help="Print summary after collection")
    args = parser.parse_args()

    try:
        metrics = collect_boot_metrics(args.output)
        if args.summary:
            print_summary(metrics)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Boot metrics collection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
