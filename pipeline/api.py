"""
FastAPI backend for Feeds.ai entertainment discovery pipeline.
"""

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Query as QueryParam
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.config import (
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD,
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


# ── Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/query")
def query_endpoint(req: QueryRequest):
    """Process a natural language query and return recommendations."""
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
    """Return all query history, most recent first."""
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
    """Return full details of a specific query from history."""
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
    """Clear all query history."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM query_history;")
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "cleared"}


@app.get("/api/entities")
def entities_list(
    vertical: str = QueryParam(None, description="Filter by vertical: game, movie, tv"),
    search: str = QueryParam(None, description="Search entity names"),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(50, ge=1, le=200),
):
    """Return paginated entity list from PostgreSQL."""
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

    # Count
    cur.execute(f"SELECT COUNT(*) as total FROM entities {where_sql};", params)
    total_count = cur.fetchone()["total"]

    # Fetch page
    offset = (page - 1) * page_size
    cur.execute(f"""
        SELECT entity_id, name, vertical, description,
               canonical_genres, themes, keywords, franchise,
               developer, publisher, composed_text
        FROM entities
        {where_sql}
        ORDER BY name
        LIMIT %s OFFSET %s;
    """, params + [page_size, offset])
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "entities": rows,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: str):
    """Return full details of a single entity."""
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


@app.get("/api/stats")
def stats():
    """Return dashboard statistics."""
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


# ── Helpers ───────────────────────────────────────────────────────────

def _sanitize(obj):
    """Make result JSON-serializable (strip numpy, etc)."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return obj
