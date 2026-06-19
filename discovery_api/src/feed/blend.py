"""Discovery v2 — BLEND CONTROLLER (V2-P4, §D).

The top-level v2 feed builder: decides feed composition by signal_strength + the bundle's flags, then
orchestrates V2-P3 retrieval + V2-P4 assembly into the v1.0 DiscoveryFeed.

  - fallback_to_global (cold-start / no clusters) → the EXISTING v1 GLOBAL feed (reuse v1's pools; no rebuild).
  - global_backfill (verticals funded by % but with no dominant cluster) → filled from global/trending (assembler).
  - exploration_fraction = f(signal_strength) → already sized the exploration set in V2-P3; honored in assembly.
  - blend weights MAY shift by signal_strength (config V2_THIN_SIGNAL_TREND_BOOST; default 0 = uniform).

Holds the persistent v2 state (profile cache + trending table) and a v1 engine for the cold-start fallback.
"""

from __future__ import annotations

import time
from typing import Iterable, Optional, Tuple

from .. import config, timeutil
from ..candidates.base import RequestContext
from ..data_access.base import DataSource
from ..data_access.substrate_client import SubstrateClient
from ..ranking.collaborative import CollaborativeIndex
from ..ranking.popularity import PopularityIndex
from ..ranking.trending import TrendingTable
from ..retrieval import build_exclusions, retrieve_candidate_sets
from .assembler_v2 import assemble_feed_v2
from .bundle_cache import BundleCache
from .feed_models import DiscoveryFeed
from .profile import UserProfile
from .profile_cache import ProfileCache


class V2FeedBuilder:
    def __init__(self, ds: DataSource, substrate=None, pop=None, trending=None, profile_cache=None,
                 bundle_cache=None, v1_engine=None, collab=None):
        self.ds = ds
        self.substrate = substrate if substrate is not None else SubstrateClient()
        self.pop = pop or PopularityIndex.from_data_source(ds)
        self.trending = trending or TrendingTable(ds)
        # Source 4 (V2-P9) collaborative index. Pass collab=False to DISABLE (the A/B "collaborative OFF" arm).
        self.collab = None if collab is False else (collab or CollaborativeIndex(ds))
        self.profile_cache = profile_cache or ProfileCache()
        self.bundle_cache = bundle_cache or BundleCache()
        self._v1_engine = v1_engine

    def _v1(self):
        if self._v1_engine is None:
            from ..engine import DiscoveryEngine
            # substrate=None → personal pools empty → a pure GLOBAL feed (the cold-start fallback)
            self._v1_engine = DiscoveryEngine(self.ds, substrate=None, popularity=self.pop)
        return self._v1_engine

    def build(self, user_id: int, *, now=None, limit: int = None, offset: int = 0,
              seen_ids: Iterable[int] = (), excluded_property_ids: Iterable[int] = (),
              profile=None) -> Tuple[DiscoveryFeed, dict]:
        """Build the v2 feed. `profile` may be injected (synthetic users); else it's cache-resolved."""
        now = now or timeutil.now()
        limit = limit or config.MAIN_FEED_PAGE_SIZE
        t0 = time.time()
        profile = profile or self.profile_cache.get(user_id, now, self.ds)
        meta = {"now": now.isoformat(), "mode": profile.mode, "signal_strength": profile.signal_strength}

        # ── cold-start / no taste clusters → v1 GLOBAL feed (reuse, don't rebuild) ──
        if profile.mode == "cold_start" or not profile.clusters:
            v1ctx = RequestContext(now=now, seen_moment_ids=set(seen_ids),
                                   excluded_property_ids=set(excluded_property_ids), limit=limit, offset=offset)
            feed = self._v1().build_feed(user_id, v1ctx)
            meta.update(path="global_fallback", timing_ms=round((time.time() - t0) * 1000, 1),
                        n_retrieve_calls=0, n_substrate_calls=0)
            return feed, meta

        # ── personalized → V2-P3 retrieval (bundle-cached) + V2-P4 three-signal assembly ──
        bkey = BundleCache.key(user_id, now, excluded_property_ids)
        bundle = self.bundle_cache.get(bkey)
        cache_state = "hit"
        if bundle is None:
            cache_state = "miss"
            bundle = retrieve_candidate_sets(profile, data_source=self.ds, client=self.substrate,
                                             now=now, trending=self.trending, collaborative=self.collab,
                                             seen_ids=seen_ids, excluded_property_ids=excluded_property_ids)
            self.bundle_cache.put(bkey, bundle)
        exclude_ids = build_exclusions(profile, self.ds, excluded_property_ids)
        # v1-shaped profile carrying the FULL engaged set as "followed" → global carousels never surface engaged
        v1_profile = UserProfile(user_id=(user_id if user_id is not None else 0),
                                 followed_entity_ids=sorted({e.target_entity_id for e in profile.engagements}),
                                 signal_strength=profile.signal_strength, mode=profile.mode)
        feed = assemble_feed_v2(profile, bundle, self.ds, self.trending, now, v1_profile=v1_profile, pop=self.pop,
                                seen_ids=set(seen_ids), excluded_property_ids=set(excluded_property_ids),
                                exclude_ids=exclude_ids, limit=limit, offset=offset)
        meta.update(path="personalized", timing_ms=round((time.time() - t0) * 1000, 1),
                    bundle_cache=cache_state, trend_confidence=bundle.trend_confidence,
                    n_trending_candidates=len(bundle.trending),
                    collab_confidence=bundle.collab_confidence, n_collaborative=len(bundle.collaborative),
                    collab_neighbors=(bundle.collab_neighborhood.n_neighbors if bundle.collab_neighborhood else 0),
                    n_retrieve_calls=(0 if cache_state == "hit" else bundle.n_retrieve_calls),
                    n_substrate_calls=(0 if cache_state == "hit" else bundle.n_substrate_calls),
                    bundle_timing_ms=bundle.timing_ms, exploration_fraction=bundle.allocation.exploration_fraction,
                    global_backfill=bundle.allocation.global_backfill)
        return feed, meta
