"""NewOnPlatform — fresh moments from unfollowed properties, TAGGED by media_platform, for the
"New on <platform>" carousels. Platforms come from the moment's media_platform_id AND its CTAs
(public_moment_ctas carries region_id + media_platform_id, so one moment can be on several platforms).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .base import (Candidate, CandidateProvider, RequestContext, _moment_candidate,
                   excluded_entity_ids, select_fresh_moments)
from ..data_access.records import Moment
from ..feed.profile import UserProfile


class NewOnPlatform(CandidateProvider):
    name = "new_on_platform"

    def _platform_ids(self, m: Moment) -> List[int]:
        plats = set()
        if m.media_platform_id is not None:
            plats.add(m.media_platform_id)
        for cta in self.ds.get_ctas_for_moment(m.moment_id):
            if cta.media_platform_id is not None:
                plats.add(cta.media_platform_id)
        return sorted(plats)

    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        excl = excluded_entity_ids(profile, context, self.ds)
        picked = select_fresh_moments(self.ds, context, excl, limit=context.limit, vertical=context.vertical)
        lk = self.ds.lookups()
        out: List[Candidate] = []
        for m, rec in picked:
            pids = self._platform_ids(m)
            out.append(_moment_candidate(self.ds, m, rec, self.name, self.popularity,
                extra={"platform_ids": pids,
                       "platform_names": [n for n in (lk.media_platform(p) for p in pids) if n]}))
        return out

    def group_by_platform(self, profile: UserProfile, context: RequestContext) -> Dict[int, List[Candidate]]:
        """{media_platform_id: [candidates]} — the per-carousel grouping the P5 assembler will shape."""
        groups: Dict[int, List[Candidate]] = defaultdict(list)
        for c in self.generate(profile, context):
            for p in c.raw_signals.get("platform_ids", []):
                groups[p].append(c)
        return dict(groups)
