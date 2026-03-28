from __future__ import annotations

import hashlib
import importlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .registry import SubstrateRuntime

GITHUB_REPO_PATTERN = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)(?:[/?#].*)?$"
)

_OPENCLAW_DATA_CLASS_DEFAULT = "synthetic"
_OPENCLAW_MAX_RAW_CHARS = 12_000
_OPENCLAW_MAX_INSIGHTS = 8
_OPENCLAW_EVIDENCE_HINTS = ("http://", "https://", "source:")
_OPENCLAW_SECURITY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "secret_material_detected"),
    (r"\b(api[_-]?key|password|secret|token)\s*[:=]\s*\S+", "secret_leak_pattern"),
    (r"\bcurl\b[^\n|]*\|\s*(bash|sh)\b", "pipe_to_shell_pattern"),
    (r"\brm\s+-rf\b", "destructive_command_pattern"),
)
_OPENCLAW_POLICY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bdeploy(?:ment)?\s+to\s+production\b", "production_path_reference"),
    (r"\b(override|bypass)\s+(policy|guardrail|gate)\b", "policy_bypass_pattern"),
)
_OPENCLAW_DIRECT_INGESTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"```", "code_fence_detected"),
    (r"\bdiff\s+--git\b", "git_patch_detected"),
    (r"\bapply_patch\b", "patch_instruction_detected"),
    (r"\b(copy|paste|copied|verbatim)\b", "copy_paste_language_detected"),
)


