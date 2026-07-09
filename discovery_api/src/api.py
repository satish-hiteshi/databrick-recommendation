"""FastAPI serving layer for the discovery-api (Endpoint 2) — port 8030.

  POST /discovery/feed  {user_id, sort_order, time_window/date_range, limit, offset, property_ids,
                         seen_ids, debug, now}  -> the v1.0 feed envelope (main feed + carousels).
  GET  /discovery/health  -> versions + data-source mode + substrate reachability.

Wraps the EXISTING engine (engine.DiscoveryEngine) — no ranking/assembly/why logic here. Mirrors
Endpoint 1's FastAPI patterns (agent_recs/src/api.py). The discovery package uses relative imports, so
run it as a PACKAGE module from the repo root (NOT --app-dir):

  ./.venv/bin/uvicorn discovery_api.src.api:app --host 0.0.0.0 --port 8030
"""

from __future__ import annotations

import sys
import threading
import time
from collections import Counter
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# central identity — the composite (profile_key + media_source_guid) every response item must emit.
_REPO_ROOT = Path(__file__).resolve().parents[4]     # src → discovery_api → local_code → E2 → ROOT
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from shared import identity as _ident   # noqa: E402

from . import config, timeutil
from .substrate_guard import assert_substrate


def _composite(entity_id) -> dict:
    """entity_id → {"profile_key", "media_source_guid"} for the response; {} if it can't be derived."""
    if not entity_id:
        return {}
    try:
        return _ident.composite_of(entity_id)
    except ValueError:
        return {}


def _canon_exclusions(property_ids) -> List[str]:
    """Canonicalise the inbound exclusion list to hashable/sortable STRING refs (so the bundle cache key
    and downstream sets stay valid). A composite dict / entity_id collapses to its entity_id string here
    (no graph I/O); a bare source_id keeps its string form and is resolved against the graph later by
    resolve_inbound_id. Composite dicts missing a guid are dropped."""
    out: List[str] = []
    for v in (property_ids or []):
        eid = _ident.coerce_to_entity_id(v)         # entity_id | composite → entity_id (no I/O); bare int → None
        if eid is not None:
            out.append(eid)
        elif isinstance(v, dict):
            continue                                # unresolvable composite (no guid) → drop
        else:
            out.append(str(v).strip())              # bare source_id → its string (resolved later vs the graph)
    return out
from .candidates import RequestContext
from .data_access import CsvDataSource, SubstrateClient, get_data_source
from .engine import DiscoveryEngine
from .feed.blend import V2FeedBuilder
from .feed.profile import build_profile
from .feed.session_store import MultiSessionOverlay, SessionStore
from .feed.taste_profile import build_taste_profile
from .ranking import PopularityIndex, ScoringWeights

DISCOVERY_PORT = 8030
ANON_USER_ID = -1                          # sentinel for absent/unknown user_id → cold-start
_FULL_FEED_LIMIT = 1_000_000               # build the WHOLE main feed; the API date-filters + paginates
# sort_order RE-WEIGHTS the existing blend via a per-request ScoringWeights passed to the scorer (P5.1:
# NO global mutation, NO lock — concurrent requests with different sort_order can't interfere).
# trending = the balanced config default; recent = recency-dominant; popular = popularity-dominant.
# Numbers are identical to P5's presets, so scores are unchanged.
def _build_presets():
    base = ScoringWeights.from_config()
    return {
        "trending": base,
        "recent":   base.with_overrides(w_popularity=0.3, w_recency=3.0, w_velocity=0.2),
        "popular":  base.with_overrides(w_popularity=3.0, w_recency=0.3, w_velocity=0.5),
    }
WEIGHT_PRESETS = _build_presets()


# ── request model (the verified contract) ──────────────────────────────
class SortOrder(str, Enum):
    recent = "recent"
    popular = "popular"
    trending = "trending"


class DateRange(BaseModel):
    start: str
    end: str


