import time

from fastapi import FastAPI, Query as QueryParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Union

from connection import get_driver, NEO4J_DATABASE, NEO4J_URI
import query as Q
import router as RT

GRAPH_PORT = 8010   # vector pipeline API = 8000; graph API = 8010 (no collision)

app = FastAPI(
    title="Feeds.ai Graph Engine API",
    description="Embedding-free Neo4j graph retrieval (router + archetypes + reranker), "
                "parallel/complementary to the Qdrant vector API.",
    version="1.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

_DRIVER = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = get_driver()
    return _DRIVER


# ── result-item formatting (vector-shape + graph extras) ──────────────────────

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
            # vector-API-shaped fields (frontend can share rendering)
            "rank": i,
            "name": r.get("name"),
            "vertical": r.get("vertical"),
            "final_score": round(sc, 4),
            "similarity_percentage": round((sc / mx) * 100) if mx > 0 else 0,
            "reasoning_short": why,
            "reasoning_long": why,
            # graph-only extras
            "entity_id": r.get("entity_id"),
            "score": round(sc, 4),
            "why": why,
        })
    return out


# ── request models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


class SimilarRequest(BaseModel):
    entity_id: str
    top_k: int = 10
    vertical: Optional[str] = None


class CrossVerticalRequest(BaseModel):
    entity_id: str
    target_vertical: str
    top_k: int = 10


class StructuredRequest(BaseModel):
    vertical: Optional[str] = None
    concept: Optional[Union[str, List[str]]] = None
    genre: Optional[Union[str, List[str]]] = None
    theme: Optional[Union[str, List[str]]] = None
    keyword: Optional[Union[str, List[str]]] = None
    franchise: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    developer_also_made: Optional[str] = None
    top_k: int = 10


class CommunityRequest(BaseModel):
    entity_id: Optional[str] = None
    community_id: Optional[int] = None
    top_k: int = 10


class ScoreWithinRequest(BaseModel):
    entity_ids: List[str]                       # the FIXED set (no retrieval / no expansion)
    structural_prefs: Optional[dict] = None     # e.g. {"mode": "co-op"} -> boost
    seed_entity: Optional[str] = None           # optional: boost shared-concept overlap w/ a seed


# ── endpoints ──────────────────────────────────────────────────────────────────

@app.post("/graph/search")
def graph_search(req: SearchRequest):
    t0 = time.time()
    try:
        d = RT.route(req.query, k=req.top_k)
    except Exception as e:  # noqa
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})

    base = {
        "query": req.query, "engine": "graph", "route": d["route"],
        "archetype": d["archetype"], "method": d.get("method"),
        "reason": d.get("rationale"), "principle": d.get("principle"),
        "vector_also": d.get("vector_also", False),
        "timings": {"total_ms": round((time.time() - t0) * 1000, 1)},
    }
    if d["route"] == "vector":
        # IMPLICIT query — honestly hand off to the vector engine, no forced graph answer.
        base.update({"status": "route_to_vector", "result_count": 0, "results": [],
                     "reason": d.get("rationale")})
        return base
    results = _fmt(d.get("results", []), req.top_k)
    base.update({"status": "success" if results else "no_results",
                 "result_count": len(results), "results": results})
    return base


@app.post("/graph/similar")
def graph_similar(req: SimilarRequest):
    r = Q.similar_by_attributes(req.entity_id, vertical=req.vertical, limit=req.top_k)
    if isinstance(r, dict):  # no_graph_signal / not_found
        return {"engine": "graph", "endpoint": "similar", "entity_id": req.entity_id,
                "route": "vector" if r.get("status") == "no_graph_signal" else "none",
                "status": r.get("status"), "reason": r.get("reason"), "result_count": 0, "results": []}
    return {"engine": "graph", "endpoint": "similar", "entity_id": req.entity_id,
            "status": "success", "result_count": len(r), "results": _fmt(r, req.top_k)}


@app.post("/graph/cross_vertical")
def graph_cross_vertical(req: CrossVerticalRequest):
    r = Q.cross_vertical(req.entity_id, req.target_vertical, limit=req.top_k)
    if isinstance(r, dict):
        return {"engine": "graph", "endpoint": "cross_vertical", "entity_id": req.entity_id,
                "target_vertical": req.target_vertical,
                "route": "vector" if r.get("status") == "no_graph_signal" else "none",
                "status": r.get("status"), "reason": r.get("reason"), "result_count": 0, "results": []}
    return {"engine": "graph", "endpoint": "cross_vertical", "entity_id": req.entity_id,
            "target_vertical": req.target_vertical, "status": "success",
            "result_count": len(r), "results": _fmt(r, req.top_k)}


@app.post("/graph/structured")
def graph_structured(req: StructuredRequest):
    filters = {k: v for k, v in req.dict().items()
               if k != "top_k" and v is not None}
    r = Q.cypher_structured(filters, limit=req.top_k)
    return {"engine": "graph", "endpoint": "structured", "filters": filters,
            "status": "success" if r else "no_results",
            "result_count": len(r), "results": _fmt(r, req.top_k)}


