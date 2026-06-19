"""The blended SCORER — turns each candidate's RAW signals into one final ordering.

    final = (1 - pw)·GLOBAL  +  pw·PERSONAL  −  w_suppression·suppression

  GLOBAL   = normalized( w_popularity·influence + w_recency·recency + w_velocity·velocity_cw )
  PERSONAL = w_semantic·semantic_affinity                                   (the user's taste)
  pw       = PERSONAL_WEIGHT_MAX · signal_strength      (cold-start → 0 → 100% GLOBAL)

Key behaviours (config-driven, deterministic, no LLM, no re-embed):
  - cold-start (signal_strength 0): pw=0 → the feed is 100% global (popularity + recency).
  - personalized (12305, signal_strength 1): pw=PERSONAL_WEIGHT_MAX → semantic affinity blends in.
  - velocity is CONFIDENCE-WEIGHTED by global volume (≈0 on dev) so it never dominates here.
  - in the clipped-influence band (many ties at 0.975) recency (and, when personal, semantic) breaks
    the ties → the trending/main feed is NOT a flat tie.
  - suppression reads dormant negatives (not_interested/done/blocked) through the profile — empty now.

`semantic_affinity` reuses the substrate scores the PROVIDERS ALREADY ATTACHED (vector neighbours /
graph_similar / co-follow) — the scorer makes NO substrate calls and re-embeds nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from .. import config
from .. import timeutil
from ..candidates.base import Candidate
from ..feed.profile import UserProfile


@dataclass(frozen=True)
class ScoringWeights:
    """The per-request blend weights. Defaults mirror config; the sort_order presets override the three
    GLOBAL weights. Passed into ScoringContext so weighting is per-build state — NO global mutation, NO
    lock. (P5.1: replaces the old config-monkeypatch+lock with no change to the blend math.)"""
    w_popularity: float
    w_recency: float
    w_velocity: float
    w_semantic: float
    w_suppression: float
    personal_weight_max: float

    @classmethod
    def from_config(cls) -> "ScoringWeights":
        return cls(config.W_POPULARITY, config.W_RECENCY, config.W_VELOCITY,
                   config.W_SEMANTIC, config.W_SUPPRESSION, config.PERSONAL_WEIGHT_MAX)

    def with_overrides(self, **kw) -> "ScoringWeights":
        return replace(self, **kw)


@dataclass
class ScoreBreakdown:
    semantic: float
    recency: float
    influence: float
    velocity: float
    suppression: float
    global_blend: float
    personal_blend: float
    personal_weight: float
    final: float
    dominant: str          # the signal that contributed most → drives the why_string

    def to_dict(self) -> dict:
        return {"semantic": round(self.semantic, 4), "recency": round(self.recency, 4),
                "influence": round(self.influence, 4), "velocity": round(self.velocity, 6),
                "suppression": round(self.suppression, 4), "global_blend": round(self.global_blend, 4),
                "personal_blend": round(self.personal_blend, 4), "personal_weight": round(self.personal_weight, 4),
                "final": round(self.final, 4), "dominant": self.dominant}


def personal_weight(signal_strength: float, max_weight: Optional[float] = None) -> float:
    """pw = personal_weight_max · clamp(signal_strength). 0 at cold-start, max at full signal.
    max_weight defaults to config.PERSONAL_WEIGHT_MAX (back-compat); the scorer passes the request's."""
    m = config.PERSONAL_WEIGHT_MAX if max_weight is None else max_weight
    return m * max(0.0, min(1.0, signal_strength or 0.0))


