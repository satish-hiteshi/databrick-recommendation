import time
from urllib.parse import urlsplit

import numpy as np


# ════════════════════════ graph driver (Neo4j Aura), lazy singleton ════════════════════════
_DRIVER = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        from neo4j import GraphDatabase
        from connection import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
        # Fail-fast timeouts (under the feeds-api ~3s budget) + recycle connections BEFORE Aura drops
        # idle ones — that idle-drop is the usual cause of intermittent "empty". Connects lazily (no
        # verify_connectivity round-trip / failure point at init).
        _DRIVER = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_lifetime=180, connection_acquisition_timeout=5,
            connection_timeout=5, keep_alive=True)
    return _DRIVER


def _reset_driver():
    global _DRIVER
    try:
        if _DRIVER is not None:
            _DRIVER.close()
    except Exception:
        pass
    _DRIVER = None


def _db():
    from connection import NEO4J_DATABASE
    return NEO4J_DATABASE


# ════════════════════════════════ vector handlers ════════════════════════════════
def _vec_query(body):
    from pipeline.query_engine import process_query
    return process_query(body["query"])


def _vec_retrieve(body):
    from pipeline.embedding_generator import embed_query_text
    from pipeline.vector_store import vector_search
    phrase = body.get("phrase", "")
    vertical = body.get("vertical")
    top_k = body.get("top_k", 50)
    verts = {vertical} if (vertical and vertical != "any") else None
    vec = np.asarray(embed_query_text(phrase), dtype=np.float32)
    out = [{"entity_id": eid, "name": name, "vertical": vert, "score": round(float(score), 6)}
           for (eid, name, vert, score) in vector_search(vec, verts, top_k)]
    return {"phrase": phrase, "model": "voyage-4-large", "vertical": vertical,
            "results": out, "count": len(out)}


