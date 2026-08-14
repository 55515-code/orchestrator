from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    key: str
    kind: str
    summary: str
    value: Any
    tags: frozenset[str]
    created_at: datetime
    expires_at: datetime | None
    hit_count: int


class CacheStore:
    """Lightweight SQLite + filesystem cache for local automation artifacts.

    Stores full values as pickle blobs on disk and metadata (including a
    human-readable summary) in SQLite.  The cache key is a SHA-256 digest of
    the canonical JSON representation of ``(kind, inputs)`` so identical
    requests produce identical keys across restarts.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._db_path = self.root / "cache.db"
        self._blobs_dir = self.root / "blobs"
        self._blobs_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    blob_path TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kind ON cache_entries(kind)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires ON cache_entries(expires_at)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with storage-layer tuned pragmas.

        WAL + synchronous=NORMAL is the documented safe pairing (fsync only on
        WAL checkpoint instead of every commit), which keeps the cache cheap on
        CoW filesystems. busy_timeout absorbs multi-process lock collisions
        between the ops panel, dashboard, and agent cycle.
        """
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.execute("PRAGMA busy_timeout=5000;")
        return connection

    @staticmethod
    def make_key(kind: str, inputs: dict[str, Any]) -> str:
        """Return a deterministic SHA-256 key for ``(kind, inputs)``."""
        canonical = json.dumps({"kind": kind, "inputs": inputs}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _blob_path(self, key: str) -> Path:
        return self._blobs_dir / f"{key}.pickle"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)

    def _tags_to_str(self, tags: frozenset[str] | list[str] | set[str] | None) -> str:
        if not tags:
            return ""
        return ",".join(sorted(str(tag) for tag in tags))

    def _tags_from_str(self, value: str) -> frozenset[str]:
        if not value:
            return frozenset()
        return frozenset(part.strip() for part in value.split(",") if part.strip())

    def has(self, key: str) -> bool:
        """Return True if ``key`` exists and has not expired."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT expires_at FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return False
        expires_at = self._parse_iso(row[0])
        return not (expires_at is not None and datetime.now(UTC) > expires_at)

    def get(self, key: str) -> Any | None:
        """Return the cached value for ``key`` or None if missing/expired."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT blob_path, expires_at FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        blob_path, expires_at = row
        if expires_at is not None and datetime.now(UTC) > self._parse_iso(expires_at):
            return None
        path = Path(blob_path)
        if not path.is_absolute():
            path = self.root / path
        try:
            with path.open("rb") as fh:
                value = pickle.load(fh)
        except (OSError, pickle.PickleError):
            self.delete(key)
            return None
        with self._connect() as conn:
            conn.execute(
                "UPDATE cache_entries SET hit_count = hit_count + 1 WHERE key = ?",
                (key,),
            )
            conn.commit()
        return value

    def get_summary(self, key: str) -> str | None:
        """Return the stored summary for ``key`` without loading the blob."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary, expires_at FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        summary, expires_at = row
        if expires_at is not None and datetime.now(UTC) > self._parse_iso(expires_at):
            return None
        return summary

    def set(
        self,
        key: str,
        value: Any,
        *,
        kind: str = "generic",
        summary: str = "",
        tags: frozenset[str] | list[str] | set[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store ``value`` under ``key`` with optional TTL."""
        blob_path = self._blob_path(key)
        full_blob_path = self.root / blob_path
        full_blob_path.parent.mkdir(parents=True, exist_ok=True)
        with full_blob_path.open("wb") as fh:
            pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
        size_bytes = full_blob_path.stat().st_size
        created_at = self._now_iso()
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.fromtimestamp(
                time.time() + ttl_seconds, tz=UTC
            ).isoformat()
        tags_str = self._tags_to_str(tags)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries
                (key, kind, summary, blob_path, tags, created_at, expires_at, hit_count, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(key) DO UPDATE SET
                    kind = excluded.kind,
                    summary = excluded.summary,
                    blob_path = excluded.blob_path,
                    tags = excluded.tags,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    hit_count = 0,
                    size_bytes = excluded.size_bytes
                """,
                (key, kind, summary or "", str(blob_path), tags_str, created_at, expires_at, size_bytes),
            )
            conn.commit()

    def delete(self, key: str) -> bool:
        """Remove ``key`` and its blob.  Return True if it existed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT blob_path FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            conn.commit()
        if row is None:
            return False
        path = self.root / row[0]
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def invalidate(
        self,
        *,
        kind: str | None = None,
        tags: list[str] | set[str] | frozenset[str] | None = None,
        older_than_days: int | None = None,
    ) -> int:
        """Remove matching entries and return the number deleted."""
        conditions: list[str] = []
        params: list[Any] = []
        if kind is not None:
            conditions.append("kind = ?")
            params.append(kind)
        if tags:
            tag_list = list(tags)
            conditions.append(
                "(" + " OR ".join("tags LIKE ?" for _ in tag_list) + ")"
            )
            params.extend(f"%{tag}%" for tag in tag_list)
        if older_than_days is not None:
            cutoff = datetime.fromtimestamp(
                time.time() - older_than_days * 86400, tz=UTC
            ).isoformat()
            conditions.append("created_at < ?")
            params.append(cutoff)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT key, blob_path FROM cache_entries WHERE {where_clause}", params
            ).fetchall()
            conn.execute(f"DELETE FROM cache_entries WHERE {where_clause}", params)
            conn.commit()
        count = 0
        for key, blob_path in rows:
            try:
                (self.root / blob_path).unlink(missing_ok=True)
                count += 1
            except OSError:
                pass
        return count

    def prune(self, max_age_days: int = 30, max_size_mb: float | None = None) -> dict[str, Any]:
        """Remove expired and old entries; optionally cap total size."""
        now = self._now_iso()
        with self._connect() as conn:
            expired_rows = conn.execute(
                "SELECT key, blob_path FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            ).fetchall()
            conn.execute(
                "DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at < ?", (now,)
            )
            conn.commit()
        removed: list[str] = []
        for key, blob_path in expired_rows:
            try:
                (self.root / blob_path).unlink(missing_ok=True)
                removed.append(key)
            except OSError:
                pass

        removed_old = []
        if max_age_days is not None and max_age_days >= 0:
            cutoff = datetime.fromtimestamp(
                time.time() - max_age_days * 86400, tz=UTC
            ).isoformat()
            with self._connect() as conn:
                old_rows = conn.execute(
                    "SELECT key, blob_path FROM cache_entries WHERE created_at < ? ORDER BY created_at ASC",
                    (cutoff,),
                ).fetchall()
                conn.execute("DELETE FROM cache_entries WHERE created_at < ?", (cutoff,))
                conn.commit()
            for key, blob_path in old_rows:
                try:
                    (self.root / blob_path).unlink(missing_ok=True)
                    removed_old.append(key)
                except OSError:
                    pass

        removed_size: list[str] = []
        if max_size_mb is not None and max_size_mb > 0:
            max_bytes = int(max_size_mb * 1024 * 1024)
            while True:
                with self._connect() as conn:
                    total = conn.execute(
                        "SELECT COALESCE(SUM(size_bytes), 0) FROM cache_entries"
                    ).fetchone()[0]
                    if total <= max_bytes:
                        break
                    row = conn.execute(
                        "SELECT key, blob_path FROM cache_entries ORDER BY hit_count ASC, created_at ASC LIMIT 1"
                    ).fetchone()
                    if row is None:
                        break
                    key, blob_path = row
                    conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                    conn.commit()
                try:
                    (self.root / blob_path).unlink(missing_ok=True)
                    removed_size.append(key)
                except OSError:
                    pass

        return {
            "expired_removed": len(removed),
            "old_removed": len(removed_old),
            "size_removed": len(removed_size),
            "total_removed": len(removed) + len(removed_old) + len(removed_size),
        }

    def stats(self) -> dict[str, Any]:
        """Return aggregate cache statistics."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(size_bytes), 0),
                    COALESCE(SUM(hit_count), 0),
                    MIN(created_at),
                    MAX(created_at)
                FROM cache_entries
                """
            ).fetchone()
        count, total_bytes, hits, oldest, newest = row or (0, 0, 0, None, None)
        kinds: dict[str, int] = {}
        with self._connect() as conn:
            for kind, kcount in conn.execute(
                "SELECT kind, COUNT(*) FROM cache_entries GROUP BY kind"
            ):
                kinds[str(kind)] = int(kcount)
        return {
            "entries": count,
            "size_bytes": total_bytes,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "total_hits": hits,
            "oldest": oldest,
            "newest": newest,
            "kinds": kinds,
        }

    def list_entries(
        self,
        *,
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return a paginated list of metadata records (without blobs)."""
        conditions: list[str] = []
        params: list[Any] = []
        if kind is not None:
            conditions.append("kind = ?")
            params.append(kind)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT key, kind, summary, tags, created_at, expires_at, hit_count, size_bytes
                FROM cache_entries
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [
            {
                "key": key,
                "kind": kind,
                "summary": summary,
                "tags": self._tags_from_str(tags),
                "created_at": created_at,
                "expires_at": expires_at,
                "hit_count": hit_count,
                "size_bytes": size_bytes,
            }
            for key, kind, summary, tags, created_at, expires_at, hit_count, size_bytes in rows
        ]
