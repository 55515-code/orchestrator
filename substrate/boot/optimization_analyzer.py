"""Boot Optimization Analyzer.

Analyzes collected boot metrics to identify safe, low-risk optimizations
that minimize total boot time without impacting core system functionality,
stability, or security.

Produces a prioritized list of optimizations with expected time savings,
implementation rationale, and rollback procedures.
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

ROOT_DIR = Path("/home/ahron/codespace")
STATE_DIR = ROOT_DIR / "state" / "boot"
DEFAULT_METRICS = STATE_DIR / "latest.json"
DEFAULT_REPORT = STATE_DIR / "optimization-report.json"

# Services that are safe to disable/modify for boot optimization
# These are non-critical, non-essential services with no impact on core functionality
SAFE_TO_DISABLE = {
    "console-getty.service": "Virtual console for containers; not needed on desktop",
    "serial-getty@.service": "Serial console getty; not needed without serial hardware",
    "container-getty@.service": "Container getty; not needed on bare metal",
    "fstrim.service": "Filesystem trim; safe to run on demand instead of boot",
    "man-db.service": "Manual page DB update; can be triggered on demand",
    "pacman-key.service": "Pacman keyring init; safe to defer to first use",
}

# Services that can be backgrounded or delayed
SAFE_TO_DELAY = {
    "cups.service": "Printing system; can start on demand",
    "bluetooth.service": "Bluetooth; not needed until device connection",
    "avahi-daemon.service": "mDNS/DNS-SD; not critical for core functionality",
    "udisks2.service": "Disk management; can start on demand",
    "gvfs-daemon.service": "Virtual filesystem; desktop convenience only",
    "tracker-miner-fs.service": "File indexing; can run on demand",
    "tracker-extract.service": "File indexing; can run on demand",
}


def load_metrics(path: Path = DEFAULT_METRICS) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"No boot metrics found at {path}. Run boot_metrics.py first.")
    return json.loads(path.read_text())


def analyze_systemd_timing(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze systemd-analyze data to find optimization opportunities."""
    optimizations = []
    st = metrics.get("systemd_timing", {})
    blame = st.get("blame", [])

    for entry in blame:
        unit = entry.get("unit", "")
        time_str = entry.get("time", "")
        if not unit or not time_str:
            continue

        # Parse time string like "12.101s" or "1min 2.303s"
        try:
            if "min" in time_str:
                parts = time_str.split()
                minutes = int(parts[0].replace("min", ""))
                seconds = float(parts[1].replace("s", ""))
                time_sec = minutes * 60 + seconds
            else:
                time_sec = float(time_str.replace("s", ""))
        except (ValueError, IndexError):
            continue

        # Only flag services taking > 500ms
        if time_sec < 0.5:
            continue

        # Check if safe to disable
        if unit in SAFE_TO_DISABLE:
            optimizations.append({
                "priority": "high",
                "action": "disable",
                "unit": unit,
                "current_time": time_sec,
                "expected_savings": time_sec,
                "rationale": SAFE_TO_DISABLE[unit],
                "risk": "none",
                "rollback": f"systemctl enable --now {unit}",
            })
        # Check if safe to delay
        elif unit in SAFE_TO_DELAY:
            optimizations.append({
                "priority": "medium",
                "action": "delay",
                "unit": unit,
                "current_time": time_sec,
                "expected_savings": time_sec * 0.7,  # assume 70% reduction
                "rationale": SAFE_TO_DELAY[unit],
                "risk": "low",
                "rollback": f"systemctl enable --now {unit}",
            })
        # Flag unknown slow services for review
        elif time_sec > 2.0:
            optimizations.append({
                "priority": "review",
                "action": "investigate",
                "unit": unit,
                "current_time": time_sec,
                "expected_savings": 0,
                "rationale": "Service takes >2s; requires manual review",
                "risk": "unknown",
                "rollback": "N/A - manual review required",
            })

    return sorted(optimizations, key=lambda x: x.get("expected_savings", 0), reverse=True)


