#!/usr/bin/env python3
"""Pre-operation credential snapshot guard.

Usage (in any wrapper script or alias):
    python3 scripts/snapshot_guard.py --path <credential-path> --reason <text> [--check]

Modes:
    default     : snapshot the path (if it exists), then exec the remaining
                  argv as the guarded command.
    --check     : verify a snapshot exists for the path (non-destructive),
                  exit 0 if protected, 1 if not.

This guarantees that destructive channel operations (logout, force re-auth,
config overwrite) always leave a restore point behind.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.credential_snapshots import list_snapshots, snapshot  # noqa: E402


def _has_recent_snapshot(path: str, root: Path) -> bool:
    snaps = list_snapshots(root=root)
    target = str(Path(path).expanduser().resolve())
    return any(s["source"] == target for s in snaps)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--path", required=True)
    parser.add_argument("--reason", default="pre-operation guard")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=None)
    args, rest = parser.parse_known_args()

    root = Path(args.root) if args.root else Path.cwd()

    if args.check:
        ok = _has_recent_snapshot(args.path, root)
        print(json.dumps({"protected": ok, "path": args.path}))
        return 0 if ok else 1

    src = Path(args.path).expanduser().resolve()
    if src.exists():
        result = snapshot(str(src), reason=args.reason, root=root)
        print(json.dumps({"snapshot": result}, indent=2), file=sys.stderr)
    else:
        print(f"guard: source missing, nothing to snapshot: {src}", file=sys.stderr)

    if rest:
        os.execvp(rest[0], rest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
