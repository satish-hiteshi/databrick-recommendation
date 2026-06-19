"""NewInGenre — fresh moments from unfollowed properties, TAGGED by the property's genre, for the
"New in <genre>" carousels. Genre source: entity.canonical_genres for game/movie/tv; podcast_categories
for podcasts (their canonical_genres are empty). Carries cold-start (global fresh, genre-grouped).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .base import (Candidate, CandidateProvider, RequestContext, _moment_candidate,
                   excluded_entity_ids, select_fresh_moments)
from ..feed.profile import UserProfile


class NewInGenre(CandidateProvider):
    name = "new_in_genre"

    def _genres_of(self, entity_id: str) -> List[str]:
        ent = self.ds.get_entity(entity_id)
        if not ent:
            return []
        return self.ds.get_podcast_categories(entity_id) if ent.vertical == "podcast" else ent.canonical_genres

    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        excl = excluded_entity_ids(profile, context, self.ds)
        picked = select_fresh_moments(self.ds, context, excl, limit=context.limit, vertical=context.vertical)
        out: List[Candidate] = []
        for m, rec in picked:
            out.append(_moment_candidate(self.ds, m, rec, self.name, self.popularity,
                                         extra={"genres": self._genres_of(m.entity_id)}))
        return out

    def group_by_genre(self, profile: UserProfile, context: RequestContext) -> Dict[str, List[Candidate]]:
        """{genre: [candidates]} — the per-carousel grouping the P5 assembler will shape."""
        groups: Dict[str, List[Candidate]] = defaultdict(list)
        for c in self.generate(profile, context):
            for g in c.raw_signals.get("genres", []):
                groups[g].append(c)
        return dict(groups)
