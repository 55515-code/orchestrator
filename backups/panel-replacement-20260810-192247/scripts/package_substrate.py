#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_INCLUDE = [
    ".env.example",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "justfile",
    "mise.toml",
    "mkdocs.yml",
    "workspace.yaml",
    "upstreams.yaml",
    "standards.yaml",
    "tool_profiles.yaml",
    "integrations.yaml",
    "config_sync_profiles.yaml",
    "chains",
    "prompts",
    "scripts",
    "docs",
    "substrate",
    "deploy",
]

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    ".direnv",
    "__pycache__",
    "aosp-eos-asteroids",
    "work",
    "tmp",
    "downloads",
    "tools",
    "site",
    "memory",
    "state",
    "generated",
}

EXCLUDE_FILES = {
    "docs/system-probe.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a portable substrate release zip with manifest and checksums."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Workspace root to package.",
    )
    parser.add_argument(
        "--output-dir",
        default="generated/releases",
        help="Directory where release artifacts will be written.",
    )
    parser.add_argument(
        "--name-prefix",
        default="local-agent-substrate",
        help="Zip filename prefix.",
    )
    return parser.parse_args()


def iter_files(root: Path) -> list[Path]:
    selected: list[Path] = []
    for rel in DEFAULT_INCLUDE:
        source = root / rel
        if not source.exists():
            continue
        if source.is_file():
            selected.append(source)
            continue
        for path in source.rglob("*"):
            if path.is_dir():
                continue
            if path.relative_to(root).as_posix() in EXCLUDE_FILES:
                continue
            if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
                continue
            selected.append(path)
    unique = sorted(set(selected))
    return unique


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"{args.name_prefix}-{timestamp}.zip"
    zip_path = output_dir / zip_name

    files = iter_files(root)
    if not files:
        raise SystemExit("No files selected for packaging.")

    checksums: list[dict[str, str | int]] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            rel = path.relative_to(root)
            archive.write(path, rel.as_posix())
            checksums.append(
                {
                    "path": rel.as_posix(),
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                }
            )

    manifest = {
        "name": args.name_prefix,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "artifact": zip_name,
        "file_count": len(files),
        "files": checksums,
    }
    manifest_path = output_dir / f"{args.name_prefix}-{timestamp}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    zip_checksum = sha256(zip_path)
    sums_path = output_dir / "SHA256SUMS"
    with sums_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{zip_checksum}  {zip_name}\n")

    print(str(zip_path))
    print(str(manifest_path))
    print(f"sha256 {zip_name}: {zip_checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
