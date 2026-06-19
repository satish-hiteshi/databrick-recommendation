"""Discovery v2 — EXPLORATION via STRUCTURED ADJACENCY (Source 3).

Exploration candidates SHARE some of the profile's top attributes but INTRODUCE a new one — graph-defined,
NOT random. Two rules:
  A. shared_genre_new_community : /graph/structured on a top profile genre, keep hits in a DIFFERENT graph
                                  community than the user's (shares the genre, sits in an unexplored region).
  B. neighbor_new_genre         : /graph/similar from a cluster's top representative member, keep hits that
                                  introduce a genre NOT in the profile (shares the neighbourhood, adds a genre).

Sized by EXPLORATION_FRACTION = f(signal_strength) (the caller passes explore_slots). Every candidate is
tagged (source_pool="exploration", adjacency_rule, shared_attrs, new_attrs) so the future feedback loop can
learn which explorations convert. HARD exclusions (followed/engaged/seen/excluded + content ids) applied.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .. import config
from ..data_access.substrate_client import SubstrateClient, run_concurrent
from .candidates import Candidate

RULE_A = "shared_genre_new_community"
RULE_B = "neighbor_new_genre"


def build_exploration(profile, client: SubstrateClient, exclude_ids: Set[str], explore_slots: int
                      ) -> Tuple[List[Candidate], int]:
    """Return (exploration_candidates, n_substrate_calls). Candidates are adjacent-not-identical and exclude
    everything in exclude_ids (followed/engaged/seen/excluded/content)."""
    if explore_slots <= 0 or not profile.clusters:
        return [], 0

    profile_genres_l: Set[str] = {g.lower() for g in profile.genre_weights}
    profile_comms: Set[int] = {c for c, _ in profile.community_support}
    top_genres = [g for g, _ in sorted(profile.genre_weights.items(), key=lambda kv: -kv[1])][
        :config.V2_EXPLORE_TOP_GENRES]

    # ── retrieval tasks (parallel) ──
    tasks: Dict[tuple, callable] = {}
    for g in top_genres:
        tasks[("A", g)] = (lambda g=g: client.graph_structured(genre=[g], top_k=config.V2_EXPLORE_PER_RULE_K))
    for c in profile.clusters:
        for seed in c.top_representative_member_entity_ids[:1]:
            tasks[("B", seed)] = (lambda s=seed: client.graph_similar(s, top_k=config.V2_EXPLORE_PER_RULE_K))
    results = run_concurrent(tasks, max_workers=config.SUBSTRATE_MAX_WORKERS)
    n_calls = len(tasks)

    # ── collect raw candidate ids with their origin ──
    a_origin: Dict[str, str] = {}    # eid -> genre that retrieved it (rule A)
    b_origin: Dict[str, str] = {}    # eid -> seed that retrieved it (rule B)
    raw_meta: Dict[str, dict] = {}   # eid -> {name, vertical}
    for (rule, key), items in results.items():
        for it in (items or []):
            eid = it.get("entity_id")
            if not eid or eid in exclude_ids:
                continue
            raw_meta.setdefault(eid, {"name": it.get("name", "") or "", "vertical": it.get("vertical") or ""})
            if rule == "A":
                a_origin.setdefault(eid, key)
            else:
                b_origin.setdefault(eid, key)

    ids = list(raw_meta)
    if not ids:
        return [], n_calls
    attrs = client.graph_score_within(ids)   # {eid: {genres(lowercase), community, influence, ...}}
    n_calls += 1

    # ── apply adjacency acceptance (shared >= MIN_SHARED AND new >= MIN_NEW) ──
    out: List[Candidate] = []
    for eid in ids:
        a = attrs.get(eid)
        if not a:
            continue
        cand_genres_l = {str(x).lower() for x in (a.get("genres") or [])}
        community = a.get("community")
        influence = float(a.get("influence") or 0.0)
        name = raw_meta[eid]["name"] or a.get("name", "")
        vertical = raw_meta[eid]["vertical"] or a.get("vertical", "")

        # Rule A — shares a top genre, lands in a NEW community
        if eid in a_origin:
            g = a_origin[eid]
            shared = [g] if g.lower() in cand_genres_l else []
            if (community is not None and community not in profile_comms
                    and len(shared) >= config.V2_EXPLORE_MIN_SHARED):
                out.append(Candidate(entity_id=eid, name=name, vertical=vertical, score=round(influence, 6),
                                     source_pool="exploration", adjacency_rule=RULE_A,
                                     shared_attrs=shared, new_attrs=[f"community:{community}"],
                                     path_scores={"graph_structured": round(influence, 6)},
                                     paths=["graph_structured"]))
                continue

        # Rule B — shares profile genres, INTRODUCES a new genre
        if eid in b_origin:
            shared = sorted(cand_genres_l & profile_genres_l)
            new = sorted(cand_genres_l - profile_genres_l)
            if len(shared) >= config.V2_EXPLORE_MIN_SHARED and len(new) >= config.V2_EXPLORE_MIN_NEW:
                out.append(Candidate(entity_id=eid, name=name, vertical=vertical, score=round(influence, 6),
                                     source_pool="exploration", adjacency_rule=RULE_B,
                                     shared_attrs=shared, new_attrs=new, seed_entity_id=b_origin[eid],
                                     path_scores={"graph_similar": round(influence, 6)},
                                     paths=["graph_similar"]))

    out.sort(key=lambda c: (-c.score, c.entity_id))
    return out[:explore_slots], n_calls
