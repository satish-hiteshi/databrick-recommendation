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
import os
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

# ── EXPERIMENTAL FLAGS (E6-COREXP-1) — env-driven; ALL DEFAULT = current behaviour (byte-identical) ──
RELEVANCE_MODE = os.getenv("E6X_RELEVANCE_MODE", "max")        # max | coherence | clustered
ESTABLISH_MODE = os.getenv("E6X_ESTABLISH_MODE", "threshold")  # threshold | topn
RANK_MODE      = os.getenv("E6X_RANK_MODE", "pop_dominant")    # pop_dominant | taste_led
TOPN           = int(os.getenv("E6X_TOPN", "200"))            # topn pool size
NULL_FLOOR     = float(os.getenv("E6X_NULL_FLOOR", "0.45"))   # topn: null if best ranking-relevance < this
COH_MAX_W      = float(os.getenv("E6X_COH_MAX_W", "0.6"))     # coherence: COH_MAX_W*max + COH_MEAN_W*mean_topk
COH_MEAN_W     = float(os.getenv("E6X_COH_MEAN_W", "0.4"))
CLU_THRESH     = float(os.getenv("E6X_CLU_THRESH", "0.75"))   # clustered: start new cluster if cos-to-mean < this
CLU_MAX        = int(os.getenv("E6X_CLU_MAX", "4"))
TL_CENT, TL_PROX, TL_REC = 0.06, 0.03, 0.03                   # taste_led: small non-relevance priors (rel = residual)
TL_POP_START = float(os.getenv("E6X_TL_POP_START", "0.35"))   # taste_led popularity ramp: weight at 2 follows
TL_POP_SLOPE = float(os.getenv("E6X_TL_POP_SLOPE", "0.03"))   #   decrease per extra follow
TL_POP_FLOOR = float(os.getenv("E6X_TL_POP_FLOOR", "0.15"))   #   never below this (residual safety net)


def _taste_pop_weight(nf):
    """Popularity safety weight for taste_led: starts high while taste is thin, recedes to a floor."""
    return max(TL_POP_FLOOR, TL_POP_START - TL_POP_SLOPE * (nf - 2))


# ── COMPANION-FEED DEDUP (E6-P5 fix) — exclude a spin-off/companion FEED of a followed/skipped property ──
# e.g. "The Ramsey Show Highlights" when "The Ramsey Show" is followed (cos 0.803 < the 0.97 follow-clone
# cutoff, and its name isn't an exact/edition match, so it slipped through). Keyed to the user's OWN picks:
# a candidate is a companion feed iff its normalized name CONTAINS a followed/skipped name (>=2 tokens) as a
# contiguous phrase AND the extra tokens are all feed-markers/filler with >=1 real marker. Numbered sequels
# ("Dark Souls III" -> extra "iii") and shared-word titles ("The Daily Beast" -> extra "beast") are KEPT.
# Default OFF -> baseline byte-identical; enabled alongside the R2 ranking via E6X_FEED_DEDUP=1.
FEED_DEDUP = os.getenv("E6X_FEED_DEDUP", "0") not in ("0", "", "false", "False")
_FEED_MARKERS = {"highlights", "highlight", "clips", "clip", "recap", "recaps", "aftershow", "aftershows",
                 "condensed", "minisode", "minisodes", "shorts", "bonus", "digest", "roundup", "snippets",
                 "rewind", "encore", "extras", "uncut"}
# filler allowed ALONGSIDE a marker but never sufficient alone (a pure cadence suffix like "X Daily" is KEPT):
_FEED_FILLER = {"the", "of", "a", "an", "and", "with", "daily", "weekly", "monthly", "nightly"}


