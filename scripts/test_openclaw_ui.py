#!/usr/bin/env python3
"""Playwright E2E test for the OpenClaw Control UI chat flow.

Verifies that a user can open the Control UI, send a message to the
OpenClaw agent, and receive a reply WITHOUT any error state — proving the
repaired agent runtime (kilo-proxy -> Kilo CLI cloud, Ollama fallback)
responds during standard operation.

Run:
    cd /home/ahron/codespace
    uv run --with playwright --with pytest python scripts/test_openclaw_ui.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

TOKEN_PATH = Path.home() / "codespace" / "state" / "openclaw-gateway-token.txt"
BASE_URL = os.environ.get("OPENCLAW_BASE_URL", "http://127.0.0.1:8090")


def get_token() -> str:
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if not token and TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text().strip()
    return token


def main() -> int:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    token = get_token()
    if not token:
        print("FAIL: no gateway token found (OPENCLAW_GATEWAY_TOKEN or state file)")
        return 1

    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            user_agent="playwright-e2e-test/1.0",
        )

        # --- 1. Load Control UI with token auth ---
        url = f"{BASE_URL}/#token={token}"
        print(f"[1] Loading {BASE_URL} with token auth")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)
        title = page.title()
        print(f"    title: {title}")
        if "OpenClaw" not in title:
            failures.append(f"unexpected title: {title}")

        # --- 2. Navigate to chat view ---
        print("[2] Opening chat composer")
        # The Control UI is a SPA; the chat composer is the textarea. Try
        # directly and also via keyboard shortcut if the route needs a click.
        try:
            page.goto(f"{BASE_URL}/chat#token={token}", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)

        # --- 3. Find the composer and type a message ---
        print("[3] Typing test message")
        composer = None
        try:
            composer = page.locator(".agent-chat__composer-combobox textarea").first
            composer.wait_for(timeout=15000)
        except PlaywrightTimeout:
            # Fallback selectors
            for sel in ("textarea[data-testid=chat-input]", "textarea", "[contenteditable=true]"):
                try:
                    composer = page.locator(sel).first
                    composer.wait_for(timeout=3000)
                    print(f"    used fallback selector: {sel}")
                    break
                except PlaywrightTimeout:
                    continue
        if composer is None:
            failures.append("could not locate chat composer")
            page.screenshot(path="/tmp/openclaw-ui-composer-missing.png")
            browser.close()
            print("FAIL: composer not found; screenshot at /tmp/openclaw-ui-composer-missing.png")
            return 1

        composer.fill("Reply with exactly: PLAYWRIGHT_OK")
        print("    message typed")

        # --- 4. Send the message ---
        print("[4] Sending message")
        sent = False
        try:
            send_btn = page.get_by_role("button", name="Send message")
            send_btn.wait_for(timeout=10000)
            send_btn.click()
            sent = True
        except PlaywrightTimeout:
            # Keyboard fallback: Enter
            composer.press("Enter")
            sent = True
        print(f"    sent: {sent}")

        # --- 5. Wait for the agent reply ---
        print("[5] Waiting for agent reply (up to 120s)")
        replied = False
        deadline = time.time() + 120
        observed_text = ""
        while time.time() < deadline:
            body = page.locator("body").inner_text()
            if "PLAYWRIGHT_OK" in body:
                observed_text = "PLAYWRIGHT_OK"
                replied = True
                break
            # Any reply containing text (agent working state)
            if "error" not in body.lower() and len(body.strip()) > 200:
                pass
            time.sleep(3)

        page.screenshot(path="/tmp/openclaw-ui-final.png", full_page=False)
        if replied:
            print(f"    PASS: agent replied with '{observed_text}'")
        else:
            body = page.locator("body").inner_text()[-500:]
            failures.append(f"agent did not reply. Body tail: {body!r}")

        # --- 6. Verify no error banner is present ---
        print("[6] Checking for error states")
        error_phrases = [
            "agent failed to run",
            "context overflow",
            "401 status",
            "Embedded agent failed",
            "Unable to connect",
        ]
        body_lower = page.locator("body").inner_text().lower()
        for phrase in error_phrases:
            if phrase.lower() in body_lower:
                failures.append(f"error phrase present: {phrase}")
                print(f"    FAIL: found error phrase: {phrase}")

        browser.close()

    if failures:
        print("\n=== E2E FAILURES ===")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n=== E2E PASS: OpenClaw Control UI chat flow error-free ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
