param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$TaskPrefix = "CodexSchedulerStudio",
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$startScript = Join-Path $PSScriptRoot "Start-CodexSchedulerHost.ps1"
$trayScript = Join-Path $PSScriptRoot "CodexSchedulerTray.ps1"
$hostTaskName = "$TaskPrefix-HostService"
$trayTaskName = "$TaskPrefix-Tray"

function Remove-TaskIfExists([string]$TaskName) {
  try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "Removed task: $TaskName"
  } catch {
    Write-Host "Task not present: $TaskName"
  }
}

if ($Uninstall) {
  Remove-TaskIfExists -TaskName $hostTaskName
  Remove-TaskIfExists -TaskName $trayTaskName
  return
}

if (-not (Test-Path $startScript)) {
  throw "Missing script: $startScript"
}
if (-not (Test-Path $trayScript)) {
  throw "Missing script: $trayScript"
}

$hostAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`" -RepoRoot `"$RepoRoot`""
$hostTrigger = New-ScheduledTaskTrigger -AtStartup
$hostPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$hostSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
  Register-ScheduledTask -TaskName $hostTaskName -Action $hostAction -Trigger $hostTrigger -Principal $hostPrincipal -Settings $hostSettings -Force | Out-Null
  Write-Host "Installed task: $hostTaskName (startup service mode)"
} catch {
  Write-Warning "Could not install SYSTEM startup task. Run this script as Administrator if you need host-as-service mode."
}

$currentUser = "$env:USERDOMAIN\$env:USERNAME"
$trayAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayScript`" -RepoRoot `"$RepoRoot`""
$trayTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$trayPrincipal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$traySettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $trayTaskName -Action $trayAction -Trigger $trayTrigger -Principal $trayPrincipal -Settings $traySettings -Force | Out-Null
Write-Host "Installed task: $trayTaskName (tray at user logon)"

Write-Host ""
Write-Host "Windows app mode installed."
Write-Host "Use Task Scheduler to verify tasks:"
Write-Host "  $hostTaskName"
Write-Host "  $trayTaskName"
