"""Composable building blocks (CONTEXT.MD §4). Each wraps a REAL engine over HTTP and returns a
uniform list of result items:

    {"entity_id", "name", "vertical", "score", "why", "source_engine"}

THE INVARIANT (what makes the architecture work):
  * Universe-establishers — graph_constrain, vector_constrain — RETRIEVE (define the candidate set).
  * Refiners — vector_rerank_within, graph_rerank_within, graph_filter_within, apply_negations —
    NEVER retrieve. They operate ONLY on the set passed in: the output is always a subset/reordering
    of the input (no new entity is ever introduced).

Engines (URLs from config):
  graph  (:8010): POST /graph/structured (constrain) · POST /graph/score_within (per-id attrs +
                  influence + pref boost, NO retrieval — powers the graph refiners).
  vector (:8000): POST /api/query (constrain — the only place free retrieval is allowed) ·
                  POST /api/score_set (score a FIXED id set vs a phrase, NO retrieval) ·
                  POST /api/embed (vectors by id / fresh text).
"""

import json
import os
import re
from typing import List, Dict, Any, Optional, Tuple

import httpx

import config

GRAPH = config.GRAPH_API_URL
VECTOR = config.VECTOR_API_URL
T = config.HTTP_TIMEOUT_S

# Deployment: collapsed into one Model Serving container (ROUTER_ENGINE_MODE=inprocess) -> no engine
# servers; _post/_get dispatch the SAME calls in-process (serving/inprocess_engines.py). Default
# 'http' keeps the local two-engine microservice behavior unchanged.
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
    "romantic": "Romance", "romance": "Romance",   # so a "not romantic" negation hard-excludes the Romance genre
    "comedies": "Comedy", "comedic": "Comedy", "funny": "Comedy", "thrillers": "Thriller", "scary": "Horror",
    # NOTE: a non-genre descriptor like "violent" deliberately has NO mapping — it is not a graph genre/theme/
    # concept node, so apply_negations cannot hard-exclude it. We do NOT fake a proxy (e.g. violent→Horror would
    # over-suppress non-violent horror and miss violent thrillers/war). Such negations conservatively no-op.
    "docs": "Documentary", "documentaries": "Documentary",
    "puzzle": "Puzzle & Trivia", "point and click": "Point-and-click",
    "reality tv": "Reality / Unscripted", "reality": "Reality / Unscripted",
    "children": "Kids", "kids'": "Kids",
}


_STOPWORDS = {"the", "and", "with", "for", "from", "into", "that", "this", "your", "you",
              "some", "any", "all", "but", "not", "are", "was"}


def _canon_concept(term: str) -> str:
    """Map a vernacular concept/genre term to the graph's canonical name (identity if unknown)."""
    if not term:
        return term
    return _CONCEPT_SYNONYMS.get(term.strip().lower(), term)


# Genre words → the graph Concept.key (lowercased canonical genre) they establish. Used ONLY to RECOVER a
# positive genre the LLM dropped on a "<genre> but not <X>" query (e.g. "a comedy but not romantic" came
# back with concepts=[], negations=['romantic'] → the positive "comedy" was lost, so the establish became a
# generic bare-vertical pagerank dump). Keyed on whole-word query matches; the negated genre is excluded so
# the working bare-vertical paths ("games but not horror") are NEVER affected (horror is the negation here).
_GENRE_WORDS = {
    "comedy": "comedy", "comedies": "comedy", "comedic": "comedy",
    "horror": "horror", "romance": "romance", "romantic": "romance", "rom-com": "romance",
    "thriller": "thriller", "thrillers": "thriller", "action": "action",
    "drama": "drama", "dramas": "drama", "dramatic": "drama",
    "sci-fi": "science fiction", "scifi": "science fiction", "science fiction": "science fiction",
    "fantasy": "fantasy", "documentary": "documentary", "documentaries": "documentary",
    "crime": "crime", "western": "western", "war": "war",
    "animated": "animation", "animation": "animation", "family": "family",
    "adventure": "adventure", "mystery": "mystery", "musical": "music",
}


def recover_positive_genres(raw_query, negations):
    """Genre words present in the raw query as a WHOLE WORD but NOT among the negations → their canonical
    Concept keys. For the negation path where the LLM dropped the positive genre. Returns [] when the only
    genre word is the negated one (so 'games but not horror' / 'tv but not reality tv' are unchanged)."""
    r = (raw_query or "").lower()
    neg = {_GENRE_WORDS.get((n or "").strip().lower(), (n or "").strip().lower()) for n in (negations or [])}
    found = []
    for word, concept in _GENRE_WORDS.items():
        if concept in neg or concept in found:
            continue
        if re.search(r"\b" + re.escape(word) + r"\b", r):
            found.append(concept)
    return found


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
    """Fetch per-id graph attributes for a FIXED set (no retrieval). Returns {entity_id: attrs}."""
    ids = _ids(items)
    if not ids:
        return {}
    data = _post(f"{GRAPH}/graph/score_within", {"entity_ids": ids})
    return {r["entity_id"]: r for r in data.get("results", [])}


