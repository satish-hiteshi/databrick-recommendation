"""SimilarToFollowed — vector neighbours of the user's followed/reacted entities, PER VERTICAL.

Personalized; EMPTY for cold-start (no seeds). Uses the vector substrate for ALL verticals — and it is
the ONLY similarity path for PODCAST seeds (the graph returns no_graph_signal for podcasts).

PERF (P5.1): the one-call-per-vertical requests (/api/neighbors already batches all of a vertical's
seeds into a single anchor list) are fired CONCURRENTLY across verticals, then assembled back in the
original vertical order — identical candidate set + scores, only faster.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List

from .base import Candidate, CandidateProvider, RequestContext, dedupe, excluded_entity_ids
from ..data_access import run_concurrent
from ..feed.profile import UserProfile


class SimilarToFollowed(CandidateProvider):
    name = "similar_to_followed"

    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        seeds = profile.personalization_seed_ids
        if not seeds or self.substrate is None:
            return []                                   # cold-start (or no substrate) → empty
        excl = excluded_entity_ids(profile, context, self.ds)
        exclude_ids = list(excl | set(seeds))
        by_vertical = defaultdict(list)
        for eid in seeds:
            ent = self.ds.get_entity(eid)
            if ent:
                by_vertical[ent.vertical].append(eid)

        # one /api/neighbors call PER VERTICAL (multi-anchor), fired CONCURRENTLY
        tasks = {v: (lambda vs=vseeds, vert=v: self.substrate.vector_neighbors(
                    anchor_ids=vs, exclude_ids=exclude_ids, vertical=vert, top_k=context.limit))
                 for v, vseeds in by_vertical.items()}
        results = run_concurrent(tasks)                 # {vertical: list|None}; SubstrateError → None

        out: List[Candidate] = []
        for vertical in by_vertical:                    # ORIGINAL vertical order → identical assembly
            for n in (results.get(vertical) or []):
                eid = n.get("entity_id")
                if not eid or eid in excl:
                    continue
                out.append(Candidate(
                    source_pool=self.name, entity_id=eid, vertical=n.get("vertical"),
                    property_id=self.ds.entity_id_to_property_id(eid),
                    raw_signals={"semantic": n.get("score"), "via": "vector_neighbors",
                                 "seed_vertical": vertical,
                                 "influence_norm": (self.popularity.normalized_influence(eid)
                                                    if self.popularity else None)}))
        return dedupe(out)[:context.limit]
