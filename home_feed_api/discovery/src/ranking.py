"""ranking.py — the discovery feed scorer + modes.

Seven signals (UC2 v1.3), each normalized to 0..1, blended per ranking mode:

  relevance  cosine(property embedding, centroid of the user's followed+liked entity embeddings),
             rescaled from [-1,1] to [0,1]. Liked entities are weighted higher than follows.
             No follows/likes -> relevance = 0 (cold-start redistributes its weight to the rest).
  centrality Neo4j graph influence (PageRank) of the property — S4 proxy until betweenness/edge-count
             from GDS is wired. log1p-compressed then pool min-maxed.
  popularity log1p(views) + real user-engagement lift (entity_scores.popularity) — S5 social proof.
  recency    newness of `event_starts_at` (newer -> higher) + a freshness boost for very-new items.
  trending   real engagement-velocity (trend engine), falling back to a views-velocity proxy.
  proximity  S6 temporal-proximity step-table on the event date: today(<24h)=0 (calendar owns it),
             1-3d=1.0, 4-7d=.8, 1-4wk=.5, 1-3mo=.25, 3-12mo=.1, >12mo=0; past<7d=.6, 7-30d=.2, >30d=0.
  richness   S7 moment-richness from moment_type (P2-1 enrichment): live/release high, patch low; the
             un-enriched default is RICHNESS_DEFAULT. Also yields is_live (moment_type == "Live Now").

Modes (config-driven weights in MODE_WEIGHTS): 'hot' = full UC2 discovery spec weights (all 7 signals);
'new' = recency-dominant; 'trending' = trend-dominant.

Personalization:
  - Positive taste centroid = follows + up-weighted likes; relevance = stretched cosine to it.
  - Negative (Rocchio) feedback: relevance -= DISLIKE_WEIGHT * cosine(item, dislike centroid), so a
    dislike pushes the feed away from that item's whole genre/neighborhood, not just the one title.
  - Calibrated mix: the visible vertical distribution is apportioned to the user's engaged verticals
    (follow/like/dislike) blended with exploration; cold-start -> balanced. This stops the feed from
    collapsing to whichever single vertical happens to score highest.

Hard rules: candidate pool excludes followed / disliked / explicitly-excluded properties; the feed
is de-duplicated to one moment per property/title.

All heavy stages (relevance, graph/pop, rank) are wrapped with obs spans so the response carries a
real `timing_ms`.
"""
import math
import sys
from datetime import datetime, timezone

import numpy as np

from data import Data, timed

# ── config: per-mode signal weights (must each sum to 1.0) ────────────────────
# 'hot' = the FULL UC2 v1.3 discovery moment-stream weights (all 7 signals; S7 moment-richness now has
# data via P2-1 enrichment, so the earlier re-normalization-over-6 is removed). NOTE: this reverts hot
# from the interim (.234 …) values to the raw spec ratios — a deliberate ranking change, not bookkeeping.
# 'new'/'trending' are alternate sort profiles (not in the spec) and carry all 7 keys so the blend never
# KeyErrors. Each row sums to 1.0.
MODE_WEIGHTS = {
    "hot":      {"rel": 0.22, "rec": 0.12, "trend": 0.25, "cent": 0.20, "pop": 0.08, "prox": 0.07, "rich": 0.06},
    "new":      {"rel": 0.10, "rec": 0.50, "trend": 0.10, "cent": 0.08, "pop": 0.05, "prox": 0.12, "rich": 0.05},
    "trending": {"rel": 0.12, "rec": 0.10, "trend": 0.47, "cent": 0.15, "pop": 0.08, "prox": 0.05, "rich": 0.03},
}
DEFAULT_MODE = "hot"

# S7 moment-richness: Databricks moment_type name -> richness weight (0..1). Live/release rank highest;
# patch/maintenance lowest. Un-enriched / unknown moments default to RICHNESS_DEFAULT ("assume average")
# — since raw_rich is NOT min-maxed, this only LIFTS enriched live/release items above the floor. All 23
# known types are mapped so a name never silently falls to the default on current data.
RICHNESS_BY_TYPE = {
    "Live Now": 1.0, "Live Service": 0.9, "Released": 0.9, "Availability": 0.85,
    "Reveal": 0.8, "Broadcast": 0.8, "Scheduled Experience": 0.75, "Competition": 0.75,
    "Session": 0.7, "Window": 0.6, "Inventory Available": 0.6, "Access Granted": 0.6,
    "Announcement": 0.5, "Coverage": 0.5, "Recognition": 0.5, "Bespoke": 0.5,
    "Update": 0.4, "Changes (Content)": 0.4, "Discovered": 0.4, "Created": 0.4,
    "Changes (Cycle)": 0.3, "Changes (Non Content)": 0.1, "Service Health Event": 0.1,
}
RICHNESS_DEFAULT = 0.5

