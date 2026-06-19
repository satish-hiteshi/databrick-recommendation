"""Discovery v2 retrieval (V2-P3): content-based retrieval (Source 2) + exploration (Source 3).

Public entrypoint: retrieve_candidate_sets(profile, data_source=...) -> CandidateBundle. Produces scored
candidate SETS only (with provenance, percentage allocation, hard exclusions). Moment selection + feed
assembly + the blend controller are V2-P4.
"""

from .candidates import AllocationPlan, Candidate, CandidateBundle, ClusterCandidateSet
from .collaborative_candidates import build_collaborative_candidates
from .compose import compose_query, deterministic_compose, llm_compose
from .content import allocate, build_content_candidates
from .exploration import build_exploration
from .pipeline import build_exclusions, retrieve_candidate_sets
from .trending_candidates import build_trending_candidates

__all__ = [
    "Candidate", "ClusterCandidateSet", "AllocationPlan", "CandidateBundle",
    "compose_query", "deterministic_compose", "llm_compose",
    "build_content_candidates", "allocate", "build_exploration",
    "build_trending_candidates", "build_collaborative_candidates",
    "retrieve_candidate_sets", "build_exclusions",
]
