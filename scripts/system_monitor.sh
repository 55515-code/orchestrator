#!/usr/bin/env bash
# system_monitor.sh — lightweight system health and log anomaly monitor.
# Intended to run from systemd timers or cron; outputs warnings to stdout/stderr.
set -uo pipefail

THRESH_DISK_WARN=85
THRESH_DISK_CRIT=95
THRESH_MEM_WARN=85
THRESH_CPU_WARN=80
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/substrate-monitor"
mkdir -p "$STATE_DIR"

log() { echo "system-monitor: $*"; }
warn() { echo "system-monitor WARNING: $*" >&2; }
crit() { echo "system-monitor CRITICAL: $*" >&2; }

check_disk() {
  df -P --local -x tmpfs -x devtmpfs -x overlay 2>/dev/null | awk 'NR>1 {print $5, $6}' | while read -r pct mount; do
    pct=${pct%%%}
    if [ "$pct" -ge "$THRESH_DISK_CRIT" ]; then
      crit "disk usage ${pct}% on ${mount} (>= ${THRESH_DISK_CRIT}%)"
    elif [ "$pct" -ge "$THRESH_DISK_WARN" ]; then
      warn "disk usage ${pct}% on ${mount} (>= ${THRESH_DISK_WARN}%)"
    fi
  done
}

check_mem() {
  if command -v free >/dev/null 2>&1; then
    mem_pct=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
    if [ "$mem_pct" -ge "$THRESH_MEM_WARN" ]; then
      warn "memory usage ${mem_pct}% (>= ${THRESH_MEM_WARN}%)"
    else
      log "memory usage ${mem_pct}%"
    fi
  fi
}

check_cpu() {
  if command -v nproc >/dev/null 2>&1; then
    cores=$(nproc)
  else
    cores=1
  fi
  load=$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo 0)
  load_pct=$(awk -v l="$load" -v c="$cores" 'BEGIN {printf "%.0f", (l/c)*100}')
  if [ "$load_pct" -ge "$THRESH_CPU_WARN" ]; then
    warn "cpu load ${load} on ${cores} cores (${load_pct}% >= ${THRESH_CPU_WARN}%)"
  else
    log "cpu load ${load} on ${cores} cores (${load_pct}%)"
  fi
}

check_failed_services() {
  if command -v systemctl >/dev/null 2>&1; then
    mapfile -t failed < <(systemctl --user --failed --plain --no-legend 2>/dev/null | awk '{print $1}')
    if [ "${#failed[@]}" -gt 0 ]; then
      warn "failed user services: ${failed[*]}"
    fi
    mapfile -t failed_sys < <(systemctl --system --failed --plain --no-legend 2>/dev/null | awk '{print $1}')
    if [ "${#failed_sys[@]}" -gt 0 ]; then
      warn "failed system services: ${failed_sys[*]}"
    fi
  fi
}

check_log_anomalies() {
  local since="${1:-24 hours ago}"
  local anomalies=0
  if command -v journalctl >/dev/null 2>&1; then
    mapfile -t sudo_fails < <(journalctl -u sudo -u auth --since "$since" --no-pager 2>/dev/null | grep -cE 'authentication failure|Failed password|sudo:.*auth failure' || true)
    mapfile -t oom < <(journalctl --since "$since" --no-pager 2>/dev/null | grep -cE 'Out of memory|oom-kill|Killed process' || true)
    mapfile -t segfault < <(journalctl --since "$since" --no-pager 2>/dev/null | grep -cE 'segfault|general protection fault' || true)
    mapfile -t disk_io < <(journalctl --since "$since" --no-pager 2>/dev/null | grep -vE 'system_monitor|system-monitor' | grep -cE 'I/O error|EXT4-fs error|BTRFS.*(error|fail)' || true)

    if [ "${sudo_fails[0]:-0}" -gt 0 ]; then
      warn "${sudo_fails[0]} sudo/auth failure(s) in last ${since}"
      anomalies=$((anomalies + sudo_fails[0]))
    fi
    if [ "${oom[0]:-0}" -gt 0 ]; then
      crit "${oom[0]} OOM event(s) in last ${since}"
      anomalies=$((anomalies + oom[0]))
    fi
    if [ "${segfault[0]:-0}" -gt 0 ]; then
      warn "${segfault[0]} segfault(s) in last ${since}"
      anomalies=$((anomalies + segfault[0]))
    fi
    if [ "${disk_io[0]:-0}" -gt 0 ]; then
      warn "${disk_io[0]} disk I/O error(s) in last ${since}"
      anomalies=$((anomalies + disk_io[0]))
    fi
  fi

  if [ "$anomalies" -eq 0 ]; then
    log "no log anomalies in last ${since}"
  fi
  echo "$anomalies" > "$STATE_DIR/last_anomaly_count"
}

main() {
  log "=== system monitor start ==="
  check_disk
  check_mem
  check_cpu
  check_failed_services
  check_log_anomalies "${1:-24 hours ago}"
  log "=== system monitor complete ==="
}

main "$@"