def _vec_score_set(body):
    from pipeline.embedding_generator import cosine_similarity, embed_query_text
    import inmemory_store
    phrase = body["phrase"]
    ids = body.get("entity_ids", [])
    pv = embed_query_text(phrase)
    emb = inmemory_store.embeddings()                 # 57k corpus vectors (parquet-backed)
    scored, missing = [], []
    for eid in ids:
        v = emb.get(eid)
        if v is None:
            missing.append(eid)
            continue
        scored.append({"entity_id": eid, "score": round(cosine_similarity(pv, v), 6)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"phrase": phrase, "model": "voyage-4-large", "scored": scored, "missing": missing,
            "n_in": len(ids), "n_scored": len(scored)}


def _vec_neighbors(body):
    from pipeline.vector_store import vector_search
    import inmemory_store
    anchor_ids = body.get("anchor_ids", [])
    exclude = set(body.get("exclude_ids") or []) | set(anchor_ids)
    vertical = body.get("vertical")
    top_k = body.get("top_k", 20)
    per_anchor = body.get("per_anchor", 25)
    verts = {vertical} if (vertical and vertical != "any") else None
    emb = inmemory_store.embeddings()                 # 57k corpus vectors (parquet-backed)
    best = {}
    for aid in anchor_ids:
        v = emb.get(aid)
        if v is None:
            continue
        for (eid, name, vert, score) in vector_search(np.asarray(v, dtype=np.float32), verts, per_anchor):
            if eid in exclude:
                continue
            sc = float(score)
            if eid not in best or sc > best[eid][0]:
                best[eid] = (sc, name, vert)
    out = [{"entity_id": eid, "name": nv[1], "vertical": nv[2], "score": round(nv[0], 6)}
           for eid, nv in best.items()]
    out.sort(key=lambda x: x["score"], reverse=True)
    return {"neighbors": out[:top_k], "n_anchors": len(anchor_ids), "n_found": len(out)}


_TEXTS = None


def _vec_texts(body):
    global _TEXTS
    if _TEXTS is None:
        from pipeline.data_loader import get_all_entities
        _TEXTS = {e["entity_id"]: {"name": e["name"], "vertical": e["vertical"],
                                   "text": (e.get("composed_text") or "").strip().replace("\n", " ")}
                  for e in get_all_entities()}
    ids = body.get("entity_ids") or []
    mx = body.get("max_chars", 600)
    out = {}
    for eid in ids:
        t = _TEXTS.get(eid)
        if t:
            out[eid] = {"name": t["name"], "vertical": t["vertical"], "text": t["text"][:mx]}
    return {"texts": out, "n": len(out)}


# ════════════════════════════════ graph handlers ════════════════════════════════
def _score_of(r):
    return float(r.get("rerank_score", r.get("score", 0)) or 0)


def _fmt(raw, top_k):
    items = list(raw)[:top_k]
    scores = [_score_of(r) for r in items]
    mx = max(scores) if scores else 1.0
    out = []
    for i, r in enumerate(items, 1):
        sc = _score_of(r)
        why = r.get("why", "") or ""
        out.append({
            "rank": i, "name": r.get("name"), "vertical": r.get("vertical"),
            "final_score": round(sc, 4),
            "similarity_percentage": round((sc / mx) * 100) if mx > 0 else 0,
            "reasoning_short": why, "reasoning_long": why,
            "entity_id": r.get("entity_id"), "score": round(sc, 4), "why": why,
        })
    return out


def _graph_structured(body):
    import query as Q
    top_k = body.get("top_k", 10)
    filters = {k: v for k, v in body.items() if k != "top_k" and v is not None}
    r = Q.cypher_structured(filters, limit=top_k)
    return {"engine": "graph", "endpoint": "structured", "filters": filters,
            "status": "success" if r else "no_results",
            "result_count": len(r), "results": _fmt(r, top_k)}


def _graph_similar(body):
    import query as Q
    eid = body.get("entity_id")
    top_k = body.get("top_k", 10)
    vertical = body.get("vertical")
    r = Q.similar_by_attributes(eid, vertical=vertical, limit=top_k)
    if isinstance(r, dict):                          # no_graph_signal / not_found
        return {"engine": "graph", "endpoint": "similar", "entity_id": eid,
                "status": r.get("status"), "reason": r.get("reason"),
                "result_count": 0, "results": []}
    return {"engine": "graph", "endpoint": "similar", "entity_id": eid, "status": "success",
            "result_count": len(r), "results": _fmt(r, top_k)}


# Cypher copied verbatim from src/api.py::_SCORE_WITHIN_CYPHER (so the result shape is identical).
_SCORE_WITHIN_CYPHER = """
MATCH (e:Entity) WHERE e.entity_id IN $ids
RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical,
       e.influence AS influence, e.community AS community,
       [(e)-[:HAS_CONCEPT]->(c)  | c.key]          AS concepts,
       [(e)-[:HAS_KEYWORD]->(k)  | toLower(k.name)] AS keywords,
       [(e)-[:HAS_GENRE]->(g)    | toLower(g.name)] AS genres,
       [(e)-[:HAS_THEME]->(t)    | toLower(t.name)] AS themes,
       [(e)-[:IN_FRANCHISE]->(f) | f.name][0]      AS franchise,
       [(e)-[:DEVELOPED_BY]->(d) | d.name][0]      AS developer,
       [(e)-[:PUBLISHED_BY]->(p) | p.name][0]      AS publisher
"""


def _graph_score_within(body):
    ids = body.get("entity_ids", [])
    prefs = body.get("structural_prefs") or {}
    seed = body.get("seed_entity")
    pref_vals = [str(v).lower() for v in prefs.values()]
    with _driver().session(database=_db()) as s:
        rows = [r.data() for r in s.run(_SCORE_WITHIN_CYPHER, ids=ids)]
        seed_concepts = set()
        if seed:
            rec = s.run("MATCH (e:Entity {entity_id:$id})-[:HAS_CONCEPT]->(c) "
                        "RETURN collect(c.key) AS cs", id=seed).single()
            if rec and rec["cs"]:
                seed_concepts = set(rec["cs"])
    infl = [(r["influence"] or 0.0) for r in rows]
    mn, mx = (min(infl), max(infl)) if infl else (0.0, 1.0)
    rng = (mx - mn) or 1.0
    out = []
    for r in rows:
        bag = set((r["concepts"] or []) + (r["keywords"] or []) + (r["genres"] or []) + (r["themes"] or []))
        name_l = (r["name"] or "").lower()
        hits = [v for v in pref_vals if v in bag or v in name_l]
        pref_match = (len(hits) / len(pref_vals)) if pref_vals else 0.0
        norm_infl = ((r["influence"] or 0.0) - mn) / rng
        seed_overlap = (len(seed_concepts & set(r["concepts"] or [])) / len(seed_concepts)) if seed_concepts else 0.0
        r["pref_match"] = round(pref_match, 3)
        r["pref_hits"] = hits
        r["score"] = round(norm_infl + 0.5 * pref_match + 0.5 * seed_overlap, 4)
        out.append(r)
    out.sort(key=lambda x: x["score"], reverse=True)
    found = {r["entity_id"] for r in rows}
    return {"results": out, "n_in": len(ids), "n_scored": len(out),
            "missing": [i for i in ids if i not in found]}


def _graph_entity_search(params):
    q = params.get("q")
    limit = int(params.get("limit", 10))
    vertical = params.get("vertical")
    cypher = (
        "MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($q) "
        "AND ($v IS NULL OR e.vertical = $v) "
        "RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical, "
        "round(e.influence,4) AS influence, "
        "size([(e)-[:HAS_CONCEPT]->()|1]) AS concept_count "
        "ORDER BY (toLower(e.name) = toLower($q)) DESC, e.influence DESC LIMIT $limit")
    with _driver().session(database=_db()) as s:
        rows = [r.data() for r in s.run(cypher, q=q, v=vertical, limit=limit)]
    return {"query": q, "count": len(rows), "entities": rows}


def _graph_concepts(params):
    min_count = int(params.get("min_count", 1))
    cypher = (
        "MATCH (c:Concept)<-[:HAS_CONCEPT]-(e) "
        "WITH c, count(e) AS n WHERE n >= $min_count "
        "RETURN c.key AS key, c.name AS name, n ORDER BY n DESC")
    with _driver().session(database=_db()) as s:
        rows = [r.data() for r in s.run(cypher, min_count=min_count)]
    return {"count": len(rows), "concepts": rows}


# ════════════════════════════════ dispatch ════════════════════════════════
_ROUTES = {
    ("POST", "/api/query"): _vec_query,
    ("POST", "/api/retrieve"): _vec_retrieve,
    ("POST", "/api/score_set"): _vec_score_set,
    ("POST", "/api/neighbors"): _vec_neighbors,
    ("POST", "/api/texts"): _vec_texts,
    ("POST", "/graph/structured"): _graph_structured,
    ("POST", "/graph/similar"): _graph_similar,
    ("POST", "/graph/score_within"): _graph_score_within,
    ("GET", "/graph/entity_search"): _graph_entity_search,
    ("GET", "/graph/concepts"): _graph_concepts,
}


_TRANSIENT = ("timeout", "timed out", "429", "rate limit", "ratelimit", "503", "502", "500",
              "service unavailable", "serviceunavailable", "temporarily unavailable",
              "connection reset", "connection refused", "sessionexpired", "session expired",
              "defunct", "unable to retrieve routing", "connection acquisition")


def _is_transient(e):
    s = (type(e).__name__ + " " + str(e)).lower()
    return any(m in s for m in _TRANSIENT)


def _is_neo4j_conn(e):
    s = (type(e).__name__ + " " + str(e)).lower()
    return any(m in s for m in ("sessionexpired", "session expired", "defunct", "serviceunavailable",
                                "service unavailable", "routing", "connection"))


def dispatch(method, url, payload):
    path = urlsplit(url).path
    fn = _ROUTES.get((method.upper(), path))
    if fn is None:
        raise ValueError(f"no in-process engine handler for {method} {path}")
    payload = payload or {}
    last = None
    for attempt in range(3):                         # 1 try + 2 retries (0.15s, 0.30s backoff)
        try:
            return fn(payload)
        except Exception as e:
            last = e
            if not _is_transient(e):
                raise
            if _is_neo4j_conn(e):                     # stale Aura connection → reconnect next attempt
                _reset_driver()
            time.sleep(0.15 * (2 ** attempt))
    raise last