def _companion_feed(cand_norm, parents):
    """True iff cand_norm is a companion FEED of a parent (followed/skipped) name.
    parents: list of (parent_norm_str, parent_token_tuple), each parent >=2 tokens."""
    for pstr, ptoks in parents:
        if pstr not in cand_norm:                       # fast substring prune (before any tokenizing)
            continue
        ct = cand_norm.split()
        n = len(ptoks)
        for i in range(len(ct) - n + 1):
            if tuple(ct[i:i + n]) == ptoks:             # parent name appears as a contiguous phrase
                extra = ct[:i] + ct[i + n:]             # tokens outside the parent phrase
                if extra and any(t in _FEED_MARKERS for t in extra) \
                        and all(t in _FEED_MARKERS or t in _FEED_FILLER for t in extra):
                    return True
    return False


def _relevance(C, followed, data):
    """Ranking relevance per RELEVANCE_MODE. Returns (rel_vec (N,), clusters_info|None).
    'max' returns exactly C.max(axis=1) so the default path is byte-identical to baseline."""
    if RELEVANCE_MODE == "coherence" and C.shape[1] > 1:
        k = min(3, C.shape[1])
        mean_topk = np.sort(C, axis=1)[:, -k:].mean(axis=1)          # mean of each candidate's top-k follow cosines
        return (COH_MAX_W * C.max(axis=1) + COH_MEAN_W * mean_topk), None
    if RELEVANCE_MODE == "clustered" and C.shape[1] > 1:
        fr = [data.emb[data.row_by_pid[p]] for p in followed if p in data.row_by_pid]
        clusters = []  # each: [sum_vec, count]
        for v in fr:
            placed = False
            for c in clusters:
                mn = c[0] / c[1]; mn = mn / np.clip(np.linalg.norm(mn), 1e-9, None)
                if float(v @ mn) >= CLU_THRESH:
                    c[0] = c[0] + v; c[1] += 1; placed = True; break
            if not placed:
                if len(clusters) < CLU_MAX:
                    clusters.append([v.copy(), 1])
                else:
                    best = max(clusters, key=lambda c: float(v @ ((c[0]/c[1]) / np.clip(np.linalg.norm(c[0]/c[1]), 1e-9, None))))
                    best[0] = best[0] + v; best[1] += 1
        total = sum(c[1] for c in clusters) or 1
        cents, wts = [], []
        for c in clusters:
            m = c[0] / c[1]; cents.append(m / np.clip(np.linalg.norm(m), 1e-9, None)); wts.append(c[1] / total)
        S = data.emb @ np.vstack(cents).T                            # (N, ncl) cosine to each interest centroid
        rel = (S * np.asarray(wts, dtype=np.float32)).max(axis=1)    # max over clusters of size_weight*cosine
        return rel, [{"size": int(c[1]), "weight": round(w, 3)} for c, w in zip(clusters, wts)]
    return C.max(axis=1), None


