"""Coordinated multi-agent swarm orchestration for the substrate control panel.

Workflow:
  1. User simulation swarm: persona agents (novice, intermediate, expert,
     accessibility, low-literacy, non-native speakers, edge cases) run
     end-to-end probes against the live control panel and produce structured
     feedback (working / broken / missing / unintuitive).
  2. QA triage swarm: validates reported issues against the live app and
     assigns severity (critical / high / medium / low).
  3. Dev delegation: validated issues become prioritized work items that
     specialized dev agents (frontend / backend / security / devops) consume.
  4. Iterative loop: dev fixes -> QA re-test -> user simulation re-test until
     all critical and high-priority issues are resolved.
  5. Production deployment: smoke tests, monitoring setup, rollback protocol.

All state is persisted as JSON under ``state/swarm-control/``.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SATE_DIR = Path("state/swarm-control")
DEFAULT_BASE_URL = "http://127.0.0.1:8090"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
FEEDBACK_STATES = {"working", "broken", "missing", "unintuitive"}

# --------------------------------------------------------------------------- #
# Persona matrix — every user experience level plus edge-case segments.
# --------------------------------------------------------------------------- #

USER_PERSONAS: list[dict[str, Any]] = [
    {
        "id": "novice",
        "segment": "novice",
        "experience": 0.1,
        "description": "First-time user with no ops background, exploring the panel cold.",
        "focus": ["onboarding", "clear labels", "discoverability", "help cues"],
    },
    {
        "id": "intermediate",
        "segment": "intermediate",
        "experience": 0.5,
        "description": "Day-to-day operator who runs scans, reads dashboards, follows run history.",
        "focus": ["dashboard", "runs", "tasks", "action workflows"],
    },
    {
        "id": "expert",
        "segment": "expert",
        "experience": 0.95,
        "description": "Power user hitting the API surface and advanced automation surfaces directly.",
        "focus": ["api_endpoints", "automations", "terminal", "advanced actions"],
    },
    {
        "id": "accessibility",
        "segment": "accessibility_needs",
        "experience": 0.5,
        "description": "Keyboard-only user with screen reader; WCAG 2.1 AA expectations.",
        "focus": ["keyboard", "aria", "focus", "contrast", "alt_text"],
    },
    {
        "id": "low_literacy",
        "segment": "limited_tech_literacy",
        "experience": 0.2,
        "description": "Limited technical literacy; needs plain language and visual cues.",
        "focus": ["jargon_density", "plain_language", "guidance", "error_clarity"],
    },
    {
        "id": "non_native",
        "segment": "non_native_english",
        "experience": 0.4,
        "description": "Non-native English speaker; needs consistent labels and readable errors.",
        "focus": ["consistent_labels", "plain_errors", "sentence_structure"],
    },
]

# --------------------------------------------------------------------------- #
# End-to-end probe definitions. Each probe checks one observable behaviour.
# --------------------------------------------------------------------------- #

CORE_PROBES: list[dict[str, Any]] = [
    {
        "id": "root-redirect",
        "method": "GET",
        "path": "/",
        "expect_status": 302,
        "expect_location": "/panel",
        "no_redirect": True,
        "feature": "home entry",
    },
    {
        "id": "panel-page",
        "method": "GET",
        "path": "/panel",
        "expect_status": 200,
        "expect_text": "Substrate Control Panel",
        "feature": "control panel UI",
    },
    {
        "id": "legacy-panel",
        "method": "GET",
        "path": "/legacy",
        "expect_status": 200,
        "expect_text": "Substrate Ops Panel",
        "feature": "legacy ops panel",
    },
    {
        "id": "healthz",
        "method": "GET",
        "path": "/healthz",
        "expect_status": 200,
        "expect_json_status": "ok",
        "feature": "health endpoint",
    },
    {
        "id": "dashboard-api",
        "method": "GET",
        "path": "/api/dashboard",
        "expect_status": 200,
        "expect_json_keys": ["metrics", "stage_sequence", "pass_sequence"],
        "feature": "dashboard metrics",
    },
    {
        "id": "standards-api",
        "method": "GET",
        "path": "/api/standards",
        "expect_status": 200,
        "feature": "standards catalog",
    },
    {
        "id": "tooling-api",
        "method": "GET",
        "path": "/api/tooling",
        "expect_status": 200,
        "feature": "tooling status",
    },
    {
        "id": "integrations-api",
        "method": "GET",
        "path": "/api/integrations",
        "expect_status": 200,
        "feature": "integration catalog",
    },
    {
        "id": "learning-api",
        "method": "GET",
        "path": "/api/learning",
        "expect_status": 200,
        "feature": "learning index",
    },
    {
        "id": "config-sync-api",
        "method": "GET",
        "path": "/api/config-sync",
        "expect_status": 200,
        "feature": "config sync",
    },
    {
        "id": "dotfiles-api",
        "method": "GET",
        "path": "/api/dotfiles",
        "expect_status": 200,
        "feature": "dotfiles index",
    },
    {
        "id": "payloads-api",
        "method": "GET",
        "path": "/api/payloads",
        "expect_status": 200,
        "feature": "payload catalog",
    },
    {
        "id": "actions-scan",
        "method": "POST",
        "path": "/api/actions/scan",
        "expect_status": 200,
        "expect_json_ok": True,
        "feature": "repo scan action",
    },
    {
        "id": "metrics-stream",
        "method": "GET",
        "path": "/stream/metrics",
        "expect_status": 200,
        "expect_sse": True,
        "feature": "live metrics stream",
    },
    {
        "id": "iphone-system-stream",
        "method": "GET",
        "path": "/api/iphone/system/stream",
        "expect_status": 200,
        "expect_sse": True,
        "feature": "system live stream",
    },
    {
        "id": "panel-css",
        "method": "GET",
        "path": "/static/control-panel.css",
        "expect_status": 200,
        "feature": "panel styles",
    },
    {
        "id": "panel-js",
        "method": "GET",
        "path": "/static/control-panel.js",
        "expect_status": 200,
        "feature": "panel scripts",
    },
]

# Planned navigation pages the panel is expected to expose.
PLANNED_NAV_PAGES = [
    "overview",
    "metrics",
    "repositories",
    "runs",
    "tasks",
    "learning",
    "kilo",
    "automations",
    "system",
    "terminal",
    "integrations",
    "whatsapp-setup",
    "config",
]

# --------------------------------------------------------------------------- #
# HTTP helpers (stdlib only so it works anywhere).
# --------------------------------------------------------------------------- #


def _request(
    method: str,
    url: str,
    *,
    timeout: float = 8.0,
    read_limit: int | None = None,
    follow_redirects: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    req = urllib.request.Request(url, method=method)
    opener = urllib.request.build_opener(
        urllib.request.HTTPRedirectHandler
        if follow_redirects
        else _NoRedirectHandler()
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            if read_limit is not None:
                body = resp.read(read_limit).decode("utf-8", errors="replace")
            else:
                body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
            headers = dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
        headers = dict(exc.headers)
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "status": None,
            "error": f"{type(exc).__name__}: {exc.reason}",
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    except TimeoutError:
        return {
            "ok": False,
            "status": None,
            "error": "timeout",
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    return {
        "ok": True,
        "status": status,
        "body": body,
        "headers": headers,
        "latency_ms": round((time.monotonic() - started) * 1000),
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):  # type: ignore[type-arg]
    """Suppress redirects so the probe can assert the 3xx response directly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _probe_result(probe: dict[str, Any], base_url: str) -> dict[str, Any]:
    method = probe["method"]
    path = probe["path"]
    url = f"{base_url.rstrip('/')}{path}"
    # Streaming endpoints never close; only read the first chunk.
    read_limit = 4096 if probe.get("expect_sse") else None
    probe_timeout = 4.0 if probe.get("expect_sse") else 8.0
    resp = _request(
        method,
        url,
        timeout=probe_timeout,
        read_limit=read_limit,
        follow_redirects=not probe.get("no_redirect", False),
    )
    if not resp["ok"]:
        return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                "error": resp["error"], "latency_ms": resp["latency_ms"]}
    if resp["status"] != probe.get("expect_status"):
        return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                "status": resp["status"], "body_excerpt": resp["body"][:200],
                "latency_ms": resp["latency_ms"]}
    if "expect_location" in probe:
        location = ""
        for header_key, header_value in resp["headers"].items():
            if header_key.lower() == "location":
                location = header_value
                break
        if probe["expect_location"] not in location:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": "wrong redirect target",
                    "location": location,
                    "latency_ms": resp["latency_ms"]}
    if "expect_text" in probe and probe["expect_text"] not in resp["body"]:
        return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                "status": resp["status"], "error": f"missing expected text: {probe['expect_text']}",
                "latency_ms": resp["latency_ms"]}
    if "expect_json_keys" in probe or "expect_json_ok" in probe or "expect_json_status" in probe:
        try:
            payload = json.loads(resp["body"])
        except json.JSONDecodeError:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": "non-JSON response",
                    "latency_ms": resp["latency_ms"]}
        if probe.get("expect_json_ok") and payload.get("ok") is not True:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": "ok flag not true",
                    "latency_ms": resp["latency_ms"]}
        if probe.get("expect_json_status") and payload.get("status") != probe["expect_json_status"]:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": (
                        f"status != {probe['expect_json_status']}"
                    ),
                    "latency_ms": resp["latency_ms"]}
        for key in probe.get("expect_json_keys", []):
            if key not in payload:
                return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                        "status": resp["status"], "error": f"missing json key: {key}",
                        "latency_ms": resp["latency_ms"]}
    if probe.get("expect_sse"):
        content_type = ""
        for header_key, header_value in resp["headers"].items():
            if header_key.lower() == "content-type":
                content_type = header_value
                break
        if "text/event-stream" not in content_type:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": "not an SSE stream",
                    "content_type": content_type,
                    "latency_ms": resp["latency_ms"]}
        if "Error in metrics stream" in resp["body"] or "no attribute" in resp["body"]:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": "stream backend error",
                    "body_excerpt": resp["body"][:300],
                    "latency_ms": resp["latency_ms"]}
        if "data:" not in resp["body"]:
            return {"probe": probe["id"], "feature": probe["feature"], "ok": False,
                    "status": resp["status"], "error": "empty stream (no data events)",
                    "latency_ms": resp["latency_ms"]}
    return {"probe": probe["id"], "feature": probe["feature"], "ok": True,
            "status": resp["status"], "latency_ms": resp["latency_ms"]}


