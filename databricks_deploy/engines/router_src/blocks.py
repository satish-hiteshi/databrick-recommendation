import json
import os
import re
from typing import List, Dict, Any, Optional, Tuple

import httpx

import config

GRAPH = config.GRAPH_API_URL
VECTOR = config.VECTOR_API_URL
T = config.HTTP_TIMEOUT_S

# Deployment: when collapsed into one Model Serving container (ROUTER_ENGINE_MODE=inprocess) there are
# no engine servers — _post/_get dispatch the SAME calls in-process (databricks_deploy/serving/
# inprocess_engines.py). Default "http" keeps the local two-engine microservice behavior unchanged.
_INPROC = os.getenv("ROUTER_ENGINE_MODE", "http").lower() == "inprocess"

Item = Dict[str, Any]


def _item(entity_id, name, vertical, score, why, source) -> Item:
    return {"entity_id": entity_id, "name": name, "vertical": vertical,
            "score": score, "why": why, "source_engine": source}


# ── concept vernacular → graph canonical concept name ──────────────────────────────
# The LLM extracts everyday terms ("RPG", "sci-fi", "animated"); the graph's Concept nodes use
# canonical names ("Role-Playing", "Science Fiction", "Animation"). The graph matches by lowercased
# key, so we only need to map the vernacular to the canonical name (it is lowercased downstream).
# Unknown terms pass through unchanged (graph just won't match → correctly returns nothing for that
# constraint, never a wrong match). Kept deliberately small + safe; tied to the live vocabulary.
_CONCEPT_SYNONYMS = {
    "rpg": "Role-Playing", "rpgs": "Role-Playing", "role playing": "Role-Playing",
    "role-playing game": "Role-Playing", "role playing game": "Role-Playing",
    "roleplaying": "Role-Playing", "jrpg": "Role-Playing", "arpg": "Role-Playing",
    "sci-fi": "Science Fiction", "scifi": "Science Fiction", "sci fi": "Science Fiction",
    "science-fiction": "Science Fiction",
    "animated": "Animation", "anime": "Animation",
    "rom-com": "Romance", "romantic comedy": "Romance", "rom coms": "Romance",
    "docs": "Documentary", "documentaries": "Documentary",
    "puzzle": "Puzzle & Trivia", "point and click": "Point-and-click",
    "reality tv": "Reality / Unscripted", "reality": "Reality / Unscripted",
    "children": "Kids", "kids'": "Kids",
}


_STOPWORDS = {"the", "and", "with", "for", "from", "into", "that", "this", "your", "you",
              "some", "any", "all", "but", "not", "are", "was"}


def _canon_concept(term: str) -> str:
    if not term:
        return term
    return _CONCEPT_SYNONYMS.get(term.strip().lower(), term)


def _post(url: str, body: dict) -> dict:
    if _INPROC:
        from inprocess_engines import dispatch
        return dispatch("POST", url, body)
    last = None
    for attempt in range(3):                 # tolerate transient 5xx (e.g. vector NLU rate-limit blips)
        try:
            r = httpx.post(url, json=body, timeout=T)
            if r.status_code < 500:
                r.raise_for_status()
                return r.json()
            last = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
        except httpx.HTTPError as e:
            last = e
    raise last


def _get(url: str, params: dict) -> dict:
    if _INPROC:
        from inprocess_engines import dispatch
        return dispatch("GET", url, params)
    return httpx.get(url, params=params, timeout=T).json()


def _ids(items: List[Item]) -> List[str]:
    return [it["entity_id"] for it in items if it.get("entity_id")]


def _graph_attrs(items: List[Item]) -> Dict[str, dict]:
    ids = _ids(items)
    if not ids:
        return {}
    data = _post(f"{GRAPH}/graph/score_within", {"entity_ids": ids})
    return {r["entity_id"]: r for r in data.get("results", [])}


# ═════════════════════════ universe establishers (retrieve) ═════════════════════════