# ═════════════════════════ universe establishers (retrieve) ═════════════════════════

def graph_constrain(hard: dict, vertical: Optional[str] = None, top_k: int = 500) -> List[Item]:
    """Translate structural hard_constraints into the graph engine's structured query
    (wraps cypher_structured via POST /graph/structured). Returns ALL entities satisfying the
    structural constraints. UNIVERSE-ESTABLISHER. (concepts/franchise/developer_relation/developer/
    publisher/vertical are graph-checkable; temporal/non-graph structural are not — handled elsewhere.)"""
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
    """Resolve an entity NAME -> entity_id via the graph engine (for seed similarity).
    NOTE: omit the `vertical` param entirely when None — httpx serialises None as `vertical=` (empty
    string), which the endpoint treats as a real (empty) filter that matches nothing."""
    params = {"q": name, "limit": 1}
    if vertical and vertical != "any":
        params["vertical"] = vertical
    r = _get(f"{GRAPH}/graph/entity_search", params)
    return r["entities"][0]["entity_id"] if r.get("entities") else None


def graph_similar(seed_entity: str, vertical: Optional[str] = None, top_k: int = 200) -> List[Item]:
    """Establish a universe by SIMILARITY to a seed (wraps graph /graph/similar via :SIMILAR_TO).
    Resolves the seed name -> id, then returns its similar entities. UNIVERSE-ESTABLISHER.
    Returns [] if the seed can't be resolved or has no graph signal (e.g. a podcast seed)."""
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


def _date_payload(date_from_ts, date_to_ts) -> dict:
    """Recency: pass UTC epoch bounds to the vector search so it range-filters `release_date_ts`
    natively at search time (payload range filter). Empty when no window → no filter."""
    d = {}
    if date_from_ts is not None:
        d["date_from_ts"] = date_from_ts
    if date_to_ts is not None:
        d["date_to_ts"] = date_to_ts
    return d


def vector_constrain(semantic_core: str, vertical: Optional[str] = None, top_n: int = 50,
                     recall_k: Optional[int] = None,
                     date_from_ts: Optional[int] = None, date_to_ts: Optional[int] = None) -> List[Item]:
    """Establish a SEMANTIC universe via the FULL vector pipeline (`/api/query`: Databricks NLU + anchor
    resolution + hybrid BM25/vector retrieval + ranking) — the strong path (06b/07a showed the full
    pipeline materially beats no-NLU retrieval). UNIVERSE-ESTABLISHER.

    TWO-STAGE (07e): when `recall_k` is set, cast a WIDE embedding recall net instead — pure Qdrant
    vector search at depth recall_k via /api/retrieve (more neighbors than /api/query's fixed 10), to be
    reranked by the cross-encoder (Stage 2). Default recall_k=None → the current /api/query behavior.

    IMPORTANT (07a): multi-vertical / cross-vertical / "all categories" queries return their results under
    `results_by_vertical` with an EMPTY top-level `results` — we read BOTH so vector-establish never
    returns a fake-empty universe on multi-vertical queries.
    The phrase passed here MUST be POSITIVE-ONLY (negations are applied later by graph apply_negations) so
    the vector NLU never over-negates to empty. Falls back to no-NLU /api/retrieve only if /api/query is
    down."""
    phrase = (semantic_core or "").strip()
    vert = vertical if (vertical and vertical != "any") else None
    dp = _date_payload(date_from_ts, date_to_ts)   # recency: epoch bounds → native payload range filter
    if recall_k:                                   # WIDE recall net for two-stage (Qdrant embedding recall)
        data = _post(f"{VECTOR}/api/retrieve", {"phrase": phrase, "vertical": vert, "top_k": recall_k, **dp})
        return [_item(r.get("entity_id"), r["name"], r["vertical"], r.get("score"),
                      f"wide recall '{semantic_core}' (cosine {(r.get('score') or 0.0):.3f})", "vector(wide)")
                for r in data.get("results", [])]
    # B1 (query-mangling fix): embed the POSITIVE PHRASE verbatim — never concatenate the pluralised
    # vertical word into the query text ("a movie to watch tonight" must NOT become "…tonight movies").
    # The vertical is passed as an explicit FILTER instead; the vector engine applies it without
    # polluting the embedded text.
    try:
        data = _post(f"{VECTOR}/api/query", {"query": phrase, "vertical": vert, **dp})
    except httpx.HTTPError:
        data = _post(f"{VECTOR}/api/retrieve", {"phrase": phrase, "vertical": vert, "top_k": top_n, **dp})
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
    return out


