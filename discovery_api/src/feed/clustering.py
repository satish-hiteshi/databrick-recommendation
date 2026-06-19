"""Discovery v2 — taste CLUSTERING (V2-P2).

Group a user's engaged entities into COHERENT clusters so distinct tastes stay separate (a recent-horror
cluster and an older family-comedy cluster do NOT blend into one mush). Cluster identity is SHARED
ATTRIBUTES (genres + keywords), never a single dominant entity.

Method (simple + explainable + deterministic — V2_STRATEGY Source 1):
  1. Seed one cluster per entity's DOMINANT genre (the genre, among the entity's genres, with the highest
     GLOBAL weight in this user's profile). Genre-less entities seed a per-vertical bucket.
  2. MERGE highly-similar clusters (genre cosine + keyword cosine, same-community bonus) — keyword overlap
     refines the coarse genre grouping (e.g. folds a tiny "Action" seed into "Science Fiction" when they
     share space/war keywords).
  3. MERGE tiny clusters (size < min) into their nearest neighbour.
  4. CAP at V2_MAX_CLUSTERS (merge the closest pairs until under the cap).

Each emitted cluster exposes its top_representative_member_entity_ids (highest effective weight) — these
become the retrieval anchors/seeds in V2-P3. All thresholds/weights come from config (V2_* block).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .. import config


@dataclass(slots=True)
class EngagedEntity:
    """One engaged property (deduped across a user's engagements), with its aggregated taste weight and
    attributes. Built by taste_profile; consumed here."""
    entity_id: str
    name: str
    vertical: str
    weight: float                          # summed effective_weight across this entity's engagements
    genres: Set[str] = field(default_factory=set)     # canonical capitalisation
    keywords: Set[str] = field(default_factory=set)   # bm25 (lowercase)
    community: Optional[int] = None
    influence: Optional[float] = None
    newest_age_days: Optional[float] = None           # min age across this entity's engagements
    band: str = "older"                               # recency band of its NEWEST engagement


@dataclass(slots=True)
class TasteCluster:
    cluster_id: int
    label: str
    member_entity_ids: List[str]
    top_representative_member_entity_ids: List[str]
    dominant_vertical: str
    dominant_verticals: List[Tuple[str, float]]       # (vertical, weight) desc
    top_genres: List[Tuple[str, float]]               # (genre, weight) desc, canonical caps
    top_keywords: List[Tuple[str, float]]             # (keyword, weight) desc
    cluster_weight: float
    cluster_share: float                              # of total taste weight
    size: int
    recency_summary: Dict[str, object]                # {mean_age_days, newest_age_days, band_counts}


# ── internal mutable cluster ────────────────────────────────────────────────────

class _C:
    __slots__ = ("cid", "members")

    def __init__(self, cid: int, members: List[EngagedEntity]):
        self.cid = cid
        self.members = list(members)

    @property
    def weight(self) -> float:
        return sum(m.weight for m in self.members)


def _profile(members: List[EngagedEntity], attr: str) -> Dict[str, float]:
    """Weighted attribute → weight map over a set of members (attr = 'genres' or 'keywords')."""
    d: Dict[str, float] = defaultdict(float)
    for m in members:
        for v in getattr(m, attr):
            d[v] += m.weight
    return dict(d)


def _cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _community_mode(members: List[EngagedEntity]) -> Optional[int]:
    c = Counter(m.community for m in members if m.community is not None)
    return c.most_common(1)[0][0] if c else None


def _similarity(c1: _C, c2: _C) -> float:
    """Cluster similarity = genre cosine + keyword cosine (+ same-community bonus). Config-weighted."""
    g = _cos(_profile(c1.members, "genres"), _profile(c2.members, "genres"))
    k = _cos(_profile(c1.members, "keywords"), _profile(c2.members, "keywords"))
    sim = config.V2_CLUSTER_SIM_W_GENRE * g + config.V2_CLUSTER_SIM_W_KEYWORD * k
    m1, m2 = _community_mode(c1.members), _community_mode(c2.members)
    if m1 is not None and m1 == m2:
        sim += config.V2_CLUSTER_COMMUNITY_BONUS
    return sim


def _best_pair(clusters: List[_C]) -> Tuple[float, int, int]:
    """Max-similarity (i, j) pair, deterministic (ties → lowest indices)."""
    best = (-1.0, -1, -1)
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            s = _similarity(clusters[i], clusters[j])
            if s > best[0]:
                best = (s, i, j)
    return best


def _merge(clusters: List[_C], i: int, j: int) -> None:
    keep, drop = clusters[i], clusters[j]
    keep.cid = min(keep.cid, drop.cid)
    keep.members.extend(drop.members)
    clusters.pop(j)


def _dominant_genre(ent: EngagedEntity, global_genre_weight: Dict[str, float]) -> str:
    """The entity's genre with the highest GLOBAL profile weight (ties → alphabetical). Genre-less →
    a per-vertical sentinel so those entities still cluster coherently by vertical."""
    if not ent.genres:
        return f"·{ent.vertical}"
    return max(sorted(ent.genres), key=lambda g: global_genre_weight.get(g, 0.0))


def cluster_engaged_entities(engaged: List[EngagedEntity],
                             global_genre_weight: Dict[str, float]) -> List[TasteCluster]:
    """Cluster the engaged entities into coherent taste clusters (see module docstring)."""
    if not engaged:
        return []

    # 1. seed one cluster per dominant genre
    seeds: Dict[str, List[EngagedEntity]] = defaultdict(list)
    for ent in engaged:
        seeds[_dominant_genre(ent, global_genre_weight)].append(ent)
    clusters = [_C(cid, members) for cid, (_key, members)
                in enumerate(sorted(seeds.items()))]   # sorted → deterministic ids

    # 2. similarity merges (keyword overlap refines the genre grouping)
    while len(clusters) > 1:
        s, i, j = _best_pair(clusters)
        if s >= config.V2_CLUSTER_MERGE_THRESHOLD:
            _merge(clusters, i, j)
        else:
            break

    # 3. tiny-cluster merges (size < min → fold into nearest)
    while len(clusters) > 1:
        tiny = [c for c in clusters if len(c.members) < config.V2_CLUSTER_MIN_SIZE]
        if not tiny:
            break
        c = min(tiny, key=lambda c: (len(c.members), c.weight, c.cid))
        ci = clusters.index(c)
        tgt = max((o for o in range(len(clusters)) if o != ci),
                  key=lambda o: (_similarity(clusters[ci], clusters[o]), -clusters[o].cid))
        lo, hi = (ci, tgt) if ci < tgt else (tgt, ci)
        # merge keeps clusters[lo]; ensure the larger/target survives by ordering so 'c' folds in
        _merge(clusters, lo, hi)

    # 4. cap at MAX_CLUSTERS
    while len(clusters) > config.V2_MAX_CLUSTERS:
        _, i, j = _best_pair(clusters)
        _merge(clusters, i, j)

    total = sum(c.weight for c in clusters) or 1.0
    out = [_finalize(c, total) for c in clusters]
    out.sort(key=lambda tc: tc.cluster_weight, reverse=True)
    for new_id, tc in enumerate(out, 1):       # stable 1..n ids by weight desc
        tc.cluster_id = new_id
    return out


def _finalize(c: _C, total_weight: float) -> TasteCluster:
    members = sorted(c.members, key=lambda m: m.weight, reverse=True)
    k = config.V2_TOP_ATTRIBUTES_K

    genre_w = sorted(_profile(members, "genres").items(), key=lambda kv: (-kv[1], kv[0]))
    kw_w = sorted(_profile(members, "keywords").items(), key=lambda kv: (-kv[1], kv[0]))

    vert_w: Dict[str, float] = defaultdict(float)
    for m in members:
        vert_w[m.vertical] += m.weight
    verts = sorted(vert_w.items(), key=lambda kv: (-kv[1], kv[0]))

    ages = [m.newest_age_days for m in members if m.newest_age_days is not None]
    wsum = sum(m.weight for m in members) or 1.0
    mean_age = sum((m.newest_age_days or 0.0) * m.weight for m in members) / wsum
    recency = {
        "mean_age_days": round(mean_age, 2),
        "newest_age_days": round(min(ages), 2) if ages else None,
        "band_counts": dict(Counter(m.band for m in members)),
    }

    top_genres = [g for g in genre_w if not g[0].startswith("·")][:k]
    label = " + ".join(g for g, _ in top_genres[:2]) if top_genres else verts[0][0].title()

    return TasteCluster(
        cluster_id=c.cid,
        label=label,
        member_entity_ids=[m.entity_id for m in members],
        top_representative_member_entity_ids=[m.entity_id for m in members[:config.V2_CLUSTER_TOP_MEMBERS]],
        dominant_vertical=verts[0][0],
        dominant_verticals=[(v, round(w, 4)) for v, w in verts],
        top_genres=[(g, round(w, 4)) for g, w in top_genres],
        top_keywords=[(kw, round(w, 4)) for kw, w in kw_w[:k]],
        cluster_weight=round(c.weight, 4),
        cluster_share=round(c.weight / total_weight, 4),
        size=len(members),
        recency_summary=recency,
    )
