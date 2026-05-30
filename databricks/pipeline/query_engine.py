import time

from pipeline.nlu import parse_query
from pipeline.retrieval import retrieve
from pipeline.negative_filter import apply_negative_filter
from pipeline.reranker import rerank
from pipeline import entity_store

_release_dates = None


def _get_release_date(entity_id):
    global _release_dates
    if _release_dates is None:
        _release_dates = {e["entity_id"]: e.get("release_date") for e in entity_store.get_all()}
    return _release_dates.get(entity_id)


def _format_result(rank, c):
    return {
        "rank":               rank,
        "name":               c["name"],
        "vertical":           c["vertical"],
        "final_score":        round(c.get("final_score", c.get("combined_score", c.get("rrf_score", 0))), 4),
        "rrf_score":          round(c.get("rrf_score", c.get("combined_score", 0)), 4),
        "vector_rank":        c.get("best_vector_rank"),
        "bm25_rank":          c.get("best_bm25_rank"),
        "appeared_in_vector": c.get("in_vector", False),
        "appeared_in_bm25":   c.get("in_bm25", False),
        "in_both_sets":       c.get("in_vector", False) and c.get("in_bm25", False),
        "shared_keywords":    c.get("shared_keywords", []),
        "appeared_in_searches": c.get("appeared_in_searches", 1),
        "negative_penalty":   c.get("negative_penalty", 0),
        "reasoning_short":    c.get("reasoning_short", ""),
        "reasoning_long":     c.get("reasoning_long", ""),
        "release_date":       _get_release_date(c.get("entity_id")) or c.get("release_date"),
    }


def _add_similarity_pct(results):
    if not results:
        return
    max_rrf = max(r["rrf_score"] for r in results) if results else 1
    for r in results:
        r["similarity_percentage"] = round((r["rrf_score"] / max_rrf) * 100) if max_rrf > 0 else 0


def process_query(user_query: str) -> dict:
    timings = {}

    t0 = time.time()
    nlu = parse_query(user_query)
    timings["nlu_ms"] = (time.time() - t0) * 1000

    t0 = time.time()
    ret = retrieve(nlu)
    timings["retrieval_ms"] = (time.time() - t0) * 1000

    candidates    = ret["candidates"]
    resolved_pos  = ret["resolved_positive"]
    resolved_neg  = ret["resolved_negative"]
    unresolved_neg_kw = ret.get("unresolved_neg_keywords", [])

    ds = nlu.get("date_filter_start")
    de = nlu.get("date_filter_end")

    if not candidates:
        timings["total_ms"] = timings["nlu_ms"] + timings["retrieval_ms"]
        error_msgs = [d.get("error", "") for d in ret.get("debug", []) if d.get("error")]
        return {
            "query":                      user_query,
            "parsed_intent":              nlu,
            "query_mode":                 nlu["query_mode"],
            "anchor_entities_resolved":   [],
            "negative_entities_resolved": [],
            "error":   "; ".join(error_msgs) or "No candidates found",
            "results": [],
            "timings": timings,
            "status":  "no_results",
            "date_filter_applied":     bool(ds or de),
            "date_filter_start":       ds,
            "date_filter_end":         de,
            "date_filter_description": f"{ds} to {de}" if ds and de else "",
        }

    t0 = time.time()
    neg_log = []
    if resolved_neg or unresolved_neg_kw:
        candidates, neg_log = apply_negative_filter(candidates, resolved_neg, unresolved_neg_kw)
    timings["filter_ms"] = (time.time() - t0) * 1000

    t0 = time.time()
    reranked = rerank(candidates, resolved_pos, nlu, nlu["query_mode"])
    timings["rerank_ms"] = (time.time() - t0) * 1000

    timings["total_ms"] = (timings["nlu_ms"] + timings["retrieval_ms"]
                           + timings["filter_ms"] + timings["rerank_ms"])

    anchor_strs = [f"{e['name']} ({e['vertical']}) [{e['match_type']}]" for e in resolved_pos]
    neg_strs    = [f"{e['name']} ({e['vertical']})" for e in resolved_neg]
    if unresolved_neg_kw:
        neg_strs += [f"[keyword: {kw}]" for kw in unresolved_neg_kw]

    date_applied = bool(ds or de)
    if date_applied:
        if ds and de:   date_desc = f"{ds} to {de}"
        elif ds:        date_desc = f"After {ds}"
        else:           date_desc = f"Before {de}"
    else:
        date_desc = ""

    base = {
        "query":                      user_query,
        "parsed_intent":              nlu,
        "query_mode":                 nlu["query_mode"],
        "anchor_entities_resolved":   anchor_strs,
        "negative_entities_resolved": neg_strs,
        "neg_filter_log":             neg_log,
        "reranker_debug":             reranked.get("debug", {}),
        "timings":                    timings,
        "status":                     "success",
        "retrieval_candidate_count":  len(ret["candidates"]),
        "post_filter_count":          len(candidates),
        "date_filter_applied":        date_applied,
        "date_filter_start":          ds,
        "date_filter_end":            de,
        "date_filter_description":    date_desc,
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
        final     = reranked["results"]
        formatted = [_format_result(i, c) for i, c in enumerate(final, 1)]
        _add_similarity_pct(formatted)
        base["results"]             = formatted
        base["results_by_vertical"] = {}

    return base
