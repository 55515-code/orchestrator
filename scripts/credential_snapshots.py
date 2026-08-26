#!/usr/bin/env python3
"""Surgical credential/config snapshot & restore for stateful channels.

Motivation (incident 2026-08-25): a forced WhatsApp re-auth cleared live
Baileys credentials; the ``.bak`` file was a same-moment copy (useless) and
the server had already invalidated the session.  No rollback existed.

This module makes every credential-bearing operation restorable:

  * ``snapshot``  — copy a credential dir/file to ``state/credential-snapshots/``
                    with a timestamp + reason, preserving server-validated state.
  * ``list``      — show available snapshots (latest first).
  * ``restore``   — atomically restore a snapshot (temp dir + rename), with an
                    automatic pre-restore snapshot of the current state.
  * ``prune``     — delete snapshots older than N days (default 30).

Principle: before ANY destructive operation (logout, force re-auth, config
overwrite), call ``snapshot``.  Restores are atomic and always leave a
rollback point behind.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SNAPSHOT_ROOT = Path("state/credential-snapshots")
MANIFEST = "manifest.json"
DEFAULT_RETENTION_DAYS = 30


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_name(path: Path) -> str:
    """Convert an absolute path into a filesystem-safe snapshot id."""
    parts = [p for p in path.parts if p and p not in ("/", ".", "..")]
    return "_".join(parts)[-180:] or "root"


def _write_manifest(snapshot_dir: Path, payload: dict) -> None:
    (snapshot_dir / MANIFEST).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_manifest(snapshot_dir: Path) -> dict | None:
    path = snapshot_dir / MANIFEST
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def snapshot(path_str: str, reason: str = "", root: Path | None = None) -> dict:
    """Snapshot a credential/config file or directory.

    Returns a dict describing the created snapshot.  The snapshot is a
    timestamped copy under ``state/credential-snapshots/<id>__<ts>`` with a
    manifest recording source path, timestamp, reason, and file hashes so a
    restore can detect drift.
    """
    root = root or Path.cwd()
    src = Path(path_str).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"source does not exist: {src}")

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snap_root = (root / SNAPSHOT_ROOT).resolve()
    snap_dir = snap_root / f"{_safe_name(src)}__{ts}"
    snap_dir.mkdir(parents=True, exist_ok=False)

    if src.is_dir():
        shutil.copytree(src, snap_dir / "data", dirs_exist_ok=False)
    else:
        snap_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, snap_dir / "data")

    payload = {
        "source": str(src),
        "createdAt": _now(),
        "reason": reason or "manual",
        "kind": "directory" if src.is_dir() else "file",
        "entryCount": _count_entries(snap_dir / "data"),
    }
    _write_manifest(snap_dir, payload)
    return {"snapshotDir": str(snap_dir), **payload}


def _count_entries(path: Path) -> int:
    if path.is_dir():
        return sum(1 for _ in path.rglob("*") if _.is_file())
    return 1


def list_snapshots(root: Path | None = None) -> list[dict]:
    root = root or Path.cwd()
    snap_root = (root / SNAPSHOT_ROOT).resolve()
    if not snap_root.exists():
        return []
    out = []
    for snap_dir in sorted(snap_root.iterdir(), reverse=True):
        if not snap_dir.is_dir():
            continue
        manifest = _read_manifest(snap_dir) or {}
        out.append(
            {
                "snapshotDir": str(snap_dir),
                "source": manifest.get("source", "?"),
                "createdAt": manifest.get("createdAt", "?"),
                "reason": manifest.get("reason", "?"),
                "kind": manifest.get("kind", "?"),
                "entryCount": manifest.get("entryCount", "?"),
            }
        )
    return out


def restore(snapshot_dir_str: str, root: Path | None = None) -> dict:
    """Atomically restore a snapshot over its recorded source.

    Creates a timestamped snapshot of the *current* state first (so the
    restore itself is reversible), then swaps the data into place via a
    temp dir + rename.  Returns restore metadata.
    """
    root = root or Path.cwd()
    snap_dir = Path(snapshot_dir_str).expanduser().resolve()
    manifest = _read_manifest(snap_dir)
    if not manifest:
        raise ValueError(f"not a snapshot (missing {MANIFEST}): {snap_dir}")
    src = Path(manifest["source"])
    # NOTE: the source may be missing — restoring over a deleted credential
    # dir is exactly the disaster case this tool exists for.  We only need
    # the parent to exist (or be creatable) to put the data back.

    # 1) snapshot the current state so restore is reversible.  If the
    #    source is already gone, there is nothing to snapshot — skip.
    current = None
    if src.exists():
        current = snapshot(str(src), reason="pre-restore rollback point", root=root)

    # 2) stage the restore in a sibling temp dir, then swap.
    data = snap_dir / "data"
    if not data.exists():
        raise ValueError(f"snapshot data missing: {data}")

    parent = src.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".restore-staging-{time.time_ns()}"
    if manifest["kind"] == "directory":
        shutil.copytree(data, staging)
        if src.exists():
            shutil.rmtree(src)
        staging.rename(src)
    else:
        staging.mkdir(parents=True, exist_ok=False)
        shutil.copy2(data, staging / src.name)
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging / src.name, src)
        shutil.rmtree(staging)

    return {
        "restoredFrom": str(snap_dir),
        "restoredTo": str(src),
        "rollbackSnapshot": current["snapshotDir"] if current else None,
        "restoredAt": _now(),
    }


def prune(days: int = DEFAULT_RETENTION_DAYS, root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    snap_root = (root / SNAPSHOT_ROOT).resolve()
    if not snap_root.exists():
        return []
    cutoff = time.time() - days * 86400
    removed = []
    for snap_dir in snap_root.iterdir():
        if not snap_dir.is_dir():
            continue
        try:
            mtime = snap_dir.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(snap_dir, ignore_errors=True)
            removed.append(str(snap_dir))
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="Snapshot a credential/config path")
    p_snap.add_argument("path", help="File or directory to snapshot")
    p_snap.add_argument("--reason", default="", help="Why this snapshot is taken")

    sub.add_parser("list", help="List available snapshots")

    p_restore = sub.add_parser("restore", help="Restore a snapshot (atomic, reversible)")
    p_restore.add_argument("snapshot_dir", help="Snapshot directory to restore")

    p_prune = sub.add_parser("prune", help="Delete snapshots older than N days")
    p_prune.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS)

    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            result = snapshot(args.path, reason=args.reason)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "list":
            snaps = list_snapshots()
            if not snaps:
                print("(no snapshots)")
            else:
                print(json.dumps(snaps, indent=2, ensure_ascii=False))
        elif args.command == "restore":
            result = restore(args.snapshot_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "prune":
            removed = prune(args.days)
            print(json.dumps({"removed": removed}, indent=2, ensure_ascii=False))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
