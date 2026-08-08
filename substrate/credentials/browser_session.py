"""Browser automation session management.

Manages Playwright persistent browser contexts with storage state persistence
for automation tasks. Uses a dedicated automation profile that maintains
logged-in sessions across runs.

Security invariants:
- Browser sessions are stored in ~/.config/substrate/automation-profile/
- Storage state (cookies + localStorage) is persisted to state/browser-sessions/
- All browser automation is audited.
- Tier 2 gating for sensitive operations.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..security.audit_trail import AuditTrail

AUTOMATION_PROFILE = Path.home() / ".config" / "substrate" / "automation-profile"
STORAGE_STATE_DIR = Path("state") / "browser-sessions"


class BrowserSession:
    """Manage a persistent browser session for automation."""

    def __init__(self, root: Path, *, audit: AuditTrail | None = None) -> None:
        self.root = Path(root)
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")
        self.profile_dir = AUTOMATION_PROFILE
        self.storage_dir = self.root / STORAGE_STATE_DIR

    def ensure_profile(self) -> Path:
        """Ensure the automation profile directory exists."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        return self.profile_dir

    def save_storage_state(self, context, service: str) -> Path:
        """Save browser storage state (cookies + localStorage) for a service."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        state_file = self.storage_dir / f"{service}.json"
        context.storage_state(path=str(state_file))
        self.audit.append("browser_session_saved", tier=0, details={"service": service, "path": str(state_file)})
        return state_file

    def load_storage_state(self, service: str) -> Path | None:
        """Load saved storage state for a service."""
        state_file = self.storage_dir / f"{service}.json"
        if state_file.exists():
            self.audit.append("browser_session_loaded", tier=0, details={"service": service})
            return state_file
        return None

    def launch_context(self, pw, service: str, *, headless: bool = True):
        """Launch a persistent browser context with saved session if available."""

        self.ensure_profile()
        storage_state = self.load_storage_state(service)

        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-first-run",
            "--disable-crash-reporter",
            "--disable-breakpad",
        ]

        # Use the system Chromium if available, otherwise Playwright's bundled
        executable_path = shutil.which("chromium") or shutil.which("google-chrome")

        context = pw.chromium.launch_persistent_context(
            str(self.profile_dir),
            executable_path=executable_path,
            headless=headless,
            ignore_default_args=["--password-store=basic", "--use-mock-keychain"],
            args=args,
            storage_state=str(storage_state) if storage_state else None,
            viewport={"width": 1440, "height": 900},
        )

        self.audit.append("browser_session_launched", tier=0, details={
            "service": service,
            "profile": str(self.profile_dir),
            "storage_state": str(storage_state) if storage_state else "none",
        })

        return context

    def interactive_login(self, service: str, login_url: str) -> None:
        """Open a browser for the user to log in interactively, then save the session."""
        from playwright.sync_api import sync_playwright

        print(f"Opening browser for {service} login at {login_url}")
        print("Please log in manually. The session will be saved when you close the browser.")

        with sync_playwright() as pw:
            context = self.launch_context(pw, service, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for the user to close the browser or navigate away
            print("Browser is open. Log in, then close the browser window to save the session.")
            try:
                context.pages[0].wait_for_close(timeout=300000)  # 5 minutes
            except Exception:
                pass

            # Save the session
            self.save_storage_state(context, service)
            context.close()

        print(f"Session saved for {service}")
