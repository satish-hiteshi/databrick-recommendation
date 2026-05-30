"""
Retrieval v3 for Feeds.ai pipeline.
Uses Reciprocal Rank Fusion (RRF) instead of weighted score combination.
Handles all 5 query modes: entity_single, entity_multi, theme_based, descriptive, mixed.
"""

import numpy as np

from pipeline.config import TOP_K_RETRIEVAL
from pipeline.entity_resolver import resolve_entity
from pipeline.vector_store import vector_search, keyword_search
from pipeline.embedding_generator import embed_query_text

RRF_K = 60               # Standard RRF smoothing constant
DUAL_SIGNAL_BONUS = 0.005 # Bonus for appearing in both vector and BM25 lists
OVERLAP_BONUS = 0.003     # Bonus per additional entity that returned this candidate
MISSING_RANK = 1000       # Rank for documents not in a list


# ── Ranked list collection ────────────────────────────────────────────

def _collect_ranked_lists(embedding, keywords, verticals_set, top_k, source_label,
                          date_start=None, date_end=None):
    """
    Run vector + BM25 search for one source. Returns two ranked lists
    (vector_list, bm25_list) and metadata for each entity seen.
    Each ranked list is: [(entity_id, rank_position), ...]
    """
    vec_results = vector_search(embedding, verticals_set, top_k,
                                 date_start=date_start, date_end=date_end)
    bm25_results = keyword_search(keywords, verticals_set, top_k,
                                   date_start=date_start, date_end=date_end)

    # Build metadata lookup
    meta = {}
    for eid, name, vert, _ in vec_results:
        meta[eid] = {"entity_id": eid, "name": name, "vertical": vert}
    for eid, name, vert, _ in bm25_results:
        if eid not in meta:
            meta[eid] = {"entity_id": eid, "name": name, "vertical": vert}

    # Ranked lists (1-indexed)
    vec_ranked = [(eid, rank + 1) for rank, (eid, _, _, _) in enumerate(vec_results)]
    bm25_ranked = [(eid, rank + 1) for rank, (eid, _, _, _) in enumerate(bm25_results)]

    debug = {
        "source": source_label,
        "vec_count": len(vec_results),
        "bm25_count": len(bm25_results),
        "vec_top5": [(n, v, f"{s:.4f}") for _, n, v, s in vec_results[:5]],
        "bm25_top5": [(n, v, f"{s:.4f}") for _, n, v, s in bm25_results[:5]],
    }

    return vec_ranked, bm25_ranked, meta, debug


# ── RRF Fusion ────────────────────────────────────────────────────────

def _rrf_fuse(all_ranked_lists, all_list_types, all_source_indices, meta_pool):
    """
    Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Args:
        all_ranked_lists: list of [(entity_id, rank), ...] for each list
        all_list_types: list of "vector" or "bm25" for each list
        all_source_indices: list of source index (which entity/theme produced this list)
        meta_pool: dict entity_id -> {name, vertical}

    Returns:
        list of candidate dicts sorted by rrf_score descending
    """
    # Build per-entity tracking
    candidates = {}

    for list_idx, ranked_list in enumerate(all_ranked_lists):
        list_type = all_list_types[list_idx]
        source_idx = all_source_indices[list_idx]

        rank_map = {eid: rank for eid, rank in ranked_list}

        for eid, rank in ranked_list:
            if eid not in candidates:
                m = meta_pool.get(eid, {})
                candidates[eid] = {
                    "entity_id": eid,
                    "name": m.get("name", ""),
                    "vertical": m.get("vertical", ""),
                    "rrf_score": 0.0,
                    "vector_ranks": [],      # best rank per vector list
                    "bm25_ranks": [],        # best rank per bm25 list
                    "in_vector": False,
                    "in_bm25": False,
                    "source_indices": set(),  # which sources contributed
                    "shared_keywords": [],
                }

            # Add RRF contribution
            rrf_contrib = 1.0 / (RRF_K + rank)
            candidates[eid]["rrf_score"] += rrf_contrib

            if list_type == "vector":
                candidates[eid]["vector_ranks"].append(rank)
                candidates[eid]["in_vector"] = True
            else:
                candidates[eid]["bm25_ranks"].append(rank)
                candidates[eid]["in_bm25"] = True

            candidates[eid]["source_indices"].add(source_idx)

    # Apply bonuses
    for c in candidates.values():
        # Dual signal bonus
        if c["in_vector"] and c["in_bm25"]:
            c["rrf_score"] += DUAL_SIGNAL_BONUS

        # Multi-entity overlap bonus
        num_sources = len(c["source_indices"])
        if num_sources > 1:
            c["rrf_score"] += OVERLAP_BONUS * (num_sources - 1)

        # Compute best ranks
        c["best_vector_rank"] = min(c["vector_ranks"]) if c["vector_ranks"] else None
        c["best_bm25_rank"] = min(c["bm25_ranks"]) if c["bm25_ranks"] else None
        c["appeared_in_searches"] = num_sources

        # For compatibility with downstream (reranker, negative_filter)
        c["combined_score"] = c["rrf_score"]
        c["vector_score"] = c["rrf_score"]  # placeholder for display
        c["bm25_score"] = 0.0               # placeholder

        # Clean up
        del c["vector_ranks"]
        del c["bm25_ranks"]
        c["source_indices"] = list(c["source_indices"])

    sorted_cands = sorted(candidates.values(), key=lambda x: x["rrf_score"], reverse=True)
    return sorted_cands


# ── Main retrieve function ────────────────────────────────────────────

