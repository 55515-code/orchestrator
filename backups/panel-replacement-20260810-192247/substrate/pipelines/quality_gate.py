"""Quality gate for generated resources.

Deterministic, offline validation applied before anything reaches the catalog:
structure, depth, banned terms, and placeholder detection. Provider output is
never trusted blindly (PF-002 vetting).
"""

from __future__ import annotations

from typing import Any

MIN_WORDS = {
    "checklist": 250,
    "template": 300,
    "guide": 400,
    "config": 150,
}
BANNED_TERMS = (
    "guaranteed returns",
    "free money",
    "act now",
    "limited time offer",
    "winner",
    "congratulations you have been selected",
    "crypto guaranteed",
    "risk-free profit",
)
PLACEHOLDER_MARKERS = (
    "lorem ipsum",
    "todo:",
    "[insert",
    "[tbd]",
    "placeholder",
    "xxxx",
)
REQUIRED_ELEMENTS = {
    "checklist": ("- [ ]",),
    "template": ("|",),
    "guide": ("##",),
    "config": (":",),
}


class QualityGate:
    """Validate resource content against structural and safety rules."""

    def validate(
        self,
        content: str,
        *,
        resource_type: str = "checklist",
        title: str | None = None,
    ) -> dict[str, Any]:
        issues: list[str] = []
        text = content or ""
        lowered = text.lower()

        if title is not None and len(title.strip()) < 8:
            issues.append("title too short")

        word_count = len(text.split())
        minimum = MIN_WORDS.get(resource_type, 250)
        if word_count < minimum:
            issues.append(f"content too short ({word_count} < {minimum} words)")

        for marker in REQUIRED_ELEMENTS.get(resource_type, ("##",)):
            if marker not in text:
                issues.append(f"missing required element for {resource_type}: '{marker}'")

        if text.count("##") < 2:
            issues.append("expected at least two section headings")

        for term in BANNED_TERMS:
            if term in lowered:
                issues.append(f"banned term present: '{term}'")

        for marker in PLACEHOLDER_MARKERS:
            if marker in lowered:
                issues.append(f"placeholder marker present: '{marker}'")

        return {"passed": not issues, "issues": issues, "word_count": word_count}
