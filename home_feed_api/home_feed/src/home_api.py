"""home_api.py — standalone FastAPI app for the UC3 Home Feed endpoint.

This is a SEPARATE app from the discovery API (discovery/src/api.py). It lives in the
home_feed/ folder and reuses the discovery engine (Data loader + UserStore + ranking
primitives) as a library via the bootstrap below — the discovery package is never modified.

Endpoint:
  POST /home-feed     follow-gated moment stream + unfollowed-discovery carousels (UC3)
  GET  /home-feed/health

Request (UC3 / Databricks Model Serving envelope):
  {"dataframe_records": [ { ...HomeFeedBody... } ]}   -> {"predictions": [ <envelope>, ... ]}
A flat single record { ...HomeFeedBody... } is also accepted (convenience) and returns the
single envelope directly.

Run (from project root):
  PYTHONUTF8=1 venv/Scripts/python.exe -m uvicorn home_api:app --app-dir home_feed/src --port 8040
"""
# --- engine bootstrap: reuse the discovery engine (discovery/src) as a library -----
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))
_DISC_SRC = _os.path.join(_ROOT, "discovery", "src")
for _p in (_HERE, _DISC_SRC):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
# -----------------------------------------------------------------------------------
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

# discovery engine (library)
from data import Data            # noqa: E402
from store import STORE          # noqa: E402

# home-feed modules (siblings in home_feed/src)
import home_carousels            # noqa: E402
import home_ranking              # noqa: E402
import home_response             # noqa: E402
from home_schema import HomeFeedBody  # noqa: E402

VERSION = "1.0"
app = FastAPI(title="Feeds.ai Home Feed (UC3)", version=VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

LIMIT_MAX = 100


@app.on_event("startup")
def _startup():
    t0 = time.perf_counter()
    d = Data.load()
    dt = (time.perf_counter() - t0) * 1000.0
    print(f"[home_api] assets loaded in {dt:.0f}ms: {d.stats()}", flush=True)
    h = STORE.health()
    print(f"[home_api] persistence: {h}", flush=True)


def _now(body: HomeFeedBody):
    """Resolve a single 'now' for the whole request (reproducible feeds).

    Returns (now_iso, now_epoch). Uses body.now (ISO-8601) when supplied, else server UTC.
    """
    dt = None
    if body.now:
        try:
            txt = body.now.strip()
            if txt.endswith("Z"):
                txt = txt[:-1] + "+00:00"
            dt = datetime.fromisoformat(txt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except ValueError:
            dt = None
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat(), dt.timestamp()


def _build_one(record: Dict[str, Any]) -> Dict[str, Any]:
    """Validate ONE request record and build its UC3 home-feed envelope."""
    try:
        body = HomeFeedBody(**record)
    except ValidationError as e:
        # missing/invalid user_id (no anonymous mode) -> 422 with the pydantic detail
        raise HTTPException(status_code=422, detail=e.errors())

    data = Data.get()
    snap = STORE.snapshot(body.user_id)
    limit = max(1, min(int(body.limit or 20), LIMIT_MAX))
    offset = max(0, int(body.offset or 0))
    excluded_verticals = body.user_prefs.excluded_verticals if body.user_prefs else []
    excluded_platforms = body.user_prefs.excluded_platforms if body.user_prefs else []
    now_iso, now_epoch = _now(body)

    items, total, meta = home_ranking.rank_home(
        body.user_id, snap, data,
        limit=limit, offset=offset, sort_order=body.sort_order,
        time_window=body.time_window, date_range=body.date_range,
        seen_ids=body.seen_ids, done_ids=body.done_ids,
        dismissed_property_ids=body.dismissed_property_ids,
        blocked_property_ids=body.blocked_property_ids,
        excluded_verticals=excluded_verticals,
        excluded_platforms=excluded_platforms, now=body.now,
    )

    carousels = home_carousels.build_home_carousels(
        data, snap, now_epoch,
        carousel_slots=body.carousel_slots, carousel_interval=body.carousel_interval,
    )

    return home_response.build_envelope(
        data, body.user_id, items, total, meta, carousels,
        sort_order=body.sort_order, time_window=body.time_window,
        limit=limit, offset=offset,
        seen_ids=body.seen_ids, done_ids=body.done_ids,
        dismissed=body.dismissed_property_ids, blocked=body.blocked_property_ids,
        now_iso=now_iso, debug=body.debug,
    )


@app.post("/home-feed")
def home_feed(payload: Dict[str, Any]):
    """UC3 home feed. Accepts a Databricks `dataframe_records` envelope or a flat record."""
    t0 = time.perf_counter()
    if isinstance(payload, dict) and "dataframe_records" in payload:
        records: List[Dict[str, Any]] = payload.get("dataframe_records") or []
        predictions = []
        for r in records:
            try:
                predictions.append(_build_one(r))
            except HTTPException as he:   # one bad record must not poison the whole batch
                predictions.append({"error": True, "status": he.status_code, "detail": he.detail})
        out: Dict[str, Any] = {"predictions": predictions}
    else:
        # flat single-record convenience form
        out = _build_one(payload)
    out_timing = round((time.perf_counter() - t0) * 1000.0, 2)
    if isinstance(out, dict) and "predictions" not in out:
        out["timing_ms"] = out_timing
    return out


@app.get("/home-feed/health")
def health():
    d = Data.get()
    return {"status": "ok", "version": VERSION, "persistence": STORE.health(), **d.stats()}
