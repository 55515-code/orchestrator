"""Market-research agent — the sales research swarm.

Tier 0 (read-only): refreshes evidence about where to advertise digital
resources and how autonomous agent networks can buy them (x402-style
micropayments, agent marketplaces, LLM discovery). Findings land in
``.research/market-demand/`` as Markdown notes plus JSON sidecars carrying
``demand_score`` / ``competition`` that feed the expansion trigger.

Also maintains ``state/sales-posture.json`` — the always-selling dashboard
listing every live sales surface so staleness is visible at a glance.

Discovery is passive and pull-based only (PF-015): this agent never sends
outbound messages or posts anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .. import _utils

TARGETS_FILE = "research-targets.yaml"


def _load_targets(runtime: Any) -> list[dict[str, Any]]:
    path = runtime.root / TARGETS_FILE
    payload = _utils.load_yaml(path)
    targets = payload.get("targets")
    if not isinstance(targets, list):
        return []
    return [target for target in targets if isinstance(target, dict)]


def _provider_note(agent: Any, prompt: str) -> str | None:
    """Optional enrichment from the configured provider; failures degrade."""
    if agent.provider in {"mock", "codex"}:
        return None
    try:
        from ..providers import DEFAULT_PROVIDER_MODELS, build_model

        model = build_model(agent.provider, DEFAULT_PROVIDER_MODELS.get(agent.provider, ""))
        if model is None:
            return None
        result = model.invoke(prompt)
        text = getattr(result, "content", None)
        return str(text).strip() or None
    except Exception:  # noqa: BLE001 - provider outage must not block research
        return None


def _sales_posture(runtime: Any) -> dict[str, Any]:
    """Snapshot of every sales surface (always-selling dashboard)."""
    site_root = runtime.root / "ahrondarnell-site"
    surfaces = [
        {
            "surface": "site_support_page",
            "path": "ahrondarnell-site/src/pages/support.astro",
            "live": (site_root / "src" / "pages" / "support.astro").exists(),
        },
        {
            "surface": "site_llms_txt",
            "path": "ahrondarnell-site/public/llms.txt",
            "live": (site_root / "public" / "llms.txt").exists(),
        },
        {
            "surface": "llm_catalog",
            "path": "resources/llm-catalog.json",
            "live": (runtime.root / "resources" / "llm-catalog.json").exists(),
        },
        {
            "surface": "worker_llms_endpoint",
            "path": "workers/resource-delivery/index.js",
            "live": "/api/llms"
            in (runtime.root / "workers" / "resource-delivery" / "index.js").read_text(
                encoding="utf-8"
            )
            if (runtime.root / "workers" / "resource-delivery" / "index.js").exists()
            else False,
        },
        {
            "surface": "worker_402_flow",
            "path": "workers/resource-delivery/index.js",
            "live": "402"
            in (runtime.root / "workers" / "resource-delivery" / "index.js").read_text(
                encoding="utf-8"
            )
            if (runtime.root / "workers" / "resource-delivery" / "index.js").exists()
            else False,
        },
        {
            "surface": "donation_wallets",
            "path": "state/crypto/wallets.json",
            "live": bool(
                _utils.load_json(runtime.root / "state" / "crypto" / "wallets.json").get(
                    "wallets"
                )
            ),
        },
    ]
    return {
        "generated_at": _utils.utc_now_iso(),
        "always_selling": True,
        "surfaces": surfaces,
        "live_count": sum(1 for surface in surfaces if surface["live"]),
    }


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator, directive
    runtime.resolve_repo(agent.repo_slug)
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    targets = _load_targets(runtime)
    if not targets:
        return {
            "status": "success",
            "note": "no research targets configured",
            "outputs": outputs,
            "actions": actions,
        }

    findings_dir = runtime.paths["research"] / "market-demand"
    findings_dir.mkdir(parents=True, exist_ok=True)

    for target in targets:
        target_id = str(target.get("id") or "unknown")
        kind = str(target.get("kind") or "channel")
        note_path = findings_dir / f"{date_str}-{target_id}.md"
        sidecar_path = findings_dir / f"{date_str}-{target_id}.json"

        prompt = (
            f"Research current advertising and monetization opportunities for: "
            f"{target.get('name', target_id)}. Focus: {target.get('focus', '')}. "
            f"Answer: {'; '.join(target.get('questions') or [])}. "
            "Cite sources; keep it under 200 words."
        )
        enrichment = _provider_note(agent, prompt)

        lines = [
            f"# Market research — {target.get('name', target_id)} ({date_str})",
            "",
            f"- Target id: `{target_id}`",
            f"- Kind: {kind}",
            f"- Focus: {target.get('focus', '')}",
            f"- Demand score: {target.get('demand_score', 0.5)}",
            f"- Competition: {target.get('competition', 0.5)}",
            f"- Agent: `{agent.id}`",
            "",
            "## Open questions",
            "",
        ]
        lines += [f"- {question}" for question in target.get("questions") or []]
        lines += ["", "## Findings", ""]
        if enrichment:
            lines += [enrichment, ""]
        else:
            lines += [
                "Provider enrichment unavailable (mock/offline mode). "
                + "Registry facts above are the source of truth for this cycle.",
                "",
            ]
        lines += [
            "## Next actions (Tier 2, human-directed)",
            "",
            "- Validate demand score against live channel evidence before spending.",
            "- If channel is viable, draft listing/copy and request publish directive.",
            "",
        ]
        note_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

        _utils.write_json(
            sidecar_path,
            {
                "target_id": target_id,
                "kind": kind,
                "date": date_str,
                "demand_score": float(target.get("demand_score", 0.5)),
                "competition": float(target.get("competition", 0.5)),
                "enriched": enrichment is not None,
                "note": str(note_path.relative_to(runtime.root)),
            },
        )
        outputs.append(str(note_path.relative_to(runtime.root)))
        actions.append(
            {
                "action": f"research:{target_id}",
                "tier": 0,
                "status": "success",
                "demand_score": float(target.get("demand_score", 0.5)),
            }
        )

    posture = _sales_posture(runtime)
    posture_path = runtime.paths["state"] / "sales-posture.json"
    _utils.write_json(posture_path, posture)
    outputs.append(str(posture_path.relative_to(runtime.root)))
    actions.append(
        {
            "action": "sales-posture-refresh",
            "tier": 0,
            "status": "success",
            "live_surfaces": posture["live_count"],
        }
    )

    return {
        "status": "success",
        "note": f"researched {len(targets)} target(s); "
        f"{posture['live_count']} sales surface(s) live",
        "outputs": outputs,
        "actions": actions,
    }