LIKE_WEIGHT = 2.0          # (legacy) liked entities weight in the taste centroid
FOLLOW_W = 1.5             # a followed entity's weight in the taste centroid
# production reaction model: all positive, weighted by intensity (fire > heart > confetti)
REACTION_WEIGHTS = {"fire": 3.0, "heart": 2.0, "confetti": 1.5}
DISLIKE_WEIGHT = 0.6       # Rocchio negative feedback: relevance -= this * sim(item, dislike centroid)
DISLIKE_PENALTY_COLD = 0.35  # no positive taste: demote disliked-neighborhood items in the cold feed
EXPLORE_FRACTION = 0.40    # calibrated mix: blend the user's engaged-vertical mix with this much uniform
DISLIKE_MIX_WEIGHT = 0.4   # a dislike signals interest in the DOMAIN, but less than a follow/like (which
                           # are 1.0) — so it shapes the vertical mix without letting a rejected vertical
                           # dominate it. (The dislike *centroid* still steers WHICH items, separately.)
PER_PROPERTY_CAP = 1       # one moment per property in the feed (kills duplicate-title spam)
FRESHNESS_DAYS = 14        # items newer than this get a recency freshness boost
FRESHNESS_BOOST = 0.15     # additive recency bump for very-new items (pre-normalization headroom)

# TASTE GATE: when a user has a taste vector, rank ONLY within their most-relevant slice, so every
# mode (hot/trending/new) surfaces what is hot/trending/new *within their preferences* — a globally
# hot but off-taste item can never reach the top. Cold-start users (no taste) skip the gate.
TASTE_GATE_FRACTION = 0.30   # keep the top 30% most-relevant candidates as the taste neighborhood
TASTE_GATE_MIN = 400         # ...but always keep at least this many so the feed never starves
REASON_SIM_MIN = 0.40        # min cosine to attribute a result to a specific liked/followed title
RELEVANCE_FLOOR = 0.45       # F4: stretched-relevance floor — drop clearly off-taste items from the taste
                             #     neighborhood so popularity/trend can't lift them above on-taste titles
GATE_MIN_KEEP = 80           # F4: ...but always keep at least this many (top by relevance) so it never starves


# ── time helpers ──────────────────────────────────────────────────────────────
def _parse_dt(s):
    """Parse an ISO-8601 timestamp (handles trailing 'Z'). Returns aware UTC datetime or None."""
    if not s:
        return None
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        # last-ditch: take the date portion
        try:
            dt = datetime.fromisoformat(txt[:10])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _minmax(vals):
    """Min-max normalize a list to 0..1. Constant/empty input -> all zeros."""
    if not vals:
        return []
    lo = min(vals)
    hi = max(vals)
    if hi - lo < 1e-12:
        return [0.0 for _ in vals]
    rng = hi - lo
    return [(v - lo) / rng for v in vals]


def _parse_time_window(s):
    """'24h' / '7d' / '30d' / '2w' / 'last_7d' / bare-number(days) -> max age in DAYS, or None."""
    if not s:
        return None
    t = str(s).strip().lower()
    if t.startswith("last_"):          # P2-4: UC2 spec sends 'last_7d'/'last_30d'
        t = t[5:]
    try:
        if t.endswith("h"):
            return float(t[:-1]) / 24.0
        if t.endswith("d"):
            return float(t[:-1])
        if t.endswith("w"):
            return float(t[:-1]) * 7.0
        return float(t)
    except ValueError:
        return None


def _parse_date_range(s):
    """'YYYY-MM-DD..YYYY-MM-DD' -> (start_dt, end_dt) aware UTC, or None."""
    if not s or ".." not in str(s):
        return None
    a, b = str(s).split("..", 1)
    start = _parse_dt(a.strip())
    end = _parse_dt(b.strip())
    if start is None or end is None:
        return None
    return (start, end)


# ── taste centroids (positive + negative) and similarity scoring ──────────────
@timed("vector_search", "build_centroid")
def _centroid(data, weighted_pids):
    """L2-normalized weighted centroid of a set of property embeddings.

    `weighted_pids` is an iterable of (property_id, weight). Properties with no embedding are
    skipped. Returns a unit (1024,) float32 vector, or None when no usable embedding is present
    (the caller treats None as 'no signal').
    """
    vecs, weights = [], []
    for pid, w in weighted_pids:
        v = data.embedding_for_pid(pid)
        if v is not None:
            vecs.append(v)
            weights.append(float(w))
    if not vecs:
        return None
    M = np.vstack(vecs)
    w = np.asarray(weights, dtype=np.float32).reshape(-1, 1)
    c = (M * w).sum(axis=0) / max(float(w.sum()), 1e-9)
    n = float(np.linalg.norm(c))
    if n < 1e-9:
        return None
    return (c / n).astype(np.float32)