class FeedRequest(BaseModel):
    user_id: Optional[int] = None                       # int DB id (NOT a Frontegg UUID); None → cold-start anon
    sort_order: SortOrder = SortOrder.trending
    time_window: Optional[str] = None                   # "last_7d" | "last_30d" | null
    date_range: Optional[DateRange] = None              # {start, end} ISO — filters main-feed moments
    limit: int = config.MAIN_FEED_PAGE_SIZE
    offset: int = 0
    # EXCLUSION list (opposite of Endpoint 1). POST composite-key migration this accepts, per element:
    #   an entity_id string ("Movie:119163"), a composite {profile_key|vertical, media_source_guid},
    #   or (backward-compat) a bare source_id int — resolved against the graph, dropped-with-warning if it
    #   collides across verticals (send the composite/entity_id to disambiguate).
    property_ids: Optional[List[Union[int, str, dict]]] = None
    seen_ids: Optional[List[int]] = None                # moment ids already shown → suppressed
    debug: bool = False
    now: Optional[str] = None                           # ISO; else config.DEFAULT_NOW_ISO / wall-clock
    engine: Optional[str] = None                        # "v1" | "v2"; None → config.V2_DEFAULT_ENGINE (?engine= overrides)
    session_id: Optional[str] = None                    # interactive demo: build the feed for THIS session's live taste (forces v2)


# ── lazy engine state (load CSVs once) ──────────────────────────────────
class _CountingSubstrate:
    """Wraps SubstrateClient, counting calls for the debug block. Thread-safe — calls now fire concurrently."""
    def __init__(self, inner): self.inner, self.calls, self._lock = inner, 0, threading.Lock()
    def reset(self):
        with self._lock: self.calls = 0
    def _bump(self):
        with self._lock: self.calls += 1
    def vector_neighbors(self, *a, **k): self._bump(); return self.inner.vector_neighbors(*a, **k)
    def vector_retrieve(self, *a, **k): self._bump(); return self.inner.vector_retrieve(*a, **k)
    def graph_similar(self, *a, **k): self._bump(); return self.inner.graph_similar(*a, **k)
    def graph_score_within(self, *a, **k): self._bump(); return self.inner.graph_score_within(*a, **k)
    def graph_structured(self, *a, **k): self._bump(); return self.inner.graph_structured(*a, **k)  # v2 content/exploration


class _State:
    def __init__(self):
        self.ds = get_data_source().load()   # CsvDataSource (mode=csv, default) | LiveDataSource (mode=live)
        self.pop = PopularityIndex.from_data_source(self.ds)
        self.raw_substrate = SubstrateClient()
        self.counter = _CountingSubstrate(self.raw_substrate)
        self.engine_full = DiscoveryEngine(self.ds, substrate=self.counter, popularity=self.pop)
        self.engine_global = DiscoveryEngine(self.ds, substrate=None, popularity=self.pop)  # substrate-down fallback
        # v2 engine (selectable beside v1): reuses ds/pop/counting-substrate; cold-start fallback REUSES engine_global
        self.v2 = V2FeedBuilder(self.ds, substrate=self.counter, pop=self.pop, v1_engine=self.engine_global)
        # interactive "build your own taste" demo: a live session overlay + its own v2 builder (caches per session uid)
        self.session_store = SessionStore()
        self.session_overlay = MultiSessionOverlay(self.ds, self.session_store)
        self.v2_session = V2FeedBuilder(self.session_overlay, substrate=self.counter, pop=self.pop)
        self._up_cache = (0.0, False)

    def invalidate_session(self, uid: int):
        self.v2_session.profile_cache.invalidate(uid)
        self.v2_session.bundle_cache.invalidate()
    def substrate_up(self) -> bool:
        ts, val = self._up_cache
        if time.time() - ts < 15:                       # cache reachability ~15s
            return val
        try:
            val = self.raw_substrate.is_up()
        except Exception:
            val = False
        self._up_cache = (time.time(), val)
        return val


_STATE: Optional[_State] = None
_STATE_LOCK = threading.Lock()


def _state() -> _State:
    global _STATE
    if _STATE is None:
        with _STATE_LOCK:
            if _STATE is None:
                _STATE = _State()
    return _STATE


# ── serialization helpers (adapt the engine objects to the v1.0 envelope) ──
def _genres(ds, entity_id):
    e = ds.get_entity(entity_id)
    if not e:
        return []
    return ds.get_podcast_categories(entity_id) if e.vertical == "podcast" else e.canonical_genres


def _item_debug(source_pool, signals):
    return {"source_pool": source_pool,
            "raw_signals": {"semantic": signals.get("semantic"), "recency": signals.get("recency"),
                            "normalized_influence": signals.get("influence"),
                            "velocity": signals.get("velocity"), "suppression": signals.get("suppression")},
            "final_score": signals.get("final")}


