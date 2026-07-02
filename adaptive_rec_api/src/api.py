"""api.py — UC6 Onboarding Adaptive Recommendations endpoint.

POST /onboarding/adaptive-rec  (dataframe_records -> predictions[])

PURE TASTE-DRIVEN (no popularity/centrality/proximity — those are cold-start/feed signals, not onboarding;
adaptive-rec only triggers at >=2 follows, so the user's OWN taste drives everything). Vector search only
(in-app cosine over the 44k-qwen embeddings stored in Postgres). No Neo4j, no global popularity, no fabrication.

DECISION LOGIC (genuine, tested on real embeddings):
  1. relevance(candidate) = MAX cosine to ANY followed property  (multi-interest safe; no fragile clustering).
  2. exclude = followed | skipped | already-suggested(session) | near-duplicates of skipped (cos > 0.90).
  3. confidence gate: relevance >= confidence_threshold (client-configurable) else suggestion = null (honest).
  4. diversity: distribute suggestions across the user's followed VERTICALS proportional to their follows
     (largest-remainder), with a small exploration weight so a genuinely-relevant other-vertical item can
     surface. Embeddings DON'T bridge verticals by theme (tested: game<->gaming-podcast ~0.28), so cross-
     vertical appears only when a candidate is genuinely relevant — never fabricated.
  5. pick = top-relevance candidate in the chosen vertical; context.confidence = that candidate's cosine.

Skip = candidate-exclusion ONLY (follow-count / interest strength untouched); accumulation happens naturally
via gate-exhaustion. Session memory (server-side, Postgres) persists `suggested` so nothing repeats.
"""
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import List

import numpy as np
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from data import Data
from store import SessionStore

app = FastAPI(title="Feeds.ai Onboarding Adaptive-Rec", version="1.0")
STORE = SessionStore()

# ── config ────────────────────────────────────────────────────────────────────
DEFAULT_THRESHOLD = 0.75      # client default confidence gate (operator-configurable per request)
MIN_FOLLOWS = 2               # no suggestion below this (acceptance)
NEAR_DUPE_COS = 0.90          # a candidate within this cosine of a SKIPPED item is a near-duplicate -> exclude
FOLLOW_DUP_COS = 0.97         # a candidate ~identical to a FOLLOWED item (diff id/name) -> duplicate -> exclude
EXPLORE_W = 0.5               # exploration weight for a relevant vertical the user hasn't followed yet
SIM_FLOOR = 0.5               # overlap-consensus: only count a follow the candidate is genuinely similar to
SKIP_PENALTY = 1.0            # proportional LOCAL penalty per unit of similarity to a skipped item
FRANCHISE_CAP = 2            # W6: at most this many suggestions from the SAME franchise per session (variety)
MAX_LIMIT = 2

# ── client ranking weights (UC6 §2 + RANKING_MODEL_v1.3 — "Onboarding adaptive recs" surface) ───
# A suggestion is GATED by relevance (cosine >= confidence_threshold). Among gated candidates the WINNER is
# chosen by this weighted blend (popularity-DOMINANT — a new user has little taste, so social proof leads).
# context.confidence / suggestion.score = the winner's COSINE (per spec §6), NOT the blend.
W_REL = 0.22    # S1 relevance  (session cosine — also the gate)
W_REC = 0.03    # S2 recency    (release freshness)
W_TREND = 0.07  # S3 trending   (population engagement velocity — NO event data in scope -> 0 contribution)
W_CENT = 0.16   # S4 centrality (graph PageRank)
W_POP = 0.48    # S5 popularity (graph user_rating) — DOMINANT
W_PROX = 0.04   # S6 proximity  (franchise/genre overlap with the user's follows)