@timed("vector_search", "score_similarity")
def _similarity_scores(data, named_centroids, pids):
    """For each named centroid, per-property cosine(centroid, embedding) min-max stretched to 0..1.

    The expensive part is the per-pid embedding-row gather and the matrix slice; those are done ONCE
    and shared across all centroids (taste + dislike), then each centroid is a cheap mat-vec.

    The corpus embeddings are L2-normalized and overwhelmingly positive-cosine, so raw cosines cluster
    in a narrow band; stretching across the pool restores the dynamic range a mode weight needs. A
    DEGENERATE pool (all cosines equal -> range ~0) carries no discriminative signal, so it maps to 0.0
    (neutral) rather than 1.0 — a dislike that cannot tell items apart must not penalize them all.
    None centroid or missing embedding -> 0.0. Returns {name: {pid: score}}.
    """
    pids = list(pids)
    out = {name: {pid: 0.0 for pid in pids} for name in named_centroids}
    rows, have_pids = [], []
    for pid in pids:
        r = data.emb_row_by_pid.get(pid)
        if r is not None:
            rows.append(r)
            have_pids.append(pid)
    if not rows:
        return out
    E = data.emb[rows]                                  # (n, dim) gathered + sliced once, shared
    for name, centroid in named_centroids.items():
        if centroid is None:
            continue
        cos = E @ centroid                              # (n,) cosines in [-1, 1] (unit vectors)
        lo = float(cos.min())
        hi = float(cos.max())
        rng = hi - lo
        stretched = np.zeros_like(cos) if rng < 1e-9 else (cos - lo) / rng
        dest = out[name]
        for pid, s in zip(have_pids, stretched):
            dest[pid] = float(s)
    return out


