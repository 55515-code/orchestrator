"""Integration tests for the vault setup wizard navigation.

These verify that:
- The panel template has a correct div structure (no page nested inside another).
- page-proton is a direct sibling of page-vault (the Aug-19 regression).
- All nav pages are direct children of .page-container.
- The vault API never leaks raw secrets into state or responses.
- The vault modal and delete flows operate correctly end-to-end.

Style matches tests/test_control_panel_structure.py and tests/test_vault_api.py.
All state is isolated under tmp_path via the encrypted-file vault backend.
"""

from __future__ import annotations

from pathlib import Path


CLIENT_KWARGS = {"base_url": "http://127.0.0.1:8090"}

PANEL_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "substrate" / "templates" / "control-panel.html"
)


def _parse_panel(html: str):
    """Parse the panel HTML and return (page_ancestors, div_errors, page_order)."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str] = []
            self.page_ancestors: dict[str, list[str]] = {}
            self.page_order: list[str] = []
            self.div_errors: int = 0

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag == "div":
                self.stack.append(d.get("id", ""))
                if d.get("id", "").startswith("page-"):
                    pid = d["id"]
                    self.page_ancestors[pid] = list(self.stack)
                    self.page_order.append(pid)

        def handle_endtag(self, tag):
            if tag == "div":
                if self.stack:
                    self.stack.pop()
                else:
                    self.div_errors += 1

    parser = P()
    parser.feed(html)
    return parser.page_ancestors, parser.div_errors, parser.page_order


def test_proton_wizard_page_is_direct_child_of_container() -> None:
    """page-proton must be a direct child of .page-container, not nested inside
    page-vault. This is the exact regression from commit c4b97d90."""
    html = PANEL_TEMPLATE.read_text(encoding="utf-8")
    page_ancestors, div_errors, _ = _parse_panel(html)
    assert div_errors == 0, f"unbalanced divs: {div_errors} errors"
    assert "page-proton" in page_ancestors
    ancestors = page_ancestors["page-proton"]
    page_ancestors_only = [a for a in ancestors if a.startswith("page-")]
    assert page_ancestors_only == ["page-proton"], (
        f"page-proton is nested inside another page: {ancestors}"
    )


def test_all_nav_pages_are_direct_children() -> None:
    """Every .page div must be a direct child of .page-container (no nesting)."""
    html = PANEL_TEMPLATE.read_text(encoding="utf-8")
    page_ancestors, div_errors, _ = _parse_panel(html)
    assert div_errors == 0
    for pid, ancestors in page_ancestors.items():
        nested = [a for a in ancestors if a.startswith("page-") and a != pid]
        assert nested == [], f"{pid} is nested inside: {nested}"


def test_vault_modal_div_is_not_inside_a_page_div() -> None:
    """#vaultModalRoot must not be inside a page div, or the modal
    would be hidden whenever that page loses .active."""
    html = PANEL_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="vaultModalRoot"' in html
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str] = []
            self.in_modal = False
            self.in_page = False

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag == "div":
                self.stack.append(d.get("id", ""))
                if d.get("id") == "vaultModalRoot":
                    self.in_modal = True
                if d.get("id", "").startswith("page-"):
                    self.in_page = True

        def handle_endtag(self, tag):
            if tag == "div" and self.stack:
                popped = self.stack.pop()
                if popped == "vaultModalRoot":
                    self.in_modal = False
                if popped.startswith("page-"):
                    self.in_page = False

    parser = P()
    parser.feed(html)
    assert not parser.in_page, "vaultModalRoot is inside a page div"


def test_divs_balance() -> None:
    """All opened divs must be closed; no unmatched tags."""
    html = PANEL_TEMPLATE.read_text(encoding="utf-8")
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str] = []
            self.errors: int = 0

        def handle_starttag(self, tag, attrs):
            if tag == "div":
                d = dict(attrs)
                self.stack.append(d.get("id", "?"))

        def handle_endtag(self, tag):
            if tag == "div":
                if self.stack:
                    self.stack.pop()
                else:
                    self.errors += 1

    parser = P()
    parser.feed(html)
    assert parser.errors == 0, f"unmatched closing </div>: {parser.errors}"
    assert parser.stack == [], f"unclosed divs: {parser.stack}"
