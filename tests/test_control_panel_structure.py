"""Structural tests for the control panel template.

Guards against the page-div nesting regression that made the Vault's
"Open setup wizard" button (and WhatsApp Setup / Config / Agents /
Pipelines navigation) appear dead: when a later `.page` div was nested
*inside* `#page-vault`, removing `.active` from the vault hid the whole
subtree, so `navigateTo()` appeared to do nothing.

The invariant checked here: every `.page` div must be a direct child of
`.page-container` (i.e. no page div may be nested inside another page
div), and all divs must balance.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL_TEMPLATE = ROOT / "substrate" / "templates" / "control-panel.html"


class DivTracker(HTMLParser):
    """Track div nesting, page ids, and balance errors."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.pages: dict[str, list[str]] = {}
        self.page_order: list[str] = []
        self.balance_errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        attrs_dict = dict(attrs)
        div_id = attrs_dict.get("id") or ""
        self.stack.append(div_id)
        if div_id.startswith("page-"):
            self.pages[div_id] = list(self.stack)
            self.page_order.append(div_id)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return
        if self.stack:
            self.stack.pop()
        else:
            self.balance_errors.append(f"unbalanced </div> at line {self.getpos()[0]}")


def _parse_panel() -> DivTracker:
    assert PANEL_TEMPLATE.exists(), f"missing template: {PANEL_TEMPLATE}"
    parser = DivTracker()
    parser.feed(PANEL_TEMPLATE.read_text(encoding="utf-8"))
    return parser


def test_panel_divs_are_balanced() -> None:
    parser = _parse_panel()
    assert parser.balance_errors == []
    # Every opened div must be closed.
    assert parser.stack == [], f"unclosed divs remain: {parser.stack}"


def test_every_page_div_is_top_level_sibling() -> None:
    """No page div may be nested inside another page div."""
    parser = _parse_panel()
    assert parser.page_order, "expected at least one .page div"
    for page_id in parser.page_order:
        ancestors = parser.pages[page_id]
        # Exactly: page-container (no id) → page div itself.
        assert ancestors[-1] == page_id, f"{page_id} not outermost: {ancestors}"
        nested_pages = [a for a in ancestors[:-1] if a.startswith("page-")]
        assert nested_pages == [], f"{page_id} is nested inside {nested_pages}"


def test_vault_page_is_not_ancestor_of_other_pages() -> None:
    """Regression: Proton/WhatsApp/Config/Agents/Pipelines pages were nested
    inside #page-vault after the Proton wizard rework, making the vault's
    'Open setup wizard' button appear to do nothing."""
    parser = _parse_panel()
    for page_id in ("page-proton", "page-whatsapp-setup", "page-config",
                    "page-agents", "page-pipelines", "page-vault"):
        assert page_id in parser.pages, f"missing page div: {page_id}"
        ancestors = parser.pages[page_id]
        assert "page-vault" not in ancestors[:-1], (
            f"{page_id} is nested inside page-vault: {ancestors}"
        )


def test_vault_modal_root_is_sibling_of_pages() -> None:
    """#vaultModalRoot must not be inside a page div either, or the modal
    would be hidden whenever that page loses .active."""
    html = PANEL_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="vaultModalRoot"' in html
    # Find the line of vaultModalRoot and ensure no page div is still open.
    for lineno, line in enumerate(html.splitlines(), 1):
        if 'id="vaultModalRoot"' in line:
            modal_line = lineno
            break
    else:  # pragma: no cover
        raise AssertionError("vaultModalRoot not found")

    # Re-parse tracking line numbers.
    class LineAware(DivTracker):
        def __init__(self) -> None:
            super().__init__()
            self.open_pages_at_line: dict[int, list[str]] = {}

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            super().handle_starttag(tag, attrs)
            if tag == "div":
                line = self.getpos()[0]
                self.open_pages_at_line[line] = [
                    i for i in self.stack if i.startswith("page-")
                ]

    tracker = LineAware()
    tracker.feed(html)
    open_pages = tracker.open_pages_at_line.get(modal_line, [])
    assert open_pages == [], (
        f"vaultModalRoot (line {modal_line}) is inside open page divs: {open_pages}"
    )
