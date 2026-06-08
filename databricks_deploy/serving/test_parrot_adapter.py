"""Offline proof of the parrot contract mapping — runs with plain `python`, NO Databricks needed.

Feeds synthetic route() outputs (single-intent, multi-intent, fallback) through the adapter and asserts
the exact parrot envelope: top-level {query, routed_to, response}, and response = a JSON string holding
{routed_to, entity_type, results:[{entity_id, score, ...}], count}. This locks the wire contract before
anything is deployed.

    python databricks_deploy/serving/test_parrot_adapter.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parrot_adapter as PA


def _check_envelope(pred, expected_query):
    assert set(pred) == {"query", "routed_to", "response"}, f"top-level keys: {set(pred)}"
    assert pred["query"] == expected_query
    assert pred["routed_to"] == PA.ROUTED_TO
    resp = pred["response"]                                  # response is a nested JSON object
    inner = json.loads(resp) if isinstance(resp, str) else resp
    assert inner["routed_to"] == PA.ROUTED_TO
    assert inner["entity_type"] == PA.ENTITY_TYPE
    assert inner["count"] == len(inner["results"])
    for r in inner["results"]:
        assert "entity_id" in r and "score" in r, "contract keys entity_id/score required on every result"
    return inner


def test_single_intent():
    route_out = {
        "query": "Final Fantasy games", "extraction_ok": True, "path_taken": "GRAPH_CONSTRAIN",
        "universe_establisher": "graph_constrain", "refinements_applied": ["vector_rerank_within"],
        "exact_vs_related": {"exact": 2, "related": 0, "backfill": False}, "timing_ms": 812,
        "intent": {"verticals": ["game"]},
        "results": [
            {"entity_id": "Game:177", "name": "Final Fantasy XVI", "vertical": "game",
             "score": 0.91, "why": "franchise match", "source_engine": "graph", "result_type": "exact"},
            {"entity_id": "Game:9", "name": "Final Fantasy VII Rebirth", "vertical": "game",
             "score": 0.88, "why": "franchise match", "source_engine": "graph", "result_type": "exact"},
        ],
    }
    pred = PA.to_parrot_response(route_out)
    inner = _check_envelope(pred, "Final Fantasy games")
    assert inner["count"] == 2
    assert inner["results"][0]["entity_id"] == "Game:177"
    assert inner["results"][0]["vertical"] == "game"         # additive feeds.ai field preserved
    assert inner["router"]["path_taken"] == "GRAPH_CONSTRAIN"
    print("ok  single-intent")


def test_multi_intent():
    route_out = {
        "query": "cozy games and feel-good movies", "extraction_ok": True, "path_taken": "MULTI_INTENT",
        "n_intents": 2,
        "groups": [
            {"group": "cozy games", "path_taken": "VECTOR_CONSTRAIN", "universe_establisher": "vector_constrain",
             "exact_vs_related": {"exact": 1, "related": 0},
             "results": [{"entity_id": "Game:42", "name": "Spiritfarer", "vertical": "game",
                          "score": 0.77, "why": "cozy vibe", "source_engine": "vector", "result_type": "exact"}]},
            {"group": "feel-good movies", "path_taken": "VECTOR_CONSTRAIN", "universe_establisher": "vector_constrain",
             "exact_vs_related": {"exact": 1, "related": 0},
             "results": [{"entity_id": "Movie:1000", "name": "Paddington 2", "vertical": "movie",
                          "score": 0.74, "why": "feel-good", "source_engine": "vector", "result_type": "exact"}]},
        ],
    }
    pred = PA.to_parrot_response(route_out)
    inner = _check_envelope(pred, "cozy games and feel-good movies")
    assert inner["count"] == 2, "multi-intent results must be flattened across groups"
    groups = {r["group"] for r in inner["results"]}
    assert groups == {"cozy games", "feel-good movies"}, "each result keeps its originating group"
    print("ok  multi-intent")


def test_fallback_and_request_parsing():
    # graceful-degradation output (LLM down) still maps cleanly
    fb = {"query": "pokemon", "extraction_ok": False, "extraction_error": "Timeout",
          "path_taken": "FALLBACK__VECTOR_CONSTRAIN(raw_query)", "universe_establisher": "vector_constrain",
          "refinements_applied": [], "exact_vs_related": {"exact": 1, "related": 0, "backfill": False},
          "results": [{"entity_id": "Game:1020", "name": "Pokemon Z-A", "vertical": "game", "score": 1.5}]}
    inner = _check_envelope(PA.to_parrot_response(fb), "pokemon")
    assert inner["router"]["extraction_ok"] is False
    assert inner["results"][0]["result_type"] == "exact"     # default applied when missing

    # request parsing accepts the real parrot wire shape + list + single dict
    rows = PA.parse_request({"dataframe_records": [{"user_id": "12345", "query": "pokemon",
                                                    "requesting_agent": "morgan"}]})
    assert rows == [{"user_id": "12345", "query": "pokemon", "requesting_agent": "morgan", "top_k": 10}]
    assert PA.parse_request([{"query": "  spaced  "}])[0]["query"] == "spaced"
    assert PA.parse_request({"query": "x", "top_k": 3})[0]["top_k"] == 3

    # empty query → shape-preserving error envelope (never a 500)
    err = PA.error_response("missing or empty 'query'")
    assert err["response"]["error"] == "missing or empty 'query'"
    print("ok  fallback + request-parsing + error envelope")


if __name__ == "__main__":
    test_single_intent()
    test_multi_intent()
    test_fallback_and_request_parsing()
    print("\nALL PASS — parrot contract mapping verified offline.")