def _moment_item(fi, debug):
    d = {"type": "moment", "moment_id": fi.moment_id, "entity_id": fi.entity_id, **_composite(fi.entity_id),
         "property_name": fi.property_name, "vertical": fi.vertical, "title": fi.title,
         "description": fi.description, "event_starts_at": fi.event_starts_at,
         "media_platform_id": fi.media_platform_id, "score": round(fi.score, 4), "why_string": fi.why_string}
    if debug:
        d["debug"] = _item_debug(fi.source_pool, fi.debug.get("signals", {}))
    return d


def _property_item(ci, ds, debug):
    d = {"type": "property", "entity_id": ci.entity_id, **_composite(ci.entity_id), "name": ci.property_name,
         "vertical": ci.vertical,
         "genres": _genres(ds, ci.entity_id), "score": round(ci.score, 4), "why_string": ci.why_string,
         "latest_moment": ci.latest_moment.to_dict() if ci.latest_moment else None}
    if debug:
        d["debug"] = _item_debug(ci.source_pool, ci.debug.get("signals", {}))
    return d


def _date_bounds(req: FeedRequest, now):
    if req.date_range:
        return timeutil.parse_ts(req.date_range.start), timeutil.parse_ts(req.date_range.end)
    days = {"last_7d": 7, "last_30d": 30}.get(req.time_window or "")
    return (now - timedelta(days=days), now) if days else (None, None)


def _date_filter(items, lo, hi):
    if lo is None and hi is None:
        return items
    out = []
    for it in items:
        ts = timeutil.parse_ts(it.event_starts_at)
        if ts is None or (lo and ts < lo) or (hi and ts > hi):
            continue
        out.append(it)
    return out


# ── v2 engine path (selectable; SAME v1.0 envelope, v2 debug breakdown) ──────
def _v2_moment_item(fi, debug):
    """Serialize a main-feed moment. Handles BOTH the v2 three-signal debug and the v1-shaped debug a
    cold-start fallback feed carries (so the envelope is valid either way)."""
    d = {"type": "moment", "moment_id": fi.moment_id, "entity_id": fi.entity_id, **_composite(fi.entity_id),
         "property_name": fi.property_name, "vertical": fi.vertical, "title": fi.title,
         "description": fi.description, "event_starts_at": fi.event_starts_at,
         "media_platform_id": fi.media_platform_id, "score": round(fi.score, 4), "why_string": fi.why_string}
    if debug:
        s = fi.debug or {}
        if "signals" in s:                      # cold-start fallback = v1 DiscoveryFeed item
            d["debug"] = _item_debug(fi.source_pool, s.get("signals", {}))
        else:                                   # v2 three-signal breakdown
            d["debug"] = {"source_pool": fi.source_pool, "taste_match": s.get("taste_match"),
                          "trending_velocity": s.get("trending_velocity"), "recency": s.get("recency"),
                          "collaborative": s.get("collaborative"), "cluster_id": s.get("cluster_id"),
                          "final_score": s.get("final_score"),
                          "raw_signals": {"semantic": s.get("semantic"), "recency": s.get("recency"),
                                          "normalized_influence": s.get("influence"),
                                          "velocity": s.get("velocity"), "suppression": s.get("suppression")}}
    return d


def _v2_property_item(ci, ds, debug):
    d = {"type": "property", "entity_id": ci.entity_id, **_composite(ci.entity_id), "name": ci.property_name,
         "vertical": ci.vertical,
         "genres": _genres(ds, ci.entity_id), "score": round(ci.score, 4), "why_string": ci.why_string,
         "latest_moment": ci.latest_moment.to_dict() if ci.latest_moment else None}
    if debug:
        s = ci.debug or {}
        d["debug"] = _item_debug(ci.source_pool, s.get("signals", {})) if "signals" in s \
            else {"source_pool": ci.source_pool, **s}
    return d


