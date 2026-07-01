"""HomeFeedAssembler — builds the E3 response: a follow-gated main moment stream with discovery
carousels interspersed (the carousels reuse E2's discovery output for UNFOLLOWED content).

Reuses the E2 response envelope (reuse.feed_models: FeedItem / Carousel / DiscoveryFeed) verbatim so
the home feed and discovery feed share one wire shape — E3 only populates new reason_types
(e.g. 'followed_new_moment', 'trending_in_your_follows') and enforces the rule:
    main_feed  ← moments of FOLLOWED properties only (from candidates.followed_moments)
    carousels  ← UNFOLLOWED discovery content, interspersed (from E2's discovery engine)

SCAFFOLD: signature + contract only. Logic is PROMPT 2+.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional


def assemble_home_feed(user_id: str,
                       main_stream_candidates: List[object],
                       discovery_carousels: List[object],
                       *,
                       now: datetime,
                       page_size: int = 20,
                       offset: int = 0,
                       carousel_every_n: int = 5,
                       debug: bool = False) -> object:
    """Interleave follow-gated moments (main) with discovery carousels; return a reuse.feed_models
    envelope (same shape as E2's DiscoveryFeed)."""
    raise NotImplementedError("PROMPT 2+: page main stream, intersperse carousels, serialize via feed_models")