# ── cross-vertical exploration (UC6 Story 3) ────────────────────────────────────
# For a user CONCENTRATED in one vertical, occasionally surface a DIFFERENT-vertical item that is TOPICALLY
# about their dominant vertical AND a graph HUB. Gated on CENTRALITY (not cosine) — embeddings don't bridge
# verticals (game<->gaming-podcast ~0.28), but the spec selects these by "high centrality in the games vertical".
# Reported confidence = that centrality (>= gate), so §6/§8 ("threshold_met -> confidence >= threshold") stays
# honest. Same-vertical logic is 100% untouched; this only ADDS candidates to explore-verticals (0 follows).
XV_MIN_DOMINANT = 4         # dominant vertical needs >= this many follows to open cross-vertical exploration
XV_EVERY = 4               # once active, make every Nth suggestion in the session a cross-vertical hub (Story 3)
_BRIDGE_TERMS = {
    "game":    ("gaming", "video game", "videogame", "esport", "gamer", "game review"),
    "movie":   ("movie", "film", "cinema", "hollywood", "box office", "blockbuster"),
    "tv":      ("television", "sitcom", "tv series", "miniseries", "episode recap"),
    "podcast": ("podcast", "radio show"),
}
_TOPIC_MASK_CACHE = {}      # vertical -> precomputed bool mask (built once, cached for the process)

# W3: edition/format words that mark the SAME title in a different package (strip for duplicate detection).
# NOT sequel/year tokens (II, 21, 2022) — those denote DIFFERENT entries, must stay.
_EDITION_RE = re.compile(r"\b(remastered|remaster|definitive|deluxe|goty|game of the year|complete|enhanced|hd|gold|ultimate|collection|edition)\b")
_NUMERAL_RE = re.compile(r"\b([ivx]+|\d+)\b")        # trailing roman/number — dropped only for FRANCHISE grouping


def _norm_name(name):
    """Normalize a title for DUPLICATE detection: lowercase, strip punctuation + edition words, keep numerals."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = _EDITION_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _franchise(name):
    """Group titles into a franchise/series: part before ':' (or whole), minus edition + trailing numerals.
    'Call of Duty: Warzone'/'...: Black Ops' -> 'call of duty'; 'Dark Souls II/III' -> 'dark souls'; 'FIFA 21' -> 'fifa'."""
    s = (name or "").split(":")[0].lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _EDITION_RE.sub(" ", s)
    s = _NUMERAL_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# W3/W6 are O(1) per candidate in the hot loop ONLY because the per-name regex (normalize + franchise) is run
# ONCE here over the whole catalogue and cached row-aligned — never per request (scalable: no 44k×regex/req).
_NAME_ARRAYS = {"norm": None, "fr": None}


def _ensure_name_arrays(data):
    if _NAME_ARRAYS["norm"] is None:
        _NAME_ARRAYS["norm"] = [_norm_name(data.meta[p].get("name")) for p in data.pids]
        _NAME_ARRAYS["fr"] = [_franchise(data.meta[p].get("name")) for p in data.pids]
    return _NAME_ARRAYS["norm"], _NAME_ARRAYS["fr"]


def _prox_overlap(data, row, foll_fr, foll_ge):
    """S6 proximity: structural closeness of a candidate to the user's follows (shared franchise/genre)."""
    score = 0.0
    if foll_fr and (data.franchises[row] & foll_fr):
        score += 1.0                                              # shared franchise -> strong
    if foll_ge:
        overlap = data.genres_sig[row] & foll_ge
        if overlap:
            score += 0.5 * len(overlap) / max(len(foll_ge), 1)    # genre overlap -> partial
    return min(score, 1.0)


def _topic_mask(data, vertical):
    """Boolean (N,) mask: candidates whose keywords are TOPICALLY about `vertical` (cross-vertical exploration).
    Built once per vertical from precomputed kw_text, then cached for the process (scalable: O(1)/request)."""
    terms = _BRIDGE_TERMS.get(vertical)
    if not terms or data.kw_text is None:
        return None
    m = _TOPIC_MASK_CACHE.get(vertical)
    if m is None:
        m = np.fromiter((any(t in s for t in terms) for s in data.kw_text), dtype=bool, count=len(data.kw_text))
        _TOPIC_MASK_CACHE[vertical] = m
    return m


