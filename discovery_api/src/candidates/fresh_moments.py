"""FreshMoments — the MAIN-FEED candidate source: recent moments (soft-recency on event_starts_at) from
UNFOLLOWED/allowed properties, with the PER-PROPERTY MOMENT CAP applied (episode-heavy podcasts can't
flood). Carries cold-start (it's global fresh content minus what the user follows).
"""

from __future__ import annotations

from typing import List

from .base import (Candidate, CandidateProvider, RequestContext, _moment_candidate,
                   excluded_entity_ids, select_fresh_moments)
from ..feed.profile import UserProfile


class FreshMoments(CandidateProvider):
    name = "fresh_moments"

    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        excl = excluded_entity_ids(profile, context, self.ds)
        picked = select_fresh_moments(self.ds, context, excl, limit=context.limit, vertical=context.vertical)
        return [_moment_candidate(self.ds, m, rec, self.name, self.popularity) for m, rec in picked]