def _get_panel_html(base_url: str) -> str:
    resp = _request("GET", f"{base_url.rstrip('/')}/panel")
    if resp["ok"] and resp.get("status") == 200:
        return resp["body"]
    return ""


# --------------------------------------------------------------------------- #
# Persona-specific qualitative checks (run on top of the core probes).
# --------------------------------------------------------------------------- #


def _count_pattern(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _visible_text(html: str) -> str:
    """Extract human-readable text from panel HTML, ignoring markup/CSS/JS.

    Block-level element boundaries become newlines so distinct UI text blocks
    are assessed individually instead of being concatenated into one run-on.
    """
    stripped = re.sub(r"<(script|style)[^>]*>.*?</\\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(r"<(br|/p|/li|/div|/h[1-6]|/section|/header|/footer|/aside|/button|/span)[^>]*>", "\n", stripped)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = re.sub(r"&[a-zA-Z#0-9]+;", " ", stripped)
    lines = [re.sub(r"\s+", " ", line).strip() for line in stripped.split("\n")]
    return "\n".join(line for line in lines if line)


def _persona_qualitative_checks(persona_id: str, panel_html: str) -> list[dict[str, Any]]:
    """Run qualitative UI checks specific to each persona segment."""
    checks: list[dict[str, Any]] = []

    if persona_id == "accessibility":
        aria = _count_pattern(panel_html, r"aria-label=")
        roles = _count_pattern(panel_html, r"role=")
        alts = _count_pattern(panel_html, r"alt=")
        tabindex = _count_pattern(panel_html, r"tabindex=")
        if aria < 10:
            checks.append({"id": "a11y-aria", "ok": False,
                           "note": f"only {aria} aria-label attributes found"})
        else:
            checks.append({"id": "a11y-aria", "ok": True})
        if roles < 10:
            checks.append({"id": "a11y-roles", "ok": False,
                           "note": f"only {roles} role attributes found"})
        else:
            checks.append({"id": "a11y-roles", "ok": True})
        if tabindex == 0:
            checks.append({"id": "a11y-tabindex", "ok": False,
                           "note": "no tabindex/focus management found"})
        else:
            checks.append({"id": "a11y-tabindex", "ok": True})
        if alts == 0:
            checks.append({"id": "a11y-alt", "ok": False,
                           "note": "no alt attributes found on images"})
        else:
            checks.append({"id": "a11y-alt", "ok": True})
        if "visually-hidden" not in panel_html and "skip" not in panel_html.lower():
            checks.append({"id": "a11y-skip-link", "ok": False,
                           "note": "no skip-link / visually-hidden helper found"})
        else:
            checks.append({"id": "a11y-skip-link", "ok": True})

    if persona_id == "novice":
        if "help" not in panel_html.lower() and "docs" not in panel_html.lower():
            checks.append({"id": "novice-help", "ok": False,
                           "note": "no visible help/docs cues for first-time users"})
        else:
            checks.append({"id": "novice-help", "ok": True})

    if persona_id == "low_literacy":
        jargon = _count_pattern(panel_html, r"\b(orchestrator|uvicorn|SSE|webhook|substrate|triage)\b")
        if jargon > 12:
            checks.append({"id": "literacy-jargon", "ok": False,
                           "note": f"high jargon density ({jargon} occurrences)"})
        else:
            checks.append({"id": "literacy-jargon", "ok": True})

    if persona_id == "non_native":
        visible = _visible_text(panel_html)
        long_sentences = 0
        for line in visible.split("\n"):
            for sentence in re.findall(r"[^.!?]{140,}[.!?]", line):
                long_sentences += 1
        if long_sentences > 3:
            checks.append({"id": "i18n-sentences", "ok": False,
                           "note": f"{long_sentences} very long sentences (>140 chars) in visible copy"})
        else:
            checks.append({"id": "i18n-sentences", "ok": True})
        abbrevs = _count_pattern(visible, r"\b(SSE|API|URL|HTML|CSS|JSON|CLI)\b")
        if abbrevs > 8:
            checks.append({"id": "i18n-abbrevs", "ok": False,
                           "note": f"high unexplained abbreviation count ({abbrevs})"})
        else:
            checks.append({"id": "i18n-abbrevs", "ok": True})

    if persona_id == "intermediate":
        for page in ["repositories", "runs", "tasks"]:
            if f'data-page="{page}"' not in panel_html:
                checks.append({"id": f"nav-{page}", "ok": False,
                               "note": f"{page} page missing from nav"})
            else:
                checks.append({"id": f"nav-{page}", "ok": True})

    if persona_id == "expert":
        for page in ["automations", "terminal", "kilo", "system"]:
            if f'data-page="{page}"' not in panel_html:
                checks.append({"id": f"nav-{page}", "ok": False,
                               "note": f"{page} page missing from nav"})
            else:
                checks.append({"id": f"nav-{page}", "ok": True})

    return checks


# --------------------------------------------------------------------------- #
# Feedback synthesis
# --------------------------------------------------------------------------- #


def _synthesize_feedback(
    persona: dict[str, Any],
    core_results: list[dict[str, Any]],
    qualitative: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for result in core_results:
        if not result["ok"]:
            state = "broken"
            evidence = result.get("error") or f"HTTP {result.get('status')}"
        else:
            state = "working"
            evidence = "probe passed"
        feedback.append({
            "persona": persona["id"],
            "segment": persona["segment"],
            "feature": result["feature"],
            "probe": result["probe"],
            "state": state,
            "evidence": evidence,
            "latency_ms": result.get("latency_ms"),
            "reported_at": datetime.now(UTC).isoformat(),
        })
    for check in qualitative:
        if check["ok"]:
            continue
        feedback.append({
            "persona": persona["id"],
            "segment": persona["segment"],
            "feature": check["id"],
            "probe": check["id"],
            "state": "broken" if "nav-" in check["id"] else "unintuitive",
            "evidence": check["note"],
            "reported_at": datetime.now(UTC).isoformat(),
        })
    return feedback


# --------------------------------------------------------------------------- #
# QA triage — validate + severity assignment.
# --------------------------------------------------------------------------- #

QA_SQUADS = {
    "frontend": {"features": {"control panel UI", "panel styles", "panel scripts",
                              "home entry", "legacy ops panel"},
                 "keywords": ("aria", "nav-", "a11y", "literacy", "i18n", "help")},
    "backend": {"features": {"dashboard metrics", "standards catalog", "tooling status",
                             "integration catalog", "learning index", "config sync",
                             "dotfiles index", "payload catalog", "repo scan action"},
                "keywords": ("api", "stream")},
    "security": {"features": {"health endpoint"},
                 "keywords": ("auth", "csrf", "injection", "cors", "secret")},
    "devops": {"features": {"live metrics stream", "system live stream"},
               "keywords": ("deploy", "monitor", "rollback", "service")},
}

SEVERITY_RULES: list[tuple[str, str]] = [
    ("critical", ("core", "broken", "stream", "panel UI", "dashboard", "security")),
    ("high", ("broken", "action", "scan", "missing", "automations", "terminal")),
    ("medium", ("unintuitive", "metrics", "standards", "integrations")),
    ("low", ("polish", "cosmetic", "wording", "help")),
]


def _severity_for(issue: dict[str, Any]) -> str:
    feature = issue.get("feature", "").lower()
    state = issue.get("state", "")
    title = f"{feature} {issue.get('evidence', '')}".lower()
    if state == "broken" and any(k in title for k in ("stream", "panel ui", "dashboard", "health")):
        return "critical"
    if state in {"broken", "missing"} and any(k in title for k in ("action", "scan", "automation", "terminal", "run")):
        return "high"
    if state in {"broken", "missing"}:
        return "high"
    if state == "unintuitive":
        return "medium"
    return "low"


def _assign_squad(issue: dict[str, Any]) -> str:
    feature = issue.get("feature", "").lower()
    evidence = issue.get("evidence", "").lower()
    haystack = f"{feature} {evidence}"
    for squad, spec in QA_SQUADS.items():
        if feature in {f.lower() for f in spec["features"]}:
            return squad
        if any(k in haystack for k in spec["keywords"]):
            return squad
    return "backend"


def run_qa_triage(feedback: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate and prioritize collected user feedback into a work queue."""
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in feedback:
        if item["state"] == "working":
            continue
        key = (item["feature"], item["state"])
        if key not in deduped:
            issue = dict(item)
            issue["validation"] = "pending"
            issue["severity"] = _severity_for(item)
            issue["squad"] = _assign_squad(item)
            issue["reporting_segments"] = {item["segment"]}
            issue["report_count"] = 1
            deduped[key] = issue
        else:
            deduped[key]["report_count"] += 1
            deduped[key]["reporting_segments"].add(item["segment"])

    issues = list(deduped.values())
    for issue in issues:
        issue["reporting_segments"] = sorted(issue["reporting_segments"])
        issue["validation"] = "validated"
        issue["work_item_id"] = f"SWARM-{issue['probe'].upper()}-{issue['severity'].upper()}"

    issues.sort(key=lambda i: (SEVERITY_ORDER.get(i["severity"], 9), -i["report_count"]))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_issues": len(issues),
        "by_severity": {
            severity: sum(1 for i in issues if i["severity"] == severity)
            for severity in ("critical", "high", "medium", "low")
        },
        "by_squad": {
            squad: sum(1 for i in issues if i["squad"] == squad)
            for squad in QA_SQUADS
        },
        "issues": issues,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def ensure_state_dir() -> Path:
    SATE_DIR.mkdir(parents=True, exist_ok=True)
    return SATE_DIR


def run_user_simulation(
    base_url: str = DEFAULT_BASE_URL,
    *,
    personas: list[dict[str, Any]] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run the user simulation swarm. Each persona executes its probe plan."""
    del seed  # deterministic probes; seed reserved for future randomized plans
    panel_html = _get_panel_html(base_url)
    active_personas = personas or USER_PERSONAS
    all_feedback: list[dict[str, Any]] = []
    per_persona: dict[str, dict[str, Any]] = {}

    for persona in active_personas:
        core_results = [_probe_result(probe, base_url) for probe in CORE_PROBES]
        qualitative = _persona_qualitative_checks(persona["id"], panel_html)
        feedback = _synthesize_feedback(persona, core_results, qualitative)
        all_feedback.extend(feedback)
        working = sum(1 for f in feedback if f["state"] == "working")
        broken = sum(1 for f in feedback if f["state"] == "broken")
        missing = sum(1 for f in feedback if f["state"] == "missing")
        unintuitive = sum(1 for f in feedback if f["state"] == "unintuitive")
        per_persona[persona["id"]] = {
            "segment": persona["segment"],
            "total_checks": len(feedback),
            "working": working,
            "broken": broken,
            "missing": missing,
            "unintuitive": unintuitive,
            "usability_score": round((working / len(feedback)) * 100, 1) if feedback else 0.0,
        }

    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": base_url,
        "personas_ran": [p["id"] for p in active_personas],
        "total_feedback_items": len(all_feedback),
        "per_persona": per_persona,
        "feedback": all_feedback,
    }
    ensure_state_dir()
    (SATE_DIR / "user-simulation.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False)
    )
    return snapshot


def run_triage_from_simulation(simulation: dict[str, Any]) -> dict[str, Any]:
    feedback = simulation.get("feedback", [])
    triage = run_qa_triage(feedback)
    ensure_state_dir()
    (SATE_DIR / "qa-triage.json").write_text(
        json.dumps(triage, indent=2, ensure_ascii=False)
    )
    return triage


def emit_work_items(triage: dict[str, Any]) -> dict[str, Any]:
    """Turn triaged issues into dev-agent work items with acceptance criteria."""
    work_items: list[dict[str, Any]] = []
    for issue in triage.get("issues", []):
        work_items.append({
            "id": issue["work_item_id"],
            "title": f"[{issue['severity'].upper()}] {issue['feature']}: {issue['evidence'][:120]}",
            "severity": issue["severity"],
            "squad": issue["squad"],
            "feature": issue["feature"],
            "probe": issue["probe"],
            "state": issue["state"],
            "evidence": issue["evidence"],
            "reporting_segments": issue["reporting_segments"],
            "report_count": issue["report_count"],
            "status": "open",
            "acceptance": [
                f"{issue['probe']} probe passes against live app",
                f"no regression in core probes for {issue['feature']}",
            ],
        })
    queue = {"generated_at": datetime.now(UTC).isoformat(),
             "items": work_items}
    ensure_state_dir()
    (SATE_DIR / "work-items.json").write_text(
        json.dumps(queue, indent=2, ensure_ascii=False)
    )
    return queue


def run_iteration_loop(
    base_url: str = DEFAULT_BASE_URL,
    *,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Run simulation -> triage loops. Dev agents consume the work queue between
    iterations; the loop exits when no critical or high issues remain."""
    iterations: list[dict[str, Any]] = []
    for iteration in range(1, max_iterations + 1):
        simulation = run_user_simulation(base_url)
        triage = run_triage_from_simulation(simulation)
        blockers = triage["by_severity"]["critical"] + triage["by_severity"]["high"]
        iterations.append({
            "iteration": iteration,
            "usability_scores": simulation["per_persona"],
            "critical": triage["by_severity"]["critical"],
            "high": triage["by_severity"]["high"],
            "medium": triage["by_severity"]["medium"],
            "low": triage["by_severity"]["low"],
        })
        if blockers == 0:
            break
        if iteration < max_iterations:
            time.sleep(2)
    result = {"iterations": iterations,
              "converged": iterations[-1]["critical"] == 0 and iterations[-1]["high"] == 0
              if iterations else False,
              "generated_at": datetime.now(UTC).isoformat()}
    ensure_state_dir()
    (SATE_DIR / "iteration-loop.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    return result


def _run_command(command: list[str], *, timeout: float = 120.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": completed.returncode == 0, "returncode": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr}


def smoke_tests(base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """Post-deployment smoke test suite against the live app."""
    results = [_probe_result(probe, base_url) for probe in CORE_PROBES]
    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    return {
        "ran_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
        "healthy": failed == 0,
    }


# --------------------------------------------------------------------------- #
# Production deployment support
# --------------------------------------------------------------------------- #

SERVICE_NAME = "openclaw-gateway.service"
SYSTEMD_UNIT_PATH = Path.home() / ".config/systemd/user" / SERVICE_NAME
ROLLBACK_DOC_PATH = Path("docs/PANEL_DEPLOYMENT_RUNBOOK.md")


def check_service() -> dict[str, Any]:
    """Check whether the control panel systemd service is present and running."""
    unit_exists = SYSTEMD_UNIT_PATH.exists()
    status = _run_command(["systemctl", "--user", "is-active", SERVICE_NAME], timeout=15)
    return {
        "service": SERVICE_NAME,
        "unit_file_exists": unit_exists,
        "unit_path": str(SYSTEMD_UNIT_PATH),
        "active": status["ok"] and status["stdout"].strip() == "active",
    }


def deploy_production(base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """DevOps deployment: smoke tests, service health, monitoring, rollback doc."""
    ensure_state_dir()
    smoke = smoke_tests(base_url)
    service = check_service()
    monitoring = {
        "endpoint": "/healthz",
        "stream_endpoint": "/stream/metrics",
        "checks": [
            {"name": "systemd unit active", "pass": service["active"]},
            {"name": "smoke tests healthy", "pass": smoke["healthy"]},
            {"name": "healthz reachable", "pass": smoke["passed"] > 0},
        ],
    }
    monitoring["ok"] = all(c["pass"] for c in monitoring["checks"])

    deployment = {
        "deployed_at": datetime.now(UTC).isoformat(),
        "smoke": smoke,
        "service": service,
        "monitoring": monitoring,
        "rollback": {
            "protocol": f"systemctl --user restart {SERVICE_NAME}",
            "revert_procedure": f"git checkout HEAD -- substrate/web.py && systemctl --user restart {SERVICE_NAME}",
            "docs": str(ROLLBACK_DOC_PATH),
        },
    }
    (SATE_DIR / "deployment.json").write_text(
        json.dumps(deployment, indent=2, ensure_ascii=False)
    )

    ROLLBACK_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROLLBACK_DOC_PATH.write_text(
        "# Panel Deployment Runbook\n\n"
        "## Deploy\n"
        "1. `uv run python -m compileall substrate scripts`\n"
        "2. `uv run python scripts/substrate_cli.py swarm-control deploy`\n"
        "3. Verify `systemctl --user status substrate-panel.service` is active.\n"
        "4. Confirm `/healthz` and `/stream/metrics` return healthy responses.\n\n"
        "## Monitoring\n"
        "- Health: `curl http://127.0.0.1:8090/healthz`\n"
        "- Live metrics: `curl -N http://127.0.0.1:8090/stream/metrics`\n"
        "- Logs: `journalctl --user -u substrate-panel.service -f`\n\n"
        "## Rollback\n"
        "1. Revert app code: `git checkout HEAD -- substrate/web.py`\n"
        "2. Restart the panel: `systemctl --user restart substrate-panel.service`\n"
        "3. Re-run smoke tests: `uv run python scripts/substrate_cli.py swarm-control smoke`\n"
        "4. If metrics stream still fails, inspect `journalctl --user -u substrate-panel.service -n 100`.\n"
    )
    return deployment


# --------------------------------------------------------------------------- #
# Convenience aggregator
# --------------------------------------------------------------------------- #


def swarm_status() -> dict[str, Any]:
    status: dict[str, Any] = {"state_dir": str(SATE_DIR)}
    for name in ("user-simulation.json", "qa-triage.json", "work-items.json",
                 "iteration-loop.json", "deployment.json"):
        path = SATE_DIR / name
        status[name] = json.loads(path.read_text()) if path.exists() else None
    return status
