"""FollowedMoments — the MAIN-STREAM candidate source (E3-new).

Generates the RAW candidate pool: every moment of the user's actively-followed properties, gathered by
graph traversal (the inverse of E2's pools, which EXCLUDE followed properties). No suppression, no cap,
no ranking here — those are applied by candidate_pool. The loaded moments are already the published
set (Step 0), so there is no status filter at traversal.
"""

from __future__ import annotations

from typing import Iterable, List

from ..candidate import CandidateMoment
from ..graph_moments import GraphMoments


def generate_followed_candidates(followed_property_ids: Iterable[int],
                                 graph: GraphMoments) -> List[CandidateMoment]:
    """Raw candidate moments from followed properties only (the inverse-gate, applied at generation).

    Properties that yield no moments contribute nothing — an empty followed set returns []."""
    return graph.moments_for_properties(followed_property_ids)
