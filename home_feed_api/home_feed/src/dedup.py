"""Serve-time near-duplicate collapse + the title-similarity primitive (the canonical home of the logic
the eval harness's redundancy flag also uses).

A property often emits near-identical moments (the same announcement card per episode, "Yogurt Shop S1E5"
×3). This collapses them BEFORE assembly, keeping the BEST of each near-duplicate cluster (the input is
score-desc, so the first kept is highest-scored / freshest on tie). It only ever removes redundancy within
ONE property and always keeps that property's best moment — presence is never traded (a property's only
moment is always kept). Genuinely distinct moments (different events/topics) have low title overlap and are
NOT collapsed; tune the threshold conservatively.
"""

from __future__ import annotations

import re
from typing import List

_WORD = re.compile(r"[a-z0-9]+")


def tokens(title: str) -> set:
    return set(_WORD.findall((title or "").lower()))


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_near_duplicate(title_a: str, title_b: str, threshold: float) -> bool:
    return jaccard(tokens(title_a), tokens(title_b)) >= threshold


def collapse_near_duplicates(scored: List, threshold: float) -> List:
    """Remove near-identical moments WITHIN the same property (duck-typed on .candidate.entity_id/.title).
    Input is the score-sorted list; the first member of each near-dup cluster (the best) is kept, the rest
    dropped. Across properties nothing is compared, so every property keeps ≥1 moment (presence preserved)."""
    kept_by_prop: dict = {}                     # entity_id → list of token-sets of kept titles (collision-safe)
    out: List = []
    for sc in scored:
        pid = sc.candidate.entity_id
        toks = tokens(sc.candidate.title)
        prior = kept_by_prop.setdefault(pid, [])
        if toks and any(jaccard(toks, t) >= threshold for t in prior):
            continue                            # near-dup of an already-kept moment of this property → collapse
        prior.append(toks)
        out.append(sc)
    return out
