from __future__ import annotations

import importlib.metadata as metadata
from dataclasses import dataclass
import shutil


EXPECTED_PACKAGES = {
    "fastapi": "0.135.2",
    "starlette": "1.0.0",
    "sqlalchemy": "2.0.48",
    "apscheduler": "3.11.2",
    "croniter": "6.2.2",
    "jinja2": "3.1.6",
}


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def run_preflight(codex_executable: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    exe = codex_executable.strip() or "codex"
    resolved = shutil.which(exe)
    if resolved:
        checks.append(CheckResult("codex_cli", "ok", f"Found at {resolved}"))
    else:
        checks.append(CheckResult("codex_cli", "error", f"'{exe}' is not on PATH."))

    for pkg, expected in EXPECTED_PACKAGES.items():
        try:
            installed = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            checks.append(CheckResult(f"dep:{pkg}", "error", "Package not installed"))
            continue
        if installed == expected:
            checks.append(CheckResult(f"dep:{pkg}", "ok", f"{installed}"))
        else:
            checks.append(CheckResult(f"dep:{pkg}", "warning", f"Installed {installed}, expected {expected}"))

    return checks
