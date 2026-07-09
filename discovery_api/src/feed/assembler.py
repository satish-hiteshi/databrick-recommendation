"""Feed assembler — produce the v1.0 DiscoveryFeed object (main feed + carousels). NOT HTTP.

MAIN FEED = ranked MOMENT items from unfollowed properties, drawn from FreshMoments + the freshest
moment of each TrendingGlobal property, scored by the blended scorer, deduped, per-property capped, and
paginated (limit/offset → next_offset). CAROUSELS come from carousels.builders. Followed / dormant-blocked
/ seen / excluded never appear (the pools exclude them; the cap stops any property dominating).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .. import config
from .. import timeutil
from ..candidates.base import Candidate, _moment_candidate, dedupe, excluded_entity_ids
from ..carousels.builders import build_carousels, representative_followed_name, top_genre
from ..ranking.scorer import ScoringContext, score_candidates
from ..why import why_string
from .feed_models import DiscoveryFeed, FeedItem, Pagination
from .profile import UserProfile


def _iso(dt):
    return dt.isoformat() if dt else None


def _build_feed_item(ds, cand: Candidate, bd, profile: UserProfile, repr_name, lk) -> FeedItem:
    m = ds.get_moment(cand.moment_id)
    ent = ds.get_entity(cand.entity_id)
    platform_name = lk.media_platform(m.media_platform_id) if (m and m.media_platform_id is not None) else None
    why = why_string(cand.source_pool, bd.dominant, profile.mode, cand.vertical,
                     genre=top_genre(ds, cand.entity_id), platform_name=platform_name,
                     repr_followed_name=repr_name)
    return FeedItem(
        moment_id=cand.moment_id, entity_id=cand.entity_id,
        property_name=(ent.name if ent else cand.entity_id), vertical=cand.vertical,
        title=(m.title if m else ""), description=(m.description if m else ""),
        event_starts_at=(_iso(m.event_starts_at) if m else None),
        media_platform_id=(m.media_platform_id if m else None),
            moment_profile_key=(m.profile_key if m else ""),
            moment_media_source_guid=(m.media_source_guid if m else ""),
        score=bd.final, why_string=why, source_pool=cand.source_pool,
        debug={"signals": bd.to_dict()})


_PERSONAL_SIGNAL_KEYS = ("semantic", "graph_similar", "co_follow_count", "via", "seed")


def _entities_to_feed_moments(ds, profile, context, pop, entity_cands: List[Candidate],
                              existing_moment_ids, max_n: int, excl) -> List[Candidate]:
    """Each top property candidate → its freshest allowed moment, PRESERVING any personal signals
    (semantic / graph_similar / co_follow) so the scorer can rank personal picks up for personalized
    users. Used for TrendingGlobal (global, no personal signal) AND the personal pools
    (SimilarToFollowed / PopularWithFansOf) — which are EMPTY for cold-start, so a cold feed stays
    exactly FreshMoments + TrendingGlobal."""
    out = []
    for cand in entity_cands[:max_n]:
        eid = cand.entity_id
        if not eid or eid in excl:
            continue
        for m in ds.get_moments_for_property(eid):
            if m.moment_id in existing_moment_ids or m.moment_id in context.seen_moment_ids:
                continue
            rec = timeutil.recency_score(m.event_starts_at, context.now)
            extra = {k: cand.raw_signals[k] for k in _PERSONAL_SIGNAL_KEYS if k in cand.raw_signals}
            out.append(_moment_candidate(ds, m, rec, cand.source_pool, pop, extra=extra))
            existing_moment_ids.add(m.moment_id)
            break                                  # freshest allowed moment only
    return out


def assemble_feed(profile: UserProfile, context, pools: Dict[str, List[Candidate]], ds, pop,
                  sctx: Optional[ScoringContext] = None) -> DiscoveryFeed:
    sctx = sctx or ScoringContext(ds, pop, context)
    repr_name = representative_followed_name(ds, profile, pop)
    lk = ds.lookups()

    # ── MAIN FEED (moments) ─────────────────────────────────────────────
    # FreshMoments + TrendingGlobal (global) + the personal pools' freshest moments. The personal pools
    # are EMPTY for cold-start, so a cold feed = FreshMoments + TrendingGlobal; for personalized users
    # their similar/popular moments carry semantic affinity and the scorer ranks them up → visibly personal.
    excl = excluded_entity_ids(profile, context, ds)
    fresh = list(pools.get("fresh_moments") or [])
    existing = {c.moment_id for c in fresh}
    extra = _entities_to_feed_moments(ds, profile, context, pop, pools.get("trending_global") or [],
                                      existing, config.TRENDING_TO_FEED, excl)
    extra += _entities_to_feed_moments(ds, profile, context, pop, pools.get("similar_to_followed") or [],
                                       existing, config.PERSONAL_TO_FEED, excl)
    extra += _entities_to_feed_moments(ds, profile, context, pop, pools.get("popular_with_fans_of") or [],
                                       existing, config.PERSONAL_TO_FEED, excl)
    main_cands = dedupe(fresh + extra)
    scored = score_candidates(main_cands, profile, context, ds, pop, sctx)

    # per-property moment cap on the SORTED list (so the freshest/best per property survive)
    capped, per_prop = [], {}
    for c, bd in scored:
        k = c.entity_id
        if k and per_prop.get(k, 0) >= config.MOMENT_CAP_PER_PROPERTY:
            continue
        per_prop[k] = per_prop.get(k, 0) + 1
        capped.append((c, bd))

    limit = context.limit or config.MAIN_FEED_PAGE_SIZE
    offset = max(0, context.offset)
    page = capped[offset:offset + limit]
    next_offset = offset + limit if offset + limit < len(capped) else None
    main_feed = [_build_feed_item(ds, c, bd, profile, repr_name, lk) for c, bd in page]

    # ── CAROUSELS ───────────────────────────────────────────────────────
    carousels = build_carousels(pools, ds, profile, context, pop, sctx, repr_name=repr_name)

    return DiscoveryFeed(
        user_id=profile.user_id, mode=profile.mode, signal_strength=profile.signal_strength,
        now=_iso(context.now), main_feed=main_feed, carousels=carousels,
        pagination=Pagination(limit=limit, offset=offset, returned=len(page),
                              next_offset=next_offset, pool_total=len(capped)))