# ── the main entry point ──────────────────────────────────────────────────────
@timed("engine", "rank_feed")
def rank_feed(user_id, snap, ranking_type="hot", limit=20, offset=0, exclude_property_ids=None,
              sort_order=None, time_window=None, date_range=None):
    """Build a re-ranked discovery feed of moments for one user.

    Returns (page_items, total_candidates_after_dedup_cap, meta).
    `snap` is the UserStore snapshot (followed/liked/disliked property-id sets).

    Extensions (manager spec): `time_window` ('24h'/'7d'/...) and `date_range`
    ('YYYY-MM-DD..YYYY-MM-DD') filter the candidate pool by `event_starts_at`; `sort_order`
    ('desc'|'asc'|'newest'|'oldest') controls the final ordering (default 'desc' by ranking_score).
    """
    data = Data.get()
    mode = (ranking_type or DEFAULT_MODE).lower()
    if mode not in MODE_WEIGHTS:
        mode = DEFAULT_MODE
    weights = MODE_WEIGHTS[mode]

    followed = snap["followed"]
    reactions = snap.get("reactions", {})          # {pid: 'heart'/'fire'/'confetti'} — all positive
    reacted = set(reactions.keys())
    watched_moments = snap.get("watched_moments", set())     # spec: suppress these consumed MOMENTS (property kept)
    watched_props = snap.get("watched_properties", set())    # legacy fallback: whole property (pre-moment_id watches)
    exclude = set(exclude_property_ids or [])
    now = datetime.now(timezone.utc)

    # 1) Candidate pool: published moments whose property the user has NOT already engaged with
    #    (not followed AND not reacted-to) and is NOT in the caller's exclusion list. Reacted items
    #    are dropped HERE so the feed never re-shows something you just hearted/fired/confetti'd — but
    #    the reaction is still fed into the taste centroid below, so we keep surfacing *similar* items.
    #    (Production reaction model has no dislike, so nothing is hard-excluded as a NEGATIVE signal.)
    candidates = [
        m for m in data.moments
        if m["property_id"] not in followed
        and m["property_id"] not in reacted
        and m["moment_id"] not in watched_moments        # moment-level: only the consumed moment is dropped
        and m["property_id"] not in watched_props         # legacy fallback: whole property (no moment_id logged)
        and m["moment_id"] not in data.suppressed_moment_ids  # P2-2: patch/maintenance types never in public feed
        and m["property_id"] not in exclude
    ]
    no_taste_ids = not (followed or reacted)
    now_epoch = now.timestamp()

    # 1b) optional filters (manager spec): date_range (absolute window) + time_window (recency),
    #     evaluated against the pre-parsed event epoch so the request path parses no timestamps.
    dr = _parse_date_range(date_range)
    tw_days = _parse_time_window(time_window)
    if dr or tw_days is not None:
        dr_lo = dr[0].timestamp() if dr else None
        dr_hi = dr[1].timestamp() if dr else None
        tw_lo = now_epoch - tw_days * 86400.0 if tw_days is not None else None
        kept = []
        for m in candidates:
            e = m.get("_event_epoch")
            if dr and (e is None or not (dr_lo <= e <= dr_hi)):
                continue
            if tw_lo is not None and (e is None or e < tw_lo):
                continue
            kept.append(m)
        candidates = kept

    # 1c) Temporal-scope HARD filters (UC2 §2): the calendar feed owns "today"; far-future and
    #     confirmed-dead stale long-tail moments don't belong in discovery. Suppress only on CONFIRMED
    #     signals (NEVER on missing entity_scores data) + a min-count starve-guard so the pool can't
    #     collapse when engagement coverage is sparse (local data has only ~141 entity_scores rows).
    TODAY_SECS = 86400.0
    YEAR_SECS = 365.0 * 86400.0
    STALE_SECS = 30.0 * 86400.0
    STALE_GUARD_MIN = 2000
    escores_tmp = getattr(data, "entity_scores", None) or {}
    _pre_temporal = len(candidates)
    scoped = []
    for m in candidates:
        e = m.get("_event_epoch")
        if e is not None:
            delta = e - now_epoch                   # >0 = future, <0 = past
            if 0 <= delta < TODAY_SECS:             # event starts within next 24h -> calendar owns "today"
                continue
            if delta > YEAR_SECS:                   # >12 months in the future -> not discovery
                continue
            if -delta > STALE_SECS:                 # published >30 days ago...
                es = escores_tmp.get(m["property_id"])
                # ...suppress ONLY when engagement data EXISTS and confirms zero trending velocity.
                # Missing entity_scores -> unknown -> KEEP (don't over-suppress a sparse long tail).
                if es is not None and es.get("trending", 0.0) == 0.0:
                    continue
        scoped.append(m)
    if len(scoped) >= STALE_GUARD_MIN:
        candidates = scoped
        temporal_suppressed = _pre_temporal - len(scoped)
    else:
        temporal_suppressed = 0                     # guard reverted — suppression would starve the feed

    if not candidates:
        return [], 0, {"mode": mode, "cold_start": no_taste_ids, "candidates": 0,
                       "temporal_suppressed": temporal_suppressed, "cold_capped": 0,
                       "filters": {"time_window": time_window, "date_range": date_range}}

    # 1d) Cold-start freshness cap (UC5 AC6): a brand-new user's first feed must feel CURRENT — no moment
    #     older than 14 days. Future/upcoming events and unknown-date items are kept; starve-guarded so a
    #     sparse pool never collapses (revert + warn instead of emptying the feed).
    cold_capped = 0
    if no_taste_ids:
        COLD_MAX_AGE = 14.0 * 86400.0
        COLD_GUARD_MIN = 200
        fresh = [m for m in candidates
                 if m.get("_event_epoch") is None or (now_epoch - m["_event_epoch"]) <= COLD_MAX_AGE]
        if len(fresh) >= COLD_GUARD_MIN:
            cold_capped = len(candidates) - len(fresh)
            candidates = fresh
        else:
            import logging
            logging.getLogger(__name__).warning(
                "[rank_feed] UC5 14-day cap REVERTED: only %d fresh < COLD_GUARD_MIN=%d",
                len(fresh), COLD_GUARD_MIN)

    # 2) Taste signal: ONE positive centroid = follows + reactions, each reaction weighted by intensity
    #    (fire > heart > confetti). No negative centroid — the production reaction model has no dislike.
    taste_weighted = ([(pid, FOLLOW_W) for pid in followed]
                      + [(pid, REACTION_WEIGHTS.get(rt, 1.5)) for pid, rt in reactions.items()])
    taste_centroid = _centroid(data, taste_weighted)
    cand_pids = {m["property_id"] for m in candidates}
    sims = _similarity_scores(data, {"taste": taste_centroid}, cand_pids)
    rel_by_pid = sims["taste"]
    # Personalize only if a usable taste centroid actually exists. A user may follow/like only
    # embedding-less properties (centroid None); treating that as "has taste" would forfeit the whole
    # relevance weight on an all-zero signal, so we fall back to the cold-start blend instead.
    has_taste = taste_centroid is not None

    # 2b) TASTE GATE — restrict the candidate pool to the user's taste neighbourhood (their top-relevance
    #     slice) BEFORE ranking. This is what makes hot/trending/new operate *within* the user's
    #     preferences: a globally-hot item the user has no affinity for is dropped here and can never
    #     reach the top. Cold-start (no taste) keeps the full pool. Dislike-only users have a dislike
    #     centroid but no taste centroid -> they also skip the gate (nothing positive to gate toward).
    gate_applied = False
    if has_taste and len(candidates) > TASTE_GATE_MIN:
        ranked = sorted(candidates, key=lambda m: rel_by_pid.get(m["property_id"], 0.0), reverse=True)
        keep_n = max(TASTE_GATE_MIN, int(len(candidates) * TASTE_GATE_FRACTION))
        gated = ranked[:keep_n]
        # F4: absolute relevance floor — drop clearly off-taste items (stretched rel < RELEVANCE_FLOOR) so
        # popularity/trend can't float them above genuinely on-taste titles. Starve-guard: if the floor
        # leaves too few, fall back to the top-by-relevance slice so the feed never empties.
        floored = [m for m in gated if rel_by_pid.get(m["property_id"], 0.0) >= RELEVANCE_FLOOR]
        candidates = floored if len(floored) >= GATE_MIN_KEEP else ranked[:GATE_MIN_KEEP]
        gate_applied = True

    # 3) Raw per-moment signals (centrality / popularity / recency / trending + 0..1 proximity), then
    #    pool-normalize the four min-max signals. Proximity is already a 0..1 step score -> used as-is.
    raw_cent, raw_pop, raw_rec, raw_trend, raw_prox, raw_rich = _raw_signals(data, candidates, now_epoch)
    cent_n = _minmax(raw_cent)
    pop_n = _minmax(raw_pop)
    rec_n = _minmax(raw_rec)
    trend_n = _minmax(raw_trend)
    prox_n = raw_prox                        # S6 is already 0..1 — do NOT min-max it
    rich_n = raw_rich                        # S7 is already 0..1 — do NOT min-max it

    # 4) Blend per mode (7 signals; UC2 v1.3). Richness lives on the moment dict (m["_richness"]), so the
    #    scored tuple is unchanged — the page-loop reads it from m, avoiding tuple-index churn.
    scored = []
    for i, m in enumerate(candidates):
        pid = m["property_id"]
        rel = rel_by_pid.get(pid, 0.0)
        cent, pop, rec, trend, prox, rich = cent_n[i], pop_n[i], rec_n[i], trend_n[i], prox_n[i], rich_n[i]
        if has_taste:
            score = (weights["rel"] * rel + weights["cent"] * cent + weights["pop"] * pop
                     + weights["trend"] * trend + weights["rec"] * rec + weights["prox"] * prox
                     + weights["rich"] * rich)
            # NOTE: reacted properties are EXCLUDED from `candidates` upstream (step 1), so this loop
            # never sees a reacted pid — the old "+0.05 reacted bonus" here was dead code and is removed.
        else:
            # No positive taste (cold start): redistribute the relevance weight across ALL other signals.
            # s is computed GENERICALLY over every non-rel weight so adding a signal can't desync it.
            # WARNING: the numerator below lists the non-rel signals EXPLICITLY — if an 8th signal is ever
            # added to MODE_WEIGHTS, add its term to BOTH this numerator and the has_taste branch above.
            s = sum(w for k, w in weights.items() if k != "rel")
            score = (weights["cent"] * cent + weights["pop"] * pop + weights["trend"] * trend
                     + weights["rec"] * rec + weights["prox"] * prox + weights["rich"] * rich) / max(s, 1e-9)
        scored.append((score, rel, cent, pop, rec, trend, prox, m))

    # 5) Sort. Default 'desc' = ranking_score (tie-break newer first); sort_order can override.
    so = (sort_order or "desc").lower()
    if so == "asc":
        scored.sort(key=lambda t: t[0])
    elif so in ("newest", "new"):
        scored.sort(key=lambda t: t[7].get("_age", 1e9))            # smallest age (newest) first
    elif so in ("oldest", "old"):
        scored.sort(key=lambda t: t[7].get("_age", 1e9), reverse=True)
    else:                                                            # 'desc' (default)
        scored.sort(key=lambda t: (t[0], -t[7].get("_age", 1e9)), reverse=True)

    # 6) De-duplicate (one moment per property), then CALIBRATE the vertical mix so the feed reflects
    #    the user's engaged verticals plus exploration (cold-start -> balanced), instead of collapsing
    #    to whichever single vertical scores highest. An explicit sort_order is the user asking for a
    #    specific order, so we honour it and skip calibration. Calibration only apportions the prefix
    #    the caller actually pages (offset+limit), not the whole tail.
    capped = _dedup(scored)
    total = len(capped)
    if so in ("asc", "newest", "new", "oldest", "old"):
        page_pool = capped
        target_mix = None
    else:
        target_mix = _target_mix(data, followed, reacted, capped)
        page_pool = _calibrate(capped, target_mix, offset + limit)

    # 7) Paginate, then attach rank + rounded score.
    page = page_pool[offset: offset + limit]
    items = []
    for idx, (score, rel, cent, pop, rec, trend, prox, m) in enumerate(page):
        items.append({
            "rank": offset + idx + 1,
            "moment_id": m["moment_id"],
            "title": m["title"],
            "property_id": m["property_id"],
            "property_name": m["property_name"],
            "vertical": m["vertical"],
            "description": m["description"],
            "thumbnail_url": m["thumbnail_url"],
            "url": m["url"],
            "views": m["views"],
            "created_at": m["created_at"],
            # P2-4: real event time for the response (falls back to created_at; 0% null in current data).
            "event_starts_at": m.get("event_starts_at") or m.get("created_at"),
            # clamp the surfaced score to >=0 (the negative-feedback term can push a raw score below 0;
            # ordering already happened above, so clamping the display value is monotonic-safe).
            "ranking_score": round(max(0.0, float(score)), 6),
            # metadata for the card (from the Neo4j graph)
            "genres": data.genres_by_pid.get(m["property_id"], []),
            "themes": data.themes_by_pid.get(m["property_id"], []),
            # whether this moment's event is still in the future (not yet released)
            "upcoming": bool(m.get("_upcoming", False)),
            # P2-2: live moment (moment_type "Live Now") — drives the LIVE badge (surfaced in P2-4)
            "is_live": bool(m.get("_is_live", False)),
            # natural-language "why you're seeing this"
            "reason": _reason(data, m["property_id"], rel, cent, pop, rec, trend, prox,
                              followed, reactions, weights, has_taste, m.get("_upcoming", False),
                              m.get("_is_live", False)),
            # explainability extras (handy for the demo UI; not required by the contract)
            "signals": {
                "relevance": round(float(rel), 4),
                "centrality": round(float(cent), 4),
                "popularity": round(float(pop), 4),
                "recency": round(float(rec), 4),
                "trending": round(float(trend), 4),
                "proximity": round(float(prox), 4),
                "richness": round(float(m.get("_richness", RICHNESS_DEFAULT)), 4),
            },
        })

    meta = {"mode": mode, "cold_start": not has_taste, "candidates": len(candidates),
            "taste_gated": gate_applied, "temporal_suppressed": temporal_suppressed,
            "cold_capped": cold_capped,
            "after_diversity": total, "graph_ok": data.graph_ok,
            "has_reactions": bool(reacted),
            "target_mix": ({v: round(p, 3) for v, p in target_mix.items()} if target_mix else None),
            "sort_order": so, "time_window": time_window, "date_range": date_range}
    return items, total, meta


