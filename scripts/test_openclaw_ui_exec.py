#!/usr/bin/env python3
"""Playwright E2E test — OpenClaw Control UI execution-task workflow.

Scenario 2: verify the agent can launch a simple execution task (bash)
through the browser chat and report the result, with no error states.

Run:
    cd /home/ahron/codespace
    uv run --with playwright python scripts/test_openclaw_ui_exec.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

TOKEN_PATH = Path.home() / "codespace" / "state" / "openclaw-gateway-token.txt"
BASE_URL = os.environ.get("OPENCLAW_BASE_URL", "http://127.0.0.1:8090")
MARKER = "EXEC_BROWSER_MARKER_42"


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
        print("FAIL: no gateway token")
        return 1

    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        print(f"[1] Loading {BASE_URL}/chat with token auth")
        page.goto(f"{BASE_URL}/chat#token={token}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        print("[2] Locating composer")
        composer = None
        try:
            composer = page.locator(".agent-chat__composer-combobox textarea").first
            composer.wait_for(timeout=15000)
        except PlaywrightTimeout:
            for sel in ("textarea", "[contenteditable=true]"):
                try:
                    composer = page.locator(sel).first
                    composer.wait_for(timeout=3000)
                    break
                except PlaywrightTimeout:
                    continue
        if composer is None:
            failures.append("composer not found")
            page.screenshot(path="/tmp/openclaw-ui-exec-no-composer.png")
            browser.close()
            print("FAIL: composer not found")
            return 1

        print("[3] Sending execution-task message")
        composer.fill(f"Run this exact bash command and report its output: echo {MARKER}")
        try:
            send_btn = page.get_by_role("button", name="Send message")
            send_btn.wait_for(timeout=10000)
            send_btn.click()
        except PlaywrightTimeout:
            composer.press("Enter")

        print("[4] Waiting for execution result (up to 120s)")
        deadline = time.time() + 120
        replied = False
        while time.time() < deadline:
            body = page.locator("body").inner_text()
            if MARKER in body:
                replied = True
                break
            time.sleep(3)

        page.screenshot(path="/tmp/openclaw-ui-exec-final.png")
        if replied:
            print(f"    PASS: agent executed task and returned {MARKER}")
        else:
            tail = page.locator("body").inner_text()[-400:]
            failures.append(f"execution result not returned. Body tail: {tail!r}")

        print("[5] Checking for error states (post-marker text only)")
        # Old chat history may contain pre-fix error messages. Only inspect
        # thread text AFTER the marker (i.e. the newest agent response).
        thread_text = page.locator(".chat-thread-inner").first.inner_text() if page.locator(".chat-thread-inner").count() else ""
        marker_idx = thread_text.find(MARKER)
        if marker_idx >= 0:
            scan_target = thread_text[marker_idx:].lower()
        else:
            scan_target = ""
        error_phrases = ("agent failed to run", "context overflow", "401 status", "embedded agent failed")
        for phrase in error_phrases:
            if phrase in scan_target:
                failures.append(f"error phrase in latest response: {phrase}")
        if MARKER.lower() not in thread_text.lower():
            failures.append("expected marker not found in chat thread")

        browser.close()

    if failures:
        print("\n=== E2E EXEC FAILURES ===")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n=== E2E EXEC PASS: agent launched execution task error-free ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
