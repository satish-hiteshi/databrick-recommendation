"""discovery_adapter.py — request/response mapping for the Endpoint-2 pyfunc (no FastAPI).

The deployed discovery endpoint speaks the SAME v1.0 envelope as discovery_api/src/api.py's
POST /discovery/feed — this module is the only place the serving request/response meets the engine, so
model.py stays a thin wrapper and the engine is untouched.

  IN : a serving row {user_id, sort_order, time_window/date_range, limit, offset, property_ids(EXCLUDE),
                      seen_ids, debug, now}
  OUT: {version, endpoint, user_id, context, request_echo, main_feed{items:[moment]},
        carousels:[{...items:[property]}], debug}

Serialization mirrors api.py::_v2_moment_item / _v2_property_item / _v2_feed (kept byte-faithful), with
datetimes coerced to ISO strings so the result is JSON-serializable for Model Serving.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from discovery_api.src import timeutil

DEFAULT_LIMIT = 20


# ── IN ─────────────────────────────────────────────────────────────────────
def parse_request(model_input) -> List[Dict[str, Any]]:
    if hasattr(model_input, "to_dict"):                      # pandas DataFrame
        rows = model_input.to_dict(orient="records")
    elif isinstance(model_input, dict):
        rows = model_input.get("dataframe_records") or [model_input]
    elif isinstance(model_input, list):
        rows = model_input
    else:
        raise TypeError(f"unsupported model_input type: {type(model_input)!r}")
    out = []
    for r in rows:
        r = dict(r)
        try:
            limit = max(1, int(r.get("limit") or DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        try:
            offset = max(0, int(r.get("offset") or 0))
        except (TypeError, ValueError):
            offset = 0
        out.append({
            "user_id": r.get("user_id"),
            "sort_order": (r.get("sort_order") or "trending"),
            "time_window": r.get("time_window"),
            "date_range": r.get("date_range"),
            "limit": limit, "offset": offset,
            "property_ids": list(r.get("property_ids") or []),   # EXCLUSION list
            "seen_ids": list(r.get("seen_ids") or []),
            "debug": bool(r.get("debug")),
            "now": r.get("now"),
        })
    return out


# ── OUT ────────────────────────────────────────────────────────────────────
def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _genres(ds, entity_id):
    e = ds.get_entity(entity_id)
    if not e:
        return []
    return ds.get_podcast_categories(entity_id) if e.vertical == "podcast" else e.canonical_genres


def _moment_item(fi, debug):
    d = {"type": "moment", "moment_id": fi.moment_id, "entity_id": fi.entity_id,
         "property_name": fi.property_name, "vertical": fi.vertical, "title": fi.title,
         "description": fi.description, "event_starts_at": _iso(fi.event_starts_at),
         "media_platform_id": fi.media_platform_id, "score": round(fi.score, 4), "why_string": fi.why_string}
    if debug:
        s = fi.debug or {}
        d["debug"] = {"source_pool": fi.source_pool, "taste_match": s.get("taste_match"),
                      "trending_velocity": s.get("trending_velocity"), "recency": s.get("recency"),
                      "collaborative": s.get("collaborative"), "cluster_id": s.get("cluster_id"),
                      "final_score": s.get("final_score")}
    return d


def _property_item(ci, ds, debug):
    lm = ci.latest_moment
    d = {"type": "property", "entity_id": ci.entity_id, "name": ci.property_name, "vertical": ci.vertical,
         "genres": _genres(ds, ci.entity_id), "score": round(ci.score, 4), "why_string": ci.why_string,
         "latest_moment": (lm.to_dict() if hasattr(lm, "to_dict") else lm) if lm else None}
    if debug:
        d["debug"] = {"source_pool": ci.source_pool, **(ci.debug or {})}
    return d


def _date_bounds(req, now):
    dr = req.get("date_range")
    if dr:
        return timeutil.parse_ts(dr.get("start")), timeutil.parse_ts(dr.get("end"))
    days = {"last_7d": 7, "last_30d": 30}.get(req.get("time_window") or "")
    return (now - timedelta(days=days), now) if days else (None, None)


def _date_filter(items, lo, hi):
    if lo is None and hi is None:
        return items
    out = []
    for it in items:
        ts = it.event_starts_at
        if ts is None or (lo and ts < lo) or (hi and ts > hi):
            continue
        out.append(it)
    return out


def serialize(feed, meta, req, now, ds) -> Dict[str, Any]:
    """DiscoveryFeed (+ V2FeedBuilder meta) -> the v1.0 envelope, date-filtered + paginated like api.py."""
    dbg = req["debug"]
    lo, hi = _date_bounds(req, now)
    filtered = _date_filter(feed.main_feed, lo, hi)
    off, lim = req["offset"], req["limit"]
    page = filtered[off:off + lim]
    next_offset = off + lim if (off + lim) < len(filtered) else None
    return {
        "version": "1.0", "endpoint": "discovery-api", "user_id": req["user_id"],
        "generated_at": now.isoformat(),
        "context": {"mode": feed.mode, "signal_strength": feed.signal_strength,
                    "substrate_reachable": True, "engine": "v2", "path": meta.get("path")},
        "request_echo": {"sort_order": req["sort_order"], "time_window": req.get("time_window"),
                         "limit": lim, "offset": off,
                         "excluded_property_ids": len(req["property_ids"]), "seen_ids": len(req["seen_ids"])},
        "main_feed": {"items": [_moment_item(i, dbg) for i in page], "count": len(page),
                      "next_offset": next_offset},
        "carousels": [{"carousel_id": c.carousel_id, "reason_type": c.reason_type.value,
                       "reason_string": c.reason_string, "item_type": c.item_type,
                       "items": [_property_item(it, ds, dbg) for it in c.items]}
                      for c in feed.carousels if c.items],
        "debug": (meta if dbg else None),
    }


def error_response(message: str, user_id=None) -> Dict[str, Any]:
    return {"version": "1.0", "endpoint": "discovery-api", "user_id": user_id,
            "context": {"mode": "error", "engine": "v2"}, "main_feed": {"items": [], "count": 0},
            "carousels": [], "error": message}
