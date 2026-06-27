"""home_carousels.py — unfollowed-discovery carousels for the UC3 home feed.

Lives in the SEPARATE home_feed/ folder and reuses the discovery engine (discovery/src)
as a library via the bootstrap below — the discovery package is never modified.

This is the ONE place the home feed surfaces UNFOLLOWED properties: "because you follow X,
you might like Y". The main stream shows moments from followed properties; these carousels
are interleaved into that stream to introduce *new* identities the user does not follow yet —
follow-suggestion shelves, not content the user already gets.

Design notes
------------
* Candidate generation is REUSED from carousels.py (``_similar`` / ``_trending`` /
  ``_popular`` / ``_fresh`` and the supporting ``_recent_pids`` / ``_genre_index`` /
  ``_filter`` helpers) via ``import carousels as C``. We do NOT modify carousels.py.
* Carousels are CHOSEN per user from their own engagement (top genre, top vertical,
  strongest seed), mirroring ``build_carousels``. Cold / thin users fall back to sensible
  global shelves. The result is capped to ``carousel_slots``.
* Item / carousel ASSEMBLY is local to this module because the UC3 contract differs from the
  carousels.py contract: a different ``carousel_type`` enum, an ``insert_after_index``
  interleave hint, per-item ``is_live`` / ``why_string``, and — critically — a freshness-gated
  ``latest_moment`` (newest moment within the last 30 days, else null). carousels.py's
  ``_latest_moment`` is intentionally NOT reused: it returns the newest moment regardless of
  age, which would surface stale (e.g. years-old) moments on a discovery card.

Public entry point: ``build_home_carousels``.
"""
# --- engine bootstrap: reuse the discovery engine (discovery/src) as a library -----
import os as _os
import sys as _sys

_DISC_SRC = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "discovery", "src",
)
if _DISC_SRC not in _sys.path:
    _sys.path.insert(0, _DISC_SRC)
# -----------------------------------------------------------------------------------
from collections import Counter

import carousels as C

# UC3 contract enums --------------------------------------------------------------
# Internal reason_type -> client carousel_type. "circle" layout is for property/identity
# (avatar) carousels; "square" for moment/content carousels.
_CAROUSEL_TYPE = {
    "similar_seed": "similar_to_followed",
    "trending": "trending_in_vertical",
    "popular": "trending_in_vertical",
    "fresh": "happening_today",
}
_CAROUSEL_LAYOUT = {
    "similar_seed": "circle",   # follow-suggestion avatars
    "trending": "circle",       # all home shelves here are property/identity -> circle
    "popular": "circle",
    "fresh": "circle",
}
# Per-shelf client cache hint. Popular / similar are stable -> longer TTL.
_CACHE_TTL = {"similar_seed": 1800, "popular": 1800, "trending": 300, "fresh": 300}
_DEFAULT_TTL = 300

MIN_ITEMS = 4                     # UC3 min bar: drop carousels with < 4 items
_RECENT_SECS = C.RECENT_SECS      # 30 days — the freshness window (reused constant)


def _fresh_latest_moment(data, pid, now_epoch):
    """Newest moment for ``pid`` WITHIN THE LAST 30 DAYS, else None.

    UC3 acceptance criterion / freshness fix: a discovery card must never advertise a stale
    moment (e.g. a 17-year-old one). If the property's newest moment is older than the 30-day
    window we return None — the property may still appear as a followable card, just with no
    ``latest_moment`` hook. Uses the pre-parsed ``_event_epoch`` (event_starts_at, fallback
    created_at) computed once at load time.
    """
    ms = data.moments_by_pid.get(pid)
    if not ms:
        return None
    best = max(ms, key=lambda m: (m.get("_event_epoch") or 0))
    epoch = best.get("_event_epoch") or 0
    if epoch < (now_epoch - _RECENT_SECS):
        return None
    return {
        "moment_id": best["moment_id"],
        "title": best["title"],
        "event_starts_at": best.get("event_starts_at"),
        "_event_epoch": epoch,
    }


def _is_live(data, latest_moment):
    """True iff the property's latest (fresh) moment is a "Live Now" type, per enrichment."""
    if not latest_moment:
        return False
    extra = data.moment_extra(latest_moment["moment_id"]) or {}
    return extra.get("moment_type_name") == "Live Now"


def _home_item(data, pid, score, why, now_epoch):
    """Build one UC3 home-carousel item (item_type 'property', freshness-gated latest_moment)."""
    prop = C._p(data, pid)
    pe = data.prop_extra(pid) or {}
    latest = _fresh_latest_moment(data, pid, now_epoch)
    item = {
        "type": "property",
        "entity_id": prop.get("entity_id"),
        "property_id": pid,
        "name": prop.get("name", f"Property {pid}"),
        "vertical": prop.get("vertical"),
        "genres": data.genres_by_pid.get(pid, []),
        "thumbnail_url": pe.get("logo_url"),          # UC3: logo_url specifically (identity avatar)
        "deep_link": f"feeds://property/{pid}",
        "score": round(float(score), 4),
        "why_string": why,
        "badge": None,
        "is_live": _is_live(data, latest),
        "card_size": "standard",
        "latest_moment": (
            {k: v for k, v in latest.items() if k != "_event_epoch"} if latest else None
        ),
    }
    return item