def retrieve(nlu_output: dict):
    """
    Full retrieval pipeline handling all 5 query modes with RRF fusion.
    """
    mode = nlu_output["query_mode"]
    pos_names = nlu_output.get("positive_entities", [])
    neg_names = nlu_output.get("negative_entities", [])
    add_kw = nlu_output.get("additional_keywords", [])
    desc_kw = nlu_output.get("description_derived_keywords", [])
    target_verts = nlu_output.get("target_verticals", ["game", "movie", "tv"])
    verticals_set = set(target_verts) if target_verts else None
    date_start = nlu_output.get("date_filter_start")
    date_end = nlu_output.get("date_filter_end")

    # Resolve positive entities via SQL
    resolved_pos = []
    for name in pos_names:
        r = resolve_entity(name)
        if r:
            resolved_pos.append(r)

    # Resolve negative entities
    resolved_neg = []
    unresolved_neg_keywords = []
    for name in neg_names:
        r = resolve_entity(name)
        if r:
            resolved_neg.append(r)
        else:
            unresolved_neg_keywords.append(name.lower())

    all_debug = []
    all_ranked_lists = []
    all_list_types = []
    all_source_indices = []
    meta_pool = {}

    def _add_source(embedding, keywords, verticals, top_k, label, source_idx):
        vec_ranked, bm25_ranked, meta, dbg = _collect_ranked_lists(
            embedding, keywords, verticals, top_k, label,
            date_start=date_start, date_end=date_end
        )
        all_debug.append(dbg)
        meta_pool.update(meta)

        all_ranked_lists.append(vec_ranked)
        all_list_types.append("vector")
        all_source_indices.append(source_idx)

        all_ranked_lists.append(bm25_ranked)
        all_list_types.append("bm25")
        all_source_indices.append(source_idx)

    # ── entity_single ─────────────────────────────────────────────
    if mode == "entity_single":
        if not resolved_pos:
            return _empty_result(mode, resolved_pos, resolved_neg,
                                 error=f"No entity resolved from: {pos_names}",
                                 unresolved_neg_kw=unresolved_neg_keywords)
        anchor = resolved_pos[0]
        _add_source(anchor["embedding"], anchor["bm25_keywords"],
                    verticals_set, TOP_K_RETRIEVAL, f"entity:{anchor['name']}", 0)

    # ── entity_multi ──────────────────────────────────────────────
    elif mode == "entity_multi":
        if not resolved_pos:
            return _empty_result(mode, resolved_pos, resolved_neg,
                                 error=f"No entities resolved from: {pos_names}",
                                 unresolved_neg_kw=unresolved_neg_keywords)
        for i, ent in enumerate(resolved_pos):
            _add_source(ent["embedding"], ent["bm25_keywords"],
                        verticals_set, 15, f"entity:{ent['name']}", i)

    # ── theme_based / descriptive ─────────────────────────────────
    elif mode in ("theme_based", "descriptive"):
        all_keywords = add_kw + desc_kw
        if not all_keywords:
            # Date-only query: use verticals as broad search terms
            if date_start or date_end:
                vert_terms = list(target_verts) if target_verts else ["entertainment"]
                search_text = " ".join(vert_terms)
                query_emb = np.array(embed_query_text(search_text), dtype=np.float32)
                _add_source(query_emb, vert_terms,
                            verticals_set, TOP_K_RETRIEVAL, f"browse:{search_text[:40]}", 0)
            else:
                return _empty_result(mode, resolved_pos, resolved_neg,
                                     error="No keywords extracted for theme/descriptive search",
                                     unresolved_neg_kw=unresolved_neg_keywords)
        else:
            search_text = " ".join(all_keywords)
            query_emb = np.array(embed_query_text(search_text), dtype=np.float32)
            _add_source(query_emb, all_keywords,
                        verticals_set, TOP_K_RETRIEVAL, f"theme:{search_text[:40]}", 0)

    # ── mixed ─────────────────────────────────────────────────────
    elif mode == "mixed":
        for i, ent in enumerate(resolved_pos):
            _add_source(ent["embedding"], ent["bm25_keywords"],
                        verticals_set, 15, f"entity:{ent['name']}", i)

        all_keywords = add_kw + desc_kw
        if all_keywords:
            search_text = " ".join(all_keywords)
            query_emb = np.array(embed_query_text(search_text), dtype=np.float32)
            _add_source(query_emb, all_keywords,
                        verticals_set, TOP_K_RETRIEVAL,
                        f"theme:{search_text[:40]}", len(resolved_pos))

        if not all_ranked_lists:
            return _empty_result(mode, resolved_pos, resolved_neg,
                                 error="No entities resolved and no keywords for mixed search",
                                 unresolved_neg_kw=unresolved_neg_keywords)
    else:
        return _empty_result(mode, resolved_pos, resolved_neg,
                             error=f"Unknown query mode: {mode}",
                             unresolved_neg_kw=unresolved_neg_keywords)

    # Fuse all lists with RRF
    sorted_candidates = _rrf_fuse(all_ranked_lists, all_list_types,
                                   all_source_indices, meta_pool)

    return {
        "candidates": sorted_candidates,
        "resolved_positive": resolved_pos,
        "resolved_negative": resolved_neg,
        "unresolved_neg_keywords": unresolved_neg_keywords,
        "query_mode": mode,
        "debug": all_debug,
    }


def _empty_result(mode, resolved_pos, resolved_neg, error="", unresolved_neg_kw=None):
    return {
        "candidates": [],
        "resolved_positive": resolved_pos,
        "resolved_negative": resolved_neg,
        "unresolved_neg_keywords": unresolved_neg_kw or [],
        "query_mode": mode,
        "debug": [{"error": error}],
    }
