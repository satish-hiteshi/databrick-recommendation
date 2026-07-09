"""HomeFeedEngine — the full E3 phase-one pipeline, end to end.

    request → follow-gate → traverse → suppress  (prompt 3)
            → rank (taste + recency + proximity)  (prompt 4)
            → serialize to the UC3 v1.0 envelope   (this prompt)

This module only WIRES the prompt-3/4/5 pieces; it adds no ranking or filtering of its own. No LLM on
the path. Construct once with the data sources (follow source + 44k graph + vectors), then call build()
per request. Empty streams (no follows / no moments) return a valid empty envelope, never an error.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .candidate_pool import build_candidate_pool, resolve_now
from .follow_source import FollowSource
from .graph_moments import GraphMoments
from .ranker import rank_pool
from .request import HomeFeedRequest
from .scorer import HomeWeights
from .serializer import build_envelope
from .substrate_guard import assert_substrate
from .suppression import SuppressionInputs, property_refs_to_entity_ids
from .vectors import VectorStore

# Fire the startup substrate guard exactly ONCE per process (the API builds the engine lazily on first
# request; multiple engine constructions must not re-run the check). SUBSTRATE_CHECK=0 bypasses it.
_SUBSTRATE_CHECKED = False


class HomeFeedEngine:
    def __init__(self, follow_source: FollowSource, graph: GraphMoments, vectors: VectorStore,
                 weights: Optional[HomeWeights] = None):
        global _SUBSTRATE_CHECKED
        if not _SUBSTRATE_CHECKED:
            assert_substrate()        # FAIL LOUD on wrong graph/parquet (:7687 57k / :7688 44k / obsolete)
            _SUBSTRATE_CHECKED = True
        self.follow_source = follow_source
        self.graph = graph
        self.vectors = vectors
        self.weights = weights or HomeWeights.from_config()

    def build(self, req: HomeFeedRequest, *, now: Optional[datetime] = None,
              interleave_mode: Optional[str] = None, interleave_margin: Optional[float] = None,
              max_moment_age_days: Optional[float] = None) -> dict:
        now = resolve_now(now)
        suppression = SuppressionInputs(
            seen_ids=set(req.seen_ids), done_ids=set(req.done_ids),
            # inbound property refs (entity_id | composite | bare source_id) → entity_ids (collision-safe)
            dismissed_property_ids=property_refs_to_entity_ids(req.dismissed_property_ids),
            blocked_property_ids=property_refs_to_entity_ids(req.blocked_property_ids),
            reacted_moment_ids=set(req.reacted_moment_ids))

        pool = build_candidate_pool(req.user_id, suppression, follow_source=self.follow_source,
                                    graph=self.graph, now=now, max_moment_age_days=max_moment_age_days)
        ranked = rank_pool(pool, graph=self.graph, vectors=self.vectors, now=now,
                           sort_mode=req.sort_order, weights=self.weights,
                           interleave_mode=interleave_mode, interleave_margin=interleave_margin)
        return build_envelope(req, pool, ranked, now, self.weights)
