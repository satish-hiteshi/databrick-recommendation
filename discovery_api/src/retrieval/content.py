"""Discovery v2 — CONTENT-BASED RETRIEVAL (Source 2).

Per taste cluster, IN PARALLEL: (a) VECTOR — compose_query → /api/retrieve (vertical-filtered); (b) GRAPH
— /graph/structured (top genres, canonical case) + /graph/similar (seeded by the cluster's top
representative members, a FEW). Merge per cluster with provenance, apply HARD exclusions, rank. Then
PERCENTAGE ALLOCATION across clusters by vertical_percentages × cluster_share.

LATENCY FIX: the number of /api/retrieve calls == number of clusters (a few), not one-per-followed-entity.
All vector+graph calls run concurrently on the bounded substrate pool (run_concurrent).
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple

from .. import config
from ..data_access.substrate_client import SubstrateClient, run_concurrent
from .candidates import AllocationPlan, Candidate, ClusterCandidateSet
from .compose import compose_query


def _norm_add(by_id: Dict[str, Candidate], items, path: str, cluster_id: int,
              exclude: Set[str], default_vertical: str) -> None:
    """Min-max normalise a source's scores and merge into by_id, recording provenance (path + path score)."""
    items = items or []
    scores = [float(i.get("score", 0) or 0) for i in items]
    if scores:
        mn, mx = min(scores), max(scores)
        rng = (mx - mn) or 1.0
    for it in items:
        eid = it.get("entity_id")
        if not eid or eid in exclude:
            continue
        norm = (float(it.get("score", 0) or 0) - mn) / rng if scores else 0.0
        cand = by_id.get(eid)
        if cand is None:
            cand = Candidate(entity_id=eid, name=it.get("name", "") or "",
                             vertical=it.get("vertical") or default_vertical, score=0.0,
                             source_pool="content", cluster_id=cluster_id)
            by_id[eid] = cand
        if path not in cand.paths:
            cand.paths.append(path)
        cand.path_scores[path] = max(cand.path_scores.get(path, 0.0), round(norm, 6))


def _finalize_scores(by_id: Dict[str, Candidate]) -> List[Candidate]:
    for cand in by_id.values():
        v = cand.path_scores.get("vector", 0.0)
        g = max(cand.path_scores.get("graph_structured", 0.0), cand.path_scores.get("graph_similar", 0.0))
        s = config.V2_MERGE_W_VECTOR * v + config.V2_MERGE_W_GRAPH * g
        if v > 0 and g > 0:
            s += config.V2_MERGE_BOTH_BONUS
        cand.score = round(s, 6)
    return sorted(by_id.values(), key=lambda c: (-c.score, c.entity_id))


def _dedupe_across_clusters(sets: List[ClusterCandidateSet]) -> List[ClusterCandidateSet]:
    """An entity may be retrieved by several clusters — keep it ONLY in the cluster where it scores highest
    (ties → the earlier/higher-weight cluster, since profile.clusters is weight-desc). Guarantees each
    candidate entity appears once across the whole content set (spec: dedupe across clusters)."""
    best: Dict[str, Tuple[float, int]] = {}
    for cs in sets:
        for c in cs.candidates:
            cur = best.get(c.entity_id)
            if cur is None or c.score > cur[0]:
                best[c.entity_id] = (c.score, cs.cluster_id)
    for cs in sets:
        cs.candidates = [c for c in cs.candidates if best[c.entity_id][1] == cs.cluster_id]
    return sets


