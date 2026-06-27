"""carousels.py — labelled horizontal carousels + the full discovery-home response.

Goes a step beyond a fixed carousel set: the carousels are CHOSEN per user from their own top genre,
top vertical, and strongest seed (the title they reacted to most), so two users get different shelves —
not a static "trending_horror". Cold users get sensible global shelves. Each item carries score,
why_string, genres, and a latest_moment freshness hook.

build_home() returns the manager-style envelope (context / request_echo / main_feed / carousels /
debug) plus our extras (genres, upcoming, signal breakdown under debug).
"""
from collections import Counter
from datetime import datetime, timezone

import numpy as np

import ranking

REACTION_W = {"fire": 3.0, "heart": 2.0, "confetti": 1.5}


def _p(data, pid):
    return data.properties.get(pid, {}) or {}


def _genre_index(data):
    if not hasattr(data, "_genre_index"):
        idx = {}
        for pid, gs in data.genres_by_pid.items():
            for g in gs:
                idx.setdefault(g, set()).add(pid)
        data._genre_index = idx
    return data._genre_index


def _pid_by_row(data):
    if not hasattr(data, "_pid_by_row"):
        data._pid_by_row = {row: pid for pid, row in data.emb_row_by_pid.items()}
    return data._pid_by_row


RECENT_SECS = 30 * 86400.0   # P2-4: carousel items must have a moment within 30 days (UC2 AC)
# P2-4: spec carousel_type by our internal reason_type; layout = circle for follow-suggestion avatars.
_CAROUSEL_TYPE = {"similar_seed": "similar_to_followed", "trending": "trending_in_vertical",
                  "new": "new_releases", "popular": "popular_in_vertical"}
_CAROUSEL_LAYOUT = {"similar_seed": "circle"}   # all other content shelves -> "square"


def _recent_pids(data, now_epoch):
    """property_ids with at least one moment within the last 30 days (carousel freshness gate). Cached on
    `data` after first compute (moments are static between reloads) — avoids an O(100k) scan per request.
    The cutoff is anchored at first compute; session drift (<< 30 days) is negligible for the PoC."""
    cached = getattr(data, "_recent_pids_cache", None)
    if cached is not None:
        return cached
    cut = now_epoch - RECENT_SECS
    pids = {m["property_id"] for m in data.moments if (m.get("_event_epoch") or 0) >= cut}
    data._recent_pids_cache = pids
    return pids


def _latest_moment(data, pid):
    ms = data.moments_by_pid.get(pid)
    if not ms:
        return None
    best = max(ms, key=lambda m: (m.get("_event_epoch") or 0))
    return {"moment_id": best["moment_id"], "title": best["title"],
            "event_starts_at": best.get("event_starts_at")}


def _item(data, pid, score, why):
    pe = data.prop_extra(pid)
    return {
        "type": "property",
        "property_id": pid,                                  # P2-4: integer id (client deep-link / follow)
        "entity_id": _p(data, pid).get("entity_id"),
        "name": _p(data, pid).get("name", f"Property {pid}"),
        "vertical": _p(data, pid).get("vertical"),
        "genres": data.genres_by_pid.get(pid, []),
        "thumbnail_url": pe.get("logo_url") or pe.get("cover_url"),   # P2-4 (P2-1 enrichment; null if absent)
        "deep_link": f"feeds://property/{pid}",             # P2-4
        "score": round(float(score), 4),
        "why_string": why,
        "badge": None,                                      # P2-4 (reserved; no per-property badge yet)
        "card_size": "standard",                            # P2-4
        "latest_moment": _latest_moment(data, pid),
    }


# ── candidate pools ───────────────────────────────────────────────────────────
def _filter(data, pid, vert, gset, exclude, recent_pids=None):
    if pid not in data.moments_by_pid:       # spec: carousels exclude zero-moment properties (follow -> see nothing)
        return False
    if recent_pids is not None and pid not in recent_pids:   # P2-4: must have a moment within 30 days
        return False
    if pid in exclude:
        return False
    if vert and _p(data, pid).get("vertical") != vert:
        return False
    if gset is not None and pid not in gset:
        return False
    return True


def _trending(data, exclude, vert=None, genre=None, k=12, recent_pids=None):
    gset = _genre_index(data).get(genre) if genre else None
    rows = [(pid, v.get("trending", 0.0)) for pid, v in (data.entity_scores or {}).items()
            if _filter(data, pid, vert, gset, exclude, recent_pids) and v.get("trending", 0.0) > 0]
    rows.sort(key=lambda kv: -kv[1])
    return rows[:k]


def _popular(data, exclude, vert=None, genre=None, k=12, recent_pids=None):
    gset = _genre_index(data).get(genre) if genre else None
    rows = [(pid, v) for pid, v in (data.influence_by_pid or {}).items()
            if _filter(data, pid, vert, gset, exclude, recent_pids)]
    rows.sort(key=lambda kv: -kv[1])
    hi = rows[0][1] if rows else 1.0
    return [(pid, v / hi) for pid, v in rows[:k]]


