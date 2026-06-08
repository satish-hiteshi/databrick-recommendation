"""Translate between the Parrot / M2M serving contract and the feeds.ai unified router.

The endpoint `parrot-api-hitashi-dev` speaks a FIXED wire contract (machine-to-machine; other agents
call it), confirmed live:

  IN : {"dataframe_records": [{"user_id", "query", "requesting_agent"}]}
  OUT: {"predictions": [{"query", "routed_to", "response": "<JSON string>"}]}
         response = {"routed_to", "entity_type", "results": [{"entity_id", "score", ...}], "count"}

The feeds.ai router (`route()`) speaks a richer NATIVE shape (path_taken, universe_establisher,
results tagged exact|related, intent, timing, …). This module is the ONLY place the two shapes meet —
all contract knowledge lives here so model.py stays a thin wrapper and the router core is untouched.

Mapping decisions (the defaults we agreed on):
  * PRESERVE every key existing M2M callers read (`entity_id`, `score`) and ADD feeds.ai fields
    alongside (`name`, `vertical`, `result_type`, `why`, `source_engine`). Adding keys is
    non-breaking: a caller reading only entity_id/score is unaffected.
  * `routed_to` = "agent-recs" (preserved from the v2 contract); each result carries its entertainment
    `vertical` (game|movie|tv|podcast); top-level `entity_type` = "entertainment".
  * The full router trace (path_taken, establisher, refinements, intent, timing) rides along under a
    `router` key inside `response`, for the UI / debugging. Unknown keys are ignored by M2M callers.

Note: feeds.ai entity_ids are vertical-prefixed STRINGS ("Movie:1000"), not the integers the old
property model returned. They go into `response` as strings; that's fine because `response` is a free
JSON string (no MLflow signature constrains its interior). If a downstream consumer ever needs integer
ids resolvable in a different catalog, add the id-mapping here — it is deliberately the one choke point.
"""

import json
from typing import Any, Dict, List

# Preserved from the existing (v2) contract so M2M callers that key off `routed_to` are unaffected.
# (If routing should vary per request/requesting_agent rather than being constant, make this dynamic.)
ROUTED_TO = "agent-recs"
ENTITY_TYPE = "entertainment"
DEFAULT_TOP_K = 10


# ── IN: parrot request → normalized rows ──────────────────────────────────────────────
def parse_request(model_input) -> List[Dict[str, Any]]:
    """Normalize any MLflow serving input into a list of {user_id, query, requesting_agent, top_k}.

    Serving may hand us a pandas DataFrame (from dataframe_records / dataframe_split), a list of row
    dicts, or a single dict — we accept all three so behavior is identical under `mlflow models serve`,
    the REST endpoint, and local unit tests.
    """
    if hasattr(model_input, "to_dict"):                      # pandas DataFrame
        rows = model_input.to_dict(orient="records")
    elif isinstance(model_input, dict):
        if "dataframe_records" in model_input:
            rows = model_input["dataframe_records"]
        elif "dataframe_split" in model_input:               # {columns, data}
            split = model_input["dataframe_split"]
            cols = split["columns"]
            rows = [dict(zip(cols, r)) for r in split["data"]]
        else:
            rows = [model_input]                             # a single bare row
    elif isinstance(model_input, list):
        rows = model_input
    else:
        raise TypeError(f"Unsupported model_input type: {type(model_input)!r}")

    norm = []
    for r in rows:
        r = dict(r)
        query = (r.get("query") or "").strip()
        top_k = r.get("top_k") or DEFAULT_TOP_K
        try:
            top_k = max(1, int(top_k))
        except (TypeError, ValueError):
            top_k = DEFAULT_TOP_K
        norm.append({
            "user_id": r.get("user_id"),
            "query": query,
            "requesting_agent": r.get("requesting_agent"),
            "top_k": top_k,
        })
    return norm


# ── OUT: router response → parrot response ────────────────────────────────────────────
def _result_items(route_out: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten the router's results into one ordered list, single- or multi-intent alike."""
    if route_out.get("path_taken") == "MULTI_INTENT":
        items = []
        for g in route_out.get("groups", []):
            for it in g.get("results", []):
                it = dict(it)
                it.setdefault("group", g.get("group"))       # keep which intent produced it
                items.append(it)
        return items
    return list(route_out.get("results", []))


def _to_parrot_result(it: Dict[str, Any]) -> Dict[str, Any]:
    """One router result item → parrot result object (contract keys first, feeds.ai fields added)."""
    score = it.get("score")
    out = {
        "entity_id": it.get("entity_id"),
        "score": round(float(score), 6) if isinstance(score, (int, float)) else score,
        # ── additive feeds.ai fields (M2M callers ignore unknown keys) ──
        "name": it.get("name"),
        "vertical": it.get("vertical"),
        "result_type": it.get("result_type", "exact"),
        "why": it.get("why"),
        "source_engine": it.get("source_engine"),
    }
    if it.get("group") is not None:
        out["group"] = it["group"]
    return out


def to_parrot_response(route_out: Dict[str, Any], *, routed_to: str = ROUTED_TO) -> Dict[str, Any]:
    """route() output → one parrot prediction dict: {query, routed_to, response(JSON string)}."""
    results = [_to_parrot_result(it) for it in _result_items(route_out)]
    inner = {
        "routed_to": routed_to,
        "entity_type": ENTITY_TYPE,
        "results": results,
        "count": len(results),
        # ── full router trace for UI / debugging (additive) ──
        "router": {
            "path_taken": route_out.get("path_taken"),
            "universe_establisher": route_out.get("universe_establisher"),
            "refinements_applied": route_out.get("refinements_applied"),
            "exact_vs_related": route_out.get("exact_vs_related"),
            "extraction_ok": route_out.get("extraction_ok"),
            "extraction_error": route_out.get("extraction_error"),
            "timing_ms": route_out.get("timing_ms"),
            "n_intents": route_out.get("n_intents"),
            "intent": route_out.get("intent"),
        },
    }
    return {
        "query": route_out.get("query", ""),
        "routed_to": routed_to,
        "response": inner,
    }


def error_response(message: str, query: str = "") -> Dict[str, Any]:
    """Shape-preserving error payload (so callers always get the same envelope, never a 500 body)."""
    inner = {"routed_to": ROUTED_TO, "entity_type": ENTITY_TYPE,
             "results": [], "count": 0, "error": message}
    return {"query": query, "routed_to": ROUTED_TO, "response": inner}
