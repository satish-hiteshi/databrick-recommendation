"""DiscoveryEngine — the end-to-end orchestrator: profile → candidate pools → score → assemble.

This is the single object the P5 HTTP API will wrap (build_feed returns the v1.0 DiscoveryFeed). It is
NOT an HTTP layer. Substrate (vector/graph) is injected (None → personalized similarity pools are empty,
which is fine for cold-start). TrendingGlobal is held as ONE instance so its per-cadence cache persists
across requests/users.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from . import config
from .candidates import (FreshMoments, NewInGenre, NewOnPlatform, PopularWithFansOf,
                         RequestContext, SimilarToFollowed, TrendingGlobal)
from .data_access import get_data_source
from .feed.assembler import assemble_feed
from .feed.feed_models import DiscoveryFeed
from .feed.profile import build_profile
from .ranking import PopularityIndex
from .ranking.scorer import ScoringContext


class DiscoveryEngine:
    def __init__(self, data_source=None, substrate=None, popularity=None):
        self.ds = data_source if data_source is not None else get_data_source()
        if hasattr(self.ds, "load"):
            self.ds.load()
        self.substrate = substrate
        self.pop = popularity or PopularityIndex.from_data_source(self.ds)
        # single TrendingGlobal instance → its per-cadence cache persists across requests/users
        self._trending = TrendingGlobal(self.ds, substrate, self.pop)
        self._fresh = FreshMoments(self.ds, substrate, self.pop)
        self._similar = SimilarToFollowed(self.ds, substrate, self.pop)
        self._popular = PopularWithFansOf(self.ds, substrate, self.pop)
        self._genre = NewInGenre(self.ds, substrate, self.pop)
        self._platform = NewOnPlatform(self.ds, substrate, self.pop)

    def build_feed(self, user_id: int, context: Optional[RequestContext] = None,
                   weights=None) -> DiscoveryFeed:
        context = context or RequestContext()
        profile = build_profile(user_id, self.ds)
        sctx = ScoringContext(self.ds, self.pop, context, weights)   # weights=None → config defaults (unchanged)
        # pools generate a deep candidate set (CANDIDATE_POOL_SIZE); the user's context.limit/offset
        # page the MAIN FEED only.
        pool_ctx = replace(context, limit=config.CANDIDATE_POOL_SIZE, offset=0)
        pools = {
            "fresh_moments": self._fresh.generate(profile, pool_ctx),
            "trending_global": self._trending.generate(profile, pool_ctx),
            "similar_to_followed": self._similar.generate(profile, pool_ctx),
            "popular_with_fans_of": self._popular.generate(profile, pool_ctx),
            "new_in_genre": self._genre.generate(profile, pool_ctx),
            "new_on_platform": self._platform.generate(profile, pool_ctx),
        }
        return assemble_feed(profile, context, pools, self.ds, self.pop, sctx)
