import json
import time
from contextlib import asynccontextmanager
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path

from fastapi import FastAPI, Query as QueryParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.config import (
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD,
    EMBEDDING_DIMENSION,
)
from pipeline.vector_store import setup_qdrant
from pipeline.query_engine import process_query


# ── Database helpers ──────────────────────────────────────────────────

def _connect():
    return psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT, dbname=POSTGRES_DB,
        user=POSTGRES_USER, password=POSTGRES_PASSWORD,
    )


def _create_history_table():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS query_history (
            id SERIAL PRIMARY KEY,
            query_text TEXT NOT NULL,
            parsed_intent JSONB,
            results JSONB,
            latency_ms FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    print("Starting Feeds.ai API server...")

    # Initialize pipeline components
    print("  Loading Qdrant + BM25 index...")
    setup_qdrant()

    # Ensure query_history table exists
    print("  Creating query_history table...")
    _create_history_table()

    elapsed = time.time() - t0
    print(f"  Startup complete in {elapsed:.1f}s")
    print(f"  API ready at http://localhost:8000")
    print(f"  Docs at http://localhost:8000/docs")

    yield  # Server runs

    print("Shutting down Feeds.ai API...")


# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Feeds.ai Entertainment Discovery API",
    description="Hybrid retrieval pipeline for cross-vertical entertainment recommendations",
    version="2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str

class LoginRequest(BaseModel):
    email: str
    password: str

class EmbedRequest(BaseModel):
    entity_ids: list[str] | None = None   # fetch STORED corpus vectors by id (no re-embed)
    text: str | None = None               # embed fresh free text (the semantic phrase)

class ScoreSetRequest(BaseModel):
    phrase: str                           # the soft semantic text
    entity_ids: list[str]                 # the FIXED set to score (no retrieval, no expansion)


# ── Router-support hooks (PROMPT: vector scoring/embedding, NO retrieval) ──────
# These exist so the router's refiner blocks (vector_rerank_within, backfill) can score a
# PASSED-IN set without re-retrieving. They reuse the SAME model the corpus was built with
# (qwen3-embedding-0-6b): stored entity vectors are FETCHED by id from the cache; only free text is
# embedded fresh (as a query). No NLU, no /api/query, no set expansion.

import numpy as _np
from pipeline.embedding_generator import load_embeddings as _load_embeddings, embed_query_text as _embed_text

_ENTITY_EMB = None

def _entity_emb():
    global _ENTITY_EMB
    if _ENTITY_EMB is None:
        _ENTITY_EMB = _load_embeddings() or {}
    return _ENTITY_EMB

def _cosine(a, b):
    a = _np.asarray(a, dtype=_np.float64); b = _np.asarray(b, dtype=_np.float64)
    na, nb = _np.linalg.norm(a), _np.linalg.norm(b)
    return float(_np.dot(a, b) / (na * nb)) if na and nb else 0.0


# ── Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/login")
def login(req: LoginRequest):
    import hashlib, time
    time.sleep(0.2)  # consistent timing

    salt = "feedsai_poc_salt_2026"
    pw_hash = hashlib.sha256((salt + req.password).encode()).hexdigest()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT email FROM app_users WHERE email = %s AND password_hash = %s;", (req.email, pw_hash))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        return {"success": True, "email": row[0]}

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=401, content={"success": False, "message": "Invalid email or password"})

