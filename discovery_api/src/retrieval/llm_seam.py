"""Discovery v2 — LLM seam for the optional llm_compose (Source 2).

REUSES Endpoint 1's LLM: it targets the SAME Databricks Foundation Model endpoint the router uses
(config.V2_LLM_ENDPOINT defaults to DATABRICKS_LLM_ENDPOINT) and loads the SAME secrets Endpoint 1 loads
(shared/vector/.env + agent_recs/.env). It mirrors agent_recs/src/llm.py:_databricks, but with a SHORT
timeout (config.V2_LLM_TIMEOUT_S) so a slow/cold LLM never stalls retrieval — any failure raises
LLMComposeError and compose_query() falls back to the deterministic composer. Kept as a self-contained
call (not a cross-package import) to control the timeout and avoid sys.path/`import config` collisions.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .. import config

# Load the same secret sources Endpoint 1 uses so DATABRICKS_TOKEN resolves identically (no duplication).
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "shared" / "vector" / ".env")
load_dotenv(_ROOT / "agent_recs" / ".env", override=False)


class LLMComposeError(RuntimeError):
    """Raised when the LLM phrase call fails — the composer falls back to deterministic."""


def llm_complete_short(system: str, user: str) -> str:
    """One short chat completion → assistant text. Short timeout; raises LLMComposeError on any failure."""
    token = os.getenv("DATABRICKS_TOKEN")
    if not token:
        raise LLMComposeError("DATABRICKS_TOKEN not set (LLM composer unavailable) — using deterministic.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0, "max_tokens": config.V2_LLM_MAX_TOKENS,
    }
    try:
        r = httpx.post(config.V2_LLM_ENDPOINT, headers=headers, json=body, timeout=config.V2_LLM_TIMEOUT_S)
        if r.status_code != 200:
            raise LLMComposeError(f"LLM HTTP {r.status_code}: {r.text[:120]}")
        j = r.json()
        return (j.get("choices", [{}])[0].get("message", {}) or {}).get("content") or ""
    except httpx.HTTPError as e:
        raise LLMComposeError(f"{type(e).__name__}: {e}")