class ScoringContext:
    """Per-request scoring helpers built ONCE per feed: the confidence-weighted global velocity index,
    a recency resolver (uses a moment's recency, or a property's freshest moment), and popularity."""

    def __init__(self, data_source, popularity, context, weights: Optional[ScoringWeights] = None):
        self.ds = data_source
        self.pop = popularity
        self.now = context.now
        self.weights = weights or ScoringWeights.from_config()   # per-request blend weights (no globals)
        # GLOBAL velocity = recent reaction + follow counts across ALL users, confidence-weighted by volume
        rc = data_source.get_global_reaction_counts(config.VELOCITY_WINDOW_DAYS, self.now)
        fc = data_source.get_global_follow_counts(config.VELOCITY_WINDOW_DAYS, self.now)
        vel: Dict[str, int] = {}
        for eid, c in rc.items():
            vel[eid] = vel.get(eid, 0) + c
        for eid, c in fc.items():
            vel[eid] = vel.get(eid, 0) + c
        self._vel = vel
        total_events = sum(vel.values())
        self.velocity_confidence = (min(1.0, total_events / config.VELOCITY_CONFIDENCE_FULL)
                                    if config.VELOCITY_CONFIDENCE_FULL else 0.0)
        self._vel_max = max(vel.values()) if vel else 0
        self._rec_cache: Dict[str, float] = {}

    def influence(self, entity_id: Optional[str]) -> float:
        v = self.pop.normalized_influence(entity_id) if entity_id else None
        return float(v) if v is not None else 0.0

    def velocity_cw(self, entity_id: Optional[str]) -> float:
        """Confidence-weighted, vertical-agnostic global velocity in [0,1] (≈0 on dev)."""
        if not entity_id or self._vel_max == 0:
            return 0.0
        return self.velocity_confidence * (self._vel.get(entity_id, 0) / self._vel_max)

    def recency(self, cand: Candidate) -> float:
        if cand.raw_signals.get("recency") is not None:
            return float(cand.raw_signals["recency"])           # moment candidate carries it
        eid = cand.entity_id                                    # property candidate → freshest moment
        if eid in self._rec_cache:
            return self._rec_cache[eid]
        ms = self.ds.get_moments_for_property(eid) if eid else []
        r = timeutil.recency_score(ms[0].event_starts_at, self.now) if ms else 0.0
        self._rec_cache[eid] = r
        return r

    def semantic(self, cand: Candidate) -> float:
        """The PERSONAL affinity the provider attached: vector-neighbour cosine / graph_similar / a
        co-follow proxy. 0 for global pools (FreshMoments/TrendingGlobal/NewIn*) → no personal signal."""
        s = cand.raw_signals.get("semantic")
        if s is None:
            s = cand.raw_signals.get("graph_similar")
        if s is None:
            cf = cand.raw_signals.get("co_follow_count")
            return min(1.0, cf / config.COFOLLOW_FULL) if cf else 0.0
        try:
            return max(0.0, min(1.0, float(s)))
        except (TypeError, ValueError):
            return 0.0

    def suppression(self, cand: Candidate, profile: UserProfile) -> float:
        """Dormant negatives (not_interested / done / blocked). Empty today → always 0; wired for later."""
        eid = cand.entity_id
        if eid and (eid in profile.not_interested_entity_ids or eid in profile.done_entity_ids
                    or eid in profile.blocked_entity_ids):
            return 1.0
        return 0.0


def score_candidate(cand: Candidate, profile: UserProfile, sctx: ScoringContext) -> ScoreBreakdown:
    sem = sctx.semantic(cand)
    rec = sctx.recency(cand)
    inf = sctx.influence(cand.entity_id)
    vel = sctx.velocity_cw(cand.entity_id)
    supp = sctx.suppression(cand, profile)

    w = sctx.weights
    wg = w.w_popularity + w.w_recency + w.w_velocity
    global_blend = ((w.w_popularity * inf + w.w_recency * rec + w.w_velocity * vel) / wg
                    if wg else 0.0)
    personal_blend = w.w_semantic * sem
    pw = personal_weight(profile.signal_strength, w.personal_weight_max)
    final = (1 - pw) * global_blend + pw * personal_blend - w.w_suppression * supp

    # which signal contributed most (for the why_string) — weighted by how it enters `final`
    contribs = {
        "semantic": pw * w.w_semantic * sem,
        "recency": (1 - pw) * w.w_recency * rec / wg if wg else 0.0,
        "popularity": (1 - pw) * w.w_popularity * inf / wg if wg else 0.0,
        "velocity": (1 - pw) * w.w_velocity * vel / wg if wg else 0.0,
    }
    dominant = max(contribs, key=contribs.get) if any(v > 0 for v in contribs.values()) else "popularity"
    return ScoreBreakdown(sem, rec, inf, vel, supp, global_blend, personal_blend, pw, final, dominant)


def score_candidates(cands: List[Candidate], profile: UserProfile, context, data_source, popularity,
                     sctx: Optional[ScoringContext] = None) -> List[Tuple[Candidate, ScoreBreakdown]]:
    """Score + rank candidates (desc by final). Reuse one ScoringContext across pools when given."""
    sctx = sctx or ScoringContext(data_source, popularity, context)
    scored = [(c, score_candidate(c, profile, sctx)) for c in cands]
    scored.sort(key=lambda cb: cb[1].final, reverse=True)
    return scored
