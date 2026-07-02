"""The config-driven blend — taste + recency + proximity + trending(stub) + richness(stub).

Mirrors E2's scorer SHAPE (a weights dataclass + a per-candidate ScoreBreakdown + a normalized weighted
blend) but over E3's moment-level signal set; E2's property-centric score_candidate doesn't drop in, so
this is the E3 blend with the same algebra. Every signal is in [0,1]; the blend is a weight-normalized
sum so the absolute score is interpretable and weights retune freely (config).

STUBS (in the formula at low weight, ready to activate — never fabricated):
  trending: neutral constant. Real source = moment_features_v1 (pending Michelle).
  richness: reads moment_type_id but returns a FLAT neutral until the moment_type taxonomy lands
            (Michelle's mapping). Both are constant across candidates → present but no ordering effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from . import config
from .candidate import CandidateMoment
from .recency import proximity_score, recency_score
from .taste import TasteContext, taste_score
from .vectors import VectorStore


@dataclass(frozen=True, slots=True)
class HomeWeights:
    taste: float
    recency: float
    proximity: float
    trending: float
    richness: float
    dwell: float = 0.0
    centrality: float = 0.0
    popularity: float = 0.0

    @staticmethod
    def from_config() -> "HomeWeights":
        return HomeWeights(taste=config.HOME_W_TASTE, recency=config.HOME_W_RECENCY,
                           proximity=config.HOME_W_PROXIMITY, trending=config.HOME_W_TRENDING,
                           richness=config.HOME_W_RICHNESS, dwell=config.HOME_W_DWELL,
                           centrality=config.HOME_W_CENTRALITY, popularity=config.HOME_W_POPULARITY)


@dataclass(slots=True)
class ScoreBreakdown:
    taste: float
    taste_cosine: float
    taste_overlap: float
    recency: float
    proximity: float
    trending: float          # STUB (neutral)
    richness: float          # STUB (neutral)
    blended: float
    sort_mode: str


def trending_stub(candidate: CandidateMoment) -> float:
    """STUB — neutral constant. Real source: moment_features_v1 engagement (pending Michelle)."""
    return config.HOME_TRENDING_STUB


def richness_stub(candidate: CandidateMoment) -> float:
    """STUB — reads moment_type_id but weights it FLAT until the taxonomy is confirmed (Michelle's
    moment_type mapping). Returns a neutral constant so it sits in the blend without ordering effect."""
    _ = candidate.moment_type_id            # read but intentionally not yet interpreted
    return config.HOME_RICHNESS_STUB


def score_candidate(candidate: CandidateMoment, ctx: TasteContext, vectors: VectorStore, now: datetime,
                    weights: HomeWeights, sort_mode: str = "relevance") -> ScoreBreakdown:
    taste, cos, overlap = taste_score(candidate, ctx, vectors)
    rec = recency_score(candidate.event_starts_at, now)
    prox = proximity_score(candidate.event_starts_at, now)
    trend = trending_stub(candidate)
    rich = richness_stub(candidate)

    if sort_mode == "recent":
        blended = rec                       # near-pure recency (still over the gated+suppressed pool)
    else:
        pairs = [(weights.taste, taste), (weights.recency, rec), (weights.proximity, prox),
                 (weights.trending, trend), (weights.richness, rich)]
        wsum = sum(w for w, _ in pairs)
        blended = sum(w * s for w, s in pairs) / wsum if wsum > 0 else 0.0
    return ScoreBreakdown(taste=taste, taste_cosine=cos, taste_overlap=overlap, recency=rec,
                          proximity=prox, trending=trend, richness=rich, blended=blended, sort_mode=sort_mode)
