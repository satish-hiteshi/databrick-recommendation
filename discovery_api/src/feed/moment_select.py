"""Discovery v2 — MOMENT SELECTION + the THREE-SIGNAL BLEND (V2-P4, §4b).

For a candidate PROPERTY, fetch its moments and rank them by:

  final = w_taste·taste_match + w_trending·trending_velocity + w_recency·recency
          + w_collaborative·collaborative   −  w_suppression·dormant  −  seen_suppression

taste_match = the property's V2-P3 cluster/candidate score (normalized 0..1).
trending_velocity = the recency-decayed velocity from ranking/trending (moment-level, rolled up to property).
recency = soft-recency of event_starts_at vs `now`. collaborative is wired but 0 (Source 4 = V2-P5).

This is where "taste + trending, recency-correct" intersects: a STALE moment of a well-matched property
loses to a RECENT/trending one. The per-property cap stops episode-heavy properties flooding; seen moments
are demoted. Followed properties are excluded upstream (asserted here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Set

from .. import config
from .. import timeutil
from ..data_access.base import DataSource
from ..ranking.trending import TrendingTable


@dataclass
class ScoredMoment:
    moment_id: int
    entity_id: str
    vertical: str
    taste_match: float
    trending_velocity: float
    recency: float
    collaborative: float
    seen_suppression: float
    final_score: float
    cluster_id: Optional[int]
    source_pool: str

    def signals(self) -> dict:
        """The per-item debug breakdown (the three-signal view + a v1-compatible mirror for the UI)."""
        return {
            "taste_match": round(self.taste_match, 4),
            "trending_velocity": round(self.trending_velocity, 6),
            "recency": round(self.recency, 4),
            "collaborative": round(self.collaborative, 4),
            "seen_suppression": round(self.seen_suppression, 4),
            "cluster_id": self.cluster_id,
            "final_score": round(self.final_score, 4),
            # v1-compatible mirror so the existing debug UI still renders something sensible:
            "semantic": round(self.taste_match, 4), "velocity": round(self.trending_velocity, 6),
            "influence": 0.0, "suppression": round(self.seen_suppression, 4),
            "final": round(self.final_score, 4),
        }


@dataclass
class BlendWeights:
    """Per-feed blend weights (V2-P8/P9 ADAPTIVE). Taste is always primary. When trending signal exists for the
    user's taste niche (`trend_confidence`→1): w_trending rises to dominate and recency drops to a TIEBREAKER.
    When trending is thin (conf→0): w_trending→0 and recency CARRIES the feed alongside taste. When a SIMILAR-
    taste neighborhood exists (`collab_confidence`→1): w_collaborative rises so similar-user endorsements
    (incl. cross-attribute) contribute; thin neighborhood → w_collaborative→0 (no regression). So:
      trending present → taste+trending dominate, recency breaks ties;  thin → taste+recency carry;
      neighborhood present → collaborative adds bubble-escape discovery on top."""
    w_taste: float
    w_trending: float
    w_recency: float
    w_collaborative: float = 0.0

    @classmethod
    def adaptive(cls, trend_confidence: float, collab_confidence: float = 0.0) -> "BlendWeights":
        conf = max(0.0, min(1.0, trend_confidence))
        cc = max(0.0, min(1.0, collab_confidence))
        return cls(
            w_taste=config.V2_W_TASTE,
            w_trending=config.V2_W_TRENDING * conf,
            w_recency=config.V2_W_RECENCY_CARRY * (1.0 - conf) + config.V2_W_RECENCY_TIEBREAK * conf,
            w_collaborative=config.V2_W_COLLABORATIVE * cc)

    @classmethod
    def fixed(cls) -> "BlendWeights":
        """Non-adaptive fallback (legacy / v1-style): the V2-P7 fixed weights; collaborative OFF (0.0)."""
        return cls(config.V2_W_TASTE, config.V2_W_TRENDING, config.V2_W_RECENCY, 0.0)


def blend_final(taste_match: float, trending_velocity: float, recency: float,
                seen_suppression: float, age_days: Optional[float] = None,
                weights: Optional[BlendWeights] = None, collaborative: float = 0.0) -> float:
    """The four-signal blend (shared by content + trending + collaborative + global_backfill). V2-P7 soft recency
    floor demotes STALE moments (> V2_RECENCY_STALE_DAYS) by V2_STALE_FACTOR. V2-P8: `weights` is per-feed
    adaptive — trending and recency are INDEPENDENT axes. V2-P9: the collaborative term is ENDORSEMENT-gated and
    ADDITIVE (NOT taste-gated) so similar-user endorsement can surface CROSS-ATTRIBUTE content (taste_match≈0)."""
    w = weights or BlendWeights.fixed()
    stale = 1.0
    if config.V2_RECENCY_STALE_DAYS and age_days is not None and age_days > config.V2_RECENCY_STALE_DAYS:
        stale = config.V2_STALE_FACTOR
    # TRENDING-AND-on-taste: the trending term is GATED BY taste_match (trending LIFTS on-taste items, it does
    # NOT flood the feed with loosely-on-taste-but-viral content). recency ADDS independently (carry/tiebreak).
    # COLLABORATIVE is ADDITIVE and NOT taste-gated: a strongly neighborhood-endorsed item surfaces even at
    # taste_match≈0 (the bubble-escape) — but w_collaborative is confidence-scaled so a thin neighborhood can't
    # flood, and the STALE floor applies (an ancient collaborative moment is demoted like any other), so the
    # escape doesn't drag in years-old catalog moments ahead of fresh ones.
    return (stale * taste_match * (w.w_taste + w.w_trending * trending_velocity)
            + w.w_recency * recency
            + stale * w.w_collaborative * collaborative   # Source 4 (V2-P9) — endorsement-gated cross-attribute escape
            - config.V2_W_SUPPRESSION * 0.0        # dormant negatives (empty today)
            - seen_suppression)


def select_moments_for_property(ds: DataSource, trending: Optional[TrendingTable], now: datetime, *,
                                entity_id: str, taste_match: float, cluster_id: Optional[int],
                                source_pool: str, seen_ids: Set[int],
                                trending_fn=None, weights: Optional[BlendWeights] = None,
                                collaborative: float = 0.0,
                                followed: Optional[Set[str]] = None,
                                cap: Optional[int] = None) -> List[ScoredMoment]:
    """Select + blend-rank up to `cap` moments of one property. Asserts the property is not followed.
    V2-P8: `trending_fn(moment_id)->velocity` supplies the NICHE-RELATIVE trending term (preferred); falls back
    to the global trending table if not given. `weights` are the per-feed adaptive weights. V2-P9:
    `collaborative` is this property's niche-relative similar-user affinity [0,1] (property-level; ENDORSEMENT-
    gated, applied to ALL the property's moments) — additive, so a cross-attribute property still surfaces."""
    if followed is not None:
        assert entity_id not in followed, f"moment_select must never see a followed property ({entity_id})"
    cap = cap if cap is not None else config.V2_MOMENT_CAP_PER_PROPERTY
    ent = ds.get_entity(entity_id)
    vertical = ent.vertical if ent else ""
    out: List[ScoredMoment] = []
    for m in ds.get_moments_for_property(entity_id):
        rec = timeutil.recency_score(m.event_starts_at, now)        # publish freshness (independent axis)
        if trending_fn is not None:
            tv = trending_fn(m.moment_id)                            # niche-relative engagement velocity
        elif trending is not None:
            tv = max(trending.trending_score(m.moment_id, now), trending.trending_score_property(entity_id, now))
        else:
            tv = 0.0
        seen = config.V2_SEEN_SUPPRESSION if m.moment_id in seen_ids else 0.0
        age_days = (now - m.event_starts_at).total_seconds() / 86400.0 if m.event_starts_at else None
        final = blend_final(taste_match, tv, rec, seen, age_days, weights, collaborative)
        out.append(ScoredMoment(m.moment_id, entity_id, vertical, taste_match, tv, rec, collaborative, seen,
                                round(final, 6), cluster_id, source_pool))
    out.sort(key=lambda s: -s.final_score)
    return out[:cap]