def _v2_feed(st, req, now, build_uid, dbg, builder=None):
    """engine=v2: build via a V2FeedBuilder and return the SAME v1.0 envelope (v2 debug when debug=true).
    builder defaults to st.v2 (base CSV); the interactive session path passes st.v2_session (live overlay)."""
    builder = builder or st.v2
    reachable = st.substrate_up()
    st.counter.reset()
    t0 = time.time()
    feed, meta = builder.build(build_uid, now=now, limit=_FULL_FEED_LIMIT, offset=0,
                               seen_ids=req.seen_ids or [], excluded_property_ids=_canon_exclusions(req.property_ids))
    timing_ms = round((time.time() - t0) * 1000, 1)

    lo, hi = _date_bounds(req, now)                       # SAME date filter + pagination as v1
    filtered = _date_filter(feed.main_feed, lo, hi)
    page = filtered[req.offset:req.offset + req.limit]
    next_offset = req.offset + req.limit if (req.offset + req.limit) < len(filtered) else None
    profile = build_profile(build_uid, builder.ds)        # followed_count (cheap; overlay for session)

    debug_block = None
    if dbg:
        pools = Counter(i.source_pool for i in feed.main_feed)
        for c in feed.carousels:
            pools.update(i.source_pool for i in c.items)
        debug_block = {
            "engine": "v2", "path": meta.get("path"), "pools_built": dict(pools),
            "exploration_fraction": meta.get("exploration_fraction"), "global_backfill": meta.get("global_backfill"),
            "bundle_cache": meta.get("bundle_cache"), "n_retrieve_calls": meta.get("n_retrieve_calls"),
            "profile_cache": builder.profile_cache.stats(), "bundle_cache_stats": builder.bundle_cache.stats(),
            "timing_ms": timing_ms, "substrate_calls": st.counter.calls, "substrate_reachable": reachable,
            "note_sort_order": "v2 honors its config three-signal blend; sort_order is echoed but not re-weighted (V2-P7)",
        }
    return {
        "version": "1.0", "endpoint": "discovery-api", "user_id": req.user_id, "generated_at": now.isoformat(),
        "context": {"mode": feed.mode, "followed_count": len(profile.followed_entity_ids),
                    "signal_strength": feed.signal_strength, "substrate_reachable": reachable, "engine": "v2"},
        "request_echo": {"sort_order": req.sort_order.value, "time_window": req.time_window,
                         "date_range": req.date_range.dict() if req.date_range else None,
                         "limit": req.limit, "offset": req.offset,
                         "excluded_property_ids": len(req.property_ids or []), "seen_ids": len(req.seen_ids or [])},
        "main_feed": {"items": [_v2_moment_item(i, dbg) for i in page], "count": len(page), "next_offset": next_offset},
        "carousels": [{"carousel_id": c.carousel_id, "reason_type": c.reason_type.value,
                       "reason_string": c.reason_string, "item_type": c.item_type,
                       "items": [_v2_property_item(it, st.ds, dbg) for it in c.items]}
                      for c in feed.carousels if c.items],
        "debug": debug_block,
    }


# ── app ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Feeds.ai Discovery API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _substrate_guard_on_startup():
    """FAIL LOUD at startup if E2 is pointed at the wrong vector/graph SERVICE (stale-substrate guard).
    E2 talks to the substrate ONLY over HTTP, so the guard validates the services behind
    config.VECTOR_API_URL / GRAPH_API_URL. SUBSTRATE_CHECK=0 skips it (handled inside assert_substrate)."""
    assert_substrate()