def vector_seed_constrain(seed_entities, vertical: Optional[str] = None, top_k: int = 200) -> List[Item]:
    """Establish a universe from one or MORE seed entities' COMBINED vector neighborhood (multi-seed union,
    CONTEXT §7-ish). Resolve each seed name → entity_id (graph), then `/api/neighbors(anchor_ids=[…],
    vertical=target)` which fetches each anchor's STORED vector, Qdrant-searches with it, merges by best
    cosine, and excludes the anchors. Handles single-seed, multi-seed union, AND cross-vertical
    (anchor=game, vertical=movie → movies near the game). UNIVERSE-ESTABLISHER. Returns [] if NO seed
    resolves (caller falls back to a raw-query vector establish)."""
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
    """{lowercased key -> display name} of the graph's REAL concept vocabulary (cached)."""
    global _concept_vocab
    if _concept_vocab is None:
        try:
            data = _get(f"{GRAPH}/graph/concepts", {})
            _concept_vocab = {c["key"].lower(): c["name"] for c in data.get("concepts", [])}
        except Exception:
            _concept_vocab = {}
    return _concept_vocab


def resolve_concepts(terms: List[str]) -> Tuple[List[str], List[str]]:
    """Split LLM-extracted concept terms into (hard graph-concepts, leftover soft terms) using the
    graph's REAL vocabulary as ground truth. A term that IS a graph concept (after synonym +
    hyphen normalisation, or via a known token inside a compound phrase) becomes a HARD constraint;
    a term the graph doesn't recognise (mood/quality words like 'dark', 'intense', 'psychological')
    is returned as a leftover for the assembler to fold into SOFT intent — so it refines rather than
    zeroing the universe. This deterministically corrects the LLM's residual hard-vs-soft mis-bucketing."""
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
    hard = [c for c in hard if c and not (c in seen or seen.add(c))]   # drop None/empty (graph Concept w/ null name)
    return hard, soft


# ═════════════════════════ refiners (NEVER retrieve; output ⊆ input) ════════════════

def vector_rerank_within(items: List[Item], semantic: str) -> List[Item]:
    """Reorder the PASSED-IN set by semantic similarity to `semantic` (cosine of the phrase vs each
    entity's STORED vector, via POST /api/score_set). Does NOT retrieve. Returns exactly the input
    members, reordered; entities with no stored vector keep their place at the end."""
    if not semantic or not items:
        return list(items)
    ids = _ids(items)
    if not ids:
        return list(items)
    data = _post(f"{VECTOR}/api/score_set", {"phrase": semantic, "entity_ids": ids})
    score_map = {s["entity_id"]: (s.get("score") or 0.0) for s in data.get("scored", [])}   # None score → 0.0 (avoid format/sort crash)
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
    """Reorder the PASSED-IN set by structural signals (PageRank influence, structural_prefs match,
    optional shared-concept overlap with a seed) via POST /graph/score_within. Does NOT retrieve.
    Returns exactly the input members, reordered; non-graph entities keep their place at the end."""
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
            bits = [f"influence {(r.get('influence') or 0):.2f}"]   # None-safe: .get(key,0) keeps a None value
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
    """Remove members of the PASSED-IN set that VIOLATE a structural hard constraint (concepts /
    franchise / developer), using per-id attributes from POST /graph/score_within. Does NOT retrieve;
    output is strictly a subset of the input. Entities whose attributes can't be verified (e.g. a
    podcast with no concepts) are dropped when a constraint is present — a hard constraint must be
    provably satisfied."""
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
    """Hard-exclude members matching any negation term (against the entity's concepts / genres /
    themes / keywords, or a name substring). Does NOT retrieve; output ⊆ input. Best-effort: a
    negation only excludes structurally when it maps to a graph attribute (e.g. 'sports', 'animated');
    name-substring catches the rest."""
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
    """FINAL-STAGE learned reranker (REFINER — reorders the established set, never retrieves/adds).
    Scores the query against each candidate's ENRICHED text via the LLM and returns the top_k reordered.
    Output is always a subset/permutation of the input (asserted by construction). Degrades to the input
    order on any failure (LLM/parse/text-fetch), so it is never worse than no-rerank on availability.

    NOTE: this is a SECOND LLM call on reranked paths (the cross-encoder dep — torch/sentence-transformers
    — is not installed; per the task this is the sanctioned fallback). Latency cost is measured in eval."""
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
    """Lazy singleton — loads the local cross-encoder once (~31s first call, then in-process)."""
    global _XENC
    if _XENC is None:
        from sentence_transformers import CrossEncoder
        _XENC = CrossEncoder(_XENC_NAME)
    return _XENC


def rerank_cross_encoder(query: str, items: List[Item], top_k: int = 10, pool: int = 100) -> List[Item]:
    """FINAL-STAGE cross-encoder reranker (REFINER — reorders the established set, never retrieves/adds).
    Scores (query, candidate_enriched_text) pairs JOINTLY with a local cross-encoder and returns the
    top_k reordered. Deterministic, no extra LLM call (unlike 09's LLM reranker). Output is a strict
    subset of the input (asserted by construction); degrades to input order on any failure."""
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
