"""PopularWithFansOf — "fans of X also like…" around the user's followed/reacted entities.

Personalized; EMPTY for cold-start. Two signals, merged + deduped:
  - similarity: graph_similar() neighbours for game/movie/tv seeds; vector_neighbors() for PODCAST seeds
    (the graph has no podcast similarity).
  - co-follow (collaborative): other users who follow the same property → THEIR other followed properties.

PERF (P5.1): the per-seed substrate calls (one /graph/similar or /api/neighbors per seed) are fired
CONCURRENTLY via run_concurrent — but results are assembled back in the ORIGINAL seed order, so the
candidate set + dedupe-first ordering + scores are byte-identical to the old serial path. Only wall-time
changes. (/graph/similar is single-id with no batch endpoint, so parallelise; calls/seed are deduped by key.)
"""

from __future__ import annotations

from typing import List

from .base import Candidate, CandidateProvider, RequestContext, dedupe, excluded_entity_ids
from ..data_access import run_concurrent
from ..feed.profile import UserProfile


class PopularWithFansOf(CandidateProvider):
    name = "popular_with_fans_of"

    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        seeds = profile.personalization_seed_ids
        if not seeds:
            return []                                   # cold-start → empty
        excl = excluded_entity_ids(profile, context, self.ds)
        exclude_ids = list(excl | set(seeds))
        out: List[Candidate] = []

        # ── similarity (graph for game/movie/tv, vector for podcast) — fired CONCURRENTLY ────
        if self.substrate is not None:
            ordered = []                                # (eid, vertical) in SEED ORDER → identical assembly
            tasks = {}
            for eid in seeds:
                ent = self.ds.get_entity(eid)
                if not ent:
                    continue
                ordered.append((eid, ent.vertical))
                if ent.vertical == "podcast":
                    tasks[eid] = (lambda e=eid: self.substrate.vector_neighbors(
                        [e], exclude_ids=exclude_ids, vertical="podcast", top_k=context.limit))
                else:
                    tasks[eid] = (lambda e=eid, v=ent.vertical: self.substrate.graph_similar(
                        e, top_k=context.limit, vertical=v))
            results = run_concurrent(tasks)             # {eid: list|None}; SubstrateError → None (graceful skip)
            for eid, vertical in ordered:               # ORIGINAL seed order → identical dedupe-first set
                if vertical == "podcast":
                    for n in (results.get(eid) or []):
                        ne = n.get("entity_id")
                        if ne and ne not in excl:
                            out.append(Candidate(self.name, entity_id=ne, vertical=n.get("vertical"),
                                property_id=self.ds.entity_id_to_property_id(ne),
                                raw_signals={"semantic": n.get("score"), "via": "vector(podcast)", "seed": eid}))
                else:
                    for r in (results.get(eid) or []):
                        ne = r.get("entity_id")
                        if ne and ne not in excl:
                            out.append(Candidate(self.name, entity_id=ne, vertical=r.get("vertical"),
                                property_id=self.ds.entity_id_to_property_id(ne),
                                raw_signals={"graph_similar": r.get("final_score", r.get("score")),
                                             "via": "graph_similar", "seed": eid}))

        # ── co-follow (collaborative filtering over follows_dev) — local CSV, unchanged ──
        cofollow: dict = {}
        for pid in profile.followed_property_ids:
            for other_uid in self.ds.get_followers_of_property(pid):
                if other_uid == profile.user_id:
                    continue
                for opid in self.ds.get_followed_property_ids(other_uid):
                    oeid = self.ds.property_id_to_entity_id(opid)
                    if oeid and oeid not in excl:
                        cofollow[oeid] = cofollow.get(oeid, 0) + 1
        for oeid, cnt in cofollow.items():
            ent = self.ds.get_entity(oeid)
            out.append(Candidate(self.name, entity_id=oeid, vertical=(ent.vertical if ent else None),
                property_id=self.ds.entity_id_to_property_id(oeid),
                raw_signals={"co_follow_count": cnt, "via": "co_follow",
                             "influence_norm": (self.popularity.normalized_influence(oeid)
                                                if self.popularity else None)}))
        return dedupe(out)[:context.limit]
