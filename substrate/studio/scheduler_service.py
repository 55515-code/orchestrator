from __future__ import annotations

from pathlib import Path
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from croniter import croniter
from sqlalchemy.orm import Session

from substrate.orchestrator import Orchestrator

from .models import Job
from .runner import execute_job


class SchedulerService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        run_root: Path,
        orchestrator: Orchestrator,
    ) -> None:
        self.session_factory = session_factory
        self.run_root = run_root
        self.orchestrator = orchestrator
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.reload_all()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def reload_all(self) -> None:
        self.scheduler.remove_all_jobs()
        with self.session_factory() as session:
            jobs = session.query(Job).filter(Job.enabled.is_(True)).all()
            for job in jobs:
                self.schedule_job(job)

    def schedule_job(self, job: Job) -> None:
        schedule_id = self.schedule_id(job.id)
        if job.schedule_type == "cron":
            cron_expr = (job.cron_expr or "").strip()
            if not croniter.is_valid(cron_expr):
                return
            trigger = CronTrigger.from_crontab(cron_expr)
        else:
            minutes = int(job.interval_minutes or 0)
            if minutes < 1:
                return
            trigger = IntervalTrigger(minutes=minutes)

        self.scheduler.add_job(
            self.execute_job_id,
            trigger=trigger,
            id=schedule_id,
            replace_existing=True,
            args=[job.id],
            coalesce=True,
            max_instances=1,
            misfire_grace_time=120,
        )

    def unschedule_job(self, job_id: int) -> None:
        try:
            self.scheduler.remove_job(self.schedule_id(job_id))
        except Exception:
            return

    def execute_job_id(self, job_id: int) -> None:
        with self.session_factory() as session:
            job = session.query(Job).filter(Job.id == job_id).one_or_none()
            if not job or not job.enabled:
                return
            execute_job(session, job, self.run_root, self.orchestrator)

    @staticmethod
    def schedule_id(job_id: int) -> str:
        return f"codex-job-{job_id}"
