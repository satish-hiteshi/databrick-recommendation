"""home_response.py — UC3 home-feed RESPONSE shaper (envelope + item field-mapping).

Lives in the SEPARATE ``home_feed/`` folder and reuses the discovery engine as a
library. This module is the boundary between the home-feed ranker
(``home_ranking.rank_home``) / carousel builder and the wire format defined by
UC3 §6 (``UC3_Home_Feed_v1.3.md``). It does two things, and nothing else:

  1. ``build_item``     — map ONE ranker item dict to a ``main_feed.items[]`` entry.
  2. ``build_envelope`` — wrap the mapped items + carousels + request echo in the
                          top-level response object.

Design / purity
---------------
* This is a SHAPER, not a ranker. It holds no ranking, carousel, scoring,
  suppression, or endpoint/routing logic. Items arrive pre-ranked and pre-ordered;
  carousels arrive pre-built. We only re-key and enrich.
* ``data`` (the discovery ``Data`` singleton) is passed in as an explicit argument —
  this module never bootstraps or owns the engine's global state, which keeps it
  trivially unit-testable and free of load-time side effects.
* ``now_iso`` is supplied by the caller. We never call ``datetime.now()`` at import
  time, so importing this module is side-effect-free and feeds stay reproducible.

Enrichment surfacing
--------------------
Display fields are surfaced from the P2-1 Databricks Silver enrichment, kept in
SEPARATE dicts on ``Data`` so the base moment/property records stay untouched:

  * ``data.moment_extra(mid)`` -> media_platform name/id, hero/thumbnail image,
    cta text, and the moment_type that drives ``is_live``.
  * ``data.prop_extra(pid)``   -> the property ``handle`` and ``logo_url`` avatar.
  * ``data.properties[pid]``   -> the canonical ``entity_id``.

Honest-null policy
------------------
Enrichment coverage is partial (~50% of moments/properties have a matching Silver
row), and that is expected and fine. ``moment_extra`` / ``prop_extra`` return ``{}``
when a row is absent, so every read uses ``.get(...)`` and degrades to ``None``.
When a value is genuinely unknown we emit an explicit ``null`` rather than inventing
a placeholder, a guessed CDN path, or a stale fallback — a client can then tell
"we don't have this" apart from "this is the value", a distinction a fabricated
default would silently destroy. ``viewer_count`` is always ``null`` in this PoC
(no live-viewer feed exists yet).
"""
from typing import Any, Dict, List, Optional, Sequence

# NOTE: this module is a pure shaper — it takes the discovery ``Data`` object as an argument and
# imports nothing from discovery/src, so it needs NO sys.path bootstrap (removed: it was dead).

# UC3 contract constants ----------------------------------------------------------
SCORE_DECIMALS = 6               # main_feed.items[].score rounding (matches ranker precision)
TRENDING_BADGE_THRESHOLD = 0.5   # signals.trending above this => "TRENDING" badge (when not LIVE/NEW)


def _badge_for(it: Dict[str, Any]) -> Optional[str]:
    """Derive the single client badge for a moment from its ranker flags.

    Priority is fixed and mutually exclusive (a moment gets at most one badge):
        LIVE     — currently live (highest signal, overrides everything).
        NEW      — an upcoming / freshly-published moment.
        TRENDING — strong population trending signal (> TRENDING_BADGE_THRESHOLD).
        None     — nothing noteworthy to flag.
    """
    if it.get("is_live"):
        return "LIVE"
    if it.get("upcoming"):
        return "NEW"
    if it.get("signals", {}).get("trending", 0) > TRENDING_BADGE_THRESHOLD:
        return "TRENDING"
    return None


