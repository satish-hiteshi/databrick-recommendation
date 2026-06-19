"""Discovery v2 — COLLABORATIVE candidate source (V2-P9, Source 4). The bubble-escape candidate generator.

MIRRORS retrieval/trending_candidates.py. Where the trending source scopes GLOBAL velocity to the user's taste,
this turns the SIMILAR-USER neighborhood's affinity (ranking.collaborative.CollaborativeIndex) into candidates —
INCLUDING cross-attribute content the taste-retrieval path would NEVER surface (a horror fan's neighbors who also
love a strategy game). Collaborative GENERATES candidates from behavioral overlap, not from content similarity.

CROSS-ATTRIBUTE BY DESIGN — the one rule that makes this different from trending: candidates are NOT re-filtered
to the target's taste attributes. We attach a best-effort cluster_id for DISPLAY grouping when an item happens to
be on-taste, but an item with NO taste overlap (cluster_id=None) is KEPT and surfaced. The endorsement gate
(distinct-neighbor count, in the index) is what prevents noise — never a taste match.

DEDUP: the pipeline removes collaborative candidates that the content/trending path already produced (those keep
their content provenance; their collaborative endorsement still lifts them via the blend's collab term). What
remains here is genuinely NEW discovery — content the user's taste profile alone would never surface.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .. import config
from .candidates import Candidate
from .trending_candidates import _attrs, _cluster_match   # reuse: taste-overlap proxy for DISPLAY grouping only


def build_collaborative_candidates(profile, collab, ds, now: datetime, exclude_ids: set
                                   ) -> Tuple[Dict[int, List[Candidate]], List[Candidate], float, Dict[str, float], Optional[object]]:
    """Returns (per_cluster, flat, confidence, collab_score, neighborhood).
       - per_cluster: {cluster_id: [Candidate]} for the on-taste subset (DISPLAY grouping only).
       - flat: ALL collaborative candidates (on-taste AND cross-attribute) ranked by affinity → carousel + feed.
       - confidence [0,1]: neighborhood-density confidence (LOW activation threshold) → adaptive w_collaborative.
       - collab_score: {entity_id: niche-relative affinity [0,1]} → the blend's collaborative term (applies to
         content candidates too, so an on-taste item similar users ALSO love gets a collaborative lift).
       - neighborhood: the Neighborhood (provenance: size, density) for meta/debug.
    Excludes already-known content (exclude_ids = engaged ∪ excluded properties). NEVER taste-refiltered."""
    if collab is None or not profile.clusters:
        return {}, [], 0.0, {}, None
    nb = collab.neighborhood(profile, now, exclude_ids)
    if nb is None or not nb.affinity:
        return {}, [], (round(nb.confidence, 4) if nb else 0.0), {}, nb

    ranked = sorted(nb.affinity.items(), key=lambda kv: -kv[1])[:config.V2_COLLAB_CANDIDATE_MAX]
    per_cluster: Dict[int, List[Candidate]] = defaultdict(list)
    flat: List[Candidate] = []
    for eid, score in ranked:
        e = ds.get_entity(eid)
        if e is None:
            continue
        # best-effort cluster assignment for DISPLAY grouping — NOT a filter. Cross-attribute items (no major
        # shared genre) get cluster_id=None and a taste proxy of 0, and are KEPT (that's the bubble-escape).
        genres_l, keywords_l = _attrs(ds, eid, e.vertical)
        best_cid, best_match = None, 0.0
        for c in profile.clusters:
            mt = _cluster_match(c, genres_l, keywords_l, e.vertical)
            if mt > best_match:
                best_match, best_cid = mt, c.cluster_id
        on_taste = best_cid is not None and best_match >= config.V2_TREND_MATCH_MIN
        cand = Candidate(
            entity_id=eid, name=e.name, vertical=e.vertical,
            score=round(best_match, 6),                 # taste-overlap PROXY (0 for cross-attribute) — NOT the gate
            source_pool="collaborative", cluster_id=(best_cid if on_taste else None),
            paths=["collaborative"], collaborative_score=round(score, 6),
            collab_endorsers=nb.endorsers.get(eid, 0), collab_neighbor_size=nb.n_neighbors)
        flat.append(cand)
        if on_taste:
            per_cluster[best_cid].append(cand)

    flat.sort(key=lambda c: -c.collaborative_score)
    collab_score = {c.entity_id: c.collaborative_score for c in flat}
    return dict(per_cluster), flat, round(nb.confidence, 4), collab_score, nb
