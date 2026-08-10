"""Resource catalog management with integrity checks.

The catalog (``resources/catalog.json``) lists every sellable or free
resource with its checksum. Publishing into the catalog is Tier 2 (requires a
human directive) and requires a valid checksum. Free resources (price 0) are
the "free to process" services surfaced on the public site.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail

CATALOG_RELATIVE = Path("resources") / "catalog.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class ResourceInventory:
    """Load, validate, and publish resources in the catalog."""

    def __init__(self, root: Path, *, audit: AuditTrail | None = None) -> None:
        self.root = Path(root)
        self.resources_dir = self.root / "resources"
        self.catalog_path = self.root / CATALOG_RELATIVE
        self.audit = audit

    def load(self) -> list[dict[str, Any]]:
        if not self.catalog_path.exists():
            return []
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        resources = payload.get("resources")
        if not isinstance(resources, list):
            raise TypeError("catalog.json must contain a 'resources' list")
        return list(resources)

    def _save(self, resources: list[dict[str, Any]]) -> None:
        payload = {
            "version": 1,
            "updated_at": _utils.utc_now_iso(),
            "resources": resources,
        }
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def get(self, resource_id: str) -> dict[str, Any] | None:
        for entry in self.load():
            if entry.get("id") == resource_id:
                return entry
        return None

    def free_resources(self) -> list[dict[str, Any]]:
        return [entry for entry in self.load() if float(entry.get("price_usdc", 0)) == 0]

    def paid_resources(self) -> list[dict[str, Any]]:
        return [entry for entry in self.load() if float(entry.get("price_usdc", 0)) > 0]

    def export_llm_catalog(self) -> dict[str, Any]:
        """Machine-readable catalog for LLM/agent discovery (bots as buyers).

        Flattens catalog entries into an agent-friendly JSON shape with
        semantic fields. Mirror of ``resources/catalog.json`` (PF-014).
        """
        entries = []
        for resource in self.load():
            entries.append(
                {
                    "id": resource.get("id"),
                    "title": resource.get("title"),
                    "category": resource.get("category"),
                    "description": resource.get("description", ""),
                    "price_usdc": resource.get("price_usdc"),
                    "free": bool(resource.get("free") or float(resource.get("price_usdc", 0)) == 0),
                    "version": resource.get("version", "1.0"),
                    "format": "markdown" if str(resource.get("file_path", "")).endswith(".md") else "yaml",
                    "topic": resource.get("topic", ""),
                    "delivery": "token-gated" if float(resource.get("price_usdc", 0)) > 0 else "free",
                }
            )
        return {
            "version": 1,
            "service": "1pointo digital resources",
            "generated_at": _utils.utc_now_iso(),
            "note": "Payments accepted in USDC/DAI on Polygon and Base. "
                    "See docs/CRYPTO_PAYMENT_RUNBOOK.md for the delivery flow.",
            "resources": entries,
        }

    def validate_checksums(self) -> dict[str, Any]:
        """Verify every catalog file exists and matches its recorded checksum."""
        problems: list[str] = []
        checked = 0
        for entry in self.load():
            rel = str(entry.get("file_path") or "")
            path = self.root / rel
            if not path.exists():
                problems.append(f"{entry.get('id')}: missing file {rel}")
                continue
            actual = sha256_file(path)
            expected = str(entry.get("checksum") or "")
            if expected and actual != expected:
                problems.append(f"{entry.get('id')}: checksum mismatch")
            checked += 1
        return {"ok": not problems, "checked": checked, "problems": problems}

    def publish(self, entry: dict[str, Any], *, directive: str = "") -> dict[str, Any]:
        """Add or replace a resource in the catalog. Tier 2: needs directive."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(f"publishing is Tier 2 ({reason})")

        resource_id = str(entry.get("id") or "").strip()
        if not resource_id:
            raise ValueError("resource entry requires an 'id'")
        rel = str(entry.get("file_path") or "")
        path = self.root / rel
        if not path.exists():
            raise FileNotFoundError(f"resource file missing: {rel}")

        computed = sha256_file(path)
        declared = str(entry.get("checksum") or "")
        if declared and declared != computed:
            raise ValueError(f"declared checksum does not match file for {resource_id}")
        entry = {**entry, "checksum": computed}

        resources = self.load()
        replaced = False
        for index, existing in enumerate(resources):
            if existing.get("id") == resource_id:
                resources[index] = entry
                replaced = True
                break
        if not replaced:
            resources.append(entry)
        self._save(resources)
        if self.audit is not None:
            self.audit.append(
                "resource_published",
                tier=TIER_HUMAN,
                details={
                    "id": resource_id,
                    "price_usdc": entry.get("price_usdc"),
                    "replaced": replaced,
                },
            )
        return {"id": resource_id, "replaced": replaced, "checksum": computed}
