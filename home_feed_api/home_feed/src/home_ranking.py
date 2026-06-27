"""home_ranking.py — the FOLLOW-GATED ranker for the UC3 home feed.

Lives in the SEPARATE home_feed/ folder and reuses the discovery engine (discovery/src)
as a library via the bootstrap below — the discovery package is never modified.

The home feed is the INVERSE of discovery. Discovery surfaces moments from properties the
user has NOT engaged with (it *drops* followed/reacted properties from the candidate pool and
gates hard on taste). The home feed is the opposite: its candidate pool is moments from the
properties the user FOLLOWS, and nothing else. The user already chose these follows, so:

  * KEEP followed + reacted properties (they ARE the feed) — never drop a property because it
    was reacted to.
  * Relevance still *scores* (so the most on-taste followed moments float up) but it never
    *cuts* — there is no taste-gate, no relevance floor, no calibration/EXPLORE apportionment,
    and no cold-start 14-day freshness cap. The only removals are explicit suppressions
    (blocked/dismissed properties, excluded verticals, and already-seen / done / watched /
    globally-suppressed moments).

We REUSE discovery/src/ranking.py's primitives by import: ``_centroid`` (taste centroid),
``_similarity_scores`` (stretched cosine relevance), ``_raw_signals`` (the 6 raw per-moment
signal lists), ``_minmax`` (pool normalization), ``_dedup`` (one moment per property),
``_reason`` (the natural-language "why"). We do NOT modify ranking.py.

Public entry point: ``rank_home``.
"""
# --- engine bootstrap: reuse the discovery engine (discovery/src) as a library -----
import os as _os, sys as _sys

_DISC_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "discovery", "src")
if _DISC_SRC not in _sys.path:
    _sys.path.insert(0, _DISC_SRC)
# -----------------------------------------------------------------------------------
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np  # noqa: F401  (kept available for callers / future signal math)

import ranking

# ── UC3 home weights ───────────────────────────────────────────────────────────
# Renormalized over the 7 COMPUTABLE signals. The UC3 spec also lists S8 dwell at 7%, but we
# have NO dwell data, so it is dropped and its mass is redistributed by renormalizing the rest.
#   raw: rel .30, rec .22, prox .15, trend .08, rich .08, cent .05, pop .05  (sum = .93)
# Each raw weight is divided by 0.93 so the surviving 7 weights sum to 1.0.
_RAW_HOME_WEIGHTS = {
    "rel": 0.30, "rec": 0.22, "prox": 0.15,
    "trend": 0.08, "rich": 0.08, "cent": 0.05, "pop": 0.05,
}
_HOME_NORM = 0.93
HOME_WEIGHTS = {k: v / _HOME_NORM for k, v in _RAW_HOME_WEIGHTS.items()}

# Taste centroid weights (mirror discovery so the home taste vector matches discovery's).
FOLLOW_W = ranking.FOLLOW_W
REACTION_WEIGHTS = ranking.REACTION_WEIGHTS
RICHNESS_DEFAULT = ranking.RICHNESS_DEFAULT
SIGNAL_STRENGTH_DIVISOR = 8.0   # follows + reaction weights >= this -> full signal strength


def _now_dt(now: Optional[str]) -> datetime:
    """Pin 'now' to an ISO-8601 string when given (handles trailing 'Z'); else server UTC time."""
    if now:
        dt = ranking._parse_dt(now)
        if dt is not None:
            return dt
    return datetime.now(timezone.utc)


def _date_range_bounds(date_range: Any) -> Optional[tuple]:
    """Normalize ``date_range`` to (lo_epoch, hi_epoch) or None.

    Accepts an object/dict with ``start``/``end`` ISO strings, a 'YYYY-MM-DD..YYYY-MM-DD'
    string (reusing ranking._parse_date_range), or None. Either bound may be None (open-ended).
    """
    if date_range is None:
        return None
    start = end = None
    if isinstance(date_range, dict):
        start = ranking._parse_dt(date_range.get("start"))
        end = ranking._parse_dt(date_range.get("end"))
    elif isinstance(date_range, str):
        parsed = ranking._parse_date_range(date_range)
        if parsed:
            start, end = parsed
    else:  # duck-typed object with .start / .end attributes
        start = ranking._parse_dt(getattr(date_range, "start", None))
        end = ranking._parse_dt(getattr(date_range, "end", None))
    if start is None and end is None:
        return None
    return (start.timestamp() if start else None, end.timestamp() if end else None)