class OpenClawUnavailableError(RuntimeError):
    """Raised when OpenClaw integration hooks are not available."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_data_class(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    return value or _OPENCLAW_DATA_CLASS_DEFAULT


def _openclaw_run_dir(runtime: SubstrateRuntime, run_id: str) -> Path:
    run_dir = runtime.paths["research"] / "openclaw" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _best_effort_openclaw_invoke(
    fn: Callable[..., Any], *, objective: str, context: str
) -> Any:
    try:
        return fn(objective=objective, context=context)
    except TypeError:
        try:
            return fn(objective, context)
        except TypeError:
            return fn({"objective": objective, "context": context})


def _resolve_openclaw_invoker() -> tuple[Callable[..., Any] | None, str]:
    try:
        module = importlib.import_module("openclaw")
    except Exception as exc:  # noqa: BLE001
        return None, f"module_unavailable:{type(exc).__name__}"

    for candidate in ("run_research_assist", "research_assist", "run"):
        fn = getattr(module, candidate, None)
        if callable(fn):
            return fn, f"python_module:{candidate}"

    client_cls = getattr(module, "OpenClawClient", None)
    if callable(client_cls):
        try:
            client = client_cls()
        except Exception as exc:  # noqa: BLE001
            return None, f"client_init_failed:{type(exc).__name__}"
        for candidate in ("run_research_assist", "research_assist", "run"):
            fn = getattr(client, candidate, None)
            if callable(fn):
                return fn, f"python_client:{candidate}"

    return None, "adapter_unavailable"


def _invoke_openclaw_untrusted_output(
    *, objective: str, context: str
) -> tuple[str, dict[str, Any]]:
    invoker, adapter_id = _resolve_openclaw_invoker()
    if invoker is None:
        raise OpenClawUnavailableError(adapter_id)
    payload = _best_effort_openclaw_invoke(invoker, objective=objective, context=context)
    if isinstance(payload, str):
        raw_text = payload
    else:
        raw_text = json.dumps(payload, indent=2, ensure_ascii=False)
    return raw_text, {
        "adapter": adapter_id,
        "collected_at": _utc_now_iso(),
    }


def _find_pattern_hits(
    text: str, patterns: tuple[tuple[str, str], ...]
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for pattern, reason in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append({"reason": reason, "pattern": pattern})
    return hits


def _extract_internalized_insights(text: str) -> list[str]:
    insights: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("```", "`")):
            continue
        line = re.sub(r"^[\-*\d.\s]+", "", line).strip()
        if not line:
            continue
        lowered = line.lower()
        if "http://" in lowered or "https://" in lowered:
            continue
        if any(
            marker in lowered
            for marker in (
                "diff --git",
                "apply_patch",
                "copy/paste",
                "copy paste",
                "verbatim",
            )
        ):
            continue
        if len(line) < 24:
            continue
        cleaned = line[:240]
        if cleaned in insights:
            continue
        insights.append(cleaned)
        if len(insights) >= _OPENCLAW_MAX_INSIGHTS:
            break
    return insights


def _revet_openclaw_output(
    runtime: SubstrateRuntime,
    *,
    stage: str,
    pass_name: str,
    data_class: str,
    raw_text: str,
    provenance_hash: str,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    normalized = raw_text.strip()

    def _gate(gate_id: str, passed: bool, reason: str, *, details: Any = None) -> bool:
        gates.append(
            {
                "gate": gate_id,
                "passed": passed,
                "reason": reason,
                "details": details,
            }
        )
        return passed

    allowed, reason = runtime.evaluate_openclaw_policy(
        stage=stage,
        pass_name=pass_name,
        manual_trigger=True,
        data_class=data_class,
    )
    if not _gate("V0_intake_policy", allowed, "ok" if allowed else reason):
        return {
            "passed": False,
            "reason": reason,
            "gates": gates,
            "insights": [],
            "provenance_hash": provenance_hash,
        }

    schema_ok = bool(normalized) and len(normalized) <= _OPENCLAW_MAX_RAW_CHARS
    schema_reason = "ok" if schema_ok else "invalid_payload_shape"
    if not _gate(
        "V1_schema_and_provenance",
        schema_ok,
        schema_reason,
        details={
            "length": len(normalized),
            "max_length": _OPENCLAW_MAX_RAW_CHARS,
            "provenance_hash": provenance_hash,
        },
    ):
        return {
            "passed": False,
            "reason": schema_reason,
            "gates": gates,
            "insights": [],
            "provenance_hash": provenance_hash,
        }

    security_hits = _find_pattern_hits(normalized, _OPENCLAW_SECURITY_PATTERNS)
    security_ok = not security_hits
    security_reason = "ok" if security_ok else "security_screen_failed"
    if not _gate(
        "V2_security_screen",
        security_ok,
        security_reason,
        details={"hits": security_hits},
    ):
        return {
            "passed": False,
            "reason": security_reason,
            "gates": gates,
            "insights": [],
            "provenance_hash": provenance_hash,
        }

    lowered = normalized.lower()
    corroborated = any(hint in lowered for hint in _OPENCLAW_EVIDENCE_HINTS)
    corroboration_reason = "ok" if corroborated else "insufficient_corroboration"
    if not _gate(
        "V3_correctness_corroboration",
        corroborated,
        corroboration_reason,
    ):
        return {
            "passed": False,
            "reason": corroboration_reason,
            "gates": gates,
            "insights": [],
            "provenance_hash": provenance_hash,
        }

    direct_ingestion_hits = _find_pattern_hits(normalized, _OPENCLAW_DIRECT_INGESTION_PATTERNS)
    policy_hits = _find_pattern_hits(normalized, _OPENCLAW_POLICY_PATTERNS)
    policy_ok = not direct_ingestion_hits and not policy_hits
    if direct_ingestion_hits:
        policy_reason = "external_code_ingestion_detected"
    elif policy_hits:
        policy_reason = "policy_compliance_failed"
    else:
        policy_reason = "ok"
    if not _gate(
        "V4_policy_compliance",
        policy_ok,
        policy_reason,
        details={"direct_ingestion_hits": direct_ingestion_hits, "policy_hits": policy_hits},
    ):
        return {
            "passed": False,
            "reason": policy_reason,
            "gates": gates,
            "insights": [],
            "provenance_hash": provenance_hash,
        }

    insights = _extract_internalized_insights(normalized)
    transform_ok = bool(insights)
    transform_reason = "ok" if transform_ok else "insight_extraction_failed"
    if not _gate(
        "V5_deterministic_transform",
        transform_ok,
        transform_reason,
        details={"insight_count": len(insights)},
    ):
        return {
            "passed": False,
            "reason": transform_reason,
            "gates": gates,
            "insights": [],
            "provenance_hash": provenance_hash,
        }

    return {
        "passed": True,
        "reason": "ok",
        "gates": gates,
        "insights": insights,
        "provenance_hash": provenance_hash,
    }


def run_openclaw_research_assist(
    runtime: SubstrateRuntime,
    *,
    run_id: str,
    stage: str,
    pass_name: str,
    objective: str,
    context: str,
    manual_trigger: bool,
    data_class: str,
) -> dict[str, Any]:
    normalized_pass = pass_name.strip().lower()
    normalized_data_class = _normalize_data_class(data_class)
    allowed, reason = runtime.evaluate_openclaw_policy(
        stage=stage,
        pass_name=normalized_pass,
        manual_trigger=manual_trigger,
        data_class=normalized_data_class,
    )
    if not allowed:
        return {
            "status": "blocked",
            "reason": reason,
            "pass_name": normalized_pass,
            "data_class": normalized_data_class,
            "imported_insights": [],
        }

    try:
        raw_output, invocation_meta = _invoke_openclaw_untrusted_output(
            objective=objective,
            context=context,
        )
    except OpenClawUnavailableError as exc:
        return {
            "status": "degraded_unavailable",
            "reason": str(exc),
            "pass_name": normalized_pass,
            "data_class": normalized_data_class,
            "imported_insights": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "degraded_unavailable",
            "reason": f"invocation_failed:{type(exc).__name__}",
            "pass_name": normalized_pass,
            "data_class": normalized_data_class,
            "imported_insights": [],
        }

    run_dir = _openclaw_run_dir(runtime, run_id)
    raw_path = run_dir / f"{normalized_pass}_openclaw_raw_quarantine.json"
    provenance_hash = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
    raw_payload = {
        "artifact_class": "openclaw_raw_quarantine",
        "recorded_at": _utc_now_iso(),
        "run_id": run_id,
        "stage": stage,
        "pass_name": normalized_pass,
        "data_class": normalized_data_class,
        "manual_trigger": manual_trigger,
        "provenance_hash": provenance_hash,
        "invocation": invocation_meta,
        "raw_output": raw_output,
    }
    _write_json(raw_path, raw_payload)

    vetting = _revet_openclaw_output(
        runtime,
        stage=stage,
        pass_name=normalized_pass,
        data_class=normalized_data_class,
        raw_text=raw_output,
        provenance_hash=provenance_hash,
    )
    vetting_report_path = run_dir / f"{normalized_pass}_openclaw_vetting_report.json"
    _write_json(
        vetting_report_path,
        {
            "artifact_class": "openclaw_vetting_report",
            "recorded_at": _utc_now_iso(),
            "run_id": run_id,
            "stage": stage,
            "pass_name": normalized_pass,
            "data_class": normalized_data_class,
            "decision": "pass" if vetting["passed"] else "fail",
            "reason": vetting["reason"],
            "gates": vetting["gates"],
            "provenance_hash": vetting["provenance_hash"],
        },
    )

    if not vetting["passed"]:
        rejected_path = run_dir / f"{normalized_pass}_openclaw_rejected_artifact.json"
        _write_json(
            rejected_path,
            {
                "artifact_class": "openclaw_rejected_artifact",
                "recorded_at": _utc_now_iso(),
                "run_id": run_id,
                "stage": stage,
                "pass_name": normalized_pass,
                "data_class": normalized_data_class,
                "reason": vetting["reason"],
                "provenance_hash": vetting["provenance_hash"],
                "raw_artifact": str(raw_path),
                "vetting_report_artifact": str(vetting_report_path),
            },
        )
        return {
            "status": "rejected",
            "reason": vetting["reason"],
            "pass_name": normalized_pass,
            "data_class": normalized_data_class,
            "raw_artifact": str(raw_path),
            "vetting_report_artifact": str(vetting_report_path),
            "rejected_artifact": str(rejected_path),
            "imported_insights": [],
        }

    insights = [str(item) for item in vetting["insights"]]
    vetted_path = run_dir / f"{normalized_pass}_vetted_research_artifact.json"
    _write_json(
        vetted_path,
        {
            "artifact_class": "vetted_research_artifact",
            "recorded_at": _utc_now_iso(),
            "run_id": run_id,
            "stage": stage,
            "pass_name": normalized_pass,
            "data_class": normalized_data_class,
            "provenance_hash": vetting["provenance_hash"],
            "adoption_policy": {
                "mode": "learn_and_adapt_never_trust_or_copy",
                "copy_paste_allowed": False,
                "direct_execution_allowed": False,
                "external_code_ingestion_allowed": False,
            },
            "insights": insights,
            "raw_artifact": str(raw_path),
            "vetting_report_artifact": str(vetting_report_path),
        },
    )
    insight_markdown = "\n".join(f"- {line}" for line in insights)
    return {
        "status": "accepted",
        "reason": "ok",
        "pass_name": normalized_pass,
        "data_class": normalized_data_class,
        "raw_artifact": str(raw_path),
        "vetting_report_artifact": str(vetting_report_path),
        "vetted_artifact": str(vetted_path),
        "imported_insights": insights,
        "insight_markdown": insight_markdown,
    }


def _load_upstreams(upstreams_file: Path) -> list[dict[str, Any]]:
    if not upstreams_file.exists():
        return []
    payload = yaml.safe_load(upstreams_file.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("upstreams.yaml must be a mapping.")
    projects = payload.get("projects", [])
    if not isinstance(projects, list):
        raise ValueError("upstreams.yaml projects must be a list.")
    normalized: list[dict[str, Any]] = []
    for index, project in enumerate(projects, start=1):
        if not isinstance(project, dict):
            raise ValueError(f"projects[{index}] must be a mapping.")
        if "slug" not in project or "repo_url" not in project:
            raise ValueError(f"projects[{index}] requires slug and repo_url.")
        normalized.append(project)
    return normalized


def _fetch_github_metadata(owner: str, repo: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "local-agent-substrate/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
    payload = json.loads(body)
    return {
        "name": payload.get("name") or repo,
        "license": (payload.get("license") or {}).get("spdx_id"),
        "stars": payload.get("stargazers_count"),
        "open_issues": payload.get("open_issues_count"),
        "pushed_at": payload.get("pushed_at"),
        "archived": bool(payload.get("archived", False)),
        "default_branch": payload.get("default_branch"),
        "html_url": payload.get("html_url"),
        "description": payload.get("description"),
    }


def refresh_upstreams(runtime: SubstrateRuntime) -> list[dict[str, Any]]:
    upstreams_file = runtime.paths["upstreams"]
    projects = _load_upstreams(upstreams_file)
    refreshed: list[dict[str, Any]] = []
    checked_at = datetime.now(timezone.utc).isoformat()

    for project in projects:
        repo_url = str(project["repo_url"])
        match = GITHUB_REPO_PATTERN.match(repo_url)
        metadata: dict[str, Any] = {}
        error_message: str | None = None
        if match:
            owner = match.group("owner")
            repo_name = match.group("repo").removesuffix(".git")
            try:
                metadata = _fetch_github_metadata(owner, repo_name)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                error_message = str(exc)
        else:
            error_message = "Only GitHub metadata enrichment is implemented."

        record = {
            "slug": str(project["slug"]),
            "name": str(project.get("name") or metadata.get("name") or project["slug"]),
            "repo_url": repo_url,
            "docs_url": project.get("docs_url"),
            "rationale": project.get("rationale"),
            "license": metadata.get("license") or project.get("license"),
            "stars": metadata.get("stars"),
            "open_issues": metadata.get("open_issues"),
            "pushed_at": metadata.get("pushed_at"),
            "archived": metadata.get("archived", False),
            "last_checked_at": checked_at,
            "metadata": {
                **metadata,
                "error": error_message,
                "source": "github_api" if match else "custom",
            },
        }
        runtime.db.upsert_source_project(record)
        refreshed.append(record)

    out_path = runtime.paths["research"] / "upstream-metadata.json"
    out_path.write_text(
        json.dumps(refreshed, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return refreshed


def source_facts_ready(runtime: SubstrateRuntime) -> bool:
    freshness_days = runtime.workspace.policy.source_freshness_days
    return runtime.db.count_fresh_sources(freshness_days) > 0