def _reason(data, pid, rel, cent, pop, rec, trend, prox, followed, reactions, weights, has_taste, upcoming=False, is_live=False):
    """Build a natural-language 'why you're seeing this' line for one result.

    Attributes the result to the single reacted/followed title most similar to it (when the match is
    strong enough), and to the global signal (trending/popular/new) that most drove its rank.
    `reactions` is a {pid: 'heart'/'fire'/'confetti'} map. `upcoming`=True means the item is not yet
    released (future event) so the recency phrasing becomes "coming soon" instead of "a recent release".
    """
    vert = (data.properties.get(pid, {}) or {}).get("vertical", "title")

    # dominant global signal by weighted contribution. Centrality folds into "popular" (both are
    # social/structural proof); proximity folds into "new" (an imminent event reads as "coming soon").
    contrib = {"trending": weights["trend"] * trend,
               "popular": weights["pop"] * pop + weights["cent"] * cent,
               "new": weights["rec"] * rec + weights["prox"] * prox}
    top = max(contrib, key=contrib.get) if any(contrib.values()) else "popular"
    new_phrase = "coming soon" if upcoming else "a recent release"
    sig_phrase = {"trending": "trending right now", "popular": "popular right now",
                  "new": new_phrase}[top]
    if is_live:                              # P2-2: a live moment always reads as live, regardless of blend
        sig_phrase = "live right now"

    # best-matching seed (a title the user reacted to / followed) by cosine
    best_name, best_verb, best_sim, best_spid = None, None, -1.0, None
    emb = data.embedding_for_pid(pid)
    if has_taste and emb is not None:
        for spid, rt in reactions.items():
            se = data.embedding_for_pid(spid)
            if se is not None:
                s = float(emb @ se)
                if s > best_sim:
                    best_sim, best_name, best_verb, best_spid = s, (data.properties.get(spid, {}) or {}).get("name"), rt, spid
        for spid in followed:
            se = data.embedding_for_pid(spid)
            if se is not None:
                s = float(emb @ se)
                if s > best_sim:
                    best_sim, best_name, best_verb, best_spid = s, (data.properties.get(spid, {}) or {}).get("name"), "follow", spid

    _emoji = {"heart": "❤️", "fire": "🔥", "confetti": "🎉"}
    if best_name and best_sim >= REASON_SIM_MIN:
        verb = "you follow" if best_verb == "follow" else f"you reacted {_emoji.get(best_verb, '')} to"
        # F2 fix: "a similar {vert}" only reads correctly when the recommended item and the SEED share a
        # vertical. Cross-vertical (e.g. a podcast surfaced off a game you follow) -> drop the clause
        # instead of printing the wrong vertical ("Elden Ring — a similar podcast").
        seed_vert = (data.properties.get(best_spid, {}) or {}).get("vertical")
        if seed_vert and seed_vert == vert:
            return f"Because {verb} {best_name} — a similar {vert} — and it's {sig_phrase}."
        return f"Because {verb} {best_name} — and it's {sig_phrase}."
    # F3 fix: no strong seed match -> state the global signal honestly; do NOT over-claim "and it
    # matches your taste" (the old has_taste branch asserted taste-match even on sub-threshold items).
    return f"{sig_phrase.capitalize()}."