def graph_constrain(hard: dict, vertical: Optional[str] = None, top_k: int = 500) -> List[Item]:
    hard = hard or {}
    vert = vertical or hard.get("vertical")
    filters: Dict[str, Any] = {"top_k": top_k}
    if vert and vert != "any":
        filters["vertical"] = vert
    if hard.get("concepts"):
        filters["concept"] = [_canon_concept(c) for c in hard["concepts"]]   # RPG→Role-Playing, etc.
    if hard.get("franchise"):
        filters["franchise"] = hard["franchise"]
    dr = hard.get("developer_relation") or {}
    if dr.get("also_made"):
        filters["developer_also_made"] = _canon_concept(dr["also_made"])      # the multi-hop concept
    struct = hard.get("structural") or {}
    if struct.get("developer"):
        filters["developer"] = struct["developer"]
    if struct.get("publisher"):
        filters["publisher"] = struct["publisher"]
    data = _post(f"{GRAPH}/graph/structured", filters)
    return [_item(r.get("entity_id"), r["name"], r["vertical"], r.get("score"),
                  r.get("why"), "graph") for r in data.get("results", [])]


def _resolve(name: str, vertical: Optional[str] = None) -> Optional[str]:
    params = {"q": name, "limit": 1}
    if vertical and vertical != "any":
        params["vertical"] = vertical
    r = _get(f"{GRAPH}/graph/entity_search", params)
    return r["entities"][0]["entity_id"] if r.get("entities") else None


def graph_similar(seed_entity: str, vertical: Optional[str] = None, top_k: int = 200) -> List[Item]:
    rid = _resolve(seed_entity, vertical)
    if not rid:
        return []
    data = _post(f"{GRAPH}/graph/similar",
                 {"entity_id": rid, "top_k": top_k,
                  "vertical": vertical if vertical and vertical != "any" else None})
    if data.get("status") != "success":
        return []                                   # no_graph_signal / not_found
    return [_item(r.get("entity_id"), r["name"], r["vertical"], r.get("score"),
                  r.get("why"), "graph_similar") for r in data.get("results", [])]


def vector_constrain(semantic_core: str, vertical: Optional[str] = None, top_n: int = 50,
                     recall_k: Optional[int] = None) -> List[Item]:
    phrase = (semantic_core or "").strip()
    vert = vertical if (vertical and vertical != "any") else None
    if recall_k:                                   # WIDE recall net for two-stage (Qdrant embedding recall)
        data = _post(f"{VECTOR}/api/retrieve", {"phrase": phrase, "vertical": vert, "top_k": recall_k})
        return [_item(r.get("entity_id"), r["name"], r["vertical"], r.get("score"),
                      f"wide recall '{semantic_core}' (cosine {r.get('score'):.3f})", "vector(wide)")
                for r in data.get("results", [])]
    q = f"{phrase} {vert}s".strip() if vert else phrase
    try:
        data = _post(f"{VECTOR}/api/query", {"query": q})
    except httpx.HTTPError:
        data = _post(f"{VECTOR}/api/retrieve", {"phrase": phrase, "vertical": vert, "top_k": top_n})
        return [_item(r.get("entity_id"), r["name"], r["vertical"], r.get("score"),
                      f"semantic match '{semantic_core}'", "vector(retrieve-fallback)")
                for r in data.get("results", [])]
    res = list(data.get("results") or [])
    if not res and data.get("results_by_vertical"):          # multi-vertical → flatten (07a critical fix)
        for v in data["results_by_vertical"].values():
            res += list(v or [])
    out: List[Item] = []
    for r in res:
        if vert and r.get("vertical") != vert:
            continue
        it = _item(r.get("entity_id"), r["name"], r["vertical"],
                   r.get("final_score"), r.get("reasoning_short") or f"semantic match '{semantic_core}'",
                   "vector")
        # passthrough the vector engine's retrieval EVIDENCE (additive — for the chat UI's dual-signal
        # card: RRF / Vector #N / BM25 #N / Dual-Signal / % match / date). NOT a scoring change.
        for k in ("rrf_score", "vector_rank", "bm25_rank", "appeared_in_vector", "appeared_in_bm25",
                  "in_both_sets", "appeared_in_searches", "shared_keywords", "similarity_percentage",
                  "release_date", "reasoning_long"):
            if k in r:
                it[k] = r[k]
        out.append(it)
        if len(out) >= top_n:
            break
    # ESTABLISHER SAFETY: an establisher must NEVER zero a POPULATED universe. The NLU pipeline can yield
    # nothing for `vert` on a SPARSE phrase — it re-targets "co-op, not too competitive" across verticals
    # and the vertical post-filter above then drops every row. Fall back to pure embedding recall
    # (/api/retrieve), which returns nearest neighbors for any phrase the vertical can answer, so a
    # legitimate game query never returns EMPTY just because the NLU spread it thin.
    if not out and phrase:
        data = _post(f"{VECTOR}/api/retrieve", {"phrase": phrase, "vertical": vert, "top_k": top_n})
        out = [_item(r.get("entity_id"), r["name"], r["vertical"], r.get("score"),
                     f"semantic match '{semantic_core}' (recall fallback)", "vector(retrieve-fallback)")
               for r in data.get("results", [])]
    return out


