"""Discovery v2 — BUNDLE CACHE (V2-P6, perf).

Memoizes the V2-P3 CandidateBundle (the result of retrieve_candidate_sets — the ~6 /api/retrieve calls
that dominate v2 latency). Keyed by the request knobs that actually CHANGE retrieval:
(user_id, now, excluded_property_ids, composer). seen_ids are NOT in the key — they're moment-level and
applied post-cache in assembly, so they never change the bundle. A repeat load for the same user/now is
sub-second (assembly only). In-memory + TTL; swap the dict for Redis later behind get()/put(). `clock` is
injectable for deterministic tests.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable, Optional

from .. import config


class BundleCache:
    def __init__(self, ttl_seconds=None, clock=time.time):
        self.ttl = ttl_seconds if ttl_seconds is not None else config.V2_BUNDLE_CACHE_TTL_SECONDS
        self._clock = clock
        self._c: dict = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(user_id: int, now: datetime, excluded_property_ids: Iterable[int] = ()):
        return (user_id, now.isoformat(), tuple(sorted(excluded_property_ids or [])), config.V2_STRING_COMPOSER)

    def get(self, key):
        ent = self._c.get(key)
        if ent is not None and (self._clock() - ent[0]) < self.ttl:
            self.hits += 1
            return ent[1]
        return None

    def put(self, key, bundle) -> None:
        self.misses += 1
        self._c[key] = (self._clock(), bundle)

    def invalidate(self) -> None:
        self._c.clear()

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "size": len(self._c), "ttl_seconds": self.ttl}
