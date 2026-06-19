"""TrendingGlobal — the GLOBAL trending pool (user-agnostic), the cold-start backbone.

This is a RECOMPUTED-AND-CACHED artifact: the global ranked list is computed ONCE per refresh cadence
(config.GLOBAL_REFRESH_SECONDS) and served to all cold-start users — NOT per request. `generate()` then
just filters the user's (tiny) exclusions off the cached list.

Pool ORDER (global, user-agnostic — distinct from the P4 per-user feed scorer): normalized per-vertical
influence + global reaction/follow VELOCITY (recent counts across ALL users) + recency. Velocity is
CONFIDENCE-WEIGHTED by how much global signal exists — on dev there are only ~31 reactions / ~80 resolved
follows, so velocity is heavily down-weighted and the order leans on influence + recency (expected).
The raw signals are attached for P4 to re-blend per user.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .base import Candidate, CandidateProvider, RequestContext, excluded_entity_ids
from .. import config
from .. import timeutil
from ..feed.profile import UserProfile


class TrendingGlobal(CandidateProvider):
    name = "trending_global"

    def __init__(self, data_source, substrate=None, popularity=None):
        super().__init__(data_source, substrate, popularity)
        self._cache_window: Optional[int] = None
        self._cache_rows: Optional[List[Tuple]] = None
        self.compute_count = 0          # observability: proves the heavy compute runs once per window

    # ── the cache wrapper (keyed by refresh-cadence window) ─────────────
    def _window_key(self, now) -> int:
        return int(now.timestamp() // max(1, config.GLOBAL_REFRESH_SECONDS))

    def global_trending(self, now) -> List[Tuple]:
        """Cached global ranked list. Recomputed only when the cadence window rolls over."""
        wk = self._window_key(now)
        if wk == self._cache_window and self._cache_rows is not None:
            return self._cache_rows
        self._cache_rows = self._compute(now)
        self._cache_window = wk
        self.compute_count += 1
        return self._cache_rows

    def _compute(self, now) -> List[Tuple]:
        if self.popularity is None:
            return []
        # global velocity (reaction + follow counts) within the recent window, across ALL users
        rcounts = self.ds.get_global_reaction_counts(config.VELOCITY_WINDOW_DAYS, now)
        fcounts = self.ds.get_global_follow_counts(config.VELOCITY_WINDOW_DAYS, now)
        vel_raw: dict = {}
        for eid, c in rcounts.items():
            vel_raw[eid] = vel_raw.get(eid, 0) + c
        for eid, c in fcounts.items():
            vel_raw[eid] = vel_raw.get(eid, 0) + c
        total_events = sum(vel_raw.values())
        confidence = (min(1.0, total_events / config.VELOCITY_CONFIDENCE_FULL)
                      if config.VELOCITY_CONFIDENCE_FULL else 0.0)
        max_vel = max(vel_raw.values()) if vel_raw else 0

        rows: List[Tuple] = []
        for eid in self.ds.all_entity_ids():
            inf = self.popularity.normalized_influence(eid)
            if inf is None:
                continue
            v = vel_raw.get(eid, 0)
            vel_norm = (v / max_vel) if max_vel else 0.0
            ms = self.ds.get_moments_for_property(eid)           # sorted newest-first
            rec = timeutil.recency_score(ms[0].event_starts_at, now) if ms else 0.0
            score = (config.TRENDING_W_INFLUENCE * inf
                     + config.TRENDING_W_VELOCITY * confidence * vel_norm
                     + config.TRENDING_W_RECENCY * rec)
            ent = self.ds.get_entity(eid)
            rows.append((score, eid, ent.vertical if ent else None, {
                "influence_norm": round(inf, 4), "velocity": v, "velocity_norm": round(vel_norm, 4),
                "velocity_confidence": round(confidence, 4), "recency": round(rec, 4),
                "trending_score": round(score, 4)}))
        rows.sort(key=lambda r: r[0], reverse=True)
        return rows[:config.TRENDING_POOL_SIZE]

    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        rows = self.global_trending(context.now)
        excl = excluded_entity_ids(profile, context, self.ds)
        out: List[Candidate] = []
        for _score, eid, vert, sig in rows:
            if eid in excl:
                continue
            if context.vertical and vert != context.vertical:
                continue
            out.append(Candidate(source_pool=self.name, entity_id=eid, vertical=vert,
                                 property_id=self.ds.entity_id_to_property_id(eid),
                                 raw_signals=dict(sig)))
            if len(out) >= context.limit:
                break
        return out
