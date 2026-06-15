import json
from typing import Any, Dict, List

# Preserved from the existing (v2) contract so M2M callers that key off `routed_to` are unaffected.
# (If routing should vary per request/requesting_agent rather than being constant, make this dynamic.)
ROUTED_TO = "agent-recs"
# feeds-api types results by id-prefix (`game:`/`property:` → property) and DROPS non-property on
# hydration. Our `Movie:`/`Tv:`/`Podcast:` prefixes aren't recognized → they'd fall back to this outer
# type. So it MUST be "property" (not "entertainment") or every non-game result is dropped client-side.
ENTITY_TYPE = "property"
DEFAULT_TOP_K = 10


# ── IN: parrot request → normalized rows ──────────────────────────────────────────────
def parse_request(model_input) -> List[Dict[str, Any]]:
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
    score = it.get("score")
    out = {
        "entity_id": it.get("entity_id"),
        "score": round(float(score), 6) if isinstance(score, (int, float)) else score,
        "entity_type": "property",   # feeds-api keeps only `property` candidates on hydration (per-item)
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


def _interleave_by_vertical(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    for r in results:
        v = r.get("vertical")
        if v not in groups:
            groups[v] = []
            order.append(v)
        groups[v].append(r)
    if len(order) <= 1:
        return results
    cols = [groups[v] for v in order]
    out, i = [], 0
    while any(i < len(c) for c in cols):
        for c in cols:
            if i < len(c):
                out.append(c[i])
        i += 1
    return out


def to_parrot_response(route_out: Dict[str, Any], *, routed_to: str = ROUTED_TO) -> Dict[str, Any]:
    results = [_to_parrot_result(it) for it in _result_items(route_out)]
    if str(route_out.get("path_taken", "")).startswith("MULTIVERTICAL"):
        results = _interleave_by_vertical(results)   # mix verticals at the top, not stacked game-first
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
    inner = {"routed_to": ROUTED_TO, "entity_type": ENTITY_TYPE,
             "results": [], "count": 0, "error": message}
    return {"query": query, "routed_to": ROUTED_TO, "response": inner}