class DataframeBody(BaseModel):
    dataframe_records: List[dict]


@app.on_event("startup")
def _startup():
    t0 = time.perf_counter()
    d = Data.get()
    _ensure_name_arrays(d)                       # precompute normalized-name / franchise arrays ONCE (W3/W6 scale)
    for v in _BRIDGE_TERMS:                       # warm cross-vertical topical masks ONCE (Story 3 scale)
        _topic_mask(d, v)
    print(f"[adaptive] loaded {d.stats()} in {(time.perf_counter()-t0)*1000:.0f}ms; "
          f"session-store persistent={STORE.health()['persistent']}", flush=True)


# ── helpers ─────────────────────────────────────────────────────────────────────
def _ints(xs):
    out = []
    for x in (xs or []):
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


def _why(data, pid, followed):
    """Name the 1-2 followed properties the candidate is most similar to; cross-vertical -> 'fans of' framing."""
    cv = data.vec(pid)
    sims = []
    for p in followed:
        v = data.vec(p)
        if v is not None and cv is not None:
            sims.append((float(cv @ v), p))
    sims.sort(reverse=True)
    names = [data.meta.get(p, {}).get("name", f"Property {p}") for _, p in sims[:2]] or ["properties you follow"]
    who = " and ".join(names)
    cand_vert = data.meta.get(pid, {}).get("vertical")
    top_follow_vert = data.meta.get(sims[0][1], {}).get("vertical") if sims else None
    cross = top_follow_vert is not None and cand_vert != top_follow_vert
    if cross:
        return f"Fans of {who} also listen to this" if cand_vert == "podcast" else f"Fans of {who} also follow this"
    return f"Because you followed {who}, you might also like this"


def _top_genres(raw, k=2):
    """Client payload wants ONLY the top-2 genres (e.g. ["battle-royale","shooter"]).
    bm25_keywords lead with real genres, then year/theme/place keywords — drop bare
    number tokens (e.g. "2026") so a year can never take a genre slot, then take first k."""
    seq = list(raw or [])
    clean = [g for g in seq if not (isinstance(g, str) and g.strip().isdigit())]
    return (clean or seq)[:k]


def _suggestion(data, pid, rel, why):
    m = data.meta.get(pid, {})
    return {
        "type": "property",
        "entity_id": str(m.get("entity_id") or pid),
        "property_id": pid,
        "name": m.get("name"),
        "vertical": m.get("vertical"),
        "genres": _top_genres(m.get("genres")),
        "thumbnail_url": None,             # not in 44k parquet (comes from moments data — not in scope)
        "deep_link": f"feeds://property/{pid}",
        "score": round(float(rel), 4),
        "why_string": why,
        "badge": None,
        "follow_cta": True,
    }


def _prediction(session_id, confidence, threshold_met, signal_count, suggestion, debug=None):
    return {
        "version": "1.0",
        "endpoint": "onboarding-adaptive-rec",
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": {"confidence": round(float(confidence), 4),
                    "threshold_met": bool(threshold_met),
                    "signal_count": int(signal_count)},
        "suggestion": suggestion,
        "debug": debug,
    }