def _blend(data, row, vertical, mc, rel, nf, foll_fr, foll_ge, skp):
    """Winner-ranking score. pop_dominant with rel=max == baseline formula (byte-identical)."""
    pop = float(data.popularity[row]); cent = float(data.centrality[row]); rec = float(data.recency[row])
    prox = _prox_overlap(data, row, foll_fr, foll_ge)
    if RANK_MODE == "taste_led":
        pw = _taste_pop_weight(nf)                                   # popularity = safety prior, ramps down with follows
        cw = TL_CENT
        if vertical == "podcast":                                    # podcast centrality is degenerate/noise -> to popularity
            pw += cw; cw = 0.0
        rw = 1.0 - (pw + cw + TL_PROX + TL_REC)                      # relevance leads (residual)
        return rw * rel + pw * pop + cw * cent + TL_PROX * prox + TL_REC * rec - skp
    return (W_REL * rel + W_POP * pop + W_CENT * cent + W_PROX * prox + W_REC * rec - skp)

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
    max_cos = C.max(axis=1)                                     # (N,) plain max-to-any: surfaced score + gate + clone cutoffs
    rel_vec, clusters_info = _relevance(C, followed, data)      # (N,) ranking relevance (== max_cos in default 'max' mode)

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
    # E6-P5 (only when FEED_DEDUP): parents for companion-feed exclusion = the user's OWN followed/skipped
    # names with >=2 tokens (short names skipped to avoid over-matching).
    feed_parents = []
    if FEED_DEDUP:
        for p in set(followed) | set(skipped):
            pn = _norm_name(data.meta.get(p, {}).get("name"))
            tk = pn.split()
            if len(tk) >= 2:
                feed_parents.append((pn, tuple(tk)))

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
    global_top = []   # all established genuine candidates (blend, cosine, pid) — for top-N fill when limit>1
    near_conf = 0.0
    # ── candidate pass (O(44k)): collect exclusion-survivors (ALL safety filters UNCHANGED) ──
    survivors = []    # (row, pid, vertical, mc, rel)
    for row, pid in enumerate(data.pids):
        if pid in exclude:
            continue
        m = data.meta[pid]
        if norm_names[row] in exclude_names:                         # W3: duplicate / edition-variant guard (precomputed)
            continue
        if feed_parents and _companion_feed(norm_names[row], feed_parents):   # E6-P5: spin-off/companion feed of a follow/skip
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
        survivors.append((row, pid, v, mc, float(rel_vec[row])))

    # ── ESTABLISH: threshold (mc >= threshold, baseline) | topn (top-N by ranking relevance + null floor) ──
    if ESTABLISH_MODE == "topn":
        established = sorted(survivors, key=lambda s: s[4], reverse=True)[:TOPN]
        if not established or established[0][4] < NULL_FLOOR:
            established = []
    else:
        established = [s for s in survivors if s[3] >= threshold]

    # ── RANK: per-vertical best-blend over established (blend uses the mode's relevance + RANK_MODE weights) ──
    for row, pid, v, mc, rel in established:
        skp = SKIP_PENALTY * max(float(skip_sim[row]) - SIM_FLOOR, 0.0) if skip_sim is not None else 0.0
        blended = _blend(data, row, v, mc, rel, signal_count, foll_fr, foll_ge, skp)
        global_top.append((blended, mc, pid))
        cur = best_per_vert.get(v)
        if cur is None or cur[3] or blended > cur[0]:            # a genuine taste pick always beats a cross pick
            best_per_vert[v] = (blended, mc, pid, False)

    # ── CROSS-VERTICAL EXPLORE (Story 3): podcast survivors NOT established, centrality-gated (trigger UNCHANGED).
    # PODCAST ONLY, topical + graph HUB. taste_led ONLY: surface the pick's real max-to-any cosine (not centrality).
    if xv_active and xv_mask is not None:
        est_pids = {s[1] for s in established}
        for row, pid, v, mc, rel in survivors:
            if v == "podcast" and v not in fvert and pid not in est_pids and xv_mask[row]:
                cen = float(data.centrality[row])
                if cen >= threshold:
                    cur = best_per_vert.get(v)
                    if cur is None or (cur[3] and cen > cur[0]):     # competes only with other cross picks
                        best_per_vert[v] = (cen, (mc if RANK_MODE == "taste_led" else cen), pid, True)

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
            _exp = {}
            if RELEVANCE_MODE != "max":
                _exp["relevance_mode"] = RELEVANCE_MODE
            if clusters_info is not None:
                _exp["clusters"] = clusters_info
            if ESTABLISH_MODE != "threshold":
                _exp["establish_mode"] = ESTABLISH_MODE
            if RANK_MODE != "pop_dominant":
                _exp["rank_mode"] = RANK_MODE
                _pw = _taste_pop_weight(signal_count)
                _pod = (data.meta.get(pid, {}).get("vertical") == "podcast")
                _cw = 0.0 if _pod else TL_CENT
                _pw2 = _pw + (TL_CENT if _pod else 0.0)
                _exp["taste_weights"] = {"relevance": round(1.0 - (_pw2 + _cw + TL_PROX + TL_REC), 3),
                                          "popularity": round(_pw2, 3), "centrality": round(_cw, 3),
                                          "proximity": TL_PROX, "recency": TL_REC}
            if _exp:
                dbg["experimental"] = _exp
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