def _fresh(data, exclude, now_epoch, vert=None, genre=None, k=12, recent_pids=None):
    gset = _genre_index(data).get(genre) if genre else None
    newest = {}
    for m in data.moments:
        pid = m["property_id"]
        if not _filter(data, pid, vert, gset, exclude, recent_pids):
            continue
        e = m.get("_event_epoch")
        if e is None or e > now_epoch:        # released only (no future)
            continue
        if pid not in newest or e > newest[pid]:
            newest[pid] = e
    rows = sorted(newest.items(), key=lambda kv: -kv[1])[:k]
    return [(pid, 1.0) for pid, _ in rows]


def _similar(data, seed_pids, exclude, k=12, recent_pids=None):
    vecs = [data.embedding_for_pid(p) for p in seed_pids]
    vecs = [v for v in vecs if v is not None]
    if not vecs:
        return []
    c = np.mean(np.vstack(vecs), axis=0)
    n = float(np.linalg.norm(c))
    if n < 1e-9:
        return []
    sims = data.emb @ (c / n)
    pbr = _pid_by_row(data)
    out = []
    for row in np.argsort(-sims):
        pid = pbr.get(int(row))
        if (pid is None or pid in exclude or pid not in data.moments_by_pid
                or (recent_pids is not None and pid not in recent_pids)):   # P2-4: recent only
            continue
        out.append((pid, float(sims[row])))
        if len(out) >= k:
            break
    return out


def _carousel(cid, rtype, rstring, data, rows, why_each, personalized):
    items = [_item(data, pid, sc, why_each) for pid, sc in rows]
    return {"carousel_id": cid, "carousel_type": _CAROUSEL_TYPE.get(rtype, rtype),   # P2-4: spec type
            "reason_type": rtype, "reason_string": rstring,
            "layout": _CAROUSEL_LAYOUT.get(rtype, "square"),    # P2-4: circle (avatars) / square (content)
            "item_type": "property", "personalized": personalized, "items": items,
            "total_available": len(items),       # P2-4: count computed for this shelf (not a broader pool total)
            "cache_ttl_seconds": 300}            # P2-4: client cache hint


# ── carousel selection (the smart bit) ─────────────────────────────────────────
def build_carousels(data, snap, now_epoch, min_items=4):
    followed = set(snap.get("followed", set()))
    reactions = snap.get("reactions", {}) or {}
    reacted = set(reactions.keys())
    exclude = followed | reacted
    recent_pids = _recent_pids(data, now_epoch)   # P2-4: carousel candidates need a moment within 30 days
    out = []

    if reacted or followed:
        # the user's top genre / vertical / strongest seed, derived from what they engaged with
        engaged = list(reacted) + list(followed)
        gcount = Counter(g for pid in engaged for g in data.genres_by_pid.get(pid, []))
        vcount = Counter(_p(data, pid).get("vertical") for pid in engaged if _p(data, pid).get("vertical"))
        top_genre = gcount.most_common(1)[0][0] if gcount else None
        top_vert = vcount.most_common(1)[0][0] if vcount else None
        # strongest seed = highest reaction weight, else a follow
        seed = max(reactions, key=lambda p: REACTION_W.get(reactions[p], 1.0)) if reactions else next(iter(followed), None)
        seed_name = _p(data, seed).get("name") if seed else None

        if seed:
            out.append(_carousel(f"more_like_{seed}", "similar_seed", f"More like {seed_name}",
                                 data, _similar(data, [seed], exclude, recent_pids=recent_pids), f"Similar to {seed_name}", True))
        if top_genre:
            r = _trending(data, exclude, genre=top_genre, recent_pids=recent_pids)
            if len(r) >= min_items:
                out.append(_carousel(f"trending_{top_genre}", "trending", f"Trending in {top_genre}",
                                     data, r, f"Trending in {top_genre} right now", True))
        if top_vert:
            out.append(_carousel(f"fresh_{top_vert}", "new", f"New {top_vert}s for you",
                                 data, _fresh(data, exclude, now_epoch, vert=top_vert, recent_pids=recent_pids), f"Recently released {top_vert}", True))
            out.append(_carousel(f"popular_{top_vert}", "popular", f"Popular {top_vert}s",
                                 data, _popular(data, exclude, vert=top_vert, recent_pids=recent_pids), f"Popular {top_vert} right now", True))
    else:
        # cold-start global shelves
        out.append(_carousel("trending_now", "trending", "Trending now",
                             data, _trending(data, exclude, recent_pids=recent_pids) or _popular(data, exclude, recent_pids=recent_pids), "Trending across Feeds.ai", False))
        for v, label in (("movie", "Popular movies"), ("game", "Top games"), ("tv", "Popular shows")):
            out.append(_carousel(f"popular_{v}", "popular", label,
                                 data, _popular(data, exclude, vert=v, recent_pids=recent_pids), f"Popular {v} right now", False))
        out.append(_carousel("new_releases", "new", "New releases",
                             data, _fresh(data, exclude, now_epoch, recent_pids=recent_pids), "Just released", False))

    # keep only carousels with enough items
    return [c for c in out if len(c["items"]) >= min_items]