@app.post("/api/query")
def query_endpoint(req: QueryRequest):
    result = process_query(req.query)

    # Count results
    result_count = len(result.get("results", []))
    for vres in result.get("results_by_vertical", {}).values():
        result_count += len(vres)

    # Save to history
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO query_history (query_text, parsed_intent, results, latency_ms)
               VALUES (%s, %s, %s, %s) RETURNING id;""",
            (
                req.query,
                json.dumps(result.get("parsed_intent", {})),
                json.dumps(_sanitize(result)),
                result.get("timings", {}).get("total_ms", 0),
            ),
        )
        history_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        result["history_id"] = history_id
    except Exception as e:
        print(f"Warning: failed to save to history: {e}")

    return result


@app.get("/api/history")
def history_list():
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, query_text, parsed_intent, latency_ms, created_at,
               jsonb_array_length(COALESCE(results->'results', '[]'::jsonb)) as result_count
        FROM query_history
        ORDER BY created_at DESC
        LIMIT 100;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    for row in rows:
        if row["created_at"]:
            row["created_at"] = row["created_at"].isoformat()

    return {"history": rows, "count": len(rows)}


@app.get("/api/history/{history_id}")
def history_detail(history_id: int):
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM query_history WHERE id = %s;", (history_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return {"error": "Not found"}, 404

    if row["created_at"]:
        row["created_at"] = row["created_at"].isoformat()
    return row


@app.delete("/api/history")
def history_clear():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM query_history;")
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "cleared"}


@app.get("/api/entities")
def entities_list(
    vertical: str = QueryParam(None, description="Filter by vertical: game, movie, tv, podcast"),
    search: str = QueryParam(None, description="Search entity names"),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(50, ge=1, le=200),
    sort_by: str = QueryParam("name", description="Sort field: name or release_date"),
    sort_dir: str = QueryParam("asc", description="Sort direction: asc or desc"),
):
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    where_clauses = []
    params = []

    if vertical:
        where_clauses.append("vertical = %s")
        params.append(vertical)
    if search:
        where_clauses.append("LOWER(name) LIKE %s")
        params.append(f"%{search.lower()}%")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Validate sort
    allowed_sort = {"name": "name", "release_date": "release_date"}
    sort_col = allowed_sort.get(sort_by, "name")
    direction = "DESC" if sort_dir == "desc" else "ASC"
    nulls = "NULLS LAST" if direction == "ASC" else "NULLS LAST"

    # Count
    cur.execute(f"SELECT COUNT(*) as total FROM entities {where_sql};", params)
    total_count = cur.fetchone()["total"]

    # Fetch page
    offset = (page - 1) * page_size
    cur.execute(f"""
        SELECT entity_id, name, vertical, description,
               canonical_genres, themes, keywords, franchise,
               developer, publisher, composed_text, release_date
        FROM entities
        {where_sql}
        ORDER BY {sort_col} {direction} {nulls}
        LIMIT %s OFFSET %s;
    """, params + [page_size, offset])
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Convert date to string
    for row in rows:
        if row.get("release_date"):
            row["release_date"] = row["release_date"].isoformat()

    return {
        "entities": rows,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: str):
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT entity_id, name, vertical, description, composed_text,
               bm25_keywords, franchise, developer, publisher,
               canonical_genres, themes, keywords
        FROM entities WHERE entity_id = %s;
    """, (entity_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return {"error": "Entity not found"}
    return row


class TextsRequest(BaseModel):
    entity_ids: list[str]
    max_chars: int = 600


@app.post("/api/texts")
def texts(req: TextsRequest):
    ids = list(req.entity_ids or [])
    if not ids:
        return {"texts": {}}
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT entity_id, name, vertical, composed_text FROM entities WHERE entity_id = ANY(%s);", (ids,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = {}
    for r in rows:
        txt = (r.get("composed_text") or "").strip().replace("\n", " ")
        out[r["entity_id"]] = {"name": r["name"], "vertical": r["vertical"],
                               "text": txt[: req.max_chars]}
    return {"texts": out, "n": len(out)}


@app.get("/api/stats")
def stats():
    conn = _connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Entity stats
    cur.execute("SELECT COUNT(*) as total FROM entities;")
    total_entities = cur.fetchone()["total"]

    cur.execute("SELECT vertical, COUNT(*) as count FROM entities GROUP BY vertical ORDER BY vertical;")
    by_vertical = {row["vertical"]: row["count"] for row in cur.fetchall()}

    # Query history stats
    cur.execute("SELECT COUNT(*) as total FROM query_history;")
    total_queries = cur.fetchone()["total"]

    cur.execute("SELECT AVG(latency_ms) as avg_latency FROM query_history;")
    avg_row = cur.fetchone()
    avg_latency = round(avg_row["avg_latency"], 1) if avg_row["avg_latency"] else 0

    cur.close()
    conn.close()

    return {
        "total_entities": total_entities,
        "entities_by_vertical": by_vertical,
        "total_queries": total_queries,
        "avg_latency_ms": avg_latency,
    }


@app.post("/api/embed")
def embed(req: EmbedRequest):
    out = {"model": "qwen3-embedding-0-6b", "dim": EMBEDDING_DIMENSION}
    if req.entity_ids:
        emb = _entity_emb()
        vecs, missing = {}, []
        for eid in req.entity_ids:
            v = emb.get(eid)
            if v is None:
                missing.append(eid)
            else:
                vecs[eid] = (v.tolist() if hasattr(v, "tolist") else list(v))
        out["entity_vectors"] = vecs
        out["missing"] = missing
    if req.text:
        out["text_vector"] = list(_embed_text(req.text))
    return out


@app.post("/api/score_set")
def score_set(req: ScoreSetRequest):
    phrase_vec = _embed_text(req.phrase)
    emb = _entity_emb()
    scored, missing = [], []
    for eid in req.entity_ids:
        v = emb.get(eid)
        if v is None:
            missing.append(eid)
            continue
        scored.append({"entity_id": eid, "score": round(_cosine(phrase_vec, v), 6)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"phrase": req.phrase, "model": "qwen3-embedding-0-6b",
            "scored": scored, "missing": missing,
            "n_in": len(req.entity_ids), "n_scored": len(scored)}


class NeighborsRequest(BaseModel):
    anchor_ids: list[str]                  # the EXACT-match entities to anchor on
    exclude_ids: list[str] | None = None   # ids to drop from neighbors (usually the exact set)
    vertical: str | None = None            # keep neighbors in the same vertical (relax structure, not vertical)
    top_k: int = 20
    per_anchor: int = 25                   # Qdrant neighbors to pull per anchor before merging


@app.post("/api/neighbors")
def neighbors(req: NeighborsRequest):
    from pipeline.vector_store import vector_search
    emb = _entity_emb()
    exclude = set(req.exclude_ids or []) | set(req.anchor_ids)
    verts = {req.vertical} if (req.vertical and req.vertical != "any") else None
    best = {}
    for aid in req.anchor_ids:
        v = emb.get(aid)
        if v is None:
            continue
        for (eid, name, vert, score) in vector_search(_np.asarray(v, dtype=_np.float32), verts, req.per_anchor):
            if eid in exclude:
                continue
            sc = float(score)
            if eid not in best or sc > best[eid][0]:
                best[eid] = (sc, name, vert)
    out = [{"entity_id": eid, "name": nv[1], "vertical": nv[2], "score": round(nv[0], 6)}
           for eid, nv in best.items()]
    out.sort(key=lambda x: x["score"], reverse=True)
    return {"neighbors": out[:req.top_k], "n_anchors": len(req.anchor_ids), "n_found": len(out)}


class RetrieveRequest(BaseModel):
    phrase: str                            # the semantic universe-definer (already understood by the router)
    vertical: str | None = None            # restrict to one vertical (None/any = all)
    top_k: int = 50


@app.post("/api/retrieve")
def retrieve_endpoint(req: RetrieveRequest):
    from pipeline.vector_store import vector_search
    verts = {req.vertical} if (req.vertical and req.vertical != "any") else None
    vec = _np.asarray(_embed_text(req.phrase), dtype=_np.float32)
    out = [{"entity_id": eid, "name": name, "vertical": vert, "score": round(float(score), 6)}
           for (eid, name, vert, score) in vector_search(vec, verts, req.top_k)]
    return {"phrase": req.phrase, "model": "qwen3-embedding-0-6b", "vertical": req.vertical,
            "results": out, "count": len(out)}


# ── Helpers ───────────────────────────────────────────────────────────

def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return obj


# ── Static frontend serving ──────────────────────────────────────────
# Serves the Vite production build from frontend/dist/ on all non-API routes.
# This lets us run API + frontend from a single port (8000).

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    # Serve static assets (JS, CSS, fonts, images, video)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static-assets")

    # Serve files from public/ that Vite copies to dist/ root (hero.mp4, favicon, etc.)
    @app.get("/hero.mp4")
    def serve_video():
        return FileResponse(FRONTEND_DIST / "hero.mp4", media_type="video/mp4")

    @app.get("/favicon.svg")
    def serve_favicon():
        return FileResponse(FRONTEND_DIST / "favicon.svg", media_type="image/svg+xml")

    # SPA catch-all: return index.html for any non-API, non-asset route
    @app.get("/{path:path}")
    def spa_catch_all(path: str):
        # Don't intercept API or asset routes
        if path.startswith("api/") or path.startswith("assets/"):
            return {"error": "not found"}
        file_path = FRONTEND_DIST / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
