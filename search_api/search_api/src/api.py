"""Endpoint 4 (Search) HTTP API — FastAPI on :8050.

POST /search → the UC4/UC7 predictions[] envelope. The engine (44k bridge + Postgres precompute + Qwen
parquet + name index) is heavy, so it is built LAZILY on first request (the E3 pattern); /search/health
triggers + reflects that build. Properties only; no moments on this path.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .engine import SearchEngine
from .request import SearchRequest

app = FastAPI(title="Feeds.ai Search (Endpoint 4)", version=config.VERSION)
# CORS for local browser testing (the frontend dev server calls :8050 cross-origin) — mirrors E2's discovery API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_engine: Optional[SearchEngine] = None


def get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


class SearchBody(BaseModel):
    query: str
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    mode: str = "auto"
    limit: int = config.DEFAULT_LIMIT
    verticals: List[str] = []
    exclude_followed: bool = True
    source_context: Optional[str] = None
    disambiguation: bool = False
    debug: bool = False


@app.get("/search/health")
def health() -> dict:
    return get_engine().health()


@app.post("/search")
def search(body: SearchBody) -> dict:
    req = SearchRequest.from_dict(body.model_dump())
    return get_engine().handle(req)
