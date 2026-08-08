#!/usr/bin/env python3
import configparser
import json
import os
from pathlib import Path
import tomllib
import xml.etree.ElementTree as ET

try:
    from ruamel.yaml import YAML
except ImportError:
    YAML = None

CONFIG_ROOT = Path("/userdata/system/configs")
NAMES = {
    "Ryujinx", "azahar-emu", "azaharplus", "cemu", "dolphin-emu",
    "duckstation", "emulationstation", "mgba", "mupen64", "PCSX2",
    "pcsx2", "ppsspp", "rpcs3", "retroarch", "shadps4", "vita3k",
    "xemu", "yuzu",
}
SKIP_PARTS = {
    ".cache", "cache", "crash_dumps", "dump", "games", "icons", "log",
    "logs", "shader", "shaders", "screenshots", "textures", "dev_flash",
}
MAX_SIZE = 8 * 1024 * 1024


def candidate_roots():
    return [CONFIG_ROOT / name for name in sorted(NAMES) if (CONFIG_ROOT / name).exists()]


def load_file(path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("rb") as stream:
            json.load(stream)
    elif suffix == ".xml":
        ET.parse(path)
    elif suffix == ".toml":
        with path.open("rb") as stream:
            tomllib.load(stream)
    elif suffix in {".yml", ".yaml"} and YAML:
        YAML(typ="safe").load(path)
    elif suffix == ".cfg":
        text = path.read_text(encoding="utf-8", errors="strict")
        if text.lstrip().startswith("<"):
            ET.parse(path)
        else:
            for number, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if line and not line.startswith(("#", ";", "[")) and "=" not in line:
                    raise ValueError(f"line {number} is not a key/value entry")
    elif suffix == ".ini":
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        parser.optionxform = str
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            parser.read_file(stream)


def main():
    checked = []
    failed = []
    stale = []
    broken = []

    for root in candidate_roots():
        for path in root.rglob("*"):
            rel_parts = set(path.relative_to(root).parts[:-1])
            if rel_parts & SKIP_PARTS:
                continue
            if path.is_symlink():
                if not path.exists():
                    broken.append(str(path))
                continue
            if not path.is_file() or path.stat().st_size > MAX_SIZE:
                continue
            if path.suffix.lower() not in {".cfg", ".ini", ".json", ".toml", ".xml", ".yaml", ".yml"}:
                continue
            try:
                load_file(path)
                checked.append(str(path))
            except Exception as exc:
                failed.append((str(path), f"{type(exc).__name__}: {exc}"))

            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(value in text for value in (
                "/var/batocerafs", "/mnt/internal-share-audit", "/roms.1", "/bios.1"
            )):
                stale.append(str(path))

    print(f"CONFIG_ROOTS {len(candidate_roots())}")
    print(f"PARSED_OK {len(checked)}")
    print(f"PARSE_FAILED {len(failed)}")
    for path, error in failed:
        print(f"FAIL {path}: {error}")
    print(f"BROKEN_LINKS {len(broken)}")
    for path in broken:
        print(f"BROKEN {path}")
    print(f"STALE_PATHS {len(stale)}")
    for path in stale:
        print(f"STALE {path}")


if __name__ == "__main__":
    main()
