#!/usr/bin/env python3
"""Create a narrowly-scoped Cloudflare API token using the user's browser session.

Drives the Cloudflare dashboard with the user's existing Chromium session
(copied profile) to create an "Edit zone DNS" token scoped ONLY to the
1pointo.com zone. The token is written to ~/.config/substrate/cf-dns-token
with 0600 permissions and is never printed.

Run: uv run --with playwright python scripts/crypto/create_cf_dns_token.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = Path(os.environ.get("CF_PROFILE_COPY", "/home/ahron/.cache/kilo/chromium-profile"))
TOKEN_FILE = Path(os.environ.get("CF_DNS_TOKEN_FILE", str(Path.home() / ".config" / "substrate" / "cf-dns-token")))
SHOT_DIR = Path(os.environ.get("CF_SHOT_DIR", "/home/ahron/.cache/kilo/cf-shots"))
ZONE_NAME = "1pointo.com"
API_TOKENS_URL = "https://dash.cloudflare.com/profile/api-tokens"


def snap(page, name: str) -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=False)
        print(f"  [shot] {SHOT_DIR / name}.png")
    except Exception:  # noqa: BLE001
        pass


def pass_turnstile(page, attempts: int = 4) -> None:
    """Click through Cloudflare's own Turnstile challenge if it appears."""
    for _ in range(attempts):
        if "Performing security verification" not in page.content():
            return
        print("  turnstile challenge detected; clicking ...")
        try:
            frame = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
            frame.locator("input[type='checkbox'], .cb-lb, label").first.click(timeout=8000)
        except Exception:  # noqa: BLE001
            try:
                page.locator("text=Verify you are human").first.click(timeout=5000)
            except Exception:  # noqa: BLE001
                pass
        page.wait_for_timeout(6000)
    if "Performing security verification" in page.content():
        raise RuntimeError("Turnstile challenge did not clear")


def main() -> int:
    with sync_playwright() as pw:
        print("launching chromium with copied profile ...")
        context = pw.chromium.launch_persistent_context(
            str(PROFILE),
            executable_path="/usr/bin/chromium",
            headless=False,
            # Chromium encrypts cookies with the OS keyring; Playwright's
            # default mock keychain would prevent session reuse.
            ignore_default_args=["--password-store=basic", "--use-mock-keychain"],
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--disable-crash-reporter",
                "--disable-breakpad",
            ],
            viewport={"width": 1440, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(API_TOKENS_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        pass_turnstile(page)
        snap(page, "01-api-tokens")

        if "login" in page.url or page.locator("text=Log in").count() > 0:
            print("ERROR: session not authenticated (login page shown)")
            snap(page, "02-login")
            context.close()
            return 3

        # Create Token -> use the "Edit zone DNS" template.
        create_btn = page.get_by_role("button", name=re_contains("Create Token"))
        if create_btn.count() == 0:
            create_btn = page.locator("button:has-text('Create Token')")
        create_btn.first.click(timeout=20000)
        time.sleep(4)
        snap(page, "02-templates")

        use_template = page.locator(
            "div:has-text('Edit zone DNS') >> text=Use template"
        ).first
        if use_template.count() == 0:
            use_template = page.get_by_role("button", name="Use template").first
        use_template.click(timeout=20000)
        time.sleep(4)
        snap(page, "03-token-form")

        # Token name.
        name_input = page.locator("input[placeholder*='oken']").first
        if name_input.count() == 0:
            name_input = page.locator("input[name*='name' i]").first
        name_input.fill("substrate-dns-edit-1pointo", timeout=10000)
        snap(page, "04-name-filled")

        # Zone resources: switch from "All zones" to a specific zone.
        resource_dropdown = page.locator(
            "button:has-text('All zones'), div[role='combobox']:has-text('All zones'), "
            "div:has-text('Include — All zones') >> nth=0"
        ).first
        try:
            resource_dropdown.click(timeout=10000)
            time.sleep(2)
            snap(page, "05-zone-dropdown-open")
            specific = page.get_by_text("Specific zone", exact=True).first
            specific.click(timeout=10000)
            time.sleep(2)
            search = page.locator("input[type='search'], input[placeholder*='Search']").first
            search.fill(ZONE_NAME, timeout=10000)
            time.sleep(2)
            snap(page, "06-zone-search")
            option = page.locator(f"text={ZONE_NAME}").first
            option.click(timeout=10000)
        except Exception as exc:  # noqa: BLE001
            print(f"  zone-resource step note: {exc}")
        time.sleep(2)
        snap(page, "07-zone-selected")

        continue_btn = page.get_by_role("button", name=re_contains("Continue to summary"))
        if continue_btn.count() == 0:
            continue_btn = page.locator("button:has-text('Continue to summary')")
        continue_btn.first.click(timeout=15000)
        time.sleep(3)
        snap(page, "08-summary")

        create_token = page.get_by_role("button", name=re_contains("Create Token"))
        if create_token.count() == 0:
            create_token = page.locator("button:has-text('Create Token')")
        create_token.first.click(timeout=15000)
        time.sleep(5)
        snap(page, "09-token-created")

        # Extract the token value. The success dialog shows it in a <code> block.
        token = ""
        for selector in (
            "code:has-text('_') >> nth=0",
            "textarea",
            "[data-testid*='token'] input",
            "pre code",
        ):
            loc = page.locator(selector).first
            if loc.count() > 0:
                candidate = loc.input_value() if loc.evaluate("e => e.tagName === 'INPUT' or e.tagName === 'TEXTAREA'") else loc.inner_text()
                candidate = str(candidate).strip()
                if len(candidate) > 30 and " " not in candidate:
                    token = candidate
                    break
        if not token:
            # Fallback: read the dialog body and extract the visible token string.
            body_text = page.locator("body").inner_text()
            for line in body_text.splitlines():
                line = line.strip()
                if len(line) >= 35 and line.count(" ") == 0:
                    token = line
                    break

        context.close()

        if not token:
            print("ERROR: could not extract token from the created-token dialog.")
            print("Inspect the screenshots in " + str(SHOT_DIR))
            return 4

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token, encoding="utf-8")
        os.chmod(TOKEN_FILE, 0o600)
        print(f"token created and saved to {TOKEN_FILE} (0600, {len(token)} chars, not shown)")
        return 0


def re_contains(pattern: str):
    import re

    return re.compile(pattern, re.IGNORECASE)


if __name__ == "__main__":
    raise SystemExit(main())
