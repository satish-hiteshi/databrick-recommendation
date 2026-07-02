"""Discovery v2 — FEED ASSEMBLER (V2-P4, §C).

Turns a V2-P3 CandidateBundle + the trending table into the EXISTING v1.0 DiscoveryFeed object (same shape
v1/P5 produce → the API and UI are unchanged). The three-signal blend (taste + trending + recency) ranks
moments (moment_select); carousels surface the per-cluster taste, the TRENDING synthesis, EXPLORATION, and
the global new-in-genre / new-on-platform rows (the last two REUSE the v1 CSV providers — no heavy substrate).

`feed_to_v1_envelope` serializes a DiscoveryFeed into the exact v1.0 HTTP envelope (mirrors api.py's
serializers) but carries the v2 per-item debug breakdown (taste_match / trending_velocity / recency /
cluster_id / final_score) so the blend is inspectable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set

from .. import config
from ..candidates.base import RequestContext, select_fresh_moments
from ..candidates.new_in_genre import NewInGenre
from ..candidates.new_on_platform import NewOnPlatform
from ..data_access.base import DataSource
from ..ranking.trending import TrendingTable
from . import why_v2
from .feed_models import Carousel, CarouselItem, DiscoveryFeed, FeedItem, LatestMoment, Pagination, ReasonType
from .moment_select import BlendWeights, ScoredMoment, blend_final, select_moments_for_property


def _iso(dt):
    return dt.isoformat() if dt else None


def _norm(score: float, mx: float) -> float:
    return max(0.0, min(1.0, score / mx)) if mx else 0.0


def _top_genre(ds: DataSource, eid: str) -> Optional[str]:
    e = ds.get_entity(eid)
    if not e:
        return None
    gs = ds.get_podcast_categories(eid) if e.vertical == "podcast" else e.canonical_genres
    return gs[0] if gs else None


def _latest_moment(ds: DataSource, eid: str) -> Optional[LatestMoment]:
    ms = ds.get_moments_for_property(eid)          # newest-first
    if not ms:
        return None
    m = ms[0]
    return LatestMoment(moment_id=m.moment_id, title=m.title or "", event_starts_at=_iso(m.event_starts_at))


def _interleave(primary: List, secondary: List, ratio_secondary: float) -> List:
    """Proportional weave: emit ~ratio_secondary of items from `secondary` so the global_backfill verticals
    actually appear in the feed (honoring vertical_percentages), instead of being buried below all content."""
    if not secondary:
        return list(primary)
    if not primary:
        return list(secondary)
    out, i, j, emitted, emitted_sec = [], 0, 0, 0, 0
    while i < len(primary) or j < len(secondary):
        want_sec = (emitted + 1) * ratio_secondary
        if j < len(secondary) and (i >= len(primary) or emitted_sec < want_sec):
            out.append(secondary[j]); j += 1; emitted_sec += 1
        else:
            out.append(primary[i]); i += 1
        emitted += 1
    return out


def _dominant(sm: ScoredMoment, weights: BlendWeights) -> str:
    contribs = {"taste": weights.w_taste * sm.taste_match,
                "trending": weights.w_trending * sm.trending_velocity,
                "recency": weights.w_recency * sm.recency,
                "collaborative": weights.w_collaborative * sm.collaborative}
    return max(contribs, key=contribs.get) if any(v > 0 for v in contribs.values()) else "recency"


def assemble_feed_v2(profile, bundle, ds: DataSource, trending: TrendingTable, now: datetime, *,
                     v1_profile, pop, seen_ids: Optional[Set[int]] = None,
                     excluded_property_ids: Optional[Set[int]] = None,
                     exclude_ids: Optional[Set[str]] = None, limit: int = None, offset: int = 0,
                     include_global: bool = True) -> DiscoveryFeed:
    seen_ids = set(seen_ids or [])
    exclude_ids = set(exclude_ids or [])
    excluded_property_ids = set(excluded_property_ids or [])
    limit = limit or config.MAIN_FEED_PAGE_SIZE
    followed = {e.target_entity_id for e in profile.engagements}

    # repr (a followed property) + top genre per cluster (for why_strings)
    repr_by_cluster: Dict[int, Optional[str]] = {}
    genre_by_cluster: Dict[int, Optional[str]] = {}
    for c in profile.clusters:
        rep = c.top_representative_member_entity_ids[0] if c.top_representative_member_entity_ids else None
        e = ds.get_entity(rep) if rep else None
        repr_by_cluster[c.cluster_id] = e.name if e else None
        genre_by_cluster[c.cluster_id] = c.top_genres[0][0] if c.top_genres else None

    all_content = [c for cs in bundle.clusters for c in cs.candidates]
    maxsc = max((c.score for c in all_content), default=1.0) or 1.0
    # #1 (V2-P7): fold cluster_share (recency-drift) into per-item taste_match so a recently-weighted
    # cluster's items RANK higher, not just get more slots. effective = norm · ((1-W) + W·share/max_share).
    max_share = max((cs.cluster_share for cs in bundle.clusters), default=0.0) or 1.0
    _W = config.V2_TASTE_CLUSTER_WEIGHTING

    def _cluster_taste(score, share):
        return _norm(score, maxsc) * ((1.0 - _W) + _W * (share / max_share))

    # V2-P8/P9: per-feed ADAPTIVE weights from the niche-relative trending confidence AND the neighborhood-
    # density collaborative confidence. _scoped_tv = niche-relative trending velocity per moment; _collab =
    # per-property similar-user affinity (applies to content items too, so an on-taste item the neighborhood
    # ALSO loves gets a collaborative lift).
    weights = BlendWeights.adaptive(bundle.trend_confidence, bundle.collab_confidence)
    _trend_vel = bundle.trend_moment_velocity
    _collab_score = bundle.collab_score

    def _scoped_tv(moment_id):
        return _trend_vel.get(moment_id, 0.0)

    def _collab(entity_id):
        return _collab_score.get(entity_id, 0.0)

    # ── MAIN FEED: content+trending clusters + collaborative discoveries, interleaved w/ global_backfill ──
    content_main: List[ScoredMoment] = []
    for cs in bundle.clusters:
        for cand in cs.allocated:
            content_main += select_moments_for_property(
                ds, trending, now, entity_id=cand.entity_id, taste_match=_cluster_taste(cand.score, cs.cluster_share),
                cluster_id=cs.cluster_id, source_pool=cand.source_pool, seen_ids=seen_ids,
                trending_fn=_scoped_tv, weights=weights, collaborative=_collab(cand.entity_id), followed=followed)

    # Source 4 (V2-P9): COLLABORATIVE discoveries (NEW properties similar users love — incl. CROSS-ATTRIBUTE,
    # taste_match≈0). NOT taste-gated: they ride the additive w_collaborative·affinity term into the feed.
    collab_main: List[ScoredMoment] = []
    for cand in bundle.collaborative:
        collab_main += select_moments_for_property(
            ds, trending, now, entity_id=cand.entity_id, taste_match=cand.score,   # cand.score = taste PROXY (0 = cross-attribute)
            cluster_id=cand.cluster_id, source_pool="collaborative", seen_ids=seen_ids,
            trending_fn=_scoped_tv, weights=weights, collaborative=cand.collaborative_score, followed=followed)

    v1ctx = RequestContext(now=now, seen_moment_ids=seen_ids, excluded_property_ids=excluded_property_ids,
                           limit=config.CANDIDATE_POOL_SIZE, offset=0)
    backfill_excl = exclude_ids | followed
    backfill_main: List[ScoredMoment] = []
    for vert, slots in bundle.allocation.global_backfill.items():
        if slots <= 0:
            continue
        for m, rec in select_fresh_moments(ds, v1ctx, backfill_excl, limit=slots, vertical=vert):
            tv = _scoped_tv(m.moment_id)
            seen = config.V2_SEEN_SUPPRESSION if m.moment_id in seen_ids else 0.0
            age_days = (now - m.event_starts_at).total_seconds() / 86400.0 if m.event_starts_at else None
            final = blend_final(0.0, tv, rec, seen, age_days, weights)
            e = ds.get_entity(m.entity_id)
            backfill_main.append(ScoredMoment(m.moment_id, m.entity_id, e.vertical if e else vert, 0.0, tv,
                                              rec, 0.0, seen, round(final, 6), None, "global_backfill"))

    # rank the personal stream (content+trending+collaborative together), then weave backfill in proportional
    # to its share of the allocation (vertical_percentages). Personal is `primary` so it dedupes ahead of backfill.
    personal_main = content_main + collab_main
    personal_main.sort(key=lambda s: -s.final_score)
    backfill_main.sort(key=lambda s: -s.final_score)
    total_bf = sum(bundle.allocation.global_backfill.values())
    denom = bundle.allocation.content_slots + total_bf
    ratio_bf = (total_bf / denom) if denom else 0.0
    main = _interleave(personal_main, backfill_main, ratio_bf)
    seen_m: Set[int] = set()
    per_prop: Dict[str, int] = {}
    capped: List[ScoredMoment] = []
    for sm in main:
        if sm.moment_id in seen_m or per_prop.get(sm.entity_id, 0) >= config.V2_MOMENT_CAP_PER_PROPERTY:
            continue
        seen_m.add(sm.moment_id)
        per_prop[sm.entity_id] = per_prop.get(sm.entity_id, 0) + 1
        capped.append(sm)

    pool_total = len(capped)
    page = capped[offset:offset + limit]
    next_offset = offset + limit if offset + limit < pool_total else None

    def build_item(sm: ScoredMoment) -> FeedItem:
        m = ds.get_moment(sm.moment_id)
        ent = ds.get_entity(sm.entity_id)
        genre = _top_genre(ds, sm.entity_id) or genre_by_cluster.get(sm.cluster_id)   # ITEM's own genre first → variety
        why = why_v2.moment_why(source_pool=sm.source_pool, dominant=_dominant(sm, weights), vertical=sm.vertical,
                                genre=genre, repr_name=repr_by_cluster.get(sm.cluster_id), seed=sm.moment_id)
        return FeedItem(
            moment_id=sm.moment_id, entity_id=sm.entity_id,
            property_name=(ent.name if ent else sm.entity_id), vertical=sm.vertical,
            title=(m.title if m else ""), description=(m.description if m else ""),
            event_starts_at=(_iso(m.event_starts_at) if m else None),
            media_platform_id=(m.media_platform_id if m else None),
            score=sm.final_score, why_string=why, source_pool=sm.source_pool, debug=sm.signals())

    main_items = [build_item(sm) for sm in page]

    # ── CAROUSELS ──
    carousels: List[Carousel] = []

    def citem(entity_id, score, why, source_pool, debug=None) -> CarouselItem:
        e = ds.get_entity(entity_id)
        return CarouselItem(entity_id=entity_id, property_name=(e.name if e else entity_id),
                            vertical=(e.vertical if e else ""), score=round(score, 4), why_string=why,
                            source_pool=source_pool, latest_moment=_latest_moment(ds, entity_id),
                            debug=debug or {})

    top_genre_overall = profile.top_genres[0][0] if profile.top_genres else None

    # (a) per-cluster carousels
    for n, cs in enumerate(bundle.clusters):
        if n >= config.V2_MAX_CLUSTER_CAROUSELS:
            break
        repr_name = repr_by_cluster.get(cs.cluster_id)
        _cands = cs.candidates[:config.V2_CLUSTER_CAROUSEL_SIZE]
        _scores = [_norm(c.score, maxsc) for c in _cands]
        # tiebreak: when a cluster's candidates all normalize to the SAME value (tied/clipped substrate
        # scores → every item renders an identical, often 1.0, score), preserve the upstream order with a
        # tiny positional decay so the carousel still differentiates. No-op when scores already vary.
        if len(_scores) > 1 and (max(_scores) - min(_scores)) < 1e-9:
            _scores = [max(0.0, s - i * 1e-3) for i, s in enumerate(_scores)]
        items = [citem(c.entity_id, s,
                       why_v2.cluster_reason(genre=_top_genre(ds, c.entity_id), repr_name=repr_name),
                       "content", {"taste_match": round(s, 4), "cluster_id": cs.cluster_id,
                                   "final_score": round(s, 4)})
                 for c, s in zip(_cands, _scores)]
        if len(items) >= config.V2_CLUSTER_CAROUSEL_MIN:
            carousels.append(Carousel(
                f"cluster_{cs.cluster_id}", ReasonType.similar_to_followed,
                why_v2.cluster_reason(genre=genre_by_cluster.get(cs.cluster_id), repr_name=repr_name),
                "property", items))

    # (b) TRENDING carousel (V2-P8) — drawn from the GLOBAL-trending-SCOPED-TO-TASTE candidate source, NOT only
    # from content candidates → populated whenever the user's taste niche has trending content, even if the
    # taste-retrieval path never selected those properties. (Fixes the V2-P7 empty-trending-carousel note.)
    tr_items: List[CarouselItem] = []
    seen_e: Set[str] = set()
    for c in bundle.trending[:config.V2_TRENDING_CAROUSEL_SIZE]:
        if c.entity_id in seen_e:
            continue
        seen_e.add(c.entity_id)
        g = _top_genre(ds, c.entity_id)
        tr_items.append(citem(c.entity_id, c.trending_velocity, why_v2.trending_reason(g), "trending",
                              {"trending_velocity": round(c.trending_velocity, 6), "taste_match": round(c.score, 4),
                               "cluster_id": c.cluster_id, "final_score": round(c.trending_velocity, 4)}))
    if tr_items:
        carousels.append(Carousel("trending", ReasonType.trending,
                                  why_v2.trending_reason(top_genre_overall), "property", tr_items))

    # (b2) COLLABORATIVE carousel (V2-P9) — what the user's taste NEIGHBORHOOD engages with that they have NOT
    # found, INCLUDING cross-attribute content (the bubble-escape). Only emits when a real neighborhood gives
    # signal (bundle.collaborative is empty otherwise). Tagged source_pool="collaborative" for the feedback loop.
    co_items: List[CarouselItem] = []
    seen_co: Set[str] = set()
    for i, c in enumerate(bundle.collaborative[:config.V2_COLLAB_CAROUSEL_SIZE]):
        if c.entity_id in seen_co:
            continue
        seen_co.add(c.entity_id)
        g = _top_genre(ds, c.entity_id)
        co_items.append(citem(c.entity_id, c.collaborative_score,
                              why_v2.collaborative_why(g, c.vertical, i), "collaborative",
                              {"collaborative": round(c.collaborative_score, 6), "taste_match": round(c.score, 4),
                               "endorsers": c.collab_endorsers, "neighborhood_size": c.collab_neighbor_size,
                               "cluster_id": c.cluster_id, "final_score": round(c.collaborative_score, 4)}))
    if co_items:
        carousels.append(Carousel("collaborative", ReasonType.popular_with_similar_users,
                                  why_v2.collaborative_reason(top_genre_overall), "property", co_items))

    # (c) EXPLORATION carousel — structured adjacency (tagged for the future feedback loop)
    ex_items = [citem(c.entity_id, c.score, why_v2.exploration_why(c.adjacency_rule, c.shared_attrs, c.new_attrs),
                      "exploration", {"adjacency_rule": c.adjacency_rule, "shared_attrs": c.shared_attrs,
                                      "new_attrs": c.new_attrs, "final_score": round(c.score, 4)})
                for c in bundle.exploration[:config.V2_EXPLORATION_CAROUSEL_SIZE]]
    if ex_items:
        carousels.append(Carousel("exploration", ReasonType.new_in_genre,
                                  why_v2.exploration_reason(top_genre_overall), "property", ex_items))

    # (d/e) global new-in-genre + new-on-platform (REUSE v1 CSV providers; no heavy substrate)
    if include_global and v1_profile is not None:
        carousels += _global_carousels(ds, pop, v1_profile, v1ctx, profile, citem)

    return DiscoveryFeed(
        user_id=(profile.user_id if profile.user_id is not None else 0), mode=profile.mode,
        signal_strength=profile.signal_strength, now=_iso(now),
        main_feed=main_items, carousels=[c for c in carousels if c.items],
        pagination=Pagination(limit=limit, offset=offset, returned=len(main_items),
                              next_offset=next_offset, pool_total=pool_total))


def _global_carousels(ds, pop, v1_profile, v1ctx, profile, citem) -> List[Carousel]:
    out: List[Carousel] = []
    groups = NewInGenre(ds, None, pop).group_by_genre(v1_profile, v1ctx)
    user_genres = [g for g, _ in profile.top_genres]
    ordered = ([g for g in user_genres if g in groups] +
               [g for g in sorted(groups, key=lambda k: -len(groups[k])) if g not in user_genres])
    n = 0
    for g in ordered:
        if n >= config.NEW_IN_GENRE_MAX_CAROUSELS:
            break
        items, seen_e = [], set()
        for cand in groups[g]:
            eid = cand.entity_id
            if not eid or eid in seen_e:
                continue
            seen_e.add(eid)
            items.append(citem(eid, cand.raw_signals.get("recency", 0.0) or 0.0, f"New in {g}",
                               "new_in_genre", {"recency": cand.raw_signals.get("recency")}))
            if len(items) >= config.CAROUSEL_SIZE:
                break
        if len(items) >= config.V2_GLOBAL_CAROUSEL_MIN:
            out.append(Carousel(f"new_in_genre_{g}", ReasonType.new_in_genre, f"New in {g}", "property", items))
            n += 1

    platgroups = NewOnPlatform(ds, None, pop).group_by_platform(v1_profile, v1ctx)
    lk = ds.lookups()
    n = 0
    for pid in sorted(platgroups, key=lambda k: -len(platgroups[k])):
        if n >= config.NEW_ON_PLATFORM_MAX_CAROUSELS:
            break
        pname = lk.media_platform(pid)
        if not pname:
            continue
        items, seen_e = [], set()
        for cand in platgroups[pid]:
            eid = cand.entity_id
            if not eid or eid in seen_e:
                continue
            seen_e.add(eid)
            items.append(citem(eid, cand.raw_signals.get("recency", 0.0) or 0.0, f"New on {pname}",
                               "new_on_platform", {"recency": cand.raw_signals.get("recency")}))
            if len(items) >= config.CAROUSEL_SIZE:
                break
        if len(items) >= config.V2_GLOBAL_CAROUSEL_MIN:
            out.append(Carousel(f"new_on_platform_{pid}", ReasonType.new_on_platform, f"New on {pname}",
                                "property", items))
            n += 1
    return out


# ── v1.0 HTTP envelope serializer (mirrors api.py; carries the v2 debug breakdown) ──
def _genres(ds, entity_id):
    e = ds.get_entity(entity_id)
    if not e:
        return []
    return ds.get_podcast_categories(entity_id) if e.vertical == "podcast" else e.canonical_genres


def _moment_item(fi: FeedItem, debug: bool) -> dict:
    d = {"type": "moment", "moment_id": fi.moment_id, "entity_id": fi.entity_id,
         "property_name": fi.property_name, "vertical": fi.vertical, "title": fi.title,
         "description": fi.description, "event_starts_at": fi.event_starts_at,
         "media_platform_id": fi.media_platform_id, "score": round(fi.score, 4), "why_string": fi.why_string}
    if debug:
        s = fi.debug
        d["debug"] = {"source_pool": fi.source_pool, "taste_match": s.get("taste_match"),
                      "trending_velocity": s.get("trending_velocity"), "recency": s.get("recency"),
                      "collaborative": s.get("collaborative"), "cluster_id": s.get("cluster_id"),
                      "final_score": s.get("final_score"),
                      "raw_signals": {"semantic": s.get("semantic"), "recency": s.get("recency"),
                                      "normalized_influence": s.get("influence"),
                                      "velocity": s.get("velocity"), "suppression": s.get("suppression")}}
    return d


def _property_item(ci: CarouselItem, ds, debug: bool) -> dict:
    d = {"type": "property", "entity_id": ci.entity_id, "name": ci.property_name, "vertical": ci.vertical,
         "genres": _genres(ds, ci.entity_id), "score": round(ci.score, 4), "why_string": ci.why_string,
         "latest_moment": ci.latest_moment.to_dict() if ci.latest_moment else None}
    if debug:
        d["debug"] = {"source_pool": ci.source_pool, **ci.debug}
    return d


def feed_to_v1_envelope(feed: DiscoveryFeed, ds, *, user_id, followed_count, request_echo,
                        substrate_reachable=True, debug=False, debug_block=None) -> dict:
    """The exact v1.0 HTTP envelope (so the API/UI contract is unchanged), with v2 per-item debug."""
    items = [_moment_item(i, debug) for i in feed.main_feed]
    return {
        "version": "1.0", "endpoint": "discovery-api", "user_id": user_id, "generated_at": feed.now,
        "context": {"mode": feed.mode, "followed_count": followed_count,
                    "signal_strength": feed.signal_strength, "substrate_reachable": substrate_reachable},
        "request_echo": request_echo,
        "main_feed": {"items": items, "count": len(items),
                      "next_offset": feed.pagination.next_offset if feed.pagination else None},
        "carousels": [{"carousel_id": c.carousel_id, "reason_type": c.reason_type.value,
                       "reason_string": c.reason_string, "item_type": c.item_type,
                       "items": [_property_item(it, ds, debug) for it in c.items]}
                      for c in feed.carousels if c.items],
        "debug": debug_block,
    }
