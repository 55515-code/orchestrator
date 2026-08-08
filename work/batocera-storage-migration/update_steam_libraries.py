#!/usr/bin/env python3
"""Add Batocera's SD card as a Steam library using structured VDF parsing."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
import time
from collections import OrderedDict
from pathlib import Path


TOKEN_RE = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text):
        if match.group(2):
            tokens.append(match.group(2))
        else:
            tokens.append(bytes(match.group(1), "utf-8").decode("unicode_escape"))
    return tokens


def parse_object(tokens: list[str], index: int = 0) -> tuple[OrderedDict[str, object], int]:
    result: OrderedDict[str, object] = OrderedDict()
    while index < len(tokens):
        if tokens[index] == "}":
            return result, index + 1
        key = tokens[index]
        index += 1
        if index >= len(tokens):
            raise ValueError(f"missing value for {key!r}")
        if tokens[index] == "{":
            value, index = parse_object(tokens, index + 1)
        else:
            value = tokens[index]
            index += 1
        result[key] = value
    return result, index


def load_vdf(path: Path) -> OrderedDict[str, object]:
    tokens = tokenize(path.read_text(encoding="utf-8", errors="strict"))
    result, index = parse_object(tokens)
    if index != len(tokens):
        raise ValueError(f"unparsed tokens in {path}")
    return result


def quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def dump_object(data: OrderedDict[str, object], depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "\t" * depth
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f'{indent}"{quote(str(key))}"')
            lines.append(f"{indent}{{")
            lines.extend(dump_object(value, depth + 1))
            lines.append(f"{indent}}}")
        else:
            lines.append(f'{indent}"{quote(str(key))}"\t\t"{quote(str(value))}"')
    return lines


def write_vdf_atomic(path: Path, data: OrderedDict[str, object]) -> None:
    content = "\n".join(dump_object(data)) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, path.stat().st_mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def read_sd_apps(steamapps: Path) -> OrderedDict[str, object]:
    apps: list[tuple[int, str, str]] = []
    for manifest in steamapps.glob("appmanifest_*.acf"):
        parsed = load_vdf(manifest)
        state = parsed.get("AppState")
        if not isinstance(state, dict):
            continue
        app_id = str(state.get("appid", ""))
        if not app_id.isdigit():
            continue
        size = str(state.get("SizeOnDisk", "0"))
        apps.append((int(app_id), app_id, size))
    apps.sort()
    return OrderedDict((app_id, size) for _, app_id, size in apps)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library-vdf", action="append", required=True)
    parser.add_argument("--sd-root", required=True)
    parser.add_argument("--steam-path", required=True)
    args = parser.parse_args()

    sd_root = Path(args.sd_root)
    steamapps = sd_root / "steamapps"
    metadata = load_vdf(sd_root / "libraryfolder.vdf")
    folder = metadata.get("libraryfolder")
    if not isinstance(folder, dict):
        raise SystemExit("invalid SD libraryfolder.vdf")

    content_id = str(folder.get("contentid", ""))
    label = str(folder.get("label", "SD01T"))
    if not content_id.isdigit() or not steamapps.is_dir():
        raise SystemExit("SD Steam metadata or steamapps directory is invalid")

    apps = read_sd_apps(steamapps)
    total_size = os.statvfs(sd_root).f_frsize * os.statvfs(sd_root).f_blocks
    stamp = time.strftime("%Y%m%d-%H%M%S")

    entry: OrderedDict[str, object] = OrderedDict(
        (
            ("path", args.steam_path),
            ("label", label),
            ("contentid", content_id),
            ("totalsize", str(total_size)),
            ("update_clean_bytes_tally", "0"),
            ("time_last_update_verified", str(int(time.time()))),
            ("apps", apps),
        )
    )

    for raw_path in args.library_vdf:
        path = Path(raw_path)
        parsed = load_vdf(path)
        libraries = parsed.get("libraryfolders")
        if not isinstance(libraries, dict) or "0" not in libraries:
            raise SystemExit(f"invalid Steam library file: {path}")
        backup = path.with_name(f"{path.name}.pre-sd-library-{stamp}")
        shutil.copy2(path, backup)
        libraries["1"] = entry
        write_vdf_atomic(path, parsed)
        print(f"updated {path}; backup {backup}")

    print(f"SD library contains {len(apps)} app manifests")


if __name__ == "__main__":
    main()