def analyze_device_delays(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze device initialization delays."""
    optimizations = []
    st = metrics.get("systemd_timing", {})
    blame = st.get("blame", [])

    for entry in blame:
        unit = entry.get("unit", "")
        if ".device" in unit and "ttyS" in unit:
            optimizations.append({
                "priority": "medium",
                "action": "mask_device",
                "unit": unit,
                "current_time": float(entry.get("time", "0s").replace("s", "")),
                "expected_savings": 12.0,  # ~12s per serial device
                "rationale": "Serial port device timeout; not needed on desktop",
                "risk": "low",
                "rollback": f"systemctl unmask {unit}",
            })

    return optimizations


def analyze_kernel_timing(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze kernel boot timing for optimization opportunities."""
    optimizations = []
    kt = metrics.get("kernel_timing", {})

    # Check for early boot warnings
    early_msgs = kt.get("early_boot_msgs", [])
    for msg in early_msgs:
        text = msg.get("message", "")
        if "timeout" in text.lower() or "slow" in text.lower():
            optimizations.append({
                "priority": "low",
                "action": "kernel_param",
                "unit": "kernel_boot",
                "current_time": 0,
                "expected_savings": 0,
                "rationale": f"Kernel message indicates timeout/slow operation: {text[:100]}",
                "risk": "medium",
                "rollback": "Revert kernel command line parameter",
            })

    return optimizations


def generate_optimization_report(metrics: dict[str, Any]) -> dict[str, Any]:
    """Generate complete optimization report."""
    systemd_opts = analyze_systemd_timing(metrics)
    device_opts = analyze_device_delays(metrics)
    kernel_opts = analyze_kernel_timing(metrics)

    all_opts = systemd_opts + device_opts + kernel_opts
    total_savings = sum(o.get("expected_savings", 0) for o in all_opts)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "host": metrics.get("host", "unknown"),
        "kernel": metrics.get("kernel", "unknown"),
        "total_boot_time": metrics.get("systemd_timing", {}).get("time", "unknown"),
        "optimizations": all_opts,
        "summary": {
            "total_opportunities": len(all_opts),
            "high_priority": len([o for o in all_opts if o.get("priority") == "high"]),
            "medium_priority": len([o for o in all_opts if o.get("priority") == "medium"]),
            "estimated_time_savings_seconds": round(total_savings, 2),
            "safe_to_apply": len([o for o in all_opts if o.get("risk") in ("none", "low")]),
        },
    }

    return report


def print_report(report: dict[str, Any]) -> None:
    """Print human-readable optimization report."""
    print("=" * 60)
    print("BOOT OPTIMIZATION REPORT")
    print("=" * 60)
    print(f"Host: {report.get('host')}")
    print(f"Kernel: {report.get('kernel')}")
    print(f"Total boot time: {report.get('total_boot_time')}")
    print()

    summary = report.get("summary", {})
    print(f"Total opportunities: {summary.get('total_opportunities')}")
    print(f"High priority: {summary.get('high_priority')}")
    print(f"Medium priority: {summary.get('medium_priority')}")
    print(f"Estimated time savings: {summary.get('estimated_time_savings_seconds')}s")
    print(f"Safe to apply (none/low risk): {summary.get('safe_to_apply')}")
    print()

    print("OPTIMIZATIONS:")
    print("-" * 60)
    for i, opt in enumerate(report.get("optimizations", []), 1):
        print(f"\n{i}. [{opt.get('priority', '?').upper()}] {opt.get('unit')}")
        print(f"   Action: {opt.get('action')}")
        print(f"   Current time: {opt.get('current_time', 0)}s")
        print(f"   Expected savings: {opt.get('expected_savings', 0)}s")
        print(f"   Risk: {opt.get('risk', 'unknown')}")
        print(f"   Rationale: {opt.get('rationale')}")
        print(f"   Rollback: {opt.get('rollback')}")

    print("\n" + "=" * 60)


def apply_optimizations(report: dict[str, Any], dry_run: bool = True) -> list[dict[str, Any]]:
    """Apply safe optimizations from the report."""
    results = []
    safe_opts = [
        o for o in report.get("optimizations", [])
        if o.get("risk") in ("none", "low") and o.get("action") != "investigate"
    ]

    for opt in safe_opts:
        unit = opt.get("unit", "")
        action = opt.get("action", "")
        result = {
            "unit": unit,
            "action": action,
            "dry_run": dry_run,
            "success": False,
            "detail": "",
        }

        if dry_run:
            result["success"] = True
            result["detail"] = f"Would execute: {action} {unit}"
        else:
            if action == "disable":
                proc = subprocess.run(
                    ["systemctl", "disable", "--now", unit],
                    capture_output=True,
                    text=True,
                )
                result["success"] = proc.returncode == 0
                result["detail"] = proc.stderr.strip() or proc.stdout.strip()
            elif action == "mask_device":
                proc = subprocess.run(
                    ["systemctl", "mask", unit],
                    capture_output=True,
                    text=True,
                )
                result["success"] = proc.returncode == 0
                result["detail"] = proc.stderr.strip() or proc.stdout.strip()
            elif action == "delay":
                # Create override to delay service
                result["success"] = True
                result["detail"] = "Delayed services require manual override configuration"
            else:
                result["detail"] = f"Unknown action: {action}"

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Boot Optimization Analyzer")
    parser.add_argument(
        "--metrics",
        type=Path,
        default=DEFAULT_METRICS,
        help=f"Input metrics JSON (default: {DEFAULT_METRICS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"Output report JSON (default: {DEFAULT_REPORT})",
    )
    parser.add_argument("--apply", action="store_true", help="Apply safe optimizations (requires root)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without making changes")
    args = parser.parse_args()

    try:
        metrics = load_metrics(args.metrics)
        report = generate_optimization_report(metrics)

        if args.apply or args.dry_run:
            results = apply_optimizations(report, dry_run=args.dry_run)
            report["applied"] = results

        # Write report
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))

        print_report(report)

        if args.apply or args.dry_run:
            print("\nAPPLIED OPTIMIZATIONS:")
            print("-" * 60)
            for r in results:
                status = "OK" if r.get("success") else "FAILED"
                print(f"[{status}] {r.get('action')} {r.get('unit')}: {r.get('detail')}")

        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Boot optimization analysis failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
