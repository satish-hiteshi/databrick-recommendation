"""Discovery v2 — PROFILE CACHE (V2-P4, §E).

Caches build_taste_profile output keyed by (user_id, now) with a config TTL (profiles change slowly).
Recompute on demand or once the TTL lapses (so taste drift is tracked). The global/cold-start feed and the
trending table keep their OWN (separate) cadences. In-memory for now; swap the dict for Redis later behind
the same get()/invalidate() surface. `clock` is injectable so tests can exercise TTL expiry deterministically.
"""

from __future__ import annotations

import time
from datetime import datetime

from .. import config
from ..data_access.base import DataSource
from .taste_profile import TasteProfile, build_taste_profile


class ProfileCache:
    def __init__(self, ttl_seconds=None, clock=time.time):
        self.ttl = ttl_seconds if ttl_seconds is not None else config.V2_PROFILE_CACHE_TTL_SECONDS
        self._clock = clock
        self._c: dict = {}            # (user_id, now_iso) -> (built_wall, TasteProfile)
        self.hits = 0
        self.misses = 0

    def get(self, user_id: int, now: datetime, ds: DataSource, force: bool = False) -> TasteProfile:
        key = (user_id, now.isoformat())
        ent = self._c.get(key)
        if ent is not None and not force and (self._clock() - ent[0]) < self.ttl:
            self.hits += 1
            return ent[1]
        self.misses += 1
        prof = build_taste_profile(user_id, now, ds)
        self._c[key] = (self._clock(), prof)
        return prof

    def invalidate(self, user_id=None) -> None:
        if user_id is None:
            self._c.clear()
        else:
            self._c = {k: v for k, v in self._c.items() if k[0] != user_id}

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "size": len(self._c), "ttl_seconds": self.ttl}
