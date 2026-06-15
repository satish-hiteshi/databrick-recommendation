import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from route import route

app = FastAPI(title="Feeds.ai Unified Router", version="2.0 (vector-primary)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


@app.post("/router/search")
def search(req: SearchRequest):
    return route(req.query, top_k=req.top_k)


def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=4).status_code < 500
    except Exception:
        return False


@app.get("/router/health")
def health():
    s = config.summary()
    return {
        "status": "ok",
        "engine": "unified-router",
        "architecture": "vector-primary (v2): vector establishes, graph refines",
        "llm_provider": s["llm_provider"],
        "databricks_token_present": s["databricks_token_present"],
        "graph_up": _up(s["graph_api_url"] + "/graph/health"),
        "vector_up": _up(s["vector_api_url"] + "/api/stats"),
        "port": 8020,
    }


@app.get("/")
def root():
    return {"service": "Feeds.ai Unified Router", "version": "2.0", "port": 8020,
            "endpoints": ["POST /router/search {query, top_k}", "GET /router/health"]}