@app.post("/discovery/feed")
def discovery_feed(req: FeedRequest, debug: bool = Query(False), engine: Optional[str] = Query(None)):
    """Build a personalised discovery feed (main feed + carousels) for the user. No NL query.
    engine selector: ?engine= (query) > req.engine (body) > config.V2_DEFAULT_ENGINE; **v2 is the committed
    default** (config resolves it; DISCOVERY_LEGACY_V1=1 restores v1 in full)."""
    try:
        st = _state()
        dbg = bool(req.debug or debug)
        now = timeutil.parse_ts(req.now) if req.now else timeutil.now()
        build_uid = req.user_id if req.user_id is not None else ANON_USER_ID

        # interactive demo: build the feed for THIS session's live taste (forces v2 over the session overlay)
        if req.session_id:
            return _v2_feed(st, req, now, st.session_store.uid(req.session_id), dbg, builder=st.v2_session)

        # ── ENGINE SELECTOR — v2 is the committed default (config.V2_DEFAULT_ENGINE); v1 below is
        #    byte-identical to before and is restored in full by DISCOVERY_LEGACY_V1=1 ──
        if (engine or req.engine or config.V2_DEFAULT_ENGINE or "v2").lower() == "v2":
            return _v2_feed(st, req, now, build_uid, dbg)

        ctx = RequestContext(now=now, limit=_FULL_FEED_LIMIT, offset=0,
                             seen_moment_ids=set(req.seen_ids or []),
                             excluded_property_ids=_canon_exclusions(req.property_ids))

        reachable = st.substrate_up()
        engine = st.engine_full if reachable else st.engine_global
        weights = WEIGHT_PRESETS[req.sort_order.value]   # per-request ScoringWeights (no global mutation/lock)
        st.counter.reset()

        t0 = time.time()
        feed = engine.build_feed(build_uid, ctx, weights=weights)
        timing_ms = round((time.time() - t0) * 1000, 1)

        # date filter (main-feed moments) + API-level pagination
        lo, hi = _date_bounds(req, now)
        filtered = _date_filter(feed.main_feed, lo, hi)
        page = filtered[req.offset:req.offset + req.limit]
        next_offset = req.offset + req.limit if (req.offset + req.limit) < len(filtered) else None

        profile = build_profile(build_uid, st.ds)        # for followed_count (cheap)

        debug_block = None
        if dbg:
            pools = Counter(i.source_pool for i in feed.main_feed)
            for c in feed.carousels:
                pools.update(i.source_pool for i in c.items)
            debug_block = {
                "pools_built": dict(pools),               # items contributed per source pool (post-assembly)
                "weights_used": {"W_POPULARITY": weights.w_popularity, "W_RECENCY": weights.w_recency,
                                 "W_VELOCITY": weights.w_velocity, "W_SEMANTIC": weights.w_semantic,
                                 "PERSONAL_WEIGHT_MAX": weights.personal_weight_max,
                                 "sort_order": req.sort_order.value},
                "timing_ms": timing_ms,
                "substrate_calls": st.counter.calls,
                "substrate_reachable": reachable,
            }

        return {
            "version": "1.0", "endpoint": "discovery-api",
            "user_id": req.user_id, "generated_at": now.isoformat(),
            "context": {"mode": feed.mode, "followed_count": len(profile.followed_entity_ids),
                        "signal_strength": feed.signal_strength,
                        "substrate_reachable": reachable},
            "request_echo": {"sort_order": req.sort_order.value, "time_window": req.time_window,
                             "date_range": req.date_range.dict() if req.date_range else None,
                             "limit": req.limit, "offset": req.offset,
                             "excluded_property_ids": len(req.property_ids or []),
                             "seen_ids": len(req.seen_ids or [])},
            "main_feed": {"items": [_moment_item(i, dbg) for i in page],
                          "count": len(page), "next_offset": next_offset},
            "carousels": [{"carousel_id": c.carousel_id, "reason_type": c.reason_type.value,
                           "reason_string": c.reason_string, "item_type": c.item_type,
                           "items": [_property_item(it, st.ds, dbg) for it in c.items]}
                          for c in feed.carousels if c.items],
            "debug": debug_block,
        }
    except Exception as e:  # never 500 silently — return a structured error (substrate-down already degrades)
        return JSONResponse(status_code=500, content={"version": "1.0", "endpoint": "discovery-api",
                                                      "error": f"{type(e).__name__}: {e}"})


# ── interactive "build your own taste" demo (live session engagement → live feed) ──
class SessionRef(BaseModel):
    session_id: str

class FollowReq(BaseModel):
    session_id: str
    property_id: int

class ReactReq(BaseModel):
    session_id: str
    moment_id: int


def _name(ds, eid):
    e = ds.get_entity(eid)
    return e.name if e else eid


def _prop_card(ds, entity_id):
    """A followable property: id + name + genres + a latest moment (the thing you can REACT to)."""
    e = ds.get_entity(entity_id)
    if e is None:
        return None
    ms = ds.get_moments_for_property(entity_id)
    latest = ms[0] if ms else None
    genres = ds.get_podcast_categories(entity_id) if e.vertical == "podcast" else e.canonical_genres
    return {"entity_id": entity_id, **_composite(entity_id),
            "property_id": ds.entity_id_to_property_id(entity_id),   # legacy source_id (ambiguous); prefer composite
            "name": e.name,
            "vertical": e.vertical, "genres": genres[:4],
            "latest_moment": ({"moment_id": latest.moment_id, "title": latest.title,
                               "event_starts_at": latest.event_starts_at.isoformat() if latest.event_starts_at else None}
                              if latest else None)}


def _session_profile(st, sid, now):
    prof = build_taste_profile(st.session_store.uid(sid), now, st.session_overlay)
    return {"mode": prof.mode, "signal_strength": prof.signal_strength, "n_follows": prof.n_follows,
            "n_reactions": prof.n_reactions, "vertical_percentages": prof.vertical_percentages,
            "top_genres": [{"genre": g, "weight": round(w, 3)} for g, w in prof.top_genres[:6]],
            "top_keywords": [{"keyword": k, "weight": round(w, 3)} for k, w in prof.top_keywords[:8]],
            "clusters": [{"cluster_id": c.cluster_id, "label": c.label, "dominant_vertical": c.dominant_vertical,
                          "cluster_share": c.cluster_share, "size": c.size,
                          "top_genres": [g for g, _ in c.top_genres[:4]],
                          "reps": [_name(st.ds, e) for e in c.top_representative_member_entity_ids]}
                         for c in prof.clusters]}


