"""B4 — no-signal RESPONSE (the recent-mixed fallback).

This is ONLY the fallback response builder. The decision of WHEN to use it lives in the pipeline:
the single trigger is the LLM's `is_gibberish` flag (route.route). When the LLM flags an input as
genuinely unintelligible, we serve a RECENT-MIXED fallback — the most recent releases across a mix of
all four verticals, future-dated rows excluded, clearly tagged low-confidence — instead of empty or a
hallucinated-vertical junk set.
"""
import os

from neo4j import GraphDatabase


# Recent-mixed: top `per` most-recent by release_date per vertical, EXCLUDING future-dated rows
# (date() = server current date), then interleaved round-robin into one mixed list.
_RECENT_CYPHER = """
UNWIND $verts AS v
CALL (v) {
  MATCH (e:Entity {vertical: v})
  WHERE e.release_date IS NOT NULL AND e.release_date <= date()
  RETURN e ORDER BY e.release_date DESC LIMIT $per
}
RETURN e.vertical AS vertical, e.entity_id AS entity_id, e.name AS name,
       toString(e.release_date) AS release_date
"""


_DRIVER = None


def _graph_driver():
    # Client Neo4j spec: singleton (do NOT recreate per call) + liveness_check discards a dropped
    # connection before a query uses it; execute_read (below) retries transient failures.
    global _DRIVER
    if _DRIVER is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
        user = os.getenv("NEO4J_USER", "neo4j")
        pw = os.getenv("NEO4J_PASSWORD", "feedsai44kGraph2026")
        _DRIVER = GraphDatabase.driver(uri, auth=(user, pw),
                                       max_connection_lifetime=300, liveness_check_timeout=30,
                                       connection_acquisition_timeout=30, keep_alive=True)
    return _DRIVER


def recent_mixed(top_k: int = 12, per: int = 3,
                 verticals=("game", "movie", "tv", "podcast")) -> list:
    """Pull recent-by-release_date entities across all verticals from the 44k graph and interleave."""
    by_vert = {v: [] for v in verticals}
    try:
        with _graph_driver().session() as s:
            rows = s.execute_read(lambda tx: tx.run(_RECENT_CYPHER, verts=list(verticals), per=per).data())
        for r in rows:
            by_vert.setdefault(r["vertical"], []).append(r)
    except Exception as e:                       # graph unreachable → empty (caller still flags no_signal)
        return []
    # round-robin interleave so the mix isn't front-loaded by one vertical
    out, i = [], 0
    while len(out) < top_k and any(i < len(by_vert[v]) for v in verticals):
        for v in verticals:
            if i < len(by_vert[v]) and len(out) < top_k:
                r = by_vert[v][i]
                out.append({
                    "entity_id": r["entity_id"], "name": r["name"], "vertical": r["vertical"],
                    "score": None, "release_date": r["release_date"],
                    "why": "recent release (no strong match for your query)",
                    "source_engine": "no_signal_fallback",
                    "result_type": "no_signal_fallback", "confidence": "low",
                })
        i += 1
    return out


def build_response(intent, top_k: int, reason: str) -> dict:
    """A full router-shaped response for the no-signal path — tagged low-confidence so QA/downstream
    can tell this is NOT a real semantic match. The trigger consults NO embedding score, so there is
    no score field here."""
    results = recent_mixed(top_k=top_k)
    return {
        "path_taken": "NO_SIGNAL_FALLBACK",
        "universe_establisher": "no_signal_fallback",
        "confidence": "low",
        "no_signal": True,
        "refinements_applied": [reason],
        "results": results,
        "exact_vs_related": {"exact": 0, "related": len(results), "backfill": False},
        "intent": intent.model_dump() if intent is not None else None,
    }
