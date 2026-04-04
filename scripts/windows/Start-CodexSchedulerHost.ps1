param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$ComposeFile = "",
  [string]$AppUrl = "http://127.0.0.1:8787",
  [int]$WaitSeconds = 90,
  [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
  $ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
}

if (-not (Test-Path $ComposeFile)) {
  throw "docker-compose.yml not found at '$ComposeFile'"
}

try {
  & docker version | Out-Null
} catch {
  throw "Docker is not available. Start Docker Desktop and retry."
}

Write-Host "Starting Codex Scheduler Studio container host..."
& docker compose -f $ComposeFile up -d --build codex-scheduler-studio | Out-Host

$deadline = (Get-Date).AddSeconds([Math]::Max(10, $WaitSeconds))
$healthy = $false
while ((Get-Date) -lt $deadline) {
  try {
    $response = Invoke-WebRequest -Uri "$AppUrl/api/health" -UseBasicParsing -TimeoutSec 3
    if ($response.StatusCode -eq 200) {
      $healthy = $true
      break
    }
  } catch {
    Start-Sleep -Seconds 2
  }
}

if (-not $healthy) {
  throw "Host started but health endpoint did not become ready within $WaitSeconds seconds."
}

Write-Host "Codex Scheduler Studio is ready at $AppUrl"
if ($OpenBrowser) {
  Start-Process $AppUrl | Out-Null
}