def vector_seed_constrain(seed_entities, vertical: Optional[str] = None, top_k: int = 200) -> List[Item]:
    if isinstance(seed_entities, str):
        names = [s.strip() for s in re.split(r",|\band\b", seed_entities) if s.strip()]   # NOT '&' (D&D)
    else:
        names = [str(s).strip() for s in (seed_entities or []) if str(s).strip()]
    vert = vertical if (vertical and vertical != "any") else None
    ids = []
    for nm in names:
        rid = _resolve(nm, None)                 # resolve in ANY vertical (seed's own vertical ≠ target)
        if rid:
            ids.append(rid)
    label = ("seeds " if len(names) > 1 else "seed ") + ", ".join(names) + (f" → {vert}" if vert else "")
    if ids:
        data = _post(f"{VECTOR}/api/neighbors",
                     {"anchor_ids": ids, "exclude_ids": ids, "vertical": vert, "top_k": top_k})
        return [_item(n["entity_id"], n["name"], n["vertical"], n.get("score"),
                      f"near {label} (combined vector neighborhood)", "vector(seed-neighbors)")
                for n in data.get("neighbors", [])]
    # no seed resolved (entity not in the graph) → semantic retrieval on the seed NAME(s), filtered to
    # the target vertical — the robust cross-vertical fallback so a seed query never falls to EMPTY
    # (e.g. "Jurassic World Dominion" + game → dinosaur/survival games).
    phrase = " ".join(names).strip()
    if not phrase:
        return []
    try:
        data = _post(f"{VECTOR}/api/retrieve", {"phrase": phrase, "vertical": vert, "top_k": top_k})
    except httpx.HTTPError:
        return []
    return [_item(n["entity_id"], n["name"], n["vertical"], n.get("score"),
                  f"semantic neighbour of {label} (seed not in graph → vector retrieval)",
                  "vector(seed-retrieve)")
            for n in data.get("results", [])]


# ── concept vocabulary (fetched once from the graph) + LLM-concept resolver ──────────
_concept_vocab: Optional[Dict[str, str]] = None


def _known_concepts() -> Dict[str, str]:
    global _concept_vocab
    if _concept_vocab is None:
        try:
            data = _get(f"{GRAPH}/graph/concepts", {})
            _concept_vocab = {c["key"].lower(): c["name"] for c in data.get("concepts", [])}
        except Exception:
            _concept_vocab = {}
    return _concept_vocab


def resolve_concepts(terms: List[str]) -> Tuple[List[str], List[str]]:
    known = _known_concepts()
    if not known:                                       # vocab unavailable → keep concepts hard (safe)
        return ([_canon_concept(t) for t in (terms or []) if t and t.strip()], [])
    hard, soft = [], []
    for t in terms or []:
        if not t or not t.strip():
            continue
        canon = _canon_concept(t).strip().lower()       # synonyms (RPG→role-playing)
        if canon in known:
            hard.append(known[canon]); continue
        hy = canon.replace("-", " ")
        if hy in known:
            hard.append(known[hy]); continue
        matched, unmatched = [], []                      # compound phrase → split known vs unknown tokens
        for w in re.split(r"[\s/&,]+|\band\b", canon):
            w = w.strip()
            if not w:
                continue
            if w in known:
                matched.append(known[w])
            elif w.replace("-", " ") in known:
                matched.append(known[w.replace("-", " ")])
            elif len(w) >= 3 and w not in _STOPWORDS:
                unmatched.append(w)
        if matched:
            hard.extend(matched)
            if unmatched:                                # keep the mood nuance ("psychological") as SOFT
                soft.append(" ".join(unmatched))
        else:
            soft.append(t)                               # unknown → mood/quality → fold to soft
    seen = set()
    hard = [c for c in hard if not (c in seen or seen.add(c))]
    return hard, soft