# ── the full discovery-home envelope ───────────────────────────────────────────
def _signal_strength(snap):
    reactions = snap.get("reactions", {}) or {}
    s = sum(REACTION_W.get(r, 1.0) for r in reactions.values()) + 1.0 * len(snap.get("followed", set()))
    return round(min(1.0, s / 8.0), 3)   # ~3 strong signals -> near 1.0


def _badge(it):
    """P2-4: derive a main-feed card badge (LIVE / TRENDING / NEW / None) from signals + flags. NOTE:
    on current data trending is ~0 (pre-launch, no engagement) and is_live is always False (no Live Now
    moments in the pool), so most badges resolve to NEW or None — thresholds are tunable."""
    if it.get("is_live"):
        return "LIVE"
    sig = it.get("signals", {}) or {}
    if sig.get("trending", 0.0) >= 0.6:
        return "TRENDING"
    if it.get("upcoming") or sig.get("recency", 0.0) >= 0.7:
        return "NEW"
    return None


def build_home(user_id, data, snap, sort_order="hot", limit=20, offset=0,
               time_window=None, date_range=None, exclude_property_ids=None, seen_ids=None, debug=False):
    now_epoch = datetime.now(timezone.utc).timestamp()
    mode_map = {"trending": "trending", "popular": "hot", "recent": "new",
                "hot": "hot", "new": "new"}
    rank_mode = mode_map.get((sort_order or "hot").lower(), "hot")   # F9: default main feed to personalized hot, not trend-dominant

    exclude = set(exclude_property_ids or []) | set(seen_ids or [])
    items, total, meta = ranking.rank_feed(user_id, snap, ranking_type=rank_mode, limit=limit, offset=offset,
                                           exclude_property_ids=list(exclude), time_window=time_window,
                                           date_range=date_range)
    main_items = []
    for it in items:
        pid = it["property_id"]
        mid = it["moment_id"]
        pe = data.prop_extra(pid)        # P2-1 enrichment (handle/icon) — {} if absent
        me = data.moment_extra(mid)      # P2-1 enrichment (platform/hero/cta) — {} if absent
        main_items.append({
            "type": "moment",
            "moment_id": mid,
            "property_id": pid,                                          # P2-4: integer id
            "entity_id": _p(data, pid).get("entity_id"),
            "property_name": it["property_name"],
            "property_handle": pe.get("handle"),                        # P2-4 (null if no enrich)
            "property_thumbnail_url": pe.get("logo_url") or pe.get("cover_url"),   # P2-4
            "vertical": it["vertical"],
            "title": it["title"],
            "description": it["description"],
            "thumbnail_url": me.get("hero_image_url") or it.get("thumbnail_url"),  # P2-4 (fallback to base col)
            "media_url": it.get("url"),                                 # P2-4
            "media_platform": me.get("media_platform_name"),           # P2-4 (null if no enrich)
            "media_platform_id": me.get("media_platform_id"),          # P2-4 (real id now; null if no enrich)
            "event_starts_at": it.get("event_starts_at"),              # P2-4: real event time (not created_at)
            "genres": it.get("genres", []),
            "upcoming": it.get("upcoming", False),
            "is_live": it.get("is_live", False),                       # P2-2/P2-4
            "viewer_count": None,                                      # P2-4 (live only; not tracked)
            "badge": _badge(it),                                       # P2-4
            "score": it["ranking_score"],
            "why_string": it["reason"],
            "debug_meta": (it["signals"] if debug else None),          # P2-4 (spec key)
        })

    carousels = build_carousels(data, snap, now_epoch)
    followed_n = len(snap.get("followed", set()))
    reacted_n = len(snap.get("reactions", {}) or {})

    return {
        "version": "1.0",
        "endpoint": "discovery-api",
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),       # P2-4: staleness/cache key
        "context": {
            "mode": "global" if meta["cold_start"] else "personalized",   # UC5: cold-start -> "global"
            "signal_strength": _signal_strength(snap),
            "substrate_reachable": bool(meta.get("graph_ok", data.graph_ok)),  # P2-4: degraded-mode flag
            "engine": "v2",                                           # P2-4
            "path": "global" if meta["cold_start"] else "personalized",   # P2-4: spec mirrors mode
            "followed_count": followed_n,
            "reaction_count": reacted_n,
        },
        "request_echo": {
            "sort_order": sort_order, "time_window": time_window, "date_range": date_range,
            "limit": limit, "offset": offset,
            "excluded_property_ids": len(exclude_property_ids or []), "seen_ids": len(seen_ids or []),
        },
        "main_feed": {"items": main_items, "count": len(main_items),
                      "next_offset": (offset + limit) if (offset + limit) < total else None},
        "carousels": carousels,
        "pagination": {"offset": offset, "limit": limit, "total_available": total,   # P2-4
                       "has_more": (offset + limit) < total},
        "debug": ({"candidates": meta["candidates"], "taste_gated": meta["taste_gated"],
                   "after_diversity": meta["after_diversity"], "target_mix": meta.get("target_mix"),
                   "graph_ok": meta["graph_ok"]} if debug else None),
    }
