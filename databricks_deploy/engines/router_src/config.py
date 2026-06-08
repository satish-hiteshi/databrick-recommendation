"""Config for the unified router: the two engine base URLs + the LLM settings.

Reuses the existing Groq key/pattern from the vector pipeline (../vector/.env) so the secret
is not duplicated. A router-local router/.env can override anything (engine URLs, model, key).
All values are read from env with sensible local-dev defaults.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROUTER_DIR = Path(__file__).resolve().parent.parent          # router/
_PROJECT_DIR = _ROUTER_DIR.parent                             # feedsai-graphdb/

# 1) reuse the vector pipeline's .env (Groq key lives here); 2) router-local override wins.
load_dotenv(_PROJECT_DIR / "vector" / ".env")
load_dotenv(_ROUTER_DIR / ".env", override=True)

# ── Engine base URLs ──────────────────────────────────────────────────
GRAPH_API_URL = os.getenv("GRAPH_API_URL", "http://localhost:8010")   # this project's graph engine
VECTOR_API_URL = os.getenv("VECTOR_API_URL", "http://localhost:8000")  # Feedsai-pipeline vector engine

# Endpoints (re-confirmed live in PROGRESS PROMPT 10)
GRAPH_SEARCH_PATH = "/graph/search"      # POST {query, top_k}
GRAPH_HEALTH_PATH = "/graph/health"
VECTOR_QUERY_PATH = "/api/query"         # POST {query}

# ── LLM provider (model-agnostic by design) ───────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "databricks").lower()   # databricks | groq

# Databricks Foundation Model endpoint (production target). Token is a SECRET (router/.env).
DATABRICKS_LLM_ENDPOINT = os.getenv(
    "DATABRICKS_LLM_ENDPOINT",
    "https://dbc-f79d5cae-0d05.cloud.databricks.com/serving-endpoints/"
    "llama_v3_3_70b_instruct_Ishaan/invocations",
)
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

# Groq (fallback provider).
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Shared LLM params
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1100"))
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "120"))   # Databricks endpoints can cold-start slowly

# ── Two-stage retrieval (07e): wide recall (Stage 1) + final-stage reranker (Stage 2). Off by default. ──
RERANK = os.getenv("RERANK", "none").lower()               # none | learned | cross_encoder | auto
RECALL_K = int(os.getenv("RECALL_K", "0"))                 # 0 = current depth; >0 = wide establisher pool

# ── Selective-rerank GATE (07f): when RERANK=auto, decide per query whether the cross-encoder fires. ──
RERANK_GATE_SIGNAL = os.getenv("RERANK_GATE_SIGNAL", "B").upper()   # B = path-based (won 07f); A = score-spread (non-discriminative)
RERANK_GATE_CV = float(os.getenv("RERANK_GATE_CV", "0.55"))         # Signal A: rerank when top-K CV < this (flat → uninformative order)

# ── HTTP ──────────────────────────────────────────────────────────────
HTTP_TIMEOUT_S = float(os.getenv("ROUTER_HTTP_TIMEOUT_S", "30"))


def summary() -> dict:
    """Non-secret config view (key/token PRESENCE only — never the values)."""
    return {
        "graph_api_url": GRAPH_API_URL,
        "vector_api_url": VECTOR_API_URL,
        "llm_provider": LLM_PROVIDER,
        "databricks_endpoint": DATABRICKS_LLM_ENDPOINT,
        "databricks_token_present": bool(DATABRICKS_TOKEN),
        "groq_model": GROQ_MODEL,
        "groq_key_present": bool(GROQ_API_KEY),
        "llm_timeout_s": LLM_TIMEOUT_S,
        "http_timeout_s": HTTP_TIMEOUT_S,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2))
