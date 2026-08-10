param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$AppUrl = "http://127.0.0.1:8787",
  [switch]$StartHostOnLaunch
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$startScript = Join-Path $PSScriptRoot "Start-CodexSchedulerHost.ps1"
$stopScript = Join-Path $PSScriptRoot "Stop-CodexSchedulerHost.ps1"

function Start-HostService {
  Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$startScript`"",
    "-RepoRoot", "`"$RepoRoot`""
  ) | Out-Null
}

function Stop-HostService {
  Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$stopScript`"",
    "-RepoRoot", "`"$RepoRoot`""
  ) | Out-Null
}

function Open-Dashboard {
  Start-Process $AppUrl | Out-Null
}

$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$notifyIcon.Icon = [System.Drawing.SystemIcons]::Application
$notifyIcon.Text = "Codex Scheduler Studio"
$notifyIcon.Visible = $true

$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip
$openItem = $contextMenu.Items.Add("Open Dashboard")
$startItem = $contextMenu.Items.Add("Start Host")
$stopItem = $contextMenu.Items.Add("Stop Host")
$separator = $contextMenu.Items.Add("-")
$exitItem = $contextMenu.Items.Add("Exit")

$openItem.Add_Click({ Open-Dashboard })
$startItem.Add_Click({ Start-HostService })
$stopItem.Add_Click({ Stop-HostService })
$exitItem.Add_Click({
  $notifyIcon.Visible = $false
  [System.Windows.Forms.Application]::Exit()
})

$notifyIcon.ContextMenuStrip = $contextMenu
$notifyIcon.Add_DoubleClick({ Open-Dashboard })
$notifyIcon.ShowBalloonTip(3500, "Codex Scheduler Studio", "Tray mode started. Double-click to open the dashboard.", [System.Windows.Forms.ToolTipIcon]::Info)

if ($StartHostOnLaunch) {
  Start-HostService
}

[System.Windows.Forms.Application]::Run()