def _me_payload(st, sid, now):
    follows = []
    for pid, ts in st.session_store.follows(sid):
        eid = st.ds.property_id_to_entity_id(pid)
        card = _prop_card(st.ds, eid) if eid else None
        if card:
            card["followed_at"] = ts.isoformat()
            follows.append(card)
    reactions = []
    for mid, ts in st.session_store.reactions(sid):
        m = st.ds.get_moment(mid)
        if m:
            reactions.append({"moment_id": mid, "entity_id": m.entity_id, "title": m.title,
                              "property_name": _name(st.ds, m.entity_id), "reacted_at": ts.isoformat()})
    return {"session_id": sid, "user_id": st.session_store.uid(sid),
            "follows": follows, "reactions": reactions, "profile": _session_profile(st, sid, now)}


@app.get("/discovery/search")
def discovery_search(q: str = Query(..., min_length=1), vertical: Optional[str] = Query(None),
                     limit: int = Query(24, ge=1, le=60)):
    """Name-search followable properties (so you can pick content to follow/react to)."""
    st = _state()
    ql = q.lower()
    verts = [vertical] if vertical else list(config.VERTICALS)
    out = []
    for v in verts:
        for e in st.ds.get_entities_by_vertical(v):
            if ql in e.name.lower() and st.ds.entity_id_to_property_id(e.entity_id):
                card = _prop_card(st.ds, e.entity_id)
                if card:
                    out.append(card)
                if len(out) >= limit:
                    break
        if len(out) >= limit:
            break
    return {"query": q, "count": len(out), "results": out}


@app.post("/discovery/follow")
def discovery_follow(req: FollowReq):
    st = _state()
    eid = st.ds.property_id_to_entity_id(req.property_id)
    if not eid or st.ds.get_entity(eid) is None:
        return JSONResponse(status_code=404, content={"error": f"property {req.property_id} not found/served"})
    st.session_store.follow(req.session_id, req.property_id, timeutil.now())
    st.invalidate_session(st.session_store.uid(req.session_id))
    return _me_payload(st, req.session_id, timeutil.now())


@app.post("/discovery/unfollow")
def discovery_unfollow(req: FollowReq):
    st = _state()
    st.session_store.unfollow(req.session_id, req.property_id)
    st.invalidate_session(st.session_store.uid(req.session_id))
    return _me_payload(st, req.session_id, timeutil.now())


@app.post("/discovery/react")
def discovery_react(req: ReactReq):
    st = _state()
    if st.ds.get_moment(req.moment_id) is None:
        return JSONResponse(status_code=404, content={"error": f"moment {req.moment_id} not found"})
    st.session_store.react(req.session_id, req.moment_id, timeutil.now())
    st.invalidate_session(st.session_store.uid(req.session_id))
    return _me_payload(st, req.session_id, timeutil.now())


@app.post("/discovery/reset")
def discovery_reset(req: SessionRef):
    st = _state()
    st.session_store.reset(req.session_id)
    st.invalidate_session(st.session_store.uid(req.session_id))
    return _me_payload(st, req.session_id, timeutil.now())


@app.get("/discovery/me")
def discovery_me(session_id: str = Query(...)):
    st = _state()
    return _me_payload(st, session_id, timeutil.now())


@app.get("/discovery/health")
def health():
    st = _state()
    return {"status": "ok", "endpoint": "discovery-api", "version": "1.0", "port": DISCOVERY_PORT,
            "data_source_mode": config.DATA_SOURCE_MODE, "entities": len(st.ds.all_entity_ids()),
            "vector_api_url": config.VECTOR_API_URL, "graph_api_url": config.GRAPH_API_URL,
            "default_engine": config.V2_DEFAULT_ENGINE, "engines": ["v1", "v2"],
            "substrate_reachable": st.substrate_up(), "now": timeutil.now().isoformat()}


@app.get("/")
def root():
    return {"service": "Feeds.ai Discovery API", "version": "1.0", "port": DISCOVERY_PORT,
            "endpoints": ["POST /discovery/feed", "GET /discovery/health"]}
