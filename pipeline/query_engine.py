"""
Query engine v2 for Feeds.ai pipeline.
Orchestrates: NLU → Retrieval → Negative Filter → Reranker.
"""

import json
import time

from pipeline.nlu import parse_query
from pipeline.retrieval import retrieve
from pipeline.negative_filter import apply_negative_filter
from pipeline.reranker import rerank


def _format_result(rank, c):
    return {
        "rank": rank,
        "name": c["name"],
        "vertical": c["vertical"],
        "final_score": round(c.get("final_score", c.get("combined_score", c.get("rrf_score", 0))), 4),
        "rrf_score": round(c.get("rrf_score", c.get("combined_score", 0)), 4),
        "vector_rank": c.get("best_vector_rank"),
        "bm25_rank": c.get("best_bm25_rank"),
        "appeared_in_vector": c.get("in_vector", False),
        "appeared_in_bm25": c.get("in_bm25", False),
        "in_both_sets": c.get("in_vector", False) and c.get("in_bm25", False),
        "shared_keywords": c.get("shared_keywords", []),
        "appeared_in_searches": c.get("appeared_in_searches", 1),
        "negative_penalty": c.get("negative_penalty", 0),
    }


def _add_similarity_pct(results):
    """Add similarity_percentage: top result = 100%, others scaled proportionally."""
    if not results:
        return
    max_rrf = max(r["rrf_score"] for r in results) if results else 1
    for r in results:
        r["similarity_percentage"] = round((r["rrf_score"] / max_rrf) * 100) if max_rrf > 0 else 0


def process_query(user_query: str) -> dict:
    """
    End-to-end Phase 2 query processing.
    Returns structured result dict with per-stage timings.
    """
    timings = {}

    # 1. NLU
    t0 = time.time()
    nlu = parse_query(user_query)
    timings["nlu_ms"] = (time.time() - t0) * 1000

    # 2. Retrieval
    t0 = time.time()
    ret = retrieve(nlu)
    timings["retrieval_ms"] = (time.time() - t0) * 1000

    candidates = ret["candidates"]
    resolved_pos = ret["resolved_positive"]
    resolved_neg = ret["resolved_negative"]
    unresolved_neg_kw = ret.get("unresolved_neg_keywords", [])

    if not candidates:
        timings["total_ms"] = timings["nlu_ms"] + timings["retrieval_ms"]
        error_msgs = [d.get("error", "") for d in ret.get("debug", []) if d.get("error")]
        return {
            "query": user_query,
            "parsed_intent": nlu,
            "query_mode": nlu["query_mode"],
            "anchor_entities_resolved": [],
            "negative_entities_resolved": [],
            "error": "; ".join(error_msgs) or "No candidates found",
            "results": [],
            "timings": timings,
            "status": "no_results",
        }

    # 3. Negative filter
    t0 = time.time()
    neg_log = []
    if resolved_neg or unresolved_neg_kw:
        candidates, neg_log = apply_negative_filter(candidates, resolved_neg, unresolved_neg_kw)
    timings["filter_ms"] = (time.time() - t0) * 1000

    # 4. Rerank
    t0 = time.time()
    reranked = rerank(candidates, resolved_pos, nlu, nlu["query_mode"])
    timings["rerank_ms"] = (time.time() - t0) * 1000

    timings["total_ms"] = (timings["nlu_ms"] + timings["retrieval_ms"]
                           + timings["filter_ms"] + timings["rerank_ms"])

    # 5. Format response
    anchor_strs = [f"{e['name']} ({e['vertical']}) [{e['match_type']}]" for e in resolved_pos]
    neg_strs = [f"{e['name']} ({e['vertical']})" for e in resolved_neg]
    if unresolved_neg_kw:
        neg_strs += [f"[keyword: {kw}]" for kw in unresolved_neg_kw]

    base = {
        "query": user_query,
        "parsed_intent": nlu,
        "query_mode": nlu["query_mode"],
        "anchor_entities_resolved": anchor_strs,
        "negative_entities_resolved": neg_strs,
        "neg_filter_log": neg_log,
        "reranker_debug": reranked.get("debug", {}),
        "timings": timings,
        "status": "success",
        "retrieval_candidate_count": len(ret["candidates"]),
        "post_filter_count": len(candidates),
    }

    if reranked.get("split_by_vertical"):
        results_by_vert = {}
        for vert, vresults in reranked["results"].items():
            formatted = [_format_result(i, c) for i, c in enumerate(vresults, 1)]
            _add_similarity_pct(formatted)
            results_by_vert[vert] = formatted
        base["results_by_vertical"] = results_by_vert
        base["results"] = []
    else:
        final = reranked["results"]
        formatted = [_format_result(i, c) for i, c in enumerate(final, 1)]
        _add_similarity_pct(formatted)
        base["results"] = formatted
        base["results_by_vertical"] = {}

    return base


