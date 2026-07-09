"""Discovery v2 — retrieval ORCHESTRATOR (V2-P3 entrypoint).

retrieve_candidate_sets(profile, ...) -> CandidateBundle: content (Source 2) + exploration (Source 3),
allocated by percentage, with HARD exclusions applied everywhere. Produces candidate SETS only — moment
selection + feed assembly + the blend controller are V2-P4.

HARD never-return set = the user's ENGAGED entities (follows ∪ reactions — a superset of followed, so
"never recommend what they follow" is guaranteed) ∪ the request's excluded property_ids. (seen_ids are
moment-level; they apply at V2-P4 moment selection, not at the property-candidate stage.)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set

from .. import config, timeutil
from ..data_access.base import DataSource
from ..data_access.substrate_client import SubstrateClient
from .candidates import AllocationPlan, Candidate, CandidateBundle
from .collaborative_candidates import build_collaborative_candidates
from .content import allocate, build_content_candidates
from .exploration import build_exploration
from .trending_candidates import build_trending_candidates


def _norm(score: float, mx: float) -> float:
    return max(0.0, min(1.0, score / mx)) if mx else 0.0


def _merge_trending_into_clusters(clusters, trend_per_cluster: Dict[int, List[Candidate]],
                                  trend_confidence: float) -> None:
    """Merge trending candidates into each cluster's pool (dedupe across paths; a property found by BOTH keeps
    the stronger provenance). Re-rank the merged pool by combined taste + adaptive-trending so a genuinely
    trending property COMPETES for the cluster's slots — even if the taste path never selected it."""
    w_trend_eff = config.V2_W_TRENDING * max(0.0, min(1.0, trend_confidence))
    by_cid = {cs.cluster_id: cs for cs in clusters}
    for cid, tcands in trend_per_cluster.items():
        cs = by_cid.get(cid)
        if cs is None:
            continue
        existing = {c.entity_id: c for c in cs.candidates}
        for tc in tcands:
            ex = existing.get(tc.entity_id)
            if ex is not None:                      # found by BOTH paths → one candidate, stronger provenance
                ex.trending_velocity = max(ex.trending_velocity, tc.trending_velocity)
                ex.best_trending_moment_id = ex.best_trending_moment_id or tc.best_trending_moment_id
                if "trending" not in ex.paths:
                    ex.paths.append("trending")
                if ex.source_pool == "content":
                    ex.source_pool = "both"
            else:                                   # trending-only property the taste path never selected
                cs.candidates.append(tc)
                existing[tc.entity_id] = tc
        mx = max((c.score for c in cs.candidates if c.source_pool in ("content", "both")), default=1.0) or 1.0
        # combined slot-rank = taste · (1 + adaptive-trending) → trending LIFTS on-taste candidates (gated by
        # taste), so a trending property the taste path missed competes for slots WITHOUT flooding off-taste.
        cs.candidates.sort(key=lambda c: -(_norm(c.score, mx) * (1.0 + w_trend_eff * c.trending_velocity)))


def _empty_allocation() -> AllocationPlan:
    return AllocationPlan(total_budget=config.V2_CANDIDATE_BUDGET, content_slots=0, exploration_slots=0,
                          exploration_fraction=0.0, by_vertical={v: 0 for v in config.VERTICALS},
                          by_cluster={}, global_backfill={}, alloc_mode=config.V2_ALLOC_MODE)


def build_exclusions(profile, data_source: DataSource,
                     excluded_property_ids: Iterable = ()) -> Set[str]:
    """The hard never-return set: engaged (followed ∪ reacted) entities + the request's excluded properties.
    Each excluded ref is an entity_id | composite | bare source_id, normalised via resolve_inbound_id."""
    excl: Set[str] = {e.target_entity_id for e in profile.engagements}
    for ref in (excluded_property_ids or []):
        eid = data_source.resolve_inbound_id(ref)
        if eid:
            excl.add(eid)
    return excl


