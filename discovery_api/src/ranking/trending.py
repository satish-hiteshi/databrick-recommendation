"""Discovery v2 — TRENDING-VELOCITY signal (V2-P4, V2_STRATEGY §4b).

A recency-decayed engagement VELOCITY, NOT raw volume. For each moment (reactions) and each property
(reactions on its moments + follows), sum events within a recent window, each EXPONENTIALLY DECAYED by
age (short half-life — trending is "now"). An old high-volume item with no recent events scores ~0; a
currently-active one scores high — this is the "old World Cup vs current tournament" fix.

PRECOMPUTED + CACHED: the table is computed once per `now` and reused for V2_TRENDING_REFRESH_SECONDS
(the refresh cadence), NOT recomputed per request. On dev it reads the reactions/follows CSVs via the
DataSource; the LiveDataSource path will refresh from the live tables (same iter_* interface).

CONFIDENCE-GATED: the score is scaled by how much recent decayed signal exists
(min(1, total/CONFIDENCE_FULL)). On dev (~31 reactions) this is ~0 — the signal is mechanically correct
but QUIET; it grows with real volume. (Relative order between two moments is still driven by velocity, so
the recency-discrimination is visible even when the gated magnitude is small.)
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional

from .. import config
from ..data_access.base import DataSource


def _decay(age_seconds: float, halflife_seconds: float) -> float:
    if halflife_seconds <= 0:
        return 1.0 if age_seconds <= 0 else 0.0
    return math.pow(0.5, max(0.0, age_seconds) / halflife_seconds)


class TrendingTable:
    """Precomputed, cached, recency-decayed engagement velocity per moment + per property."""

    def __init__(self, data_source: DataSource, clock=time.time):
        self.ds = data_source
        self._clock = clock
        self._cache: Dict[str, dict] = {}     # now_iso -> table

    # ── build (cached per `now` + refresh cadence) ──
    def ensure(self, now: datetime) -> dict:
        refresh = max(1, config.V2_TRENDING_REFRESH_SECONDS)
        key = str(int(now.timestamp() // refresh))
        ent = self._cache.get(key)
        if ent is not None and (self._clock() - ent["built_wall"]) < config.V2_TRENDING_REFRESH_SECONDS:
            return ent
        ent = self._compute(now)
        ent["built_wall"] = self._clock()
        self._cache[key] = ent
        return ent

    def _compute(self, now: datetime) -> dict:
        hl = config.V2_TRENDING_HALFLIFE_DAYS * 86400.0
        window_s = config.V2_TRENDING_WINDOW_DAYS * 86400.0
        m_raw: Dict[int, float] = defaultdict(float)
        e_raw: Dict[str, float] = defaultdict(float)
        n_events = 0

        for ev in self.ds.iter_reaction_events():
            if ev.created_at is None:
                continue
            age = (now - ev.created_at).total_seconds()
            if age < 0 or age > window_s:
                continue
            w = config.V2_TRENDING_REACTION_WEIGHT * _decay(age, hl)
            m_raw[ev.moment_id] += w
            if ev.entity_id:
                e_raw[ev.entity_id] += w
            n_events += 1

        for fe in self.ds.iter_follow_events():
            if fe.created_at is None or not fe.entity_id:
                continue
            age = (now - fe.created_at).total_seconds()
            if age < 0 or age > window_s:
                continue
            e_raw[fe.entity_id] += config.V2_TRENDING_FOLLOW_WEIGHT * _decay(age, hl)
            n_events += 1

        total = sum(m_raw.values()) + sum(e_raw.values())
        confidence = (min(1.0, total / config.V2_TRENDING_CONFIDENCE_FULL)
                      if config.V2_TRENDING_CONFIDENCE_FULL > 0 else 0.0)
        m_max = max(m_raw.values()) if m_raw else 0.0
        e_max = max(e_raw.values()) if e_raw else 0.0
        return {
            "m_norm": {k: v / m_max for k, v in m_raw.items()} if m_max else {},
            "e_norm": {k: v / e_max for k, v in e_raw.items()} if e_max else {},
            "m_raw": dict(m_raw), "e_raw": dict(e_raw),
            "confidence": confidence, "n_events": n_events,
        }

    # ── reads (confidence-gated) ──
    def trending_score(self, moment_id: int, now: datetime) -> float:
        """Confidence-gated, normalized moment velocity in [0,1] (≈0 on thin dev data)."""
        t = self.ensure(now)
        return t["confidence"] * t["m_norm"].get(moment_id, 0.0)

    def trending_score_property(self, entity_id: str, now: datetime) -> float:
        """Confidence-gated, normalized property velocity in [0,1] (rolled up from its moments + follows)."""
        t = self.ensure(now)
        return t["confidence"] * t["e_norm"].get(entity_id, 0.0)

    def confidence(self, now: datetime) -> float:
        return self.ensure(now)["confidence"]

    # ── RAW velocities (V2-P8): engagement velocity ONLY, NO global normalisation, NO publish-date
    # assumption — so the candidate path can normalise WITHIN a user's taste niche (niche-relative trending). ──
    def raw_moment_velocity(self, moment_id: int, now: datetime) -> float:
        """Raw recency-decayed engagement velocity for a moment (independent of its publish/event date)."""
        return self.ensure(now)["m_raw"].get(moment_id, 0.0)

    def raw_property_velocity(self, entity_id: str, now: datetime) -> float:
        return self.ensure(now)["e_raw"].get(entity_id, 0.0)

    def top_moments(self, now: datetime, k: int):
        """Top-k (moment_id, raw_velocity) by raw decayed velocity — the trending-candidate scan source."""
        t = self.ensure(now)
        return sorted(t["m_raw"].items(), key=lambda kv: -kv[1])[:k]

    def debug(self, now: datetime, moment_id: Optional[int] = None,
              entity_id: Optional[str] = None) -> dict:
        t = self.ensure(now)
        return {"confidence": round(t["confidence"], 6), "n_events": t["n_events"],
                "moment_norm": round(t["m_norm"].get(moment_id, 0.0), 6) if moment_id is not None else None,
                "moment_raw": round(t["m_raw"].get(moment_id, 0.0), 6) if moment_id is not None else None,
                "property_norm": round(t["e_norm"].get(entity_id, 0.0), 6) if entity_id else None}
