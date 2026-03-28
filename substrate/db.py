from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class OrchestratorDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY,
                  run_type TEXT NOT NULL,
                  repo_slug TEXT,
                  task_id TEXT,
                  objective TEXT,
                  stage TEXT NOT NULL DEFAULT 'local',
                  mode TEXT,
                  provider TEXT,
                  model TEXT,
                  status TEXT NOT NULL,
                  chain_path TEXT,
                  run_dir TEXT,
                  started_at TEXT NOT NULL,
                  finished_at TEXT,
                  exit_code INTEGER,
                  error_text TEXT,
                  metadata_json TEXT
                );
                """
            )
            columns = connection.execute("PRAGMA table_info(runs)").fetchall()
            column_names = {row["name"] for row in columns}
            if "stage" not in column_names:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN stage TEXT NOT NULL DEFAULT 'local';"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT NOT NULL,
                  ts TEXT NOT NULL,
                  level TEXT NOT NULL,
                  message TEXT NOT NULL,
                  payload_json TEXT,
                  FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS repository_snapshots (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  scanned_at TEXT NOT NULL,
                  repo_slug TEXT NOT NULL,
                  repo_path TEXT NOT NULL,
                  is_git_repo INTEGER NOT NULL,
                  branch TEXT,
                  dirty INTEGER,
                  last_commit_at TEXT,
                  remote_url TEXT,
                  default_branch TEXT,
                  details_json TEXT
                );
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_projects (
                  slug TEXT PRIMARY KEY,
                  name TEXT,
                  repo_url TEXT NOT NULL,
                  docs_url TEXT,
                  rationale TEXT,
                  license TEXT,
                  stars INTEGER,
                  open_issues INTEGER,
                  pushed_at TEXT,
                  archived INTEGER NOT NULL DEFAULT 0,
                  last_checked_at TEXT,
                  metadata_json TEXT
                );
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id);"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_repo_snapshots_slug ON repository_snapshots(repo_slug, id DESC);"
            )
            connection.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _as_json(self, payload: dict[str, Any] | None) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=False)

    def create_run(
        self,
        *,
        run_id: str,
        run_type: str,
        repo_slug: str | None,
        task_id: str | None,
        objective: str | None,
        stage: str,
        mode: str,
        provider: str | None,
        model: str | None,
        chain_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                  run_id, run_type, repo_slug, task_id, objective, stage, mode,
                  provider, model, status, chain_path, started_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
                """,
                (
                    run_id,
                    run_type,
                    repo_slug,
                    task_id,
                    objective,
                    stage,
                    mode,
                    provider,
                    model,
                    chain_path,
                    self._now(),
                    self._as_json(metadata),
                ),
            )
            connection.commit()

    def complete_run(
        self,
        *,
        run_id: str,
        status: str,
        run_dir: str | None = None,
        exit_code: int | None = None,
        error_text: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, run_dir = COALESCE(?, run_dir),
                    exit_code = COALESCE(?, exit_code), error_text = COALESCE(?, error_text)
                WHERE run_id = ?
                """,
                (status, self._now(), run_dir, exit_code, error_text, run_id),
            )
            connection.commit()

    def add_event(
        self,
        *,
        run_id: str,
        level: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_events (run_id, ts, level, message, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, self._now(), level, message, self._as_json(payload)),
            )
            connection.commit()

    def record_repository_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_snapshots (
                  scanned_at, repo_slug, repo_path, is_git_repo, branch, dirty,
                  last_commit_at, remote_url, default_branch, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.get("scanned_at", self._now()),
                    snapshot["repo_slug"],
                    snapshot["repo_path"],
                    int(bool(snapshot.get("is_git_repo", False))),
                    snapshot.get("branch"),
                    int(bool(snapshot.get("dirty", False)))
                    if snapshot.get("dirty") is not None
                    else None,
                    snapshot.get("last_commit_at"),
                    snapshot.get("remote_url"),
                    snapshot.get("default_branch"),
                    self._as_json(snapshot.get("details")),
                ),
            )
            connection.commit()

    def upsert_source_project(self, project: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_projects (
                  slug, name, repo_url, docs_url, rationale, license, stars,
                  open_issues, pushed_at, archived, last_checked_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                  name = excluded.name,
                  repo_url = excluded.repo_url,
                  docs_url = excluded.docs_url,
                  rationale = excluded.rationale,
                  license = excluded.license,
                  stars = excluded.stars,
                  open_issues = excluded.open_issues,
                  pushed_at = excluded.pushed_at,
                  archived = excluded.archived,
                  last_checked_at = excluded.last_checked_at,
                  metadata_json = excluded.metadata_json
                """,
                (
                    project["slug"],
                    project.get("name"),
                    project["repo_url"],
                    project.get("docs_url"),
                    project.get("rationale"),
                    project.get("license"),
                    project.get("stars"),
                    project.get("open_issues"),
                    project.get("pushed_at"),
                    int(bool(project.get("archived", False))),
                    project.get("last_checked_at"),
                    self._as_json(project.get("metadata")),
                ),
            )
            connection.commit()

    def list_recent_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, run_type, repo_slug, task_id, objective, mode, provider, model,
                       stage, status, chain_path, run_dir, started_at, finished_at, exit_code, error_text
                FROM runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, run_type, repo_slug, task_id, objective, mode, provider, model,
                       stage, status, chain_path, run_dir, started_at, finished_at, exit_code, error_text,
                       metadata_json
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            data = dict(row)
            if data.get("metadata_json"):
                data["metadata"] = json.loads(data["metadata_json"])
            data.pop("metadata_json", None)
            return data

    def list_run_events(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, ts, level, message, payload_json
                FROM run_events
                WHERE run_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            if item.get("payload_json"):
                item["payload"] = json.loads(item["payload_json"])
            item.pop("payload_json", None)
            events.append(item)
        events.reverse()
        return events

    def latest_repository_snapshots(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.scanned_at, s.repo_slug, s.repo_path, s.is_git_repo, s.branch, s.dirty,
                       s.last_commit_at, s.remote_url, s.default_branch, s.details_json
                FROM repository_snapshots s
                INNER JOIN (
                  SELECT repo_slug, MAX(id) AS max_id
                  FROM repository_snapshots
                  GROUP BY repo_slug
                ) latest
                ON latest.repo_slug = s.repo_slug AND latest.max_id = s.id
                ORDER BY s.repo_slug
                """
            ).fetchall()
        snapshots = []
        for row in rows:
            item = dict(row)
            item["is_git_repo"] = bool(item["is_git_repo"])
            item["dirty"] = (
                bool(item["dirty"]) if item.get("dirty") is not None else None
            )
            if item.get("details_json"):
                item["details"] = json.loads(item["details_json"])
            item.pop("details_json", None)
            snapshots.append(item)
        return snapshots

    def list_source_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT slug, name, repo_url, docs_url, rationale, license, stars, open_issues,
                       pushed_at, archived, last_checked_at, metadata_json
                FROM source_projects
                ORDER BY stars DESC, slug ASC
                """
            ).fetchall()
        projects = []
        for row in rows:
            item = dict(row)
            item["archived"] = bool(item["archived"])
            if item.get("metadata_json"):
                item["metadata"] = json.loads(item["metadata_json"])
            item.pop("metadata_json", None)
            projects.append(item)
        return projects

    def count_fresh_sources(self, freshness_days: int) -> int:
        threshold = datetime.now(timezone.utc) - timedelta(days=freshness_days)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM source_projects
                WHERE last_checked_at >= ?
                """,
                (threshold.isoformat(),),
            ).fetchone()
        return int(row["count"]) if row else 0

    def dashboard_metrics(self) -> dict[str, Any]:
        with self._connect() as connection:
            runs = connection.execute("SELECT COUNT(*) AS count FROM runs").fetchone()[
                "count"
            ]
            success = connection.execute(
                "SELECT COUNT(*) AS count FROM runs WHERE status = 'success'"
            ).fetchone()["count"]
            running = connection.execute(
                "SELECT COUNT(*) AS count FROM runs WHERE status = 'running'"
            ).fetchone()["count"]
            repos = connection.execute(
                "SELECT COUNT(DISTINCT repo_slug) AS count FROM repository_snapshots"
            ).fetchone()["count"]
            sources = connection.execute(
                "SELECT COUNT(*) AS count FROM source_projects"
            ).fetchone()["count"]
        success_rate = round((success / runs) * 100, 2) if runs else 0.0
        return {
            "runs_total": int(runs),
            "runs_success": int(success),
            "runs_running": int(running),
            "success_rate": success_rate,
            "repositories_total": int(repos),
            "sources_total": int(sources),
        }

    def has_successful_stage(self, repo_slug: str, stage: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM runs
                WHERE repo_slug = ? AND stage = ? AND status = 'success'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (repo_slug, stage),
            ).fetchone()
        return row is not None