def _carousel(cid, rtype, reason_string, data, rows, why_each, now_epoch):
    """Assemble a UC3 carousel dict from candidate ``rows`` [(pid, score), ...]."""
    items = [_home_item(data, pid, sc, why_each, now_epoch) for pid, sc in rows]
    return {
        "carousel_id": cid,
        "carousel_type": _CAROUSEL_TYPE.get(rtype, "editorial"),
        "layout": _CAROUSEL_LAYOUT.get(rtype, "circle"),
        "reason_type": rtype,
        "reason_string": reason_string,
        "item_type": "property",
        "insert_after_index": 0,                      # set by build_home_carousels after selection
        "items": items,
        "total_available": len(items),
        "cache_ttl_seconds": _CACHE_TTL.get(rtype, _DEFAULT_TTL),
    }


def _engaged_signals(data, snap):
    """Derive (top_genre, top_vert, seed_pid, seed_name) from the user's engagement.

    Mirrors build_carousels: top genre / vertical by frequency over reacted+followed; strongest
    seed = the highest-weighted reaction, else any follow.
    """
    followed = set(snap.get("followed", set()))
    reactions = snap.get("reactions", {}) or {}
    reacted = set(reactions.keys())
    engaged = list(reacted) + list(followed)

    gcount = Counter(g for pid in engaged for g in data.genres_by_pid.get(pid, []))
    vcount = Counter(
        C._p(data, pid).get("vertical") for pid in engaged if C._p(data, pid).get("vertical")
    )
    top_genre = gcount.most_common(1)[0][0] if gcount else None
    top_vert = vcount.most_common(1)[0][0] if vcount else None

    if reactions:
        seed = max(reactions, key=lambda p: C.REACTION_W.get(reactions[p], 1.0))
    else:
        seed = next(iter(followed), None)
    seed_name = C._p(data, seed).get("name") if seed else None
    return top_genre, top_vert, seed, seed_name


def build_home_carousels(data, snap, now_epoch, *, carousel_slots=3, carousel_interval=5):
    """Unfollowed-discovery carousels for the UC3 home feed (interleaved into the main stream).

    Surfaces ONLY unfollowed properties as follow-suggestion shelves. Candidate generation is
    reused from carousels.py; assembly follows the UC3 contract (freshness-gated latest_moment,
    insert_after_index interleave hints, per-item is_live / why_string).

    Returns a list of at most ``carousel_slots`` carousel dicts, each with >= 4 items, ordered by
    insertion position. ``insert_after_index`` for the i-th carousel (0-based) is
    ``(i + 1) * carousel_interval - 1``.
    """
    # Defensive clamps: a non-positive interval would emit negative insert_after_index; cap slots.
    carousel_interval = max(1, int(carousel_interval or 5))
    carousel_slots = max(0, min(int(carousel_slots or 3), 20))

    followed = set(snap.get("followed", set()))
    reactions = snap.get("reactions", {}) or {}
    reacted = set(reactions.keys())
    exclude = followed | reacted          # same exclusion as build_carousels: never re-surface
    recent_pids = C._recent_pids(data, now_epoch)   # 30-day candidate gate (reused)

    candidates = []   # ordered (cid, rtype, reason_string, rows, why_each)

    if reacted or followed:
        top_genre, top_vert, seed, seed_name = _engaged_signals(data, snap)

        if seed:
            rows = C._similar(data, [seed], exclude, recent_pids=recent_pids)
            candidates.append((
                f"more_like_{seed}", "similar_seed",
                f"Because you follow {seed_name}", rows, f"Similar to {seed_name}",
            ))
        if top_genre:
            rows = C._trending(data, exclude, genre=top_genre, recent_pids=recent_pids)
            candidates.append((
                f"trending_{top_genre}", "trending",
                f"Trending in {top_genre}", rows, f"Trending in {top_genre} right now",
            ))
        if top_vert:
            rows = C._popular(data, exclude, vert=top_vert, recent_pids=recent_pids)
            candidates.append((
                f"popular_{top_vert}", "popular",
                f"Popular {top_vert}s to discover", rows, f"Popular {top_vert} right now",
            ))
            rows = C._fresh(data, exclude, now_epoch, vert=top_vert, recent_pids=recent_pids)
            candidates.append((
                f"fresh_{top_vert}", "fresh",
                f"New {top_vert}s happening now", rows, f"Recently active {top_vert}",
            ))
    else:
        # cold / thin user: sensible global discovery shelves
        rows = C._trending(data, exclude, recent_pids=recent_pids) or C._popular(
            data, exclude, recent_pids=recent_pids
        )
        candidates.append((
            "trending_now", "trending", "Trending now", rows, "Trending across Feeds.ai",
        ))
        for vert, label in (("movie", "Popular movies"), ("game", "Top games"),
                            ("tv", "Popular shows")):
            rows = C._popular(data, exclude, vert=vert, recent_pids=recent_pids)
            candidates.append((
                f"popular_{vert}", "popular", label, rows, f"Popular {vert} right now",
            ))
        rows = C._fresh(data, exclude, now_epoch, recent_pids=recent_pids)
        candidates.append((
            "new_releases", "fresh", "Happening now", rows, "Recently active",
        ))

    # Assemble, keep only shelves meeting the min bar, cap to carousel_slots, then assign
    # interleave positions in final order.
    out = []
    for cid, rtype, reason_string, rows, why_each in candidates:
        if len(out) >= carousel_slots:
            break
        carousel = _carousel(cid, rtype, reason_string, data, rows, why_each, now_epoch)
        if len(carousel["items"]) >= MIN_ITEMS:
            out.append(carousel)

    for i, carousel in enumerate(out):
        carousel["insert_after_index"] = (i + 1) * carousel_interval - 1

    return out