# ── the endpoint ─────────────────────────────────────────────────────────────────
@app.post("/onboarding/adaptive-rec")
def adaptive_rec(body: DataframeBody):
    data = Data.get()
    norm_names, franchises = _ensure_name_arrays(data)   # row-aligned, precomputed once (W3/W6 — no regex/req)
    rec = (body.dataframe_records or [{}])[0]
    session_id = rec.get("session_id")
    followed = list(dict.fromkeys(_ints(rec.get("followed_property_ids"))))   # dedup, preserve order
    skipped = _ints(rec.get("skipped_property_ids"))
    exclude_ids = _ints(rec.get("exclude_ids"))
    threshold = min(1.0, max(0.0, float(rec.get("confidence_threshold")
                                        if rec.get("confidence_threshold") is not None else DEFAULT_THRESHOLD)))
    vfilter = {str(v).lower() for v in (rec.get("verticals") or [])} or None
    limit = max(1, min(int(rec.get("limit") or 1), MAX_LIMIT))
    debug = bool(rec.get("debug"))

    sess = STORE.get(session_id)
    signal_count = len(set(followed))

    # ACCEPTANCE: >= 2 followed before any suggestion
    if signal_count < MIN_FOLLOWS:
        return {"predictions": [_prediction(session_id, 0.0, False, signal_count, None,
                                            debug={"reason": "fewer than 2 followed"} if debug else None)]}

    # follow embedding matrix -> relevance = max cosine to ANY follow
    F = [data.vec(p) for p in followed]
    F = [v for v in F if v is not None]
    if not F:
        return {"predictions": [_prediction(session_id, 0.0, False, signal_count, None,
                                            debug={"reason": "no embeddings for followed set"} if debug else None)]}
    C = data.emb @ np.vstack(F).T                               # (N, k) cosine to each followed property
    max_cos = C.max(axis=1)                                     # (N,) S1 relevance = confidence + gate (0..1)

    # SKIP = proportional, LOCAL negative applied to the blended score below (Story 2: a local disinterest
    # signal, not a category ban). Near-identical clones of a skip are excluded outright further down.
    Sv = [data.vec(p) for p in skipped]
    Sv = [v for v in Sv if v is not None]
    skip_sim = (data.emb @ np.vstack(Sv).T).max(axis=1) if Sv else None

    # follows' franchise/genre union -> S6 proximity overlap for candidates
    foll_fr, foll_ge = set(), set()
    for p in followed:
        r = data.row_by_pid.get(p)
        if r is not None:
            foll_fr |= data.franchises[r]
            foll_ge |= data.genres_sig[r]

    exclude = set(followed) | set(skipped) | set(exclude_ids) | sess["suggested"]
    # W3: exclude by NORMALIZED name — catches duplicate titles (two "Shaman King") AND edition-variants
    # ("X" vs "X Remastered") under different property_ids; sequels/annuals stay distinct.
    exclude_names = {_norm_name(data.meta.get(p, {}).get("name")) for p in exclude if data.meta.get(p)}
    exclude_names.discard("")
    # W6: how many suggestions already made per FRANCHISE this session (cap repeats for variety)
    served_fr = Counter(_franchise(data.meta.get(p, {}).get("name")) for p in sess["suggested"] if data.meta.get(p))

    # user's vertical interest (target) + already-served (from session) — proportional diversity guard
    fvert = {}
    for p in followed:
        v = data.meta.get(p, {}).get("vertical")
        if v:
            fvert[v] = fvert.get(v, 0) + 1
    # Story 3: user concentrated in one vertical -> open cross-vertical exploration (centrality-gated, below)
    dominant_vert = max(fvert, key=fvert.get) if fvert else None
    xv_active = bool(dominant_vert and fvert[dominant_vert] >= XV_MIN_DOMINANT)
    xv_mask = _topic_mask(data, dominant_vert) if xv_active else None
    served = {}
    for p in sess["suggested"]:
        v = data.meta.get(p, {}).get("vertical")
        if v:
            served[v] = served.get(v, 0) + 1
    served_total = sum(served.values())

    # best candidate per vertical: tuple = (rank, confidence, pid, is_cross)
    best_per_vert = {}
    global_top = []   # all gated genuine candidates (blend, cosine, pid) — for top-N fill when limit>1
    near_conf = 0.0
    for row, pid in enumerate(data.pids):
        if pid in exclude:
            continue
        m = data.meta[pid]
        if norm_names[row] in exclude_names:                         # W3: duplicate / edition-variant guard (precomputed)
            continue
        if served_fr.get(franchises[row], 0) >= FRANCHISE_CAP:       # W6: cap same-franchise suggestions/session
            continue
        v = m.get("vertical")
        if vfilter is not None and v not in vfilter:
            continue
        mc = float(max_cos[row])
        if mc > FOLLOW_DUP_COS:                                  # ~identical to a followed item -> duplicate, skip
            continue
        if mc > near_conf:
            near_conf = mc
        if skip_sim is not None and float(skip_sim[row]) > NEAR_DUPE_COS:   # near-duplicate of a skipped item
            continue
        if mc >= threshold:
            # SAME-VERTICAL / taste path (UNCHANGED): cosine gate, rank by weighted blend, confidence = cosine
            prox = _prox_overlap(data, row, foll_fr, foll_ge)
            skp = SKIP_PENALTY * max(float(skip_sim[row]) - SIM_FLOOR, 0.0) if skip_sim is not None else 0.0
            blended = (W_REL * mc + W_POP * float(data.popularity[row]) + W_CENT * float(data.centrality[row])
                       + W_PROX * prox + W_REC * float(data.recency[row]) - skp)
            global_top.append((blended, mc, pid))
            cur = best_per_vert.get(v)
            if cur is None or cur[3] or blended > cur[0]:        # a genuine taste pick always beats a cross pick
                best_per_vert[v] = (blended, mc, pid, False)
        elif xv_active and v == "podcast" and v not in fvert and xv_mask is not None and xv_mask[row]:
            # CROSS-VERTICAL EXPLORE (Story 3): "a gaming podcast or YouTube channel" — PODCAST ONLY (spec is
            # explicit; TV/movie cross picks are out-of-scope and produced irrelevant hits e.g. a kids' cartoon).
            # Topically about the dominant vertical + a graph HUB. Gate on CENTRALITY; confidence = centrality.
            # Adds to the podcast explore slot only — never displaces a real taste pick (is_cross comparison above).
            cen = float(data.centrality[row])
            if cen >= threshold:
                cur = best_per_vert.get(v)
                if cur is None or (cur[3] and cen > cur[0]):     # competes only with other cross picks
                    best_per_vert[v] = (cen, cen, pid, True)

    if not best_per_vert:
        return {"predictions": [_prediction(session_id, near_conf, False, signal_count, None,
                                            debug={"reason": "no candidate >= threshold", "threshold": threshold} if debug else None)]}

    # choose vertical(s) by largest-remainder over interest weights (diversity guard so minor interests are
    # represented over the sequence); within each vertical the weighted-blend winner is taken. Vertical is
    # implicit — the system computes it from the user's own follows, no preset rule.
    genuine = {v: t for v, t in best_per_vert.items() if not t[3]}   # same-vertical taste picks (cosine-gated)
    cross = {v: t for v, t in best_per_vert.items() if t[3]}         # cross-vertical hubs (centrality-gated)
    # Story 3: once the user is concentrated (xv_active), make every XV_EVERY-th suggestion a cross-vertical hub.
    inject = xv_active and bool(cross) and (served_total + 1) % XV_EVERY == 0

    weights = {v: (fvert.get(v, 0) or EXPLORE_W) for v in genuine}
    tw = sum(weights.values()) or 1.0

    def priority(v):
        return (weights[v] / tw) * (served_total + 1) - served.get(v, 0)

    if inject:                                                   # this turn -> a cross-vertical hub
        order = sorted(cross, key=lambda v: cross[v][0], reverse=True)
        if limit > 1:                                            # fill any remaining slots with genuine picks
            order += [v for v in sorted(genuine, key=priority, reverse=True) if v not in cross]
    else:                                                        # normal turn -> proportional over taste picks
        order = sorted(genuine, key=priority, reverse=True) or sorted(cross, key=lambda v: cross[v][0], reverse=True)

    # PRIMARY pick = winner of the chosen vertical order (proportional / cross-vertical inject)
    primary = best_per_vert[order[0]]                           # (rank, confidence, pid, is_cross)
    picks = [primary]
    chosen = {primary[2]}
    # client wants the TOP-N relevant (limit up to 2): fill remaining slots with the next most-relevant
    # DISTINCT candidates by weighted blend (may be same vertical — "top 2 relevant").
    if limit > 1:
        for b, mc, pid in sorted(global_top, key=lambda x: -x[0]):
            if len(picks) >= limit:
                break
            if pid not in chosen:
                picks.append((b, mc, pid, False))
                chosen.add(pid)

    def _wsig(pid):
        wr = data.row_by_pid.get(pid)
        if wr is None:
            return {}
        return {"relevance": round(float(max_cos[wr]), 3), "popularity": round(float(data.popularity[wr]), 3),
                "centrality": round(float(data.centrality[wr]), 3),
                "proximity": round(_prox_overlap(data, wr, foll_fr, foll_ge), 3),
                "recency": round(float(data.recency[wr]), 3)}

    preds = []
    for rank, conf, pid, is_cross in picks:                     # one prediction per surfaced suggestion
        sug = _suggestion(data, pid, conf, _why(data, pid, followed))   # score = confidence (cosine; centrality for cross)
        if is_cross:
            sug["badge"] = "cross-vertical"
        dbg = None
        if debug:
            dbg = {"threshold": threshold, "target_verticals": fvert, "served": served,
                   "gate": "cross-vertical (centrality)" if is_cross else "relevance (cosine)",
                   "cross_vertical": is_cross,
                   "weights": {"popularity": W_POP, "relevance": W_REL, "centrality": W_CENT,
                               "proximity": W_PROX, "recency": W_REC, "trending": W_TREND},
                   "winner_signals": _wsig(pid), "top_blend": round(rank, 4)}
        preds.append(_prediction(session_id, conf, True, signal_count, sug, debug=dbg))
    STORE.record(session_id, suggested_ids=[p[2] for p in picks])   # persist ALL surfaced suggestions
    return {"predictions": preds}


