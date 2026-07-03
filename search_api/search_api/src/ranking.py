"""Ranking — per-signal scoring + the per-(mode,vertical) weighted sum (v1.3 weights, podcast-adapted).

final_score = sum(weight_i * signal_i), signals each 0..1:
  relevance  — name: match-quality (exact 1.0 > fuzzy); thematic: cosine min-max'd over the candidate set
  centrality — entity_centrality.centrality_pct (0 for podcasts via the weight table; 0 if no row)
  popularity — property_popularity.popularity_pct
  recency    — exp-decay from recency_date, JUNK-DATE GATED (clamp <1980 / >now+3y)  [tiny weight]
  trending   — 0.0 inert (reserved)        proximity — 0.0 inert (properties-only, reserved)
The scoring_mode (name vs thematic) is taken from each result's match_type, so a merged auto/both list
scores name-hits with name weights and thematic-hits with thematic weights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from . import config


@dataclass(slots=True)
class SearchResult:
    property_id: int
    entity_id: Optional[str]
    name: str
    vertical: str
    match_type: str               # exact | fuzzy | thematic
    relevance: float              # 0..1
    genres: list = field(default_factory=list)
    cosine: Optional[float] = None
    centrality_pct: float = 0.0
    popularity_pct: float = 0.0
    signals: dict = field(default_factory=dict)
    final_score: float = 0.0
    disambiguation_confidence: float = 0.0
    tier: int = 1                 # 0 = exact-identity tier (pinned above all non-exact); 1 = fuzzy/thematic
    twin_demoted: bool = False    # a name match whose title has a much-more-popular UNBRIDGED twin → framed "Named …", never "Best match" / MLT


def recency_score(rd: Optional[date], now: datetime) -> float:
    """Exp-decay from recency_date, junk-gated like E3 (absurd <1980 / >now+3y → 0.0). Upcoming → fresh."""
    if rd is None:
        return 0.0
    if rd.year < config.RECENCY_JUNK_MIN_YEAR:
        return 0.0
    age_days = (now.date() - rd).days
    if age_days < -config.RECENCY_JUNK_MAX_FUTURE_DAYS:     # further than +3y out → junk-future
        return 0.0
    if age_days < 0:                                        # upcoming within 3y → treat as fresh
        return 1.0
    return float(0.5 ** (age_days / config.RECENCY_HALFLIFE_DAYS))


#   exact > prefix > fuzzy_typo > fuzzy/thematic. fuzzy_typo (a whole-name typo, Fix 2) is pinned ABOVE thematic
#   so a misspelled NAME ("fortnight"→Fortnite) leads over high-cosine thematic; plain fuzzy stays tied w/ thematic.
_TIER_MAP = {"exact": 0, "prefix": 1, "fuzzy_typo": 2, "fuzzy": 3, "thematic": 3}


def _scoring_mode(match_type: str) -> str:
    return "name" if match_type in ("exact", "prefix", "fuzzy_typo", "fuzzy") else "thematic"


def _finite(x: float, default: float = 0.0) -> float:
    """Coerce NaN/Inf (or a non-number) to a JSON-safe finite value. A single non-finite score makes the
    Databricks serving layer reject the whole response with a 400 (invalid JSON), so every value that can
    reach the envelope passes through this."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def score_result(r: SearchResult, store, now: datetime) -> SearchResult:
    r.tier = _TIER_MAP.get(r.match_type, 2)          # exact(0) > prefix(1) > fuzzy/thematic(2); UC4 Story 1
    w = config.weights_for(_scoring_mode(r.match_type), r.vertical)
    r.centrality_pct = _finite(store.centrality_pct(r.property_id))
    r.popularity_pct = _finite(store.popularity_pct(r.property_id))
    rec = _finite(recency_score(store.recency_date(r.property_id), now))
    r.signals = {
        "relevance": round(_finite(r.relevance), 6),
        "centrality": round(r.centrality_pct, 6),
        "popularity": round(r.popularity_pct, 6),
        "recency": round(rec, 6),
        "trending": config.TRENDING_INERT,
        "proximity": config.PROXIMITY_INERT,
    }
    r.final_score = round(_finite(sum(w[k] * r.signals[k] for k in config.SIGNALS)), 6)
    return r


def minmax_relevance(cosines: List[float]) -> List[float]:
    """Min-max normalize thematic cosines over the candidate set → relevance in [0,1] (top = 1.0).
    NaN-safe: a non-finite cosine (e.g. from a degenerate query vector) is treated as no-signal (0.0) and
    never propagates — otherwise a NaN slips past the ``hi - lo`` guard (NaN comparisons are always False)
    and poisons final_score, which the Databricks serving layer rejects with a 400."""
    if not cosines:
        return []
    finite = [c for c in cosines if math.isfinite(c)]
    if not finite:
        return [0.0 for _ in cosines]
    lo, hi = min(finite), max(finite)
    if hi - lo < 1e-9:
        return [1.0 if math.isfinite(c) else 0.0 for c in cosines]
    return [((c - lo) / (hi - lo)) if math.isfinite(c) else 0.0 for c in cosines]
