"""Discovery v2 — candidate-set data structures (V2-P3 intermediate).

This package produces SCORED CANDIDATE SETS only (content + exploration, with provenance, allocated by
percentage, exclusions applied). It does NOT do moment selection or feed assembly — that is V2-P4, which
consumes a `CandidateBundle`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Candidate:
    """One candidate PROPERTY with full provenance (which pool / cluster / retrieval paths produced it)."""
    entity_id: str
    name: str
    vertical: str
    score: float                                       # merged, source-normalized rank score (taste/retrieval)
    source_pool: str                                   # "content" | "exploration" | "trending" | "both" | "collaborative"
    cluster_id: Optional[int] = None                   # taste cluster that produced it (content/trending); None for cross-attribute collaborative
    paths: List[str] = field(default_factory=list)     # ["vector","graph_structured","graph_similar","trending","collaborative"]
    path_scores: Dict[str, float] = field(default_factory=dict)
    # ── trending provenance (V2-P8: source_pool="trending"/"both") ──
    trending_velocity: float = 0.0                     # niche-relative trending velocity of its best moment [0,1]
    best_trending_moment_id: Optional[int] = None      # the specific TRENDING moment that earned this candidate
    # ── collaborative provenance (V2-P9: source_pool="collaborative") ──
    collaborative_score: float = 0.0                   # niche-relative similar-user affinity [0,1] (the blend's collab term)
    collab_endorsers: int = 0                          # # distinct similar users who endorse it (the endorsement gate / social proof)
    collab_neighbor_size: int = 0                      # size of the taste neighborhood that produced it
    # ── exploration provenance (source_pool="exploration") ──
    adjacency_rule: Optional[str] = None               # which structured-adjacency rule produced it
    shared_attrs: List[str] = field(default_factory=list)   # attrs SHARED with the profile (stays adjacent)
    new_attrs: List[str] = field(default_factory=list)      # the NEW attr introduced (not identical)
    seed_entity_id: Optional[str] = None               # the profile entity it was reached from (rule B)


@dataclass
class ClusterCandidateSet:
    cluster_id: int
    label: str
    dominant_vertical: str
    phrase: str                                        # the composed query string used (vector path)
    composer: str                                      # "deterministic" | "llm"
    cluster_share: float
    slot_quota: int                                    # allocated budget (vertical% × cluster_share)
    candidates: List[Candidate]                        # merged, deduped, ranked (FULL list)

    @property
    def allocated(self) -> List[Candidate]:
        """The first slot_quota candidates — the cluster's contribution to the feed budget."""
        return self.candidates[:self.slot_quota]


@dataclass
class AllocationPlan:
    total_budget: int
    content_slots: int
    exploration_slots: int
    exploration_fraction: float
    by_vertical: Dict[str, int]                        # content slots per vertical (from vertical_percentages)
    by_cluster: Dict[int, int]                         # content slots per cluster (vertical% × cluster_share)
    global_backfill: Dict[str, int]                    # vertical → slots w/ budget but NO cluster (V2-P4 global fill)
    alloc_mode: str


@dataclass
class CandidateBundle:
    """The V2-P3 output. V2-P4 turns this into moments + the v1.0 feed envelope."""
    user_id: Optional[int]
    mode: str
    signal_strength: float
    fallback_to_global: bool                           # True for cold-start / no clusters → caller uses global feed
    allocation: AllocationPlan
    clusters: List[ClusterCandidateSet]
    exploration: List[Candidate]
    excluded_entity_count: int                         # size of the hard never-return set
    n_retrieve_calls: int                              # = number of /api/retrieve (vector) calls = #clusters
    n_substrate_calls: int                             # all vector+graph calls made
    timing_ms: Dict[str, float]
    # ── trending candidate source (V2-P8) ──
    trending: List[Candidate] = field(default_factory=list)          # trending-on-taste candidates (for the carousel)
    trend_confidence: float = 0.0                                    # niche-relative trending confidence [0,1] → adaptive w_trending
    trend_moment_velocity: Dict[int, float] = field(default_factory=dict)  # moment_id → niche-relative velocity (for the blend)
    # ── collaborative candidate source (V2-P9, Source 4) ──
    collaborative: List[Candidate] = field(default_factory=list)     # NEW similar-user discoveries (incl. CROSS-ATTRIBUTE) → carousel + feed stream
    collab_confidence: float = 0.0                                   # neighborhood-density confidence [0,1] → adaptive w_collaborative
    collab_score: Dict[str, float] = field(default_factory=dict)     # entity_id → niche-relative affinity (the blend's collab term; covers content items too)
    collab_neighborhood: Optional[object] = None                    # the Neighborhood (size/density provenance) for meta/debug

    def all_candidate_ids(self) -> List[str]:
        out = [c.entity_id for cs in self.clusters for c in cs.candidates]
        out += [c.entity_id for c in self.exploration]
        out += [c.entity_id for c in self.trending]
        out += [c.entity_id for c in self.collaborative]
        return out
