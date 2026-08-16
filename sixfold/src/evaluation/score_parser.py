#!/usr/bin/env python3
"""Critique sheet: score all panels 0-10 on 8 criteria, weighted.

Criteria: simplicity(×3), elemental readability(×2), continuity(×1.5),
negative-space balance(×1.5), family resemblance(×2.5), originality(×2.5),
micro-narrative integration(×1.5), thumbnail readability(×1).
Output JSON lines for machine comparison across critics.
"""
import json, sys
from pathlib import Path

CRITERIA = [
    ("simplicity", 3.0),
    ("elemental_readability", 2.0),
    ("continuity", 1.5),
    ("negative_space", 1.5),
    ("family_resemblance", 2.5),
    ("originality", 2.5),
    ("micro_narrative", 1.5),
    ("thumbnail_readability", 1.0),
]

def parse_scores(text):
    """Parse 'criterion: N/10' patterns from critic text."""
    import re
    scores = {}
    for name, _ in CRITERIA:
        m = re.search(rf"{name.replace('_', ' ')}\s*:?\s*(\d+(?:\.\d+)?)\s*/?\s*10?", text, re.I)
        if m:
            scores[name] = float(m.group(1))
    return scores

if __name__ == "__main__":
    text = sys.stdin.read()
    print(json.dumps(parse_scores(text), indent=2))
