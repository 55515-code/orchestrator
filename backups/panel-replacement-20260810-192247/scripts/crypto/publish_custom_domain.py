#!/usr/bin/env python3
"""Publish the Pages production deployment to the 1pointo.com custom domain.

Automates the DNS change the OAuth token cannot make:
  1. Find the 1pointo.com zone and its root DNS records.
  2. Remove stale A/AAAA/CNAME records pinning the domain to an old deployment.
  3. Create a proxied CNAME 1pointo.com -> ahrondarnell-site.pages.dev.
  4. Poll the Pages custom-domain status until active.
  5. Verify /support and /resources serve the new content.

Requires a Cloudflare API token with "Zone -> DNS -> Edit" for the 1pointo.com
zone (create one at https://dash.cloudflare.com/profile/api-tokens, template
"Edit zone DNS", scoped to the 1pointo.com zone). Provide via
CLOUDFLARE_API_TOKEN.

Run: uv run python scripts/crypto/publish_custom_domain.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ACCOUNT_ID = "b3f6a813ec38c471e0f307efb85dcb13"
ZONE_NAME = "1pointo.com"
PAGES_PROJECT = "ahrondarnell-site"
PAGES_TARGET = "ahrondarnell-site.pages.dev"
API = "https://api.cloudflare.com/client/v4"

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CloudflareError(RuntimeError):
    pass


def _request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        raise CloudflareError(f"{method} {url} -> HTTP {exc.code}: {body.get('errors')}") from exc
    if not body.get("success"):
        raise CloudflareError(f"{method} {url} -> {body.get('errors')}")
    return body


def find_zone_id(token: str) -> str:
    body = _request(
        "GET", f"{API}/zones?name={ZONE_NAME}", token
    )
    zones = body.get("result") or []
    if not zones:
        raise CloudflareError(f"no Cloudflare zone for {ZONE_NAME}")
    return str(zones[0]["id"])


def fix_dns(token: str, zone_id: str) -> None:
    records = _request(
        "GET",
        f"{API}/zones/{zone_id}/dns_records?name={ZONE_NAME}&per_page=50",
        token,
    )["result"]
    root = [r for r in records if str(r.get("name")).rstrip(".") == ZONE_NAME]
    desired = next((r for r in root if r.get("type") == "CNAME"
                    and str(r.get("content")).rstrip(".") == PAGES_TARGET), None)
    if desired:
        print(f"DNS already correct: CNAME {ZONE_NAME} -> {PAGES_TARGET} (record {desired['id']})")
        return
    for record in root:
        if record.get("type") in {"A", "AAAA", "CNAME"}:
            _request("DELETE", f"{API}/zones/{zone_id}/dns_records/{record['id']}", token)
            print(f"removed stale {record['type']} record {record['id']}: "
                  f"{record.get('content')}")
    created = _request(
        "POST",
        f"{API}/zones/{zone_id}/dns_records",
        token,
        {
            "type": "CNAME",
            "name": ZONE_NAME,
            "content": PAGES_TARGET,
            "proxied": True,
            "comment": "Pages production — managed by scripts/crypto/publish_custom_domain.py",
        },
    )["result"]
    print(f"created CNAME {ZONE_NAME} -> {PAGES_TARGET} (record {created['id']})")


def wait_for_domain_active(token: str, timeout_seconds: int = 240) -> None:
    url = f"{API}/accounts/{ACCOUNT_ID}/pages/projects/{PAGES_PROJECT}/domains/{ZONE_NAME}"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = _request("GET", url, token)["result"]
        status = result.get("status")
        verification = (result.get("verification_data") or {}).get("status")
        print(f"custom domain status: {status} (verification: {verification})")
        if status == "active":
            return
        time.sleep(15)
    raise CloudflareError(f"custom domain did not reach 'active' within {timeout_seconds}s")


def verify_site() -> dict:
    checks = {}
    for path, needle in (
        ("/support/", "copy-btn"),
        ("/resources/", "card__title"),
    ):
        try:
            with urllib.request.urlopen(f"https://{ZONE_NAME}{path}", timeout=30) as response:
                html = response.read().decode("utf-8")
            checks[path] = html.count(needle) > 0
        except Exception as exc:  # noqa: BLE001
            checks[path] = f"error: {exc}"
    return checks


def main() -> int:
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    token_file = Path(
        os.getenv("CLOUDFLARE_DNS_TOKEN_FILE", str(Path.home() / ".config" / "substrate" / "cf-dns-token"))
    )
    if not token and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        import getpass

        token = getpass.getpass(
            "Paste a Cloudflare API token with 'Zone -> DNS -> Edit' for "
            "1pointo.com: "
        ).strip()
    if not token:
        print("no token provided", file=sys.stderr)
        return 2

    try:
        zone_id = find_zone_id(token)
        print(f"zone found: {ZONE_NAME} ({zone_id})")
        fix_dns(token, zone_id)
        wait_for_domain_active(token)
        checks = verify_site()
        print(json.dumps({"published": True, "checks": checks}, indent=2))
        return 0
    except CloudflareError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
