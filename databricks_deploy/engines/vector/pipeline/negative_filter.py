"""
Negative entity filtering for Feeds.ai pipeline.
Handles two cases:
  1. Resolved negative entities (from SQL) — embedding similarity + keyword overlap + franchise exclusion
  2. Unresolved keyword negatives (e.g., "comedy") — keyword overlap penalization only
"""

import numpy as np

from pipeline.entity_resolver import batch_fetch_entities


def _cosine_sim(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    dot = np.dot(a, b)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def apply_negative_filter(candidates, negative_entities, unresolved_neg_keywords=None):
    """
    Penalize or remove candidates similar to negative entities or matching negative keywords.

    Args:
        candidates: list of candidate dicts with entity_id, combined_score, etc.
        negative_entities: list of resolved negative entity dicts from entity_resolver
            (each has entity_id, embedding, bm25_keywords, franchise)
        unresolved_neg_keywords: list of lowercase keyword strings that didn't resolve
            as entities (e.g., "comedy", "romance"). Penalizes via keyword/text overlap.

    Returns:
        (filtered_candidates, debug_log)
    """
    if not candidates:
        return candidates, []

    has_resolved = bool(negative_entities)
    has_unresolved = bool(unresolved_neg_keywords)

    if not has_resolved and not has_unresolved:
        return candidates, []

    # Batch-fetch candidate data from PostgreSQL
    cand_ids = [c["entity_id"] for c in candidates]
    cand_data = batch_fetch_entities(cand_ids)

    # Prepare resolved negative entity data
    neg_embeddings = []
    neg_keyword_sets = []
    neg_franchises = set()
    if has_resolved:
        for neg in negative_entities:
            if neg.get("embedding") is not None:
                neg_embeddings.append((neg["name"], neg["embedding"]))
            neg_kws = set(kw.lower() for kw in neg.get("bm25_keywords", []))
            neg_keyword_sets.append((neg["name"], neg_kws))
            if neg.get("franchise"):
                neg_franchises.add(neg["franchise"])

    # Prepare unresolved keyword set
    unresolved_kw_set = set(unresolved_neg_keywords or [])

    debug_log = []
    filtered = []

    for c in candidates:
        eid = c["entity_id"]
        cd = cand_data.get(eid, {})
        cand_emb = cd.get("embedding")
        cand_kws = set(kw.lower() for kw in cd.get("bm25_keywords", []))
        cand_text = cd.get("composed_text", "").lower()
        cand_franchise = cd.get("franchise")

        original_score = c["combined_score"]
        total_penalty = 0.0
        reasons = []

        # ── Resolved negative entity checks ──

        # Franchise exclusion (hard remove)
        if cand_franchise and cand_franchise in neg_franchises:
            debug_log.append({
                "entity_id": eid,
                "name": c["name"],
                "action": "REMOVED",
                "reason": f"franchise match: {cand_franchise}",
                "original_score": round(original_score, 4),
            })
            continue

        # Embedding similarity penalty
        if cand_emb is not None:
            for neg_name, neg_emb in neg_embeddings:
                sim = _cosine_sim(cand_emb, neg_emb)
                if sim > 0.6:
                    penalty = 0.3 * sim
                    total_penalty += penalty
                    reasons.append(f"emb_sim({neg_name})={sim:.3f}, penalty={penalty:.3f}")

        # Keyword overlap with resolved negatives
        if cand_kws:
            for neg_name, neg_kw_set in neg_keyword_sets:
                shared = cand_kws & neg_kw_set
                overlap_ratio = len(shared) / len(cand_kws)
                if overlap_ratio > 0.4:
                    total_penalty += 0.1
                    reasons.append(
                        f"kw_overlap({neg_name})={overlap_ratio:.0%} "
                        f"({len(shared)}/{len(cand_kws)}), penalty=0.1"
                    )

        # ── Unresolved keyword negative checks ──
        # These are genre/theme terms like "comedy" that didn't match an entity in the DB.
        # Penalize candidates whose keywords or composed_text contain these terms.
        for neg_kw in unresolved_kw_set:
            # Check BM25 keywords
            if neg_kw in cand_kws:
                total_penalty += 0.15
                reasons.append(f"neg_kw_match('{neg_kw}' in bm25_keywords), penalty=0.15")
            # Check composed text (weaker signal)
            elif neg_kw in cand_text:
                total_penalty += 0.08
                reasons.append(f"neg_kw_text('{neg_kw}' in composed_text), penalty=0.08")

        # Apply penalty
        new_score = original_score - total_penalty

        # Score floor
        if new_score <= 0.0:
            debug_log.append({
                "entity_id": eid,
                "name": c["name"],
                "action": "REMOVED",
                "reason": f"score below floor ({original_score:.4f} - {total_penalty:.4f} = {new_score:.4f})",
                "original_score": round(original_score, 4),
                "penalty": round(total_penalty, 4),
            })
            continue

        if total_penalty > 0:
            debug_log.append({
                "entity_id": eid,
                "name": c["name"],
                "action": "PENALIZED",
                "reason": "; ".join(reasons),
                "original_score": round(original_score, 4),
                "penalty": round(total_penalty, 4),
                "new_score": round(new_score, 4),
            })

        c["combined_score"] = new_score
        c["negative_penalty"] = round(total_penalty, 4)
        filtered.append(c)

    # Re-sort after penalties
    filtered.sort(key=lambda x: x["combined_score"], reverse=True)

    return filtered, debug_log