@timed("engine", "raw_signals")
def _raw_signals(data, candidates, now_epoch):
    """Compute raw (un-normalized) centrality / popularity / recency / trending + the already-0..1
    temporal-proximity and moment-richness per candidate moment, using the pre-parsed `_event_epoch`
    (set at load) so the hot path does no timestamp parsing. Returns 6 parallel lists aligned to
    `candidates`. Richness + is_live are also stored on each moment dict (like _upcoming/_age) so the
    page-loop surfaces them without growing the scored tuple."""
    raw_cent, raw_pop, raw_rec, raw_trend, raw_prox, raw_rich = [], [], [], [], [], []
    escores = getattr(data, "entity_scores", None) or {}
    for m in candidates:
        pid = m["property_id"]
        es = escores.get(pid)
        # signed age in days: >0 = already released (past), <0 = upcoming/unreleased (future event).
        # The OLD code clamped future to 0, which wrongly made unreleased "Coming Soon" items look
        # brand-new and top the "New" feed. Now we use the absolute distance from now so a title
        # releasing in 4 months no longer ranks as fresher than one released yesterday.
        e = m.get("_event_epoch")
        if e is not None:
            signed_age = (now_epoch - e) / 86400.0
            eff_age = abs(signed_age)
            m["_upcoming"] = signed_age < -0.5      # event is in the future -> not yet released
            m["_age"] = eff_age
        else:
            signed_age = None
            eff_age = None
            m["_upcoming"] = False
            m["_age"] = 1e9

        # S4 centrality (proxy): Neo4j PageRank influence, log1p-compressed (heavily right-skewed),
        # pool min-maxed downstream. Kept SEPARATE from popularity so each carries its own spec weight.
        infl = data.influence_by_pid.get(pid, 0.0)
        raw_cent.append(math.log1p(max(0.0, infl)))

        # S5 popularity: log1p(views) + real engagement lift (entity_scores.popularity, already 0..1).
        # The 0.2 / 1.5 sub-weights preserve the original views-vs-engagement balance WITHIN popularity.
        views_pop = math.log1p(max(0, m["views"]))
        es_pop = es["popularity"] if es else 0.0
        raw_pop.append(0.2 * views_pop + 1.5 * es_pop)

        # S2 recency peaks at release and decays BOTH ways (newer past = higher; far future = lower),
        # so unreleased titles months away no longer dominate. The freshness boost is given ONLY to
        # just-RELEASED items (0..FRESHNESS_DAYS in the past), never to upcoming ones.
        if eff_age is None:
            rec = 0.0
        else:
            rec = 1.0 / (1.0 + eff_age / 30.0)
            if 0.0 <= signed_age <= FRESHNESS_DAYS:
                rec += FRESHNESS_BOOST
        raw_rec.append(rec)

        # S3 trending: real engagement-velocity from the trend engine (Phase 4) when present; this is
        # the views-velocity proxy's working replacement (the proxy was dead — `views` is all-null).
        # Fallback to the proxy for un-engaged properties so the signal still exists pre-events.
        if es is not None:
            raw_trend.append(es["trending"])
        else:
            a = eff_age if eff_age is not None else 365.0
            raw_trend.append(max(0, m["views"]) / (a + 2.0))

        # S6 temporal proximity: a step lookup on the event date (already 0..1 -> NOT min-maxed). The
        # future branch (signed_age < 0) earns the upcoming-event score; today (<24h out) = 0 (calendar
        # owns it); the past branch (>=0, incl. just-released today) decays. Missing date -> 0.0. The
        # append is UNCONDITIONAL so the list stays positionally aligned with the other four.
        if signed_age is None:
            raw_prox.append(0.0)
        elif signed_age < 0:                   # future / unreleased
            d = -signed_age                    # days until the event
            if d < 1:      raw_prox.append(0.0)     # today (<24h) — calendar feed owns it
            elif d < 4:    raw_prox.append(1.0)     # 1-3 days
            elif d < 7:    raw_prox.append(0.8)     # 4-7 days
            elif d < 28:   raw_prox.append(0.5)     # 1-4 weeks
            elif d < 90:   raw_prox.append(0.25)    # 1-3 months
            elif d < 365:  raw_prox.append(0.1)     # 3-12 months
            else:          raw_prox.append(0.0)     # >12 months
        else:                                  # past / already released (incl. just-released today)
            if signed_age < 7:    raw_prox.append(0.6)    # past < 7 days
            elif signed_age < 30: raw_prox.append(0.2)    # past 7-30 days
            else:                 raw_prox.append(0.0)    # past > 30 days

        # S7 moment-richness (P2-1 enrichment): moment_type -> 0..1 (live/release high, patch low).
        # Stored on the moment (like _upcoming/_age) so the page-loop surfaces richness + is_live WITHOUT
        # growing the scored tuple. Un-enriched moments (~45%) default to RICHNESS_DEFAULT.
        # DATA NOTE: the current discovery pool overlaps only "Released"/"Reveal" types — the 36k "Live
        # Now" rows live on a separate live-rail surface and are absent from public_moments.csv, so
        # is_live is always False on this export. The flag + the _reason "live right now" branch are
        # infrastructure that activates AUTOMATICALLY if Live Now moments ever enter the discovery pool.
        mtype = data.moment_extra(m["moment_id"]).get("moment_type_name")
        rich = RICHNESS_BY_TYPE.get(mtype, RICHNESS_DEFAULT)
        m["_richness"] = rich
        m["_is_live"] = (mtype == "Live Now")
        raw_rich.append(rich)

    return raw_cent, raw_pop, raw_rec, raw_trend, raw_prox, raw_rich


