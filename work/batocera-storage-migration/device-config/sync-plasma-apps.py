#!/usr/bin/env python3
"""Generate persistent Plasma launchers from installed Steam manifests."""

from __future__ import annotations

import os
import re
import shutil
from collections import OrderedDict
from pathlib import Path


TOKEN_RE = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')
EXCLUDED_NAMES = (
    "proton ",
    "steam linux runtime",
    "steamworks common redistributables",
)
MANIFEST_DIRS = (
    Path("/userdata/system/add-ons/steam/.local/share/Steam/steamapps"),
    Path("/userdata/steam-sd/steamapps"),
)
OUTPUT = Path("/userdata/system/containers/arch-plasma/home/deck/.local/share/applications/steam-games")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text):
        if match.group(2):
            tokens.append(match.group(2))
        else:
            tokens.append(re.sub(r'\\(["\\])', r'\1', match.group(1)))
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


def desktop_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace("\r", " ")


def icon_for(appid: str) -> str:
    images = Path("/userdata/roms/steam/images")
    matches = sorted(images.glob(f"{appid}_*"))
    if matches:
        return f"/mnt/roms/steam/images/{matches[0].name}"
    return "steam"


def main() -> None:
    apps: dict[int, tuple[str, str]] = {}
    for directory in MANIFEST_DIRS:
        if not directory.is_dir():
            continue
        for manifest in directory.glob("appmanifest_*.acf"):
            try:
                state = load_vdf(manifest).get("AppState")
            except (OSError, UnicodeError, ValueError) as error:
                print(f"Skipping {manifest}: {error}")
                continue
            if not isinstance(state, dict):
                continue
            appid = str(state.get("appid", ""))
            name = str(state.get("name", "")).strip()
            if not appid.isdigit() or not name:
                continue
            if name.casefold().startswith(EXCLUDED_NAMES):
                continue
            apps[int(appid)] = (appid, name)

    staging = OUTPUT.with_name(f".{OUTPUT.name}.new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for _, (appid, name) in sorted(apps.items(), key=lambda item: item[1][1].casefold()):
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={desktop_escape(name)}\n"
            f"Exec=/usr/local/bin/batocera-desktop-command steam-app:{appid}\n"
            f"Icon={icon_for(appid)}\n"
            "Terminal=false\n"
            "Categories=Game;\n"
            "Keywords=Steam;Game;\n"
        )
        launcher = staging / f"steam-{appid}.desktop"
        launcher.write_text(content, encoding="utf-8")
        os.chown(launcher, 1000, 1000)
    os.chown(staging, 1000, 1000)
    shutil.rmtree(OUTPUT, ignore_errors=True)
    staging.rename(OUTPUT)
    print(f"Generated {len(apps)} Plasma Steam launchers")


if __name__ == "__main__":
    main()
