"""Discovery v2 — COLLABORATIVE FILTERING index (V2-P9, Source 4). The taste NEIGHBORHOOD + similar-user affinity.

MIRRORS ranking/trending.py — where the trending table aggregates GLOBAL engagement velocity, this aggregates
SIMILAR-USER engagement affinity:
  trending:      scope GLOBAL trending → to the user's taste → niche-relative confidence → adaptive blend.
  collaborative: find SIMILAR-taste users → aggregate THEIR engagement → niche-relative confidence → adaptive blend.

THE BUBBLE-ESCAPE: content retrieval (taste) and trending can only surface things related to the user's existing
taste attributes. Collaborative escapes that: it finds users whose taste profile is similar to THIS user's, then
surfaces what THOSE users engage with that this user has NOT — INCLUDING content that shares NO attributes with
the user's taste (the classic "horror fans who also love this strategy game"). Content similarity can never find
that link; behavioral overlap can. This is the highest-value discovery source.

ENDORSEMENT-GATED, NOT taste-gated (the critical difference from trending): an item surfaces because similar
users endorse it (neighbor affinity + a minimum distinct-endorser count), NOT because it matches the target's
genres. It is NEVER re-filtered down to the user's taste attributes — that would collapse it back into the
content bubble and defeat the purpose.

NICHE-RELATIVE + LOW THRESHOLD (the V2-P8 lesson): a neighborhood of even a FEW genuinely-similar users is a real
signal. Confidence scales with neighborhood DENSITY (sum of neighbor similarities) and activates at a LOW absolute
threshold (config) — niche tastes get collaborative recommendations too, not just mainstream.

PRECOMPUTED + CACHED per `now` (like the trending table). SCALING SEAM (documented, NOT over-built): the neighbor
search is a direct cosine over users sharing ≥1 genre (a genre inverted-index prunes the scan); at very large user
counts this moves to a precomputed/indexed similarity (LSH/ANN over taste vectors, or a similar-user graph).
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .. import config
from ..data_access.base import DataSource


def _decay(age_seconds: float, halflife_seconds: float) -> float:
    if halflife_seconds <= 0:
        return 1.0 if age_seconds <= 0 else 0.0
    return math.pow(0.5, max(0.0, age_seconds) / halflife_seconds)


def _cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine over two sparse weight maps (taste-profile similarity). 0 if no shared key."""
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class UserVector:
    """One user's recency-decayed taste signature + their engaged set (the neighbor aggregation source)."""
    user_id: int
    genre_w: Dict[str, float]            # lowercased genre -> decayed weight
    keyword_w: Dict[str, float]          # lowercased keyword -> decayed weight
    entities: Dict[str, float]           # entity_id -> decayed engagement weight (this user's engaged set)
    mass: float                          # total decayed engagement weight (volume)


@dataclass
class Neighborhood:
    """The target's taste neighborhood + the similar-user affinity it endorses (the collaborative signal)."""
    n_neighbors: int
    mass: float                                  # sum of neighbor similarities (DENSITY → drives confidence)
    confidence: float                            # niche-relative, LOW-threshold [0,1] → adaptive w_collaborative
    affinity: Dict[str, float] = field(default_factory=dict)    # entity_id -> niche-relative collaborative score [0,1]
    endorsers: Dict[str, int] = field(default_factory=dict)     # entity_id -> distinct neighbor count (provenance + gate)
    neighbor_ids: List[Tuple[int, float]] = field(default_factory=list)   # (uid, similarity) desc — provenance