@app.get("/onboarding/health")
def health():
    d = Data.get()
    return {"status": "ok", **d.stats(), "session_store": STORE.health()}


@app.get("/onboarding/search")
def search(q: str = "", limit: int = 12):
    """Find properties by name (for the test UI)."""
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


_UI = """<!doctype html><html><head><meta charset="utf-8"><title>Onboarding Adaptive-Rec — Live Test</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;max-width:760px;margin:24px auto;padding:0 16px;color:#1a2330;background:#f6f8fb}
 h1{font-size:20px;color:#1b4965} .row{margin:14px 0}
 input[type=text]{width:100%;padding:9px 12px;border:1px solid #c9d4e0;border-radius:8px;font-size:15px}
 .res button{margin:3px;padding:5px 9px;border:1px solid #b9c6d6;background:#fff;border-radius:14px;cursor:pointer;font-size:13px}
 .res button:hover{background:#eef4fb}
 .chip{display:inline-block;margin:3px;padding:4px 10px;background:#dbeafe;border-radius:14px;font-size:13px}
 .chip b{cursor:pointer;color:#b00;margin-left:6px}
 .skip{background:#fde2e2}
 #go{padding:10px 18px;background:#1b4965;color:#fff;border:0;border-radius:8px;font-size:15px;cursor:pointer}
 .card{margin-top:14px;padding:16px;border:1px solid #cfe0c3;border-left:5px solid #2e7d32;border-radius:10px;background:#fff}
 .card.null{border-left-color:#b00;background:#fff7f7}
 .match{float:right;background:#2e7d32;color:#fff;padding:2px 9px;border-radius:12px;font-size:13px}
 .why{color:#555;font-style:italic;margin:6px 0}
 .b{padding:7px 14px;border-radius:7px;border:0;cursor:pointer;font-size:14px;margin-right:8px}
 .follow{background:#2e7d32;color:#fff} .skipb{background:#fff;border:1px solid #b00;color:#b00}
 label{font-size:13px;color:#444} small{color:#777}
</style></head><body>
<h1>🎮 Onboarding Adaptive-Rec — Live Test</h1>
<div class="row"><label>Confidence threshold: <b id="thrv">0.60</b></label>
 <input type="range" id="thr" min="0.40" max="0.90" step="0.05" value="0.60" style="width:220px;vertical-align:middle"></div>
<div class="row"><label>1) Search & follow properties (need ≥2):</label>
 <input type="text" id="q" placeholder="type a name… e.g. Fortnite, John Wick, Game Theory"><div class="res" id="res"></div></div>
<div class="row"><b>Following:</b> <span id="followed"><small>none yet</small></span></div>
<div class="row"><b>Skipped:</b> <span id="skipped"><small>none</small></span></div>
<div class="row"><button id="go" onclick="getSug()">Get suggestion ▶</button>
 <button class="b" style="background:#eee" onclick="reset()">reset</button></div>
<div id="out"></div>
<script>
let followed=[],skipped=[],names={},last=[],sug=null,sid="ui_"+Math.random().toString(36).slice(2);
const thr=document.getElementById('thr');thr.oninput=()=>document.getElementById('thrv').innerText=(+thr.value).toFixed(2);
const esc=s=>(s||"").replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
document.getElementById('q').oninput=function(){clearTimeout(window.t);window.t=setTimeout(doSearch,300)};
async function doSearch(){const q=document.getElementById('q').value;if(!q){document.getElementById('res').innerHTML='';return}
 const d=await(await fetch('/onboarding/search?q='+encodeURIComponent(q))).json();last=d;
 document.getElementById('res').innerHTML=d.map((x,i)=>`<button onclick="pick(${i})">${esc(x.name)} <small>[${x.vertical}]</small></button>`).join('')||'<small>no match</small>';}
function pick(i){const x=last[i];names[x.property_id]=esc(x.name)+' ['+x.vertical+']';if(!followed.includes(x.property_id))followed.push(x.property_id);render();}
function rm(p){followed=followed.filter(x=>x!=p);render();}
function render(){document.getElementById('followed').innerHTML=followed.length?followed.map(p=>`<span class="chip">${names[p]||p}<b onclick="rm(${p})">✕</b></span>`).join(''):'<small>none yet</small>';
 document.getElementById('skipped').innerHTML=skipped.length?skipped.map(p=>`<span class="chip skip">${names[p]||p}</span>`).join(''):'<small>none</small>';}
function reset(){followed=[];skipped=[];sug=null;sid="ui_"+Math.random().toString(36).slice(2);document.getElementById('out').innerHTML='';render();}
async function getSug(){
 const d=(await(await fetch('/onboarding/adaptive-rec',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({dataframe_records:[{session_id:sid,followed_property_ids:followed,skipped_property_ids:skipped,confidence_threshold:+thr.value}]})})).json()).predictions[0];
 const c=d.context;sug=d.suggestion;const o=document.getElementById('out');
 if(!sug){o.innerHTML=`<div class="card null"><b>No suggestion</b> — threshold not met.<br><small>best match so far: ${Math.round(c.confidence*100)}% · follows: ${c.signal_count}</small></div>`;return}
 names[sug.property_id]=esc(sug.name)+' ['+sug.vertical+']';
 o.innerHTML=`<div class="card"><span class="match">${Math.round(c.confidence*100)}% match</span>
  <b>${esc(sug.name)}</b> <small>[${sug.vertical}]</small>
  <div class="why">${esc(sug.why_string)}</div>
  <button class="b follow" onclick="acc()">＋ Follow (next)</button>
  <button class="b skipb" onclick="skp()">Skip</button></div>`;}
function acc(){followed.push(sug.property_id);render();getSug();}
function skp(){skipped.push(sug.property_id);render();getSug();}
render();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def ui():
    return _UI