def _signal_strength(followed: set, reactions: dict) -> float:
    """0..1 confidence in the user's taste from their follows + reaction intensities.

    A user with several follows and strong reactions has a stronger signal than a 1-follow user.
    Capped at 1.0 (>= SIGNAL_STRENGTH_DIVISOR worth of engagement = full strength).
    """
    rweight = sum(REACTION_WEIGHTS.get(rt, 1.5) for rt in (reactions or {}).values())
    return min(1.0, (rweight + len(followed)) / SIGNAL_STRENGTH_DIVISOR)


def _home_reason(name, vertical, is_live, upcoming, rel, cent, pop, rec, trend, prox, weights):
    """Home-feed 'why' line. The moment is FROM a property the user FOLLOWS, so the reason
    states that relationship directly, then adds the dominant non-relevance signal as colour.

    We deliberately do NOT reuse discovery's ``ranking._reason`` here: on a follow-gated feed it
    scans the followed set for the most-similar seed, which for a followed item is the item's OWN
    property (self-cosine = 1.0), producing "Because you follow X — a similar X — and it's ...".
    That self-attribution reads as broken on every card. This stays honest: it never claims the
    item was discovered via similarity to something else.
    """
    label = name or "a property you follow"
    if is_live:
        return f"{label} is live now"
    if upcoming:
        return f"Coming soon from {label}"
    contrib = {
        "trending": weights["trend"] * trend,
        "new": weights["rec"] * rec + weights["prox"] * prox,
        "popular": weights["pop"] * pop + weights["cent"] * cent,
    }
    top = max(contrib, key=contrib.get) if any(v > 0 for v in contrib.values()) else "new"
    if top == "trending":
        return f"Trending now — from {label}"
    if top == "popular":
        return f"From {label} — popular right now"
    return f"New from {label}"