def retrieve_candidate_sets(profile, *, data_source: DataSource, client: Optional[SubstrateClient] = None,
                            now: Optional[datetime] = None, trending=None, collaborative=None,
                            seen_ids: Iterable[int] = (),
                            excluded_property_ids: Iterable[int] = ()) -> CandidateBundle:
    """Build the candidate bundle for a taste profile. Cold-start / no-clusters → fallback_to_global.
    `trending` (a TrendingTable) + `now` enable the V2-P8 trending candidate source; `collaborative`
    (a CollaborativeIndex) enables the V2-P9 collaborative (similar-user, bubble-escape) candidate source."""
    client = client or SubstrateClient()
    now = now or timeutil.now()
    t_start = time.time()
    exclude_ids = build_exclusions(profile, data_source, excluded_property_ids)

    # Cold-start / no taste signal → the global feed carries it (V2-P4); no personalized retrieval.
    if profile.mode == "cold_start" or not profile.clusters:
        return CandidateBundle(
            user_id=profile.user_id, mode=profile.mode, signal_strength=profile.signal_strength,
            fallback_to_global=True, allocation=_empty_allocation(), clusters=[], exploration=[],
            excluded_entity_count=len(exclude_ids), n_retrieve_calls=0, n_substrate_calls=0,
            timing_ms={"total": round((time.time() - t_start) * 1000, 1)})

    # ── Source 2: content-based (taste) retrieval (parallel per cluster) ──
    t0 = time.time()
    clusters, n_ret, n_sub = build_content_candidates(profile, client, exclude_ids)
    t_content = (time.time() - t0) * 1000

    # ── Source 2b (V2-P8): TRENDING candidate source — global trending scoped to taste, merged in ──
    t_tr = time.time()
    trend_per_cluster, trend_conf, trend_mom_vel, trend_flat = build_trending_candidates(
        profile, trending, data_source, now, exclude_ids)
    _merge_trending_into_clusters(clusters, trend_per_cluster, trend_conf)
    t_trending = (time.time() - t_tr) * 1000

    allocation = allocate(profile, clusters)
    content_ids = {c.entity_id for cs in clusters for c in cs.candidates}

    # ── Source 4 (V2-P9): COLLABORATIVE — similar-user discoveries (incl. CROSS-ATTRIBUTE), deduped vs
    # content/trending. collab_score covers ALL endorsed entities (so an on-taste content item similar users
    # ALSO love gets a collaborative lift); bundle.collaborative holds only the NEW discoveries (the escape). ──
    t_co = time.time()
    _co_per_cluster, collab_flat, collab_conf, collab_score, neighborhood = build_collaborative_candidates(
        profile, collaborative, data_source, now, exclude_ids)
    collab_new = [c for c in collab_flat if c.entity_id not in content_ids]   # dedupe: keep only NEW discoveries
    collab_new_ids = {c.entity_id for c in collab_new}
    t_collab = (time.time() - t_co) * 1000

    # ── Source 3: exploration (excludes ALL content+trending+collaborative ids, to keep pools distinct) ──
    t1 = time.time()
    exploration, n_sub2 = build_exploration(profile, client, exclude_ids | content_ids | collab_new_ids,
                                            allocation.exploration_slots)
    t_explore = (time.time() - t1) * 1000

    return CandidateBundle(
        user_id=profile.user_id, mode=profile.mode, signal_strength=profile.signal_strength,
        fallback_to_global=False, allocation=allocation, clusters=clusters, exploration=exploration,
        excluded_entity_count=len(exclude_ids), n_retrieve_calls=n_ret, n_substrate_calls=n_sub + n_sub2,
        trending=trend_flat, trend_confidence=trend_conf, trend_moment_velocity=trend_mom_vel,
        collaborative=collab_new, collab_confidence=collab_conf, collab_score=collab_score,
        collab_neighborhood=neighborhood,
        timing_ms={"content": round(t_content, 1), "trending": round(t_trending, 1),
                   "collaborative": round(t_collab, 1), "exploration": round(t_explore, 1),
                   "total": round((time.time() - t_start) * 1000, 1)})
