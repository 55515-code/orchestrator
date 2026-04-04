from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from substrate.orchestrator import Orchestrator

from ...models import Job, RunRecord
from ...runner import execute_job


def execute_now(
    *,
    session: Session,
    job: Job,
    run_root: Path,
    orchestrator: Orchestrator,
) -> RunRecord:
    return execute_job(session, job, run_root, orchestrator)