def _dedup(scored):
    """Keep at most PER_PROPERTY_CAP moments per property, preserving best-first order. With the cap at
    1 this collapses every multi-moment property ("Crimson Desert x3", "Diablo IV on PC / Xbox / Xbox
    One" are one property each) to a single card. We deliberately do NOT dedup across properties by
    title — two distinct entities may legitimately share a title (a remake, a game and its adaptation),
    and dropping one could starve a vertical the calibration is trying to fill."""
    per_property = {}
    out = []
    for tup in scored:
        pid = tup[7]["property_id"]
        if per_property.get(pid, 0) >= PER_PROPERTY_CAP:
            continue
        per_property[pid] = per_property.get(pid, 0) + 1
        out.append(tup)
    return out


def _target_mix(data, followed, reacted, pool):
    """Target vertical proportions for calibration, over the verticals present in `pool` (the post-dedup
    scored tuples).

    Any interaction with a vertical signals interest in that *domain* (a movie-watcher who dislikes one
    movie is still a movie-watcher; the dislike centroid handles *which* movies). Follows/likes count
    fully; a dislike counts DISLIKE_MIX_WEIGHT (< 1) so a rejected vertical shapes the mix without
    dominating it. The engaged mix is blended with EXPLORE_FRACTION of uniform so the user always sees
    some discovery. No signal at all -> uniform across present verticals (balanced cold-start, which is
    what stops a fresh user getting 0 games / 7 podcasts).

    Returns {vertical: proportion} over the verticals present in `pool`.
    """
    present = set()
    for tup in pool:
        present.add(tup[7]["vertical"] or "other")
    if not present:
        return {}
    uniform = 1.0 / len(present)

    engaged = {}
    for pids, weight in ((followed, 1.0), (reacted, 1.0)):
        for pid in pids:
            p = data.properties.get(pid)
            v = (p["vertical"] if p else None) or "other"
            if v in present:
                engaged[v] = engaged.get(v, 0.0) + weight
    total = sum(engaged.values())
    if total <= 0:
        return {v: uniform for v in present}
    return {
        v: (1.0 - EXPLORE_FRACTION) * (engaged.get(v, 0.0) / total) + EXPLORE_FRACTION * uniform
        for v in present
    }