def build_item(data: Any, it: Dict[str, Any], debug: bool = False) -> Dict[str, Any]:
    """Map ONE ranker item dict to a UC3 ``main_feed.items[]`` entry.

    ``it`` follows the ``home_ranking.rank_home`` item contract::

        {"rank","moment_id","property_id","property_name","vertical","title",
         "description","url","event_starts_at","score","reason","is_live",
         "richness","upcoming","signals":{...}}

    Display enrichment is read from ``data.moment_extra(mid)`` / ``data.prop_extra(pid)``
    and from ``data.properties[pid]``; every read degrades to ``None`` (honest-null
    policy) because enrichment coverage is partial by design (~50%).
    """
    mid = it.get("moment_id")
    pid = it.get("property_id")

    # Separate P2-1 enrichment dicts — each {} when the row is absent (never raises).
    m_extra = data.moment_extra(mid)
    p_extra = data.prop_extra(pid)
    prop = data.properties.get(pid, {})

    # Moment image: prefer the richer hero image, fall back to the plain thumbnail.
    thumbnail_url = m_extra.get("hero_image_url") or m_extra.get("thumbnail_url")

    return {
        "type": "moment",
        "moment_id": mid,
        "entity_id": prop.get("entity_id"),
        "property_id": pid,
        "property_name": it.get("property_name"),
        "property_handle": p_extra.get("handle"),
        "property_thumbnail_url": p_extra.get("logo_url"),
        "vertical": it.get("vertical"),
        "title": it.get("title"),
        "description": it.get("description"),
        "thumbnail_url": thumbnail_url,
        "media_url": it.get("url"),
        "media_platform": m_extra.get("media_platform_name"),
        "media_platform_id": m_extra.get("media_platform_id"),
        "event_starts_at": it.get("event_starts_at"),
        "rank": it.get("rank"),
        "score": round(float(it.get("score", 0.0)), SCORE_DECIMALS),
        "why_string": it.get("reason"),
        "badge": _badge_for(it),
        "is_live": bool(it.get("is_live")),
        "viewer_count": None,            # no live-viewer feed in this PoC — honest null
        "is_followed": True,             # home stream is follow-gated => always true (UC3 assertion)
        "debug_meta": it.get("signals") if debug else None,
    }


def build_envelope(
    data: Any,
    user_id: Any,
    items: Sequence[Dict[str, Any]],
    total: int,
    meta: Dict[str, Any],
    carousels: List[Dict[str, Any]],
    *,
    sort_order: Any,
    time_window: Any,
    limit: int,
    offset: int,
    seen_ids: Optional[Sequence[Any]],
    done_ids: Optional[Sequence[Any]],
    dismissed: Optional[Sequence[Any]],
    blocked: Optional[Sequence[Any]],
    now_iso: str,
    debug: bool = False,
) -> Dict[str, Any]:
    """Wrap mapped items + carousels in the top-level UC3 home-feed response object.

    ``items`` are pre-ranked ranker dicts (mapped here via ``build_item``); ``carousels``
    are pre-built UC3 carousel objects, passed through untouched. ``meta`` is the ranker's
    context/diagnostics bag (``signal_strength``, ``follow_count``, ...) and is echoed into
    the ``debug`` key only when ``debug`` is true.

    ``mode`` is ALWAYS ``"personalized"`` for the home feed — there is no anonymous/global
    mode (UC3 §6 ``context.mode``), unlike the discovery feed which falls back to ``"global"``
    on cold start.

    ``now_iso`` is supplied by the caller for reproducibility; this module never reads the
    clock at import time.
    """
    next_offset = offset + limit if offset + limit < total else None

    return {
        "version": "1.0",
        "endpoint": "home-feed",
        "user_id": user_id,
        "generated_at": now_iso,
        "context": {
            "mode": "personalized",   # always personalized for home feed (never "global")
            "signal_strength": meta.get("signal_strength", 0.0),
            "engine": "v2",
            "path": "home_feed",
            "follow_count": meta.get("follow_count", 0),
        },
        "request_echo": {
            "sort_order": sort_order,
            "time_window": time_window,
            "limit": limit,
            "offset": offset,
            "seen_ids": len(seen_ids or []),
            "done_ids": len(done_ids or []),
            "dismissed_property_ids": len(dismissed or []),
            "blocked_property_ids": len(blocked or []),
        },
        "main_feed": {
            "items": [build_item(data, it, debug) for it in items],
            "count": len(items),
            "next_offset": next_offset,
        },
        "carousels": carousels,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total_available": total,
            "has_more": (offset + limit) < total,
        },
        "debug": meta if debug else None,
    }