# ═════════════════════════ refiners (NEVER retrieve; output ⊆ input) ════════════════

def vector_rerank_within(items: List[Item], semantic: str) -> List[Item]:
    if not semantic or not items:
        return list(items)
    ids = _ids(items)
    if not ids:
        return list(items)
    data = _post(f"{VECTOR}/api/score_set", {"phrase": semantic, "entity_ids": ids})
    score_map = {s["entity_id"]: s["score"] for s in data.get("scored", [])}
    scored, unscored = [], []
    for it in items:
        eid = it.get("entity_id")
        if eid in score_map:
            ni = dict(it)
            ni["score"] = score_map[eid]
            ni["why"] = f"semantic rerank ‘{semantic}’ (cosine {score_map[eid]:.3f})"
            ni["source_engine"] = (it.get("source_engine") or "") + "+vector_rerank"
            scored.append(ni)
        else:
            unscored.append(dict(it))
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored + unscored


def graph_rerank_within(items: List[Item], structural_prefs: Optional[dict] = None,
                        seed_entity: Optional[str] = None) -> List[Item]:
    if not items:
        return []
    ids = _ids(items)
    if not ids:
        return list(items)
    data = _post(f"{GRAPH}/graph/score_within",
                 {"entity_ids": ids, "structural_prefs": structural_prefs or {},
                  "seed_entity": seed_entity})
    score_map = {r["entity_id"]: r for r in data.get("results", [])}
    scored, unscored = [], []
    for it in items:
        r = score_map.get(it.get("entity_id"))
        if r is not None:
            ni = dict(it)
            ni["score"] = r["score"]
            bits = [f"influence {r.get('influence', 0):.2f}"]
            if r.get("pref_hits"):
                bits.append("prefs: " + ", ".join(r["pref_hits"]))
            ni["why"] = "graph rerank (" + "; ".join(bits) + ")"
            ni["source_engine"] = (it.get("source_engine") or "") + "+graph_rerank"
            scored.append(ni)
        else:
            unscored.append(dict(it))
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored + unscored


def graph_filter_within(items: List[Item], hard: dict) -> List[Item]:
    hard = hard or {}
    req_concepts = {c.lower() for c in (hard.get("concepts") or [])}
    fr = (hard.get("franchise") or "").lower() or None
    dev = ((hard.get("structural") or {}).get("developer") or "").lower() or None
    if not (req_concepts or fr or dev):
        return list(items)                       # nothing structural to filter on
    attrs = _graph_attrs(items)
    kept = []
    for it in items:
        a = attrs.get(it.get("entity_id"))
        if a is None:
            continue                             # unverifiable vs a hard constraint -> exclude
        ok = True
        if req_concepts and not req_concepts.issubset({c.lower() for c in (a.get("concepts") or [])}):
            ok = False
        if fr and (a.get("franchise") or "").lower() != fr:
            ok = False
        if dev and (a.get("developer") or "").lower() != dev:
            ok = False
        if ok:
            kept.append(dict(it))
    return kept


def apply_negations(items: List[Item], negations: Optional[List[str]]) -> List[Item]:
    raw = [n.strip().lower() for n in (negations or []) if n and n.strip()]
    if not raw:
        return list(items)
    # each negation contributes its raw form (for name-substring) + its canonical concept (for the
    # attribute bag): "animated"→"animation", "reality tv"→"reality / unscripted", etc.
    negs = [(n, _canon_concept(n).lower()) for n in raw]
    attrs = _graph_attrs(items)
    kept = []
    for it in items:
        a = attrs.get(it.get("entity_id")) or {}
        bag = {x.lower() for x in
               (a.get("concepts", []) + a.get("genres", []) + a.get("themes", []) + a.get("keywords", []))}
        name_l = (it.get("name") or "").lower()
        hit = False
        for n, canon in negs:
            ntoks = set(n.replace("-", " ").split())
            if (n in bag or canon in bag or n in name_l or (ntoks and ntoks <= bag)):
                hit = True
                break
        if not hit:
            kept.append(dict(it))
    return kept


