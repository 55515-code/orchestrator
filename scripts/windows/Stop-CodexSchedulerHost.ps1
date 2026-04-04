param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$ComposeFile = "",
  [switch]$Down
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
  $ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
}

if (-not (Test-Path $ComposeFile)) {
  throw "docker-compose.yml not found at '$ComposeFile'"
}

if ($Down) {
  Write-Host "Stopping and removing stack containers..."
  & docker compose -f $ComposeFile down | Out-Host
} else {
  Write-Host "Stopping Codex Scheduler Studio service container..."
  & docker compose -f $ComposeFile stop codex-scheduler-studio | Out-Host
}

Write-Host "Host stop command completed."