class CollaborativeIndex:
    """Precomputed, cached per-`now` user-taste vectors + neighbor search + neighborhood aggregation."""

    def __init__(self, data_source: DataSource, clock=time.time):
        self.ds = data_source
        self._clock = clock
        self._cache: Dict[str, dict] = {}

    # ── build (cached per `now` + refresh cadence; mirrors TrendingTable.ensure) ──
    def ensure(self, now: datetime) -> dict:
        key = now.isoformat()
        ent = self._cache.get(key)
        if ent is not None and (self._clock() - ent["built_wall"]) < config.V2_COLLAB_REFRESH_SECONDS:
            return ent
        ent = self._compute(now)
        ent["built_wall"] = self._clock()
        self._cache[key] = ent
        return ent

    def _compute(self, now: datetime) -> dict:
        hl = config.V2_COLLAB_HALFLIFE_DAYS * 86400.0
        # 1) group ALL users' engagement (follows + reactions) into recency-decayed per-user entity weights
        per_user_ent: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for ev in self.ds.iter_reaction_events():
            if ev.created_at is None or not ev.entity_id:
                continue
            age = (now - ev.created_at).total_seconds()
            if age < 0:
                continue
            per_user_ent[ev.user_id][ev.entity_id] += config.V2_BASE_WEIGHT_REACTION * _decay(age, hl)
        for fe in self.ds.iter_follow_events():
            if fe.created_at is None or not fe.entity_id:
                continue
            age = (now - fe.created_at).total_seconds()
            if age < 0:
                continue
            per_user_ent[fe.user_id][fe.entity_id] += config.V2_BASE_WEIGHT_FOLLOW * _decay(age, hl)

        # 2) per-entity attribute cache (genres + keywords; podcasts fall back to categories) — fetched once
        attr_cache: Dict[str, Tuple[frozenset, frozenset]] = {}

        def attrs(eid: str) -> Tuple[frozenset, frozenset]:
            a = attr_cache.get(eid)
            if a is None:
                e = self.ds.get_entity(eid)
                if e is None:
                    a = (frozenset(), frozenset())
                else:
                    genres = e.canonical_genres
                    if not genres and e.vertical == "podcast":
                        genres = self.ds.get_podcast_categories(eid)
                    a = (frozenset(g.lower() for g in genres), frozenset(k.lower() for k in e.bm25_keywords))
                attr_cache[eid] = a
            return a

        # 3) build each user's taste vector + a genre inverted-index (prunes the neighbor scan at scale)
        vectors: Dict[int, UserVector] = {}
        genre_index: Dict[str, List[int]] = defaultdict(list)
        for uid, ent_w in per_user_ent.items():
            gw: Dict[str, float] = defaultdict(float)
            kw: Dict[str, float] = defaultdict(float)
            mass = 0.0
            for eid, w in ent_w.items():
                gset, kset = attrs(eid)
                for g in gset:
                    gw[g] += w
                for k in kset:
                    kw[k] += w
                mass += w
            vectors[uid] = UserVector(uid, dict(gw), dict(kw), dict(ent_w), round(mass, 6))
            for g in gw:
                genre_index[g].append(uid)
        return {"vectors": vectors, "genre_index": dict(genre_index), "n_users": len(vectors)}

    # ── target vector (built from the user's OWN profile — same representation as neighbors) ──
    def target_vector(self, profile) -> UserVector:
        gw = {g.lower(): w for g, w in profile.genre_weights.items()}
        kw = {k.lower(): w for k, w in profile.keyword_weights.items()}
        ent = {e.target_entity_id: 1.0 for e in profile.engagements}
        return UserVector(profile.user_id if profile.user_id is not None else -1, gw, kw, ent, float(len(ent)))

    # ── neighbor search (taste-profile cosine; LOW similarity floor; pruned by shared genre) ──
    def neighbors(self, target: UserVector, now: datetime,
                  exclude_user_id: Optional[int] = None) -> List[Tuple[int, float]]:
        t = self.ensure(now)
        vectors = t["vectors"]
        gindex = t["genre_index"]
        cand: set = set()
        for g in target.genre_w:                       # SCALE: only users sharing ≥1 genre can be similar
            cand.update(gindex.get(g, ()))
        wg, wk = config.V2_COLLAB_SIM_W_GENRE, config.V2_COLLAB_SIM_W_KEYWORD
        out: List[Tuple[int, float]] = []
        for uid in cand:
            if uid == exclude_user_id:
                continue
            v = vectors[uid]
            sim = wg * _cos(target.genre_w, v.genre_w) + wk * _cos(target.keyword_w, v.keyword_w)
            if sim >= config.V2_COLLAB_SIM_MIN:
                out.append((uid, round(sim, 6)))
        out.sort(key=lambda kv: -kv[1])
        return out[:config.V2_COLLAB_MAX_NEIGHBORS]

    # ── neighborhood aggregation (the similar-user affinity; the collaborative signal) ──
    def neighborhood(self, profile, now: datetime, exclude_ids: set) -> Neighborhood:
        """For `profile`'s target user, return the taste neighborhood + the affinity it endorses, with
        already-known content (exclude_ids = engaged ∪ excluded properties) removed. NICHE-RELATIVE
        normalisation + LOW-threshold confidence (NOT global user volume). Cross-attribute by design —
        NEVER re-filtered to the target's taste attributes."""
        target = self.target_vector(profile)
        nbrs = self.neighbors(target, now, exclude_user_id=target.user_id)
        if not nbrs:
            return Neighborhood(0, 0.0, 0.0)
        vectors = self.ensure(now)["vectors"]
        mass = sum(s for _, s in nbrs)
        conf = (min(1.0, mass / config.V2_COLLAB_CONFIDENCE_FULL)
                if config.V2_COLLAB_CONFIDENCE_FULL > 0 else 0.0)
        if conf > 0 and config.V2_COLLAB_CONF_EXPONENT != 1.0:
            conf = conf ** config.V2_COLLAB_CONF_EXPONENT

        # aggregate neighbor engagement, weighted by each neighbor's similarity (their own decayed weight too)
        affinity: Dict[str, float] = defaultdict(float)
        endorsers: Dict[str, int] = defaultdict(int)
        for uid, sim in nbrs:
            for eid, w in vectors[uid].entities.items():
                if eid in exclude_ids:                 # NEVER recommend already-followed/engaged/excluded
                    continue
                affinity[eid] += sim * w
                endorsers[eid] += 1
        # ENDORSEMENT gate (not a taste gate): need ≥ MIN_ENDORSERS distinct neighbors → not a single-user fluke
        kept = {e: a for e, a in affinity.items() if endorsers[e] >= config.V2_COLLAB_MIN_ENDORSERS}
        if not kept:
            return Neighborhood(len(nbrs), round(mass, 4), round(conf, 4), neighbor_ids=nbrs[:20])
        amax = max(kept.values()) or 1.0              # niche-relative: normalise WITHIN the neighborhood's affinity
        norm = {e: round(a / amax, 6) for e, a in kept.items()}
        return Neighborhood(len(nbrs), round(mass, 4), round(conf, 4), norm,
                            {e: endorsers[e] for e in norm}, nbrs[:20])

    def debug(self, profile, now: datetime, exclude_ids=frozenset()) -> dict:
        nb = self.neighborhood(profile, now, set(exclude_ids))
        return {"n_neighbors": nb.n_neighbors, "neighborhood_mass": nb.mass, "confidence": nb.confidence,
                "n_endorsed": len(nb.affinity),
                "top": sorted(nb.affinity.items(), key=lambda kv: -kv[1])[:5]}