def rank_home(user_id, snap, data, *, limit=20, offset=0, sort_order="relevance",
              time_window=None, date_range=None, seen_ids=None, done_ids=None,
              dismissed_property_ids=None, blocked_property_ids=None,
              excluded_verticals=None, excluded_platforms=None, now=None):
    """Build the FOLLOW-GATED home feed of moments for one user.

    Returns ``(items, total, meta)``. ``snap`` is the UserStore snapshot
    (followed / reactions / watched_moments / watched_properties). ``data`` is the Data singleton.

    Home-mode is the inverse of discovery: candidates are moments of FOLLOWED properties only;
    followed/reacted properties are KEPT; relevance scores but never cuts; the only removals are
    explicit property/vertical/moment suppressions. See module docstring.
    """
    followed = set(snap.get("followed", set()) or set())
    reactions = dict(snap.get("reactions", {}) or {})
    n_follows = len(followed)
    sig_strength = _signal_strength(followed, reactions)

    # Cold-start: no follows -> the home feed has no candidate pool at all. Return empty.
    if not followed:
        return [], 0, {"follow_count": 0, "signal_strength": sig_strength, "cold_start": True,
                       "candidates": 0, "zero_moment_follows": 0}

    # 0) Normalize all suppression inputs to sets/None.
    seen_set = set(seen_ids or [])                      # MOMENT ids
    done_set = set(done_ids or [])                      # MOMENT ids
    dismissed_props = set(dismissed_property_ids or [])  # PROPERTY ids (soft)
    blocked_props = set(blocked_property_ids or [])      # PROPERTY ids (hard)
    excluded_verts = {str(v).strip().lower() for v in (excluded_verticals or [])}
    watched_moments = set(snap.get("watched_moments", set()) or set())   # MOMENT ids
    watched_props = set(snap.get("watched_properties", set()) or set())  # legacy WATCH (no moment_id)
    suppressed_mids = getattr(data, "suppressed_moment_ids", set()) or set()
    excluded_plats = {str(p).strip().lower() for p in (excluded_platforms or [])}
    prop_excluded = blocked_props | dismissed_props
    # union of all moment-level suppressions (seen/done/watched/global) — filtered on moment_id
    moment_suppressed = seen_set | done_set | watched_moments | suppressed_mids
    # Legacy property-level WATCH (events logged with no moment_id) -> suppress that property's
    # moments at MOMENT level. A followed property must never be dropped wholesale, only its
    # already-consumed content; this matches discovery's legacy fallback without removing the follow.
    for _wpid in watched_props:
        for _wm in data.moments_by_pid.get(_wpid, []):
            moment_suppressed.add(_wm.get("moment_id"))

    now_dt = _now_dt(now)
    now_epoch = now_dt.timestamp()

    # time_window ('last_7d'/'last_30d'/...) -> max age in days; date_range -> absolute epoch bounds.
    tw_days = ranking._parse_time_window(time_window)
    tw_lo = now_epoch - tw_days * 86400.0 if tw_days is not None else None
    dr = _date_range_bounds(date_range)
    dr_lo, dr_hi = (dr if dr else (None, None))

    # 1) FOLLOW-GATE: candidate pool = moments of FOLLOWED properties ONLY. Walk each followed
    #    property's own moment list (never scan all of data.moments). Apply property-, vertical-
    #    and moment-level suppressions inline. zero_moment_follows = follows that contribute none.
    candidates = []
    zero_moment_follows = 0
    for pid in followed:
        if pid in prop_excluded:
            continue
        ms = data.moments_by_pid.get(pid, [])
        kept_any = False
        for m in ms:
            mid = m.get("moment_id")
            if mid in moment_suppressed:                       # MOMENT-level (never property_id)
                continue
            vert = (m.get("vertical") or "")
            if excluded_verts and str(vert).strip().lower() in excluded_verts:
                continue
            if excluded_plats:                                 # UC3 Story 2: "never show me <platform>"
                _plat = data.moment_extra(mid).get("media_platform_name") or ""
                if str(_plat).strip().lower() in excluded_plats:
                    continue
            e = m.get("_event_epoch")
            if tw_lo is not None and (e is None or e < tw_lo):  # recency window
                continue
            if dr_lo is not None and (e is None or e < dr_lo):  # absolute range (lower bound)
                continue
            if dr_hi is not None and (e is None or e > dr_hi):  # absolute range (upper bound)
                continue
            candidates.append(m)
            kept_any = True
        if not ms or not kept_any:
            zero_moment_follows += 1

    base_meta = {"follow_count": n_follows, "signal_strength": sig_strength,
                 "cold_start": False, "candidates": len(candidates),
                 "zero_moment_follows": zero_moment_follows}

    if not candidates:
        return [], 0, base_meta

    # 2) Relevance: taste centroid from follows (FOLLOW_W) + reactions (fire/heart/confetti),
    #    scored as stretched cosine over the candidate properties. centroid None -> relevance 0
    #    for every candidate (a user following only embedding-less properties still gets a feed,
    #    just driven by the other six signals — relevance never CUTS here).
    taste_weighted = ([(pid, FOLLOW_W) for pid in followed]
                      + [(pid, REACTION_WEIGHTS.get(rt, 1.5)) for pid, rt in reactions.items()])
    taste_centroid = ranking._centroid(data, taste_weighted)
    has_taste = taste_centroid is not None
    cand_pids = {m["property_id"] for m in candidates}
    if has_taste:
        sims = ranking._similarity_scores(data, {"taste": taste_centroid}, cand_pids)
        rel_by_pid = sims.get("taste", {})
    else:
        rel_by_pid = {}

    # 3) Raw per-moment signals. _raw_signals now returns 6 lists (cent,pop,rec,trend,prox,rich);
    #    be DEFENSIVE about its arity in case it reverts to 5. Also writes _richness/_is_live/
    #    _upcoming/_age onto each moment dict (used below for the contract fields).
    sig = ranking._raw_signals(data, candidates, now_epoch)
    rc, rp, rr, rt = sig[0], sig[1], sig[2], sig[3]
    rx = sig[4]
    rich = sig[5] if len(sig) > 5 else [0.0] * len(candidates)

    cent_n = ranking._minmax(rc)
    pop_n = ranking._minmax(rp)
    rec_n = ranking._minmax(rr)
    trend_n = ranking._minmax(rt)
    prox_n = rx        # proximity is already 0..1 — do NOT min-max
    rich_n = rich      # richness is already 0..1 — do NOT min-max

    # 4) Blend with HOME_WEIGHTS. Relevance always contributes (0 when no taste centroid). The
    #    scored tuple mirrors discovery's shape so _dedup (which keys off tup[7]) works unchanged.
    w = HOME_WEIGHTS
    scored = []
    for i, m in enumerate(candidates):
        pid = m["property_id"]
        rel = rel_by_pid.get(pid, 0.0)
        cent, pop, rec, trend, prox, rh = (cent_n[i], pop_n[i], rec_n[i], trend_n[i],
                                           prox_n[i], rich_n[i])
        score = (w["rel"] * rel + w["rec"] * rec + w["prox"] * prox + w["trend"] * trend
                 + w["rich"] * rh + w["cent"] * cent + w["pop"] * pop)
        scored.append((score, rel, cent, pop, rec, trend, prox, m))

    # 5) Sort. _raw_signals (step 3) has already written _age = abs(days from now) onto every
    #    moment (1e9 when the event date is unknown), so we sort on that — matching discovery's
    #    own newest/oldest convention (rank_feed uses _age too). Default = score desc, tie-break
    #    newer first (smaller _age). 'recent' = nearest-to-now event first regardless of score.
    so = (sort_order or "relevance").lower()
    if so == "recent":
        scored.sort(key=lambda t: t[7].get("_age", 1e9))                 # smallest _age (newest) first
    else:                                              # 'relevance' (default) / anything else
        scored.sort(key=lambda t: (t[0], -t[7].get("_age", 1e9)), reverse=True)

    # 6) Dedup to one moment per property, then paginate. Relevance never cuts; the full deduped
    #    list is the total.
    capped = ranking._dedup(scored)
    total = len(capped)
    page = capped[offset: offset + limit]

    items = []
    for idx, (score, rel, cent, pop, rec, trend, prox, m) in enumerate(page):
        pid = m["property_id"]
        mid = m["moment_id"]
        extra = data.moment_extra(mid) or {}
        mtype = extra.get("moment_type_name")
        is_live = (mtype == "Live Now")
        rich_val = float(m.get("_richness", ranking.RICHNESS_BY_TYPE.get(mtype, RICHNESS_DEFAULT)))
        reason = _home_reason(m.get("property_name"), m.get("vertical"), is_live,
                              bool(m.get("_upcoming", False)), rel, cent, pop, rec, trend, prox, w)
        items.append({
            "rank": offset + idx + 1,
            "moment_id": mid,
            "property_id": pid,
            "property_name": m.get("property_name"),
            "vertical": m.get("vertical"),
            "title": m.get("title"),
            "description": m.get("description"),
            "url": m.get("url"),
            "event_starts_at": m.get("event_starts_at"),
            "score": round(max(0.0, float(score)), 6),   # clamp >=0 (matches discovery; >1 impossible)
            "reason": reason,
            "is_live": bool(is_live),
            "richness": round(rich_val, 4),
            "upcoming": bool(m.get("_upcoming", False)),
            "signals": {
                "relevance": round(float(rel), 4),
                "centrality": round(float(cent), 4),
                "popularity": round(float(pop), 4),
                "recency": round(float(rec), 4),
                "trending": round(float(trend), 4),
                "proximity": round(float(prox), 4),
                "richness": round(rich_val, 4),
            },
        })

    meta = dict(base_meta)
    meta["candidates"] = len(candidates)
    return items, total, meta
