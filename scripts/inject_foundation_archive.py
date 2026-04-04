#!/usr/bin/env python3
"""Inject an external app archive into this repository with a reviewable plan.

This utility is intentionally conservative:
- Defaults to dry-run mode.
- Excludes known local-state/secret paths.
- Produces a merge plan before writes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from urllib.error import URLError
import zipfile
from pathlib import Path

EXCLUDED_NAMES = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "memory",
    "artifacts",
}


def _download_if_url(source: str, workspace: Path) -> Path:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        candidate = Path(source).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"archive not found: {candidate}")
        return candidate

    target = workspace / "incoming-foundation.archive"
    with urllib.request.urlopen(source, timeout=30) as response, target.open("wb") as fh:
        shutil.copyfileobj(response, fh)
    return target


def _extract_archive(archive: Path, destination: Path) -> Path:
    suffixes = {s.lower() for s in archive.suffixes}
    if ".zip" in suffixes:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(destination)
        return destination

    if any(s in suffixes for s in {".tar", ".gz", ".bz2", ".xz", ".tgz"}):
        with tarfile.open(archive) as tf:
            tf.extractall(destination)
        return destination

    raise ValueError(f"unsupported archive type: {archive.name}")


def _guess_foundation_root(extracted: Path) -> Path:
    children = [p for p in extracted.iterdir() if p.is_dir()]
    if len(children) == 1:
        return children[0]

    for child in children:
        if (child / "pyproject.toml").exists() or (child / "package.json").exists():
            return child

    return extracted


def _relative_candidates(root: Path) -> set[Path]:
    entries: set[Path] = set()
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_NAMES for part in rel.parts):
            continue
        entries.add(rel)
    return entries


def build_merge_plan(source_root: Path, target_root: Path) -> dict[str, object]:
    source_entries = _relative_candidates(source_root)
    target_entries = _relative_candidates(target_root)

    add = sorted(p.as_posix() for p in source_entries - target_entries)
    replace = sorted(
        p.as_posix() for p in source_entries & target_entries if (source_root / p).is_file()
    )
    remove_candidates = sorted(p.as_posix() for p in target_entries - source_entries)

    return {
        "source_root": str(source_root),
        "target_root": str(target_root),
        "add": add,
        "replace": replace,
        "remove_candidates": remove_candidates,
        "summary": {
            "add": len(add),
            "replace": len(replace),
            "remove_candidates": len(remove_candidates),
        },
    }


def apply_merge(source_root: Path, target_root: Path) -> None:
    for path in sorted(source_root.rglob("*")):
        rel = path.relative_to(source_root)
        if any(part in EXCLUDED_NAMES for part in rel.parts):
            continue
        destination = target_root / rel
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and optionally apply a foundation archive merge into this repo."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path or URL to a zip/tar archive containing the more mature foundation app.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Repository root where files should be merged (default: current directory).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the merge. Without this flag, the command only prints a plan.",
    )
    parser.add_argument(
        "--plan-out",
        default="artifacts/foundation-merge-plan.json",
        help="Where to write the generated merge plan JSON.",
    )
    parser.add_argument(
        "--source-subdir",
        default="",
        help="Optional subdirectory inside extracted archive to treat as app root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    plan_out = Path(args.plan_out).expanduser()
    if not plan_out.is_absolute():
        plan_out = workspace / plan_out

    try:
        with tempfile.TemporaryDirectory(prefix="foundation-import-") as tmp:
            temp_root = Path(tmp)
            archive = _download_if_url(args.source, temp_root)
            extracted_root = _extract_archive(archive, temp_root / "extracted")
            foundation_root = _guess_foundation_root(extracted_root)
            if args.source_subdir:
                foundation_root = (foundation_root / args.source_subdir).resolve()
                if not foundation_root.exists():
                    raise FileNotFoundError(
                        f"source subdir not found in archive: {args.source_subdir}"
                    )

            plan = build_merge_plan(foundation_root, workspace)
            plan["applied"] = bool(args.apply)
            plan["pid"] = os.getpid()
            plan_out.parent.mkdir(parents=True, exist_ok=True)
            plan_out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")

            if args.apply:
                apply_merge(foundation_root, workspace)
    except (URLError, FileNotFoundError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "source": args.source}))
        return 2

    print(json.dumps({"ok": True, "plan": str(plan_out), "applied": args.apply}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
