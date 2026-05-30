"""
Reranker v2 for Feeds.ai pipeline.
Supports Phase 2: multi-entity, keyword boosting, per-vertical splitting, franchise diversity.
"""

from collections import Counter

from pipeline.config import TOP_K_RESULTS
from pipeline.data_loader import get_all_entities
from pipeline.entity_resolver import batch_fetch_entities
from pipeline.reasoning import attach_reasoning


# ── Cached lookups ────────────────────────────────────────────────────

_entity_keywords = None
_entity_franchises = None
_entity_composed = None


def _ensure_lookups():
    global _entity_keywords, _entity_franchises, _entity_composed
    if _entity_keywords is None:
        entities = get_all_entities()
        _entity_keywords = {
            e["entity_id"]: [kw.lower() for kw in e["bm25_keywords"]]
            for e in entities
        }
        _entity_franchises = {
            e["entity_id"]: e.get("franchise")
            for e in entities
        }
        _entity_composed = {
            e["entity_id"]: e.get("composed_text", "").lower()
            for e in entities
        }


def _get_kw(eid):
    _ensure_lookups()
    return _entity_keywords.get(eid, [])


def _get_franchise(eid):
    _ensure_lookups()
    return _entity_franchises.get(eid)


def _get_composed(eid):
    _ensure_lookups()
    return _entity_composed.get(eid, "")


# ── Main rerank function ─────────────────────────────────────────────

def rerank(candidates, positive_entities, nlu_output, query_mode, top_k=TOP_K_RESULTS):
    """
    Apply reranking rules to merged candidates.

    Args:
        candidates: list of candidate dicts from retrieval (with combined_score)
        positive_entities: list of resolved positive entity dicts
        nlu_output: dict from NLU with additional_keywords, description_derived_keywords,
                    target_verticals, query_type
        query_mode: string query mode from NLU
        top_k: max results per vertical

    Returns:
        dict with:
          results: list of final ranked results (or dict of vertical -> results for multi-vertical)
          debug: reranking debug info
    """
    if not candidates:
        return {"results": [], "debug": {"note": "no candidates"}}

    target_verticals = nlu_output.get("target_verticals", ["game", "movie", "tv"])
    query_type = nlu_output.get("query_type", "cross_vertical")
    add_kw = nlu_output.get("additional_keywords", [])
    desc_kw = nlu_output.get("description_derived_keywords", [])
    boost_keywords = [kw.lower() for kw in (add_kw + desc_kw)]

    pos_ids = set(e["entity_id"] for e in positive_entities)
    pos_franchises = set(
        e.get("franchise") for e in positive_entities if e.get("franchise")
    )
    pos_verticals = set(e["vertical"] for e in positive_entities)

    debug = {
        "self_excluded": [],
        "franchise_boosted": [],
        "keyword_boosted": [],
        "franchise_capped": [],
    }

    # 1. Self-exclusion
    results = []
    for c in candidates:
        if c["entity_id"] in pos_ids:
            debug["self_excluded"].append(c["name"])
        else:
            results.append(c)

    # 2-4. Score adjustments
    for c in results:
        eid = c["entity_id"]
        score = c["combined_score"]
        adjustments = {}

        # 2. Franchise boost (+0.10)
        cand_franchise = _get_franchise(eid)
        if cand_franchise and cand_franchise in pos_franchises:
            score += 0.10
            adjustments["franchise_boost"] = 0.10
            debug["franchise_boosted"].append(c["name"])

        # 3. Post-retrieval keyword boosting
        if boost_keywords:
            cand_kws = _get_kw(eid)
            cand_text = _get_composed(eid)
            kw_boost = 0.0

            for kw in boost_keywords:
                if kw in cand_kws:
                    kw_boost += 0.05
                elif kw in cand_text:
                    kw_boost += 0.03

            kw_boost = min(kw_boost, 0.20)
            if kw_boost > 0:
                score += kw_boost
                adjustments["keyword_boost"] = round(kw_boost, 4)
                debug["keyword_boosted"].append((c["name"], round(kw_boost, 4)))

        # 4. Vertical-aware weighting (multi-entity)
        if query_mode in ("entity_multi", "mixed") and pos_verticals:
            cand_vert = c["vertical"]
            if cand_vert in pos_verticals and cand_vert in target_verticals:
                score *= 1.1
                adjustments["vertical_weight"] = 1.1

        c["final_score"] = round(score, 4)
        c["adjustments"] = adjustments

        # Populate shared keywords with positive entities
        anchor_kw_set = set()
        for e in positive_entities:
            anchor_kw_set.update(kw.lower() for kw in e.get("bm25_keywords", []))
        cand_kws_set = set(_get_kw(eid))
        c["shared_keywords"] = sorted(anchor_kw_set & cand_kws_set)

    # Sort by final score
    results.sort(key=lambda x: x["final_score"], reverse=True)

    # 5-6. Per-vertical splitting vs single-vertical
    if len(target_verticals) > 1:
        # Multi-vertical: split and take top_k per vertical
        per_vertical = {}
        for vert in target_verticals:
            vert_results = [c for c in results if c["vertical"] == vert]
            if len(vert_results) >= 3:
                vert_results = _enforce_franchise_diversity(vert_results, debug)
                final_vert = vert_results[:top_k]
                attach_reasoning(final_vert, positive_entities, nlu_output)
                per_vertical[vert] = final_vert

        return {"results": per_vertical, "debug": debug, "split_by_vertical": True}
    else:
        single_vert = target_verticals[0] if target_verticals else None
        if single_vert:
            results = [c for c in results if c["vertical"] == single_vert]

        results = _enforce_franchise_diversity(results, debug)
        final_results = results[:top_k]
        attach_reasoning(final_results, positive_entities, nlu_output)

        return {"results": final_results, "debug": debug, "split_by_vertical": False}


def _enforce_franchise_diversity(results, debug):
    """Cap at 3 results per franchise within a result list."""
    franchise_counts = Counter()
    filtered = []
    for c in results:
        f = _get_franchise(c["entity_id"])
        if f:
            franchise_counts[f] += 1
            if franchise_counts[f] > 3:
                debug["franchise_capped"].append((c["name"], f))
                continue
        filtered.append(c)
    return filtered
