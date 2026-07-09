"""rank_pool — turn the prompt-3 candidate pool into an ordered, capped feed (NO serialization).

    build taste context (followed → vectors + attrs)
      → score every candidate (taste + recency + proximity + trending/richness stubs)
      → sort (relevance = full blend, default | recent = near-pure recency)
      → per-property cap APPLIED HERE (best-N by score), relocated from prompt-3's raw-pool stage.

The cap now keeps each property's BEST N by blended score, not its newest N (prompt-3's interim). The
prompt-3 front half no longer caps (candidate_pool.build_candidate_pool(apply_cap=False) by default).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from . import config
from .candidate import CandidateMoment, CandidatePool
from .graph_moments import GraphMoments
from .dedup import collapse_near_duplicates
from .interleave import compute_fairness_quota, interleave
from .scorer import HomeWeights, ScoreBreakdown, score_candidate
from .taste import build_taste_context
from .vectors import VectorStore

_AWARE_MIN = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class ScoredCandidate:
    candidate: CandidateMoment
    breakdown: ScoreBreakdown
    rank: int = 0


def _event_ts(c: CandidateMoment) -> float:
    return (c.event_starts_at or _AWARE_MIN).timestamp()


def cap_per_property_by_score(scored: List[ScoredCandidate], cap: int) -> List[ScoredCandidate]:
    """Keep each property's BEST `cap` candidates by blended score (recency tie-break). cap<=0 disables.
    Preserves the incoming global order otherwise (the list is already sorted)."""
    if cap is None or cap <= 0:
        return scored
    seen: dict = {}
    out: List[ScoredCandidate] = []
    for sc in scored:                                   # scored is already globally sorted best-first
        pid = sc.candidate.entity_id                    # group per property by entity_id (collision-safe)
        if seen.get(pid, 0) >= cap:
            continue
        seen[pid] = seen.get(pid, 0) + 1
        out.append(sc)
    return out


def rank_pool(pool: CandidatePool, *, graph: GraphMoments, vectors: VectorStore, now: datetime,
              sort_mode: Optional[str] = None, weights: Optional[HomeWeights] = None,
              per_property_cap: Optional[int] = None, interleave_mode: Optional[str] = None,
              interleave_margin: Optional[float] = None) -> List[ScoredCandidate]:
    sort_mode = (sort_mode or config.HOME_SORT_MODE).lower()
    weights = weights or HomeWeights.from_config()
    cap = config.HOME_PER_PROPERTY_CAP if per_property_cap is None else per_property_cap
    imode = (interleave_mode or config.HOME_INTERLEAVE_MODE).lower()
    margin = config.HOME_INTERLEAVE_MARGIN if interleave_margin is None else interleave_margin
    if not pool.candidates:
        return []

    ctx = build_taste_context(pool.followed_property_ids, graph, vectors)
    scored = [ScoredCandidate(candidate=c, breakdown=score_candidate(c, ctx, vectors, now, weights, sort_mode))
              for c in pool.candidates]

    # global sort: blended desc, then most-recent, then moment_id (stable, deterministic)
    scored.sort(key=lambda sc: (sc.breakdown.blended, _event_ts(sc.candidate), sc.candidate.moment_id),
                reverse=True)
    # cap FIRST (bounds eligible moments/property) → then interleave (orders across properties).
    # The cap runs exactly here, once; interleave only reorders the capped list (never caps again).
    scored = cap_per_property_by_score(scored, cap)
    # E4 serve-time near-duplicate collapse — AFTER cap, BEFORE quota/interleave (so dupes don't eat quota slots).
    if config.HOME_DEDUP_ENABLED:
        scored = collapse_near_duplicates(scored, config.HOME_DEDUP_SIMILARITY)
    # E4 fairness quota: SMOOTHLY scaled by active-property count (no cliff); thin → loose (Story 4).
    quota = compute_fairness_quota(
        active_properties=len({sc.candidate.entity_id for sc in scored}),
        window=config.HOME_FAIRNESS_WINDOW, factor=config.HOME_FAIRNESS_QUOTA_FACTOR,
        min_quota=config.HOME_FAIRNESS_MIN_QUOTA, free_below_active=config.HOME_FAIRNESS_FREE_BELOW_ACTIVE)
    scored = interleave(scored, imode, margin, now=now, bands=config.HOME_FRESHNESS_BANDS_DAYS,
                        band_mode=config.HOME_FRESHNESS_BAND_MODE, quota=quota, window=config.HOME_FAIRNESS_WINDOW)
    for i, sc in enumerate(scored, 1):          # final feed position AFTER interleave
        sc.rank = i
    return scored