def _calibrate(scored, target, need):
    """Calibrated re-rank via largest-remainder apportionment: emit items so the prefix approximates
    `target` vertical proportions while keeping each vertical score-ordered. Only the first `need`
    items (= offset+limit, the slice the caller actually pages) are produced; the long tail the user
    never sees is left untouched, keeping this O(need * verticals) rather than O(pool).

    A vertical drops out of the rotation the moment its bucket empties, so no quota is wasted scanning
    exhausted verticals. When that happens the remaining verticals share the freed slots in proportion
    to their own weights (the prefix the user sees is unaffected in practice — buckets rarely empty
    within the first page).
    """
    if need is None or need <= 0:
        need = len(scored)
    if not target:
        return scored[:need]
    buckets = {}
    for tup in scored:
        buckets.setdefault(tup[7]["vertical"] or "other", []).append(tup)
    active = [v for v in buckets if buckets[v]]
    if len(active) <= 1:
        return scored[:need]

    wsum = sum(max(0.0, target.get(v, 0.0)) for v in active) or 1.0
    weights = {v: max(0.0, target.get(v, 0.0)) / wsum for v in active}

    placed = {v: 0 for v in active}
    out = []
    while active and len(out) < need:
        n = len(out) + 1
        # available vertical with the largest unmet quota (ties -> higher target share)
        pick = max(active, key=lambda v: (weights[v] * n - placed[v], weights[v]))
        out.append(buckets[pick].pop(0))
        placed[pick] += 1
        if not buckets[pick]:
            active.remove(pick)
    return out