_RERANK_SYS = (
    "You are a search RERANKER for an entertainment discovery system (games, movies, TV, podcasts). "
    "Given a user query and a numbered list of candidate titles (each with its vertical and a short "
    "enriched description), reorder ALL candidates from MOST to LEAST relevant to the query — judging "
    "true relevance to EVERY part of the query (entities, theme, mood, constraints), not just surface "
    "word overlap. Return ONLY strict json: {\"order\": [indices]} containing every candidate index "
    "exactly once, most relevant first. No prose."
)


def rerank_learned(query: str, items: List[Item], top_k: int = 10, pool: int = 40) -> List[Item]:
    if not items:
        return []
    pool_items = items[:pool]
    ids = [it["entity_id"] for it in pool_items if it.get("entity_id")]
    texts: Dict[str, dict] = {}
    try:
        texts = _post(f"{VECTOR}/api/texts", {"entity_ids": ids, "max_chars": 280}).get("texts", {})
    except Exception:
        texts = {}
    lines = []
    for i, it in enumerate(pool_items):
        snip = (texts.get(it.get("entity_id"), {}) or {}).get("text", "")
        lines.append(f"[{i}] {it['name']} ({it['vertical']}) — {snip}".strip())
    user = f'Query: "{query}"\n\nCandidates:\n' + "\n".join(lines) + \
           '\n\nReturn {"order": [indices most→least relevant, every index exactly once]}.'
    try:
        from llm import llm_complete
        raw = llm_complete(_RERANK_SYS, user)
        a, b = raw.find("{"), raw.rfind("}")
        order = json.loads(raw[a:b + 1]).get("order", [])
    except Exception:
        return [dict(it) for it in pool_items[:top_k]]          # graceful no-op (original order)
    seen, reordered = set(), []
    for idx in order:
        if isinstance(idx, int) and 0 <= idx < len(pool_items) and idx not in seen:
            seen.add(idx)
            reordered.append(pool_items[idx])
    for i, it in enumerate(pool_items):                          # append any the LLM dropped (permutation)
        if i not in seen:
            reordered.append(it)
    out = []
    for it in reordered[:top_k]:
        ni = dict(it)
        ni["source_engine"] = (it.get("source_engine") or "") + "+rerank_learned"
        out.append(ni)
    return out


# ── cross-encoder reranker (local; Stage 2 of two-stage retrieval, 07e) ──────────────
_XENC = None
_XENC_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _cross_encoder():
    global _XENC
    if _XENC is None:
        from sentence_transformers import CrossEncoder
        _XENC = CrossEncoder(_XENC_NAME)
    return _XENC


def rerank_cross_encoder(query: str, items: List[Item], top_k: int = 10, pool: int = 100) -> List[Item]:
    if not items:
        return []
    pool_items = items[:pool]
    ids = [it["entity_id"] for it in pool_items if it.get("entity_id")]
    texts: Dict[str, dict] = {}
    try:
        texts = _post(f"{VECTOR}/api/texts", {"entity_ids": ids, "max_chars": 500}).get("texts", {})
    except Exception:
        texts = {}
    pairs = []
    for it in pool_items:
        snip = (texts.get(it.get("entity_id"), {}) or {}).get("text", "")
        pairs.append((query, f"{it['name']} ({it['vertical']}). {snip}".strip()))
    try:
        scores = _cross_encoder().predict(pairs)
    except Exception:
        return [dict(it) for it in pool_items[:top_k]]          # graceful no-op (original order)
    order = sorted(range(len(pool_items)), key=lambda i: -float(scores[i]))
    out = []
    for i in order[:top_k]:
        ni = dict(pool_items[i])
        ni["score"] = round(float(scores[i]), 4)
        ni["source_engine"] = (pool_items[i].get("source_engine") or "") + "+xenc"
        ni["why"] = f"cross-encoder rerank (score {ni['score']})" + (f" · {pool_items[i].get('why','')}" if pool_items[i].get("why") else "")
        out.append(ni)
    return out


if __name__ == "__main__":
    s = graph_constrain({"vertical": "game", "concepts": ["horror"],
                         "developer_relation": {"also_made": "Role-Playing"}})
    print(f"graph_constrain(multi-hop) -> {len(s)} items; sample:")
    for it in s[:3]:
        print("  ", json.dumps(it, ensure_ascii=False))