@app.post("/graph/community")
def graph_community(req: CommunityRequest):
    r = Q.community_browse(entity_id=req.entity_id, community_id=req.community_id, limit=req.top_k)
    if isinstance(r, dict):
        return {"engine": "graph", "endpoint": "community", "status": r.get("status"),
                "reason": r.get("reason"), "result_count": 0, "results": []}
    return {"engine": "graph", "endpoint": "community", "status": "success",
            "result_count": len(r), "results": _fmt(r, req.top_k)}


_SCORE_WITHIN_CYPHER = """
MATCH (e:Entity) WHERE e.entity_id IN $ids
RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical,
       COALESCE(e.influence, e.pagerank, 0.0) AS influence, e.community AS community,
       [(e)-[:HAS_CONCEPT]->(c)  | c.key]          AS concepts,
       [(e)-[:HAS_KEYWORD]->(k)  | toLower(k.name)] AS keywords,
       [(e)-[:HAS_GENRE]->(g)    | toLower(g.name)] AS genres,
       [(e)-[:HAS_THEME]->(t)    | toLower(t.name)] AS themes,
       [(e)-[:IN_FRANCHISE]->(f) | f.name][0]      AS franchise,
       [(e)-[:DEVELOPED_BY]->(d) | d.name][0]      AS developer,
       [(e)-[:PUBLISHED_BY]->(p) | p.name][0]      AS publisher
"""


@app.post("/graph/score_within")
def score_within(req: ScoreWithinRequest):
    pref_vals = [str(v).lower() for v in (req.structural_prefs or {}).values()]
    with _driver().session(database=NEO4J_DATABASE) as s:
        rows = [r.data() for r in s.run(_SCORE_WITHIN_CYPHER, ids=req.entity_ids)]
        seed_concepts = set()
        if req.seed_entity:
            rec = s.run("MATCH (e:Entity {entity_id:$id})-[:HAS_CONCEPT]->(c) "
                        "RETURN collect(c.key) AS cs", id=req.seed_entity).single()
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
    return {"results": out, "n_in": len(req.entity_ids), "n_scored": len(out),
            "missing": [i for i in req.entity_ids if i not in found]}


@app.get("/graph/entity_search")
def entity_search(q: str = QueryParam(..., min_length=1),
                  limit: int = QueryParam(10, ge=1, le=50),
                  vertical: Optional[str] = QueryParam(None)):
    cypher = (
        "MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($q) "
        "AND ($v IS NULL OR e.vertical = $v) "
        "RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical, "
        "round(COALESCE(e.influence, e.pagerank, 0.0),4) AS influence, "
        "size([(e)-[:HAS_CONCEPT]->()|1]) AS concept_count "
        "ORDER BY (toLower(e.name) = toLower($q)) DESC, COALESCE(e.influence, e.pagerank, 0.0) DESC LIMIT $limit")
    with _driver().session(database=NEO4J_DATABASE) as s:
        rows = [r.data() for r in s.run(cypher, q=q, v=vertical, limit=limit)]
    return {"query": q, "count": len(rows), "entities": rows}


@app.get("/graph/concepts")
def concepts(min_count: int = QueryParam(1, ge=1)):
    cypher = (
        "MATCH (c:Concept)<-[:HAS_CONCEPT]-(e) "
        "WITH c, count(e) AS n WHERE n >= $min_count "
        "RETURN c.key AS key, c.name AS name, n ORDER BY n DESC")
    with _driver().session(database=NEO4J_DATABASE) as s:
        rows = [r.data() for r in s.run(cypher, min_count=min_count)]
    return {"count": len(rows), "concepts": rows}


@app.get("/graph/health")
def health():
    try:
        with _driver().session(database=NEO4J_DATABASE) as s:
            comp = s.run("CALL dbms.components() YIELD versions, edition "
                         "RETURN versions[0] AS v, edition").single()
            gds = s.run("RETURN gds.version() AS v").single()["v"]
            counts = s.run(
                "RETURN { entities: count{(e:Entity)}, concepts: count{(:Concept)}, "
                "similar_to: count{()-[:SIMILAR_TO]->()}, "
                "knn_similar: count{()-[:KNN_SIMILAR]->()} } AS c").single()["c"]
            verts = {r["v"]: r["n"] for r in s.run(
                "MATCH (e:Entity) RETURN e.vertical AS v, count(*) AS n ORDER BY n DESC")}
        return {"status": "ok", "engine": "graph", "neo4j_uri": NEO4J_URI,
                "neo4j_version": comp["v"], "edition": comp["edition"], "gds_version": gds,
                "counts": counts, "entities_by_vertical": verts, "port": GRAPH_PORT}
    except Exception as e:  # noqa
        return JSONResponse(status_code=503, content={"status": "down", "error": str(e)})


@app.get("/")
def root():
    return {"service": "Feeds.ai Graph Engine API", "version": "1.0", "port": GRAPH_PORT,
            "vector_api_port": 8000,
            "endpoints": ["POST /graph/search", "POST /graph/similar",
                          "POST /graph/cross_vertical", "POST /graph/structured",
                          "POST /graph/community", "GET /graph/entity_search?q=",
                          "GET /graph/health"]}