def build_content_candidates(profile, client: SubstrateClient, exclude_ids: Set[str]
                             ) -> Tuple[List[ClusterCandidateSet], int, int]:
    """Retrieve + merge per cluster. Returns (cluster_sets, n_retrieve_calls, n_substrate_calls)."""
    clusters = profile.clusters
    if not clusters:
        return [], 0, 0

    # ── compose phrases (parallelised when the LLM composer is selected) ──
    if config.V2_STRING_COMPOSER == "llm":
        ctasks = {c.cluster_id: (lambda c=c: compose_query(c)) for c in clusters}
        cres = run_concurrent(ctasks)
        phrases = {c.cluster_id: (cres.get(c.cluster_id) or compose_query(c)) for c in clusters}
    else:
        phrases = {c.cluster_id: compose_query(c) for c in clusters}

    # ── build ONE flat task map for all clusters' vector + graph calls → maximal concurrency ──
    tasks: Dict[tuple, callable] = {}
    for c in clusters:
        phrase, _ = phrases[c.cluster_id]
        genres = [g for g, _ in c.top_genres[:config.V2_GRAPH_STRUCTURED_GENRES]]   # canonical case
        tasks[("vec", c.cluster_id)] = (
            lambda ph=phrase, v=c.dominant_vertical: client.vector_retrieve(ph, vertical=v, top_k=config.V2_RETRIEVE_TOP_K))
        if genres:
            tasks[("gstruct", c.cluster_id)] = (
                lambda gs=genres, v=c.dominant_vertical: client.graph_structured(vertical=v, genre=gs, top_k=config.V2_GRAPH_TOP_K))
        for seed in c.top_representative_member_entity_ids[:config.V2_GRAPH_SIMILAR_SEEDS]:
            tasks[("gsim", c.cluster_id, seed)] = (
                lambda s=seed, v=c.dominant_vertical: client.graph_similar(s, top_k=config.V2_GRAPH_TOP_K, vertical=v))

    results = run_concurrent(tasks, max_workers=config.SUBSTRATE_MAX_WORKERS)
    n_retrieve_calls = sum(1 for k in tasks if k[0] == "vec")
    n_substrate_calls = len(tasks)

    # ── assemble + merge per cluster ──
    out: List[ClusterCandidateSet] = []
    for c in clusters:
        phrase, composer = phrases[c.cluster_id]
        by_id: Dict[str, Candidate] = {}
        _norm_add(by_id, results.get(("vec", c.cluster_id)), "vector", c.cluster_id, exclude_ids, c.dominant_vertical)
        _norm_add(by_id, results.get(("gstruct", c.cluster_id)), "graph_structured", c.cluster_id, exclude_ids, c.dominant_vertical)
        for seed in c.top_representative_member_entity_ids[:config.V2_GRAPH_SIMILAR_SEEDS]:
            _norm_add(by_id, results.get(("gsim", c.cluster_id, seed)), "graph_similar", c.cluster_id, exclude_ids, c.dominant_vertical)
        ranked = _finalize_scores(by_id)
        out.append(ClusterCandidateSet(
            cluster_id=c.cluster_id, label=c.label, dominant_vertical=c.dominant_vertical,
            phrase=phrase, composer=composer, cluster_share=c.cluster_share,
            slot_quota=0, candidates=ranked))
    out = _dedupe_across_clusters(out)   # an entity belongs to its best-scoring cluster only
    return out, n_retrieve_calls, n_substrate_calls


def allocate(profile, cluster_sets: List[ClusterCandidateSet]) -> AllocationPlan:
    """Split the candidate budget: exploration_fraction(signal) off the top, then content slots across
    verticals by vertical_percentages, and within a vertical across its clusters by cluster_share. Mutates
    each ClusterCandidateSet.slot_quota. A vertical with budget but no cluster → global_backfill (V2-P4)."""
    ss = profile.signal_strength
    frac = config.V2_EXPLORE_FRAC_MAX - (config.V2_EXPLORE_FRAC_MAX - config.V2_EXPLORE_FRAC_MIN) * ss
    frac = max(config.V2_EXPLORE_FRAC_MIN, min(config.V2_EXPLORE_FRAC_MAX, frac))
    total = config.V2_CANDIDATE_BUDGET
    explore_slots = round(total * frac)
    content_slots = total - explore_slots

    by_vertical = {v: int(round(content_slots * profile.vertical_percentages.get(v, 0.0)))
                   for v in config.VERTICALS}
    by_cluster: Dict[int, int] = {}
    global_backfill: Dict[str, int] = {}

    if config.V2_ALLOC_MODE == "cluster_share":
        sh = sum(c.cluster_share for c in cluster_sets) or 1.0
        for c in cluster_sets:
            by_cluster[c.cluster_id] = max(config.V2_MIN_CLUSTER_SLOTS, int(round(content_slots * c.cluster_share / sh)))
    else:  # vertical_then_cluster (default)
        for v in config.VERTICALS:
            vcl = [c for c in cluster_sets if c.dominant_vertical == v]
            if not vcl:
                if by_vertical[v] > 0:
                    global_backfill[v] = by_vertical[v]
                continue
            shs = sum(c.cluster_share for c in vcl) or 1.0
            for c in vcl:
                by_cluster[c.cluster_id] = max(config.V2_MIN_CLUSTER_SLOTS,
                                               int(round(by_vertical[v] * c.cluster_share / shs)))

    for c in cluster_sets:
        c.slot_quota = by_cluster.get(c.cluster_id, config.V2_MIN_CLUSTER_SLOTS)

    return AllocationPlan(total_budget=total, content_slots=content_slots, exploration_slots=explore_slots,
                          exploration_fraction=round(frac, 4), by_vertical=by_vertical,
                          by_cluster=by_cluster, global_backfill=global_backfill,
                          alloc_mode=config.V2_ALLOC_MODE)
