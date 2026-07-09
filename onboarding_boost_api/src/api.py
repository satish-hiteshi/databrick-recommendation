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
import os
import sys
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

# shared/identity.py is FROZEN — import, never edit. Used to (a) ACCEPT inbound composite/entity_id ids and
# (b) EMIT the composite on the confirm response. Repo root -> feedsai-graphdb/ -> `shared.identity`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.identity import (composite_of, composite_fields, parse_entity_id,  # noqa: E402
                             candidate_entity_ids, coerce_to_entity_id)

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


def _resolve_inbound_ids(data, xs, id_space="auto"):
    """Normalize an inbound property-id list to served ROW INDICES (the UNAMBIGUOUS runtime key), accepting
    the POST-MIGRATION composite forms PRIMARY, with backward-compat for the bare integer:

      * entity_id string  "Movie:119163"                             -> the EXACT row (row_by_eid) — twin-correct
      * composite dict     {"profile_key"|"vertical", "media_source_guid"} -> the EXACT row (row_by_eid)
      * bare int/str       119163  (DEPRECATED, vertical-AMBIGUOUS)   -> the guid bridge picks ONE served row
        (row_by_pid, first twin); a warning names the full candidate set — callers SHOULD send entity_id/composite.

    Returns (rows, warnings). Rows are threaded through build_boost → taste_vector / candidates / _point_id so a
    followed Movie:119163 binds ITS OWN vector + excludes Movie:119163, never the Game twin (the E6 row pattern)."""
    rows, warnings = [], []
    for x in (xs or []):
        # 1) composite dict or entity_id string -> coerce to an entity_id, then resolve to its UNAMBIGUOUS row
        eid = None
        if isinstance(x, dict):
            eid = coerce_to_entity_id(x)
            if eid is None:
                warnings.append(f"unresolvable composite dict: {x!r}"); continue
        elif isinstance(x, str) and ":" in x:
            try:
                eid = parse_entity_id(x).entity_id
            except ValueError:
                warnings.append(f"malformed entity_id: {x!r}"); continue
        if eid is not None:
            # entity_id/composite → the EXACT served ROW via row_by_eid (twin-correct; NO collapse to the bare
            # guid). This is what binds the seed's OWN vector + excludes the right twin. The old vertical guard
            # is gone: the row IS the pinned entity, so a Movie:119163 seed can never be dropped for the Game twin.
            row = data.row_by_eid.get(eid)
            if row is None:
                # legacy pid-keyed store (no entity_id index): fall back via the guid bridge to the served row.
                guid = parse_entity_id(eid).media_source_guid
                r = data.resolve(guid, id_space)
                row = data.row_by_pid.get(r) if r is not None else None
                if row is None:
                    warnings.append(f"{eid}: guid {guid} not served"); continue
            rows.append(row)
            continue
        # 2) backward-compat bare int/str guid — DEPRECATED, vertical-AMBIGUOUS across the ~321 collisions. The
        #    guid bridge picks ONE served row (row_by_pid, first twin); we surface the full candidate set so the
        #    caller migrates to entity_id/composite.
        try:
            guid = int(x)
        except (TypeError, ValueError):
            warnings.append(f"unrecognised id: {x!r}"); continue
        r = data.resolve(guid, id_space)
        row = data.row_by_pid.get(r) if r is not None else None
        if row is None:
            warnings.append(f"bare id {guid}: not served"); continue
        served_vert = data.row_meta(row).get("vertical")
        warnings.append(f"bare id {guid} is DEPRECATED/vertical-ambiguous (could be any of "
                        f"{candidate_entity_ids(guid)}); resolved to served vertical {served_vert!r} — "
                        f"send entity_id/composite to disambiguate")
        rows.append(row)
    # de-dup rows, preserve order
    return list(dict.fromkeys(rows)), warnings


def _composite_for_pid(data, pid):
    """Served external pid -> {entity_id, profile_key, media_source_guid} using the row's entity_id (the
    universal survivor); fall back to (vertical, guid) if entity_id is absent/unrecognised."""
    m = data.meta.get(pid, {})
    eid = m.get("entity_id")
    if eid:
        try:
            c = composite_of(str(eid))
            return {"entity_id": str(eid), **c}
        except ValueError:
            pass
    vert = m.get("vertical")
    if vert:
        c = composite_fields(vert, pid)
        return {"entity_id": f"{vert}:{pid}", **c}   # last-resort; vertical known but prefix non-standard
    return {"entity_id": str(eid) if eid else None, "profile_key": None, "media_source_guid": str(pid)}


def _first(body: DataframeBody):
    return (body.dataframe_records or [{}])[0]


# ── Step 1: build the boost payload ────────────────────────────────────────────
@app.post("/onboarding/boost")
def boost(body: DataframeBody):
    data = Data.get()
    rec = _first(body)
    user_id = rec.get("user_id")
    session_id = rec.get("session_id")
    target_per_vertical = rec.get("target_per_vertical") or gaps.DEFAULT_TARGET_PER_VERTICAL
    total_cap = rec.get("total_cap") or gaps.DEFAULT_TOTAL_CAP
    gap_threshold = rec.get("gap_threshold") or gaps.DEFAULT_GAP_THRESHOLD
    exclude_verticals = rec.get("exclude_verticals") or []
    richness_floor = rec.get("richness_floor")
    id_space = (rec.get("id_space") or "auto").lower()      # auto | public | external (bare-guid space)
    deepen_covered = rec.get("deepen_covered", True)         # deepen covered verticals (default ON)
    deepen_per_vertical = rec.get("deepen_per_vertical")
    debug = bool(rec.get("debug"))

    # INBOUND ids — accept composite/entity_id PRIMARY + backward-compat bare int (warn on ambiguity).
    # The resolver returns already-served ROW INDICES (the UNAMBIGUOUS runtime key) — twin-correct for the
    # ~321 collisions — which build_boost threads straight through to taste/exclude/candidates.
    followed_rows, in_warn = _resolve_inbound_ids(data, rec.get("followed_property_ids"), id_space)
    exclude_rows, ex_warn = _resolve_inbound_ids(data, rec.get("exclude_ids"), id_space)
    id_warnings = in_warn + ex_warn
    if id_warnings:
        for w in id_warnings:
            print(f"[boost.inbound] {w}", flush=True)

    ctx, groups, dbg = gaps.build_boost(
        data, VS, followed=followed_rows, target_per_vertical=target_per_vertical, total_cap=total_cap,
        gap_threshold=gap_threshold, exclude_verticals=exclude_verticals, exclude_ids=exclude_rows,
        richness_floor=richness_floor, id_space="auto", deepen_covered=bool(deepen_covered),
        deepen_per_vertical=deepen_per_vertical, debug=debug)
    if id_warnings and isinstance(ctx, dict):
        ctx["inbound_id_warnings"] = id_warnings   # surface deprecation/ambiguity to the caller

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
    written_pids = result.get("property_ids", [])
    return {"predictions": [{
        "version": "1.0", "endpoint": "onboarding-boost-confirm", "user_id": user_id,
        "session_id": session_id, "action": "confirm",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # bare source_id/guid list (backward-compat; vertical-AMBIGUOUS across the ~321 collisions)
        "followed_property_ids": written_pids,
        # NEW — the unambiguous post-migration key for each written follow (entity_id + composite)
        "followed": [_composite_for_pid(data, p) for p in written_pids],
        # DEPRECATED — the OLD public property_id is GONE post-migration (public_id() -> None); kept as an
        # explicit list of nulls so existing clients don't KeyError. Remove once no client reads it.
        "followed_public_ids": [data.public_id(p) for p in written_pids],
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
