"""Discovery v2 — why_strings + reason_strings for the v2 surfaces (V2-P4). ADDITIVE: reuses the v1
VERTICAL_LABEL but adds the trending + exploration phrasings (§C) without touching why/templates.py."""

from __future__ import annotations

from typing import List, Optional

from ..why.templates import VERTICAL_LABEL


def _vlabel(v: Optional[str]) -> str:
    return VERTICAL_LABEL.get((v or "").lower(), (v or "content"))


# ── per-item ────────────────────────────────────────────────────────────────────
def moment_why(*, source_pool: str, dominant: str, vertical: Optional[str], genre: Optional[str] = None,
               repr_name: Optional[str] = None, seed: int = 0) -> str:
    """V2-P7: vary phrasing by the DOMINANT signal AND the item's own genre/seed, so a personalized feed
    isn't all "Because you follow {rep}". `seed` (the moment_id) picks deterministically among variants.
    V2-P9: collaborative items (and collaborative-DOMINANT content) convey SOCIAL PROOF, not taste/genre."""
    if source_pool == "collaborative":
        return _collab_why(genre, vertical, seed)
    if source_pool in ("content", "trending", "both"):
        if dominant == "collaborative":
            return _collab_why(genre, vertical, seed)
        if dominant == "trending":
            opts = [f"Trending in {genre}" if genre else f"Trending {_vlabel(vertical)}",
                    f"Hot right now{f' in {genre}' if genre else ''}",
                    f"Picking up steam{f' in {genre}' if genre else ''}"]
            return opts[seed % len(opts)]
        if dominant == "recency":
            opts = [f"New in {genre}" if genre else f"New {_vlabel(vertical)}",
                    f"Just dropped{f' — {genre}' if genre else ''}",
                    f"Fresh {_vlabel(vertical)} for you"]
            return opts[seed % len(opts)]
        # taste-dominant → vary across genre- and follow-based phrasings
        opts = []
        if genre:
            opts += [f"More {genre} you'll like", f"Because you're into {genre}",
                     f"Right up your alley: {genre}", f"Matches your taste in {genre}"]
        if repr_name:
            opts += [f"Because you follow {repr_name}", f"Like {repr_name}, but new to you"]
        if not opts:
            opts = [f"Recommended {_vlabel(vertical)}"]
        return opts[seed % len(opts)]
    if source_pool == "global_backfill":
        if dominant == "trending":
            return f"Trending {_vlabel(vertical)}"
        opts = [f"New {_vlabel(vertical)}", f"Fresh in {_vlabel(vertical)}", f"Worth a look · {_vlabel(vertical)}"]
        return opts[seed % len(opts)]
    return f"New {_vlabel(vertical)}"


def _collab_why(genre: Optional[str], vertical: Optional[str], seed: int) -> str:
    """SOCIAL-PROOF phrasing for a collaborative item — conveys 'people with your taste', NOT a genre match
    (the item may be CROSS-ATTRIBUTE / off-genre, that's the point). Templated, no LLM."""
    opts = ["Loved by people with taste like yours",
            "Fans of your favorites are into this",
            f"Big with people who like {genre}" if genre else "Popular with similar tastes",
            "You might not expect it, but people like you love this"]
    return opts[seed % len(opts)]


def collaborative_why(genre: Optional[str] = None, vertical: Optional[str] = None, seed: int = 0) -> str:
    return _collab_why(genre, vertical, seed)


def exploration_why(rule: Optional[str], shared: List[str], new: List[str]) -> str:
    if rule == "neighbor_new_genre" and new:
        return f"You might also like {new[0]}"
    if shared:
        return f"Branching out from {shared[0]}"
    return "Something a little different"


# ── per-carousel ──────────────────────────────────────────────────────────────────
def cluster_reason(*, genre: Optional[str] = None, repr_name: Optional[str] = None) -> str:
    if repr_name:
        return f"Because you follow {repr_name}"
    return f"More {genre} you might like" if genre else "Recommended for you"


def trending_reason(genre: Optional[str] = None) -> str:
    return f"Trending in {genre}" if genre else "Trending right now"


def trending_taste_reason(genre: Optional[str] = None) -> str:
    return f"Popular right now with fans of {genre}" if genre else "Popular right now"


def collaborative_reason(genre: Optional[str] = None) -> str:
    """Header for the collaborative carousel — social proof from the taste neighborhood (V2-P9)."""
    return f"People who like {genre} are loving these" if genre else "People with your taste are loving these"


def exploration_reason(genre: Optional[str] = None) -> str:
    return f"Branching out from {genre}" if genre else "Something a little different"
