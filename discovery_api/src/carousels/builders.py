"""Carousel builders — turn scored pools into horizontal carousels of PROPERTIES.

Emits, in order, only carousels that meet CAROUSEL_MIN_SIZE:
  similar_to_followed (personalized) · popular_with_fans_of (personalized) · trending (always) ·
  new_in_genre × top genres (always) · new_on_platform × top platforms (always).
Each item is a property with a why_string + a latest_moment hook + a debug signal breakdown. Shared
item helpers (top_genre / latest_moment / representative_followed_name) are reused by the assembler.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

from .. import config
from ..feed.feed_models import Carousel, CarouselItem, LatestMoment, ReasonType
from ..ranking.scorer import score_candidates
from ..why import reason_string, why_string


def _iso(dt):
    return dt.isoformat() if dt else None


def top_genre(ds, entity_id: str) -> Optional[str]:
    ent = ds.get_entity(entity_id)
    if not ent:
        return None
    gs = ds.get_podcast_categories(entity_id) if ent.vertical == "podcast" else ent.canonical_genres
    return gs[0] if gs else None


def latest_moment_for(ds, entity_id: str, prefer_moment_id: Optional[int] = None) -> Optional[LatestMoment]:
    m = ds.get_moment(prefer_moment_id) if prefer_moment_id is not None else None
    if m is None:
        ms = ds.get_moments_for_property(entity_id)
        m = ms[0] if ms else None
    return LatestMoment(m.moment_id, m.title, _iso(m.event_starts_at),
                        moment_profile_key=m.profile_key,
                        moment_media_source_guid=m.media_source_guid) if m else None


def representative_followed_name(ds, profile, popularity) -> Optional[str]:
    """A recognizable followed property (highest normalized influence) → its name, for personal phrasings."""
    best, best_v = None, -1.0
    for eid in profile.followed_entity_ids:
        v = popularity.normalized_influence(eid) or 0.0
        if v > best_v:
            best_v, best = v, eid
    ent = ds.get_entity(best) if best else None
    return ent.name if ent else None


def build_carousel_item(ds, cand, bd, profile, *, genre=None, platform_name=None,
                        repr_followed_name=None) -> CarouselItem:
    ent = ds.get_entity(cand.entity_id)
    name = ent.name if ent else cand.entity_id
    vertical = cand.vertical or (ent.vertical if ent else None)
    g = genre if genre is not None else top_genre(ds, cand.entity_id)
    why = why_string(cand.source_pool, bd.dominant, profile.mode, vertical,
                     genre=g, platform_name=platform_name, repr_followed_name=repr_followed_name)
    return CarouselItem(
        entity_id=cand.entity_id, property_name=name, vertical=vertical, score=bd.final,
        why_string=why, source_pool=cand.source_pool,
        latest_moment=latest_moment_for(ds, cand.entity_id, cand.moment_id),
        debug={"signals": bd.to_dict()})


def _property_carousel(carousel_id, reason_type, scored, ds, profile, context, repr_name,
                       *, scope_genre=None, scope_platform=None) -> Optional[Carousel]:
    """Dedupe scored candidates to ONE item per property; emit only if ≥ CAROUSEL_MIN_SIZE."""
    seen, items = set(), []
    for cand, bd in scored:
        eid = cand.entity_id
        if not eid or eid in seen:
            continue
        seen.add(eid)
        items.append(build_carousel_item(ds, cand, bd, profile, genre=scope_genre,
                                         platform_name=scope_platform, repr_followed_name=repr_name))
        if len(items) >= config.CAROUSEL_SIZE:
            break
    if len(items) < config.CAROUSEL_MIN_SIZE:
        return None
    reason = reason_string(reason_type, genre=scope_genre, platform_name=scope_platform,
                           vertical=context.vertical, repr_followed_name=repr_name)
    return Carousel(carousel_id, reason_type, reason, "property", items)


def _grouped_carousels(pool_cands, key_field, reason_type, ds, profile, context, pop, sctx, repr_name,
                       max_carousels, label_fn) -> List[Carousel]:
    """new_in_genre / new_on_platform: group moment candidates by genre/platform → a carousel per scope."""
    groups = defaultdict(list)
    for cand in pool_cands:
        for k in (cand.raw_signals.get(key_field) or []):
            groups[k].append(cand)
    ranked = sorted(groups.items(), key=lambda kv: len({c.entity_id for c in kv[1]}), reverse=True)
    out, n = [], 0
    for k, cands in ranked:
        if n >= max_carousels:
            break
        label = label_fn(k)
        if not label:
            continue
        scored = score_candidates(cands, profile, context, ds, pop, sctx)
        kw = {"scope_genre": label} if reason_type == ReasonType.new_in_genre else {"scope_platform": label}
        car = _property_carousel(f"{reason_type.value}:{k}", reason_type, scored, ds, profile, context, repr_name, **kw)
        if car:
            out.append(car); n += 1
    return out


def build_carousels(pools, ds, profile, context, pop, sctx, repr_name=None) -> List[Carousel]:
    """Build all v1.0 carousels (in order) from the raw candidate pools. Personalized-only carousels
    (similar_to_followed / popular_with_fans_of) are naturally skipped for cold-start (empty pools)."""
    if repr_name is None:
        repr_name = representative_followed_name(ds, profile, pop)
    carousels: List[Carousel] = []

    def entity_carousel(pool_name, reason_type):
        raw = pools.get(pool_name) or []
        if not raw:
            return
        scored = score_candidates(raw, profile, context, ds, pop, sctx)
        car = _property_carousel(reason_type.value, reason_type, scored, ds, profile, context, repr_name)
        if car:
            carousels.append(car)

    entity_carousel("similar_to_followed", ReasonType.similar_to_followed)   # personalized
    entity_carousel("popular_with_fans_of", ReasonType.popular_with_fans_of)  # personalized
    entity_carousel("trending_global", ReasonType.trending)                   # always

    lk = ds.lookups()
    carousels += _grouped_carousels(pools.get("new_in_genre") or [], "genres", ReasonType.new_in_genre,
                                    ds, profile, context, pop, sctx, repr_name,
                                    config.NEW_IN_GENRE_MAX_CAROUSELS, label_fn=lambda g: g)
    carousels += _grouped_carousels(pools.get("new_on_platform") or [], "platform_ids", ReasonType.new_on_platform,
                                    ds, profile, context, pop, sctx, repr_name,
                                    config.NEW_ON_PLATFORM_MAX_CAROUSELS,
                                    label_fn=lambda pid: None if pid in (0, None) else lk.media_platform(pid))
    return carousels
