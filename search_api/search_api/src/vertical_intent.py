"""Vertical-word intent — detect a vertical keyword in the query, strip it from the embed text, and name
the vertical(s) to soft-boost.

Case-insensitive, word-boundary matched; the LONGEST keyword strips first so "tv show" is consumed before
"tv"/"show". Multiple vertical words → all named verticals returned. The embed text is never empty — if the
query was only vertical words ("movies"), it falls back to the raw query so the embedder still has signal.
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple

from . import config

_ORDERED: List[Tuple[str, str]] = []


def _ordered_keywords() -> List[Tuple[str, str]]:
    global _ORDERED
    if not _ORDERED:
        pairs = [(kw, vert) for vert, kws in config.VERTICAL_KEYWORDS.items() for kw in kws]
        pairs.sort(key=lambda p: -len(p[0]))          # longest first (phrases before single words)
        _ORDERED = pairs
    return _ORDERED


def detect_verticals(query: str) -> Tuple[Set[str], str]:
    """Return (detected_verticals, embed_text) where embed_text is the query minus the vertical word(s)."""
    q = query or ""
    stripped = q
    detected: Set[str] = set()
    for kw, vert in _ordered_keywords():
        pat = r"\b" + re.escape(kw) + r"\b"
        if re.search(pat, stripped, flags=re.IGNORECASE):
            detected.add(vert)
            stripped = re.sub(pat, " ", stripped, flags=re.IGNORECASE)
    stripped = " ".join(stripped.split()).strip()
    embed_text = stripped if stripped else q          # never embed empty → fall back to the raw query
    return detected, embed_text
