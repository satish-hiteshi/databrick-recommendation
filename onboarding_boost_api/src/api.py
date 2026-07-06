"""api.py — UC8 Onboarding Boost endpoint (standalone FastAPI; default :8050).

Two-step flow (spec §6):
  POST /onboarding/boost           -> detect vertical gaps from the seed set, return a boost payload
                                      grouped by vertical (Step 1). Records the offer for confirm.
  POST /onboarding/boost/confirm   -> all-or-nothing batch follow write to the local follows store
                                      (Step 2). action="skip" records the skip and writes nothing.

Helpers for the demo / frontend:
  GET  /onboarding/boost/health    -> data + store status
  GET  /onboarding/boost/search    -> find seed properties by name
  GET  /onboarding/boost/verticals -> served verticals + counts
  GET  /                           -> built-in test page (the React app is the primary UI)

Does NOT import or touch UC6 (adaptive_rec) / discovery / home_feed. Reuses only the shared DB tables.
"""
import time
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from data import Data
import gaps
import vector_store
from store import BoostStore
from ui import PAGE

app = FastAPI(title="Feeds.ai Onboarding Boost (UC8)", version="1.0")
STORE = BoostStore()
VS = None            # vector backend (memory | qdrant), built at startup


class DataframeBody(BaseModel):
    dataframe_records: List[dict]


@app.on_event("startup")
def _startup():
    global VS
    t0 = time.perf_counter()
    d = Data.get()
    gaps.warm(d)
    VS = vector_store.get_store(d)
    print(f"[boost] loaded {d.stats()} in {(time.perf_counter()-t0)*1000:.0f}ms; "
          f"vector_backend={VS.name}; store persistent={STORE.health()['persistent']}", flush=True)


def _ints(xs):
    out = []
    for x in (xs or []):
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


def _first(body: DataframeBody):
    return (body.dataframe_records or [{}])[0]


# ── Step 1: build the boost payload ────────────────────────────────────────────
@app.post("/onboarding/boost")
def boost(body: DataframeBody):
    data = Data.get()
    rec = _first(body)
    user_id = rec.get("user_id")
    session_id = rec.get("session_id")
    followed = _ints(rec.get("followed_property_ids"))
    target_per_vertical = rec.get("target_per_vertical") or gaps.DEFAULT_TARGET_PER_VERTICAL
    total_cap = rec.get("total_cap") or gaps.DEFAULT_TOTAL_CAP
    gap_threshold = rec.get("gap_threshold") or gaps.DEFAULT_GAP_THRESHOLD
    exclude_verticals = rec.get("exclude_verticals") or []
    exclude_ids = _ints(rec.get("exclude_ids"))
    richness_floor = rec.get("richness_floor")
    id_space = (rec.get("id_space") or "auto").lower()      # auto | public | external
    deepen_covered = rec.get("deepen_covered", True)         # deepen covered verticals (default ON)
    deepen_per_vertical = rec.get("deepen_per_vertical")
    debug = bool(rec.get("debug"))

    ctx, groups, dbg = gaps.build_boost(
        data, VS, followed=followed, target_per_vertical=target_per_vertical, total_cap=total_cap,
        gap_threshold=gap_threshold, exclude_verticals=exclude_verticals, exclude_ids=exclude_ids,
        richness_floor=richness_floor, id_space=id_space, deepen_covered=bool(deepen_covered),
        deepen_per_vertical=deepen_per_vertical, debug=debug)

    # record the offer (all proposed pids) so /confirm can write exactly this set (all-or-nothing)
    offered = [p["property_id"] for g in groups for p in g["properties"]]
    STORE.record_offer(session_id, user_id, offered)

    pred = {
        "version": "1.0",
        "endpoint": "onboarding-boost",
        "user_id": user_id,
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": ctx,
        "boost_payload": groups,
        "write_path": "confirm_then_write",
        "debug": dbg,
    }
    return {"predictions": [pred]}


# ── Step 2: confirm (batch follow write) or skip ───────────────────────────────
@app.post("/onboarding/boost/confirm")
def confirm(body: DataframeBody):
    data = Data.get()
    rec = _first(body)
    user_id = rec.get("user_id")
    session_id = rec.get("session_id")
    action = (rec.get("action") or "confirm").lower()

    if action == "skip":
        return {"predictions": [{
            "version": "1.0", "endpoint": "onboarding-boost-confirm", "user_id": user_id,
            "session_id": session_id, "action": "skip", "written": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_followed_now": STORE.followed_count(user_id)}]}

    offer = STORE.get_offer(session_id)
    if offer is None:
        return {"predictions": [{
            "version": "1.0", "endpoint": "onboarding-boost-confirm", "user_id": user_id,
            "session_id": session_id, "action": "confirm", "error": "no_offer_for_session",
            "written": 0, "generated_at": datetime.now(timezone.utc).isoformat()}]}

    vmap = {pid: data.meta.get(pid, {}).get("vertical") for pid in offer["property_ids"]}
    result = STORE.confirm(session_id, user_id, vmap=vmap)
    return {"predictions": [{
        "version": "1.0", "endpoint": "onboarding-boost-confirm", "user_id": user_id,
        "session_id": session_id, "action": "confirm",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "followed_property_ids": result.get("property_ids", []),
        "followed_public_ids": [data.public_id(p) for p in result.get("property_ids", [])],
        "written": result.get("written", 0), "already_followed": result.get("already", 0),
        "error": result.get("error"),
        "total_followed_now": STORE.followed_count(user_id)}]}


@app.get("/onboarding/boost/health")
def health():
    d = Data.get()
    return {"status": "ok", **d.stats(), "store": STORE.health()}


@app.get("/onboarding/boost/verticals")
def verticals():
    return Data.get().stats().get("verticals", {})


@app.get("/onboarding/boost/search")
def search(q: str = "", limit: int = 12):
    data = Data.get()
    ql = q.strip().lower()
    out = []
    if ql:
        for pid in data.pids:
            m = data.meta[pid]
            nm = m.get("name") or ""
            if ql in nm.lower():
                out.append({"property_id": pid, "name": nm, "vertical": m.get("vertical")})
                if len(out) >= limit:
                    break
    return out


@app.get("/", response_class=HTMLResponse)
def ui():
    return PAGE