def print_results(output: dict):
    """Pretty-print query results."""
    print(f"\n{'='*70}")
    print(f"Query: {output['query']}")
    print(f"{'='*70}")

    nlu = output["parsed_intent"]
    print(f"\nNLU: mode={nlu['query_mode']}, pos={nlu['positive_entities']}, "
          f"neg={nlu['negative_entities']}")
    print(f"  kw={nlu['additional_keywords']}, derived={nlu['description_derived_keywords']}")
    print(f"  verticals={nlu['target_verticals']}, type={nlu['query_type']}")

    if output.get("anchor_entities_resolved"):
        print(f"\nResolved: {output['anchor_entities_resolved']}")
    if output.get("negative_entities_resolved"):
        print(f"Negatives: {output['negative_entities_resolved']}")

    if output["status"] != "success":
        print(f"\n  ERROR: {output.get('error', 'unknown')}")
        _print_timings(output["timings"])
        return

    # Neg filter summary
    neg_log = output.get("neg_filter_log", [])
    if neg_log:
        penalized = sum(1 for e in neg_log if e["action"] == "PENALIZED")
        removed = sum(1 for e in neg_log if e["action"] == "REMOVED")
        print(f"\nNeg filter: {penalized} penalized, {removed} removed "
              f"({output['retrieval_candidate_count']} → {output['post_filter_count']})")

    # Results
    if output.get("results_by_vertical"):
        for vert, results in output["results_by_vertical"].items():
            print(f"\n  [{vert.upper()}] ({len(results)} results):")
            _print_table(results)
    elif output.get("results"):
        print(f"\n  Results ({len(output['results'])}):")
        _print_table(output["results"])
    else:
        print("\n  No results.")

    _print_timings(output["timings"])


def _print_table(results):
    for r in results:
        both = "*" if r.get("in_both_sets") else " "
        pen = f" pen={r['negative_penalty']:.2f}" if r.get("negative_penalty") else ""
        print(f"    {r['rank']:>2}. {r['name']:<40} {r['vertical']:<6} "
              f"final={r['final_score']:.4f} vec={r['vector_score']:.4f} "
              f"bm25={r['bm25_score']:.4f} {both}{pen}")
        if r.get("shared_keywords"):
            print(f"        kw: {', '.join(r['shared_keywords'][:5])}")


def _print_timings(t):
    parts = []
    for key in ["nlu_ms", "retrieval_ms", "filter_ms", "rerank_ms"]:
        if key in t:
            label = key.replace("_ms", "")
            parts.append(f"{label}={t[key]:.0f}ms")
    total = t.get("total_ms", 0)
    print(f"\nTiming: {', '.join(parts)} → total={total:.0f}ms")


if __name__ == "__main__":
    from pipeline.vector_store import setup_qdrant
    print("Initializing Qdrant + BM25 index...")
    setup_qdrant()

    print("\n" + "=" * 70)
    print("Feeds.ai Query Engine v2 — Interactive Mode")
    print("Type a query or 'quit' to exit.")
    print("=" * 70)

    while True:
        try:
            query = input("\n> ").strip()
            if not query or query.lower() in ("quit", "exit", "q"):
                break
            output = process_query(query)
            print_results(output)
        except (KeyboardInterrupt, EOFError):
            break

    print("\nGoodbye!")
