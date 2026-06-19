"""Templated why_strings (per item) + reason_strings (per carousel). Deterministic, NO LLM.

The why_string comes from the DOMINANT signal that ranked the item (from the scorer's breakdown),
specialised by the source pool; for cold-start there is no personal reason so phrasings are global
("Trending now", "New movies", "Popular podcasts"). Every item gets a non-empty why_string and every
carousel a reason_string. Inputs are plain values the assembler precomputes — this module has no data
dependencies.
"""

from __future__ import annotations

from typing import Optional

from ..feed.feed_models import ReasonType

VERTICAL_LABEL = {"game": "games", "movie": "movies", "tv": "TV shows", "podcast": "podcasts"}


def _vlabel(vertical: Optional[str]) -> str:
    return VERTICAL_LABEL.get((vertical or "").lower(), (vertical or "content"))


def why_string(source_pool: str, dominant: str, mode: str, vertical: Optional[str], *,
               genre: Optional[str] = None, platform_name: Optional[str] = None,
               repr_followed_name: Optional[str] = None) -> str:
    """Per-item reason from (source_pool, dominant signal, personalization mode)."""
    personalized = mode == "personalized"

    if source_pool == "similar_to_followed" and personalized:
        return f"Because you follow {repr_followed_name}" if repr_followed_name else "More like what you follow"
    if source_pool == "popular_with_fans_of" and personalized:
        if repr_followed_name:
            return f"Popular with fans of {repr_followed_name}"
        return f"Popular with people who enjoy {genre}" if genre else "Popular with people who like what you do"
    if source_pool == "new_in_genre":
        return f"New in {genre}" if genre else f"New {_vlabel(vertical)}"
    if source_pool == "new_on_platform":
        return f"New on {platform_name}" if platform_name else f"New {_vlabel(vertical)}"
    if source_pool == "trending_global":
        return f"Trending in {genre}" if genre else "Trending now"
    if source_pool == "fresh_moments":
        return f"New {_vlabel(vertical)}" if dominant in ("recency", "semantic") else f"Popular {_vlabel(vertical)}"

    # fallback by dominant signal
    if dominant == "recency":
        return f"New {_vlabel(vertical)}"
    if dominant == "popularity":
        return f"Popular {_vlabel(vertical)}"
    if dominant == "velocity":
        return "Gaining attention"
    if dominant == "semantic" and personalized:
        return f"Because you follow {repr_followed_name}" if repr_followed_name else "Recommended for you"
    return f"Trending {_vlabel(vertical)}"


def reason_string(reason_type: ReasonType, *, genre: Optional[str] = None,
                  platform_name: Optional[str] = None, vertical: Optional[str] = None,
                  repr_followed_name: Optional[str] = None) -> str:
    """Per-carousel reason from its type + scope."""
    rt = reason_type
    if rt == ReasonType.trending:
        return f"Trending in {genre}" if genre else "Trending now"
    if rt == ReasonType.similar_to_followed:
        return f"Because you follow {repr_followed_name}" if repr_followed_name else "More like what you follow"
    if rt == ReasonType.popular_with_fans_of:
        if repr_followed_name:
            return f"Popular with fans of {repr_followed_name}"
        return f"Popular with people who enjoy {genre}" if genre else "Popular with people who like what you do"
    if rt == ReasonType.new_in_genre:
        return f"New in {genre}" if genre else "New releases"
    if rt == ReasonType.new_on_platform:
        return f"New on {platform_name}" if platform_name else "New on your platforms"
    if rt == ReasonType.new_in_vertical:
        return f"New {_vlabel(vertical)}"
    if rt == ReasonType.happening_today:
        return "Happening today"
    return "Recommended for you"
