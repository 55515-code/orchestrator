from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DeploymentRequest:
    task_name: str
    host: str
    port: int
    python_path: str
    user: str
    logon_type: str
    password: str | None
    codex_scheduler_db: str | None
    codex_scheduler_disable_autostart: bool
    run_level: str
    working_directory: str


def _ps_escape(value: str) -> str:
    return value.replace("`", "``").replace('"', '`"')


def _run_powershell(script: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def install_headless_task(request: DeploymentRequest) -> dict:
    working_dir = Path(request.working_directory).resolve()
    uvicorn_args = f'-m uvicorn substrate.web:app --host {_ps_escape(request.host)} --port {request.port}'
    env_lines = []
    if request.codex_scheduler_db:
        env_lines.append(f'$env:CODEX_SCHEDULER_DB = "{_ps_escape(request.codex_scheduler_db)}"')
    if request.codex_scheduler_disable_autostart:
        env_lines.append('$env:CODEX_SCHEDULER_DISABLE_AUTOSTART = "1"')

    env_block = "\n".join(env_lines)
    run_level = "Highest" if request.run_level.lower() == "highest" else "Limited"

    logon_type = request.logon_type.lower()
    if logon_type not in {"interactive", "s4u", "password"}:
        raise RuntimeError("logon_type must be interactive, s4u, or password.")

    if logon_type == "password" and not request.password:
        raise RuntimeError("Password is required when logon_type=password.")

    principal_line = ""
    register_line = ""
    if logon_type == "password":
        register_line = (
            f'Register-ScheduledTask -TaskName "{_ps_escape(request.task_name)}" -Action $action -Trigger $trigger '
            f'-Settings $settings -User "{_ps_escape(request.user)}" -Password "{_ps_escape(request.password or "")}" -RunLevel {run_level} -Force | Out-Null'
        )
    else:
        ps_logon = "Interactive" if logon_type == "interactive" else "S4U"
        principal_line = f'$principal = New-ScheduledTaskPrincipal -UserId "{_ps_escape(request.user)}" -LogonType {ps_logon} -RunLevel {run_level}'
        register_line = (
            f'Register-ScheduledTask -TaskName "{_ps_escape(request.task_name)}" -Action $action -Trigger $trigger '
            f'-Settings $settings -Principal $principal -Force | Out-Null'
        )

    script = f"""
$ErrorActionPreference = "Stop"
{env_block}
$action = New-ScheduledTaskAction -Execute "{_ps_escape(request.python_path)}" -Argument "{_ps_escape(uvicorn_args)}" -WorkingDirectory "{_ps_escape(str(working_dir))}"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
{principal_line}
{register_line}
Write-Output "ok"
""".strip()

    code, stdout, stderr = _run_powershell(script)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "Failed to install scheduled task.")

    return {"task_name": request.task_name, "status": "installed", "stdout": stdout.strip()}


def uninstall_headless_task(task_name: str) -> dict:
    script = f"""
$ErrorActionPreference = "Stop"
if (Get-ScheduledTask -TaskName "{_ps_escape(task_name)}" -ErrorAction SilentlyContinue) {{
  Unregister-ScheduledTask -TaskName "{_ps_escape(task_name)}" -Confirm:$false
  Write-Output "removed"
}} else {{
  Write-Output "not_found"
}}
""".strip()
    code, stdout, stderr = _run_powershell(script)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "Failed to remove scheduled task.")
    return {"task_name": task_name, "status": stdout.strip()}


def get_task_status(task_name: str) -> dict:
    script = f"""
$task = Get-ScheduledTask -TaskName "{_ps_escape(task_name)}" -ErrorAction SilentlyContinue
if ($null -eq $task) {{
  Write-Output "{{""exists"":false}}"
}} else {{
  $obj = [PSCustomObject]@{{ exists = $true; state = $task.State.ToString(); taskPath = $task.TaskPath; taskName = $task.TaskName }}
  $obj | ConvertTo-Json -Compress
}}
""".strip()
    code, stdout, stderr = _run_powershell(script)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "Failed to query scheduled task.")
    return json.loads(stdout.strip())
