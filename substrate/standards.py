from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .registry import SubstrateRuntime

DEFAULT_STANDARDS_FILE = "standards.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must be a YAML mapping.")
    return payload


def _ensure_mapping(payload: Any, field: str) -> dict[str, str]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be a mapping.")
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        normalized[str(key)] = str(value)
    return normalized


def _ensure_list(payload: Any, field: str) -> list[Any]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError(f"{field} must be a list.")
    return payload


def _normalize_standard(raw: dict[str, Any], *, track_id: str) -> dict[str, Any]:
    standard_id = str(raw.get("id") or "").strip()
    if not standard_id:
        raise ValueError(f"Track '{track_id}' contains a standard without id.")
    name = str(raw.get("name") or standard_id)
    return {
        "id": standard_id,
        "name": name,
        "format": str(raw.get("format") or "unspecified"),
        "source_url": str(raw.get("source_url") or ""),
        "repo_url": str(raw.get("repo_url") or ""),
        "maintained_by": str(raw.get("maintained_by") or "community"),
        "notes": str(raw.get("notes") or ""),
        "stage_notes": _ensure_mapping(
            raw.get("stage_notes"), f"standards[{standard_id}].stage_notes"
        ),
        "pass_notes": _ensure_mapping(
            raw.get("pass_notes"), f"standards[{standard_id}].pass_notes"
        ),
    }


def _build_matrix(
    *,
    stage_sequence: list[str],
    pass_sequence: list[str],
    stage_notes: dict[str, str],
    pass_notes: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stage in stage_sequence:
        passes: list[dict[str, str]] = []
        for pass_name in pass_sequence:
            notes = " ".join(
                part
                for part in [stage_notes.get(stage), pass_notes.get(pass_name)]
                if part
            ).strip()
            passes.append({"pass": pass_name, "guidance": notes})
        rows.append({"stage": stage, "passes": passes})
    return rows


def _catalog_payload(
    root: Path,
    *,
    stage_sequence: list[str],
    pass_sequence: list[str],
    track_id: str | None = None,
) -> dict[str, Any]:
    source = _load_yaml(root / DEFAULT_STANDARDS_FILE)
    defaults = (
        source.get("defaults") if isinstance(source.get("defaults"), dict) else {}
    )
    global_stage_notes = _ensure_mapping(
        defaults.get("stage_notes") if isinstance(defaults, dict) else None,
        "defaults.stage_notes",
    )
    global_pass_notes = _ensure_mapping(
        defaults.get("pass_notes") if isinstance(defaults, dict) else None,
        "defaults.pass_notes",
    )

    principles: list[dict[str, str]] = []
    for raw_principle in _ensure_list(source.get("principles"), "principles"):
        if not isinstance(raw_principle, dict):
            raise ValueError("principles items must be mappings.")
        principles.append(
            {
                "id": str(raw_principle.get("id") or ""),
                "text": str(raw_principle.get("text") or ""),
            }
        )

    tracks_payload: list[dict[str, Any]] = []
    standards_total = 0
    for raw_track in _ensure_list(source.get("tracks"), "tracks"):
        if not isinstance(raw_track, dict):
            raise ValueError("tracks items must be mappings.")
        current_track_id = str(raw_track.get("id") or "").strip()
        if not current_track_id:
            raise ValueError("track id is required.")
        if track_id and current_track_id != track_id:
            continue

        track_stage_notes = {
            **global_stage_notes,
            **_ensure_mapping(
                raw_track.get("stage_notes"), f"tracks[{current_track_id}].stage_notes"
            ),
        }
        track_pass_notes = {
            **global_pass_notes,
            **_ensure_mapping(
                raw_track.get("pass_notes"), f"tracks[{current_track_id}].pass_notes"
            ),
        }

        standards: list[dict[str, Any]] = []
        for raw_standard in _ensure_list(
            raw_track.get("standards"), f"tracks[{current_track_id}].standards"
        ):
            if not isinstance(raw_standard, dict):
                raise ValueError(
                    f"tracks[{current_track_id}].standards items must be mappings."
                )
            standard = _normalize_standard(raw_standard, track_id=current_track_id)
            matrix = _build_matrix(
                stage_sequence=stage_sequence,
                pass_sequence=pass_sequence,
                stage_notes={**track_stage_notes, **standard["stage_notes"]},
                pass_notes={**track_pass_notes, **standard["pass_notes"]},
            )
            standards.append(
                {
                    **standard,
                    "execution_matrix": matrix,
                }
            )

        standards_total += len(standards)
        tracks_payload.append(
            {
                "id": current_track_id,
                "name": str(raw_track.get("name") or current_track_id),
                "description": str(raw_track.get("description") or ""),
                "tags": [
                    str(item)
                    for item in _ensure_list(
                        raw_track.get("tags"), f"tracks[{current_track_id}].tags"
                    )
                ],
                "standards_count": len(standards),
                "standards": standards,
            }
        )

    return {
        "version": int(source.get("version") or 1),
        "principles": principles,
        "summary": {
            "tracks_total": len(tracks_payload),
            "standards_total": standards_total,
        },
        "tracks": tracks_payload,
    }


def standards_payload(
    runtime: SubstrateRuntime, track_id: str | None = None
) -> dict[str, Any]:
    return _catalog_payload(
        runtime.root,
        stage_sequence=list(runtime.workspace.policy.stage_sequence),
        pass_sequence=list(runtime.workspace.policy.pass_sequence),
        track_id=track_id,
    )
