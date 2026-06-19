"""Discovery v2 — TRENDING AS A FIRST-CLASS CANDIDATE SOURCE (V2-P8).

THE FIX: before V2-P8, trending was only a moment-level tiebreaker INSIDE taste-selected properties — a
trending moment in a property the taste path did not pick could never surface. Here, global trending moments
(ranking.trending — recency-decayed engagement VELOCITY across ALL users) are SCOPED to the user's taste
(per cluster) and emitted as candidates DIRECTLY, independent of whether the taste-retrieval path selected
their parent property. Trending now GENERATES candidates, not just orders them.

NICHE-RELATIVE BY DESIGN (built for scale, not for dev thinness): velocities are RAW (engagement only — no
global normalisation, no publish-date assumption) and are normalised WITHIN the user's taste niche, so a few
users surging on niche content is a real signal there — it does NOT need mainstream/global volume to register.
The confidence gate triggers at a LOW absolute threshold (config).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .. import config
from .candidates import Candidate


def _cluster_match(cluster, genres_l: set, keywords_l: set, vertical: str) -> float:
    """Taste overlap of a property with a cluster in [0,1]: genre + keyword overlap (cluster sim weights),
    plus a same-vertical bonus. Mirrors how the taste clusters themselves were formed."""
    cg = {g.lower(): w for g, w in cluster.top_genres}
    ck = {k.lower() for k, _ in cluster.top_keywords}
    if cg:
        top_w = max(cg.values())
        major = {g for g, w in cg.items() if w >= config.V2_TREND_GENRE_MIN_FRACTION * top_w}
        if not (genres_l & major):
            return 0.0                   # must share a MAJOR (primary) cluster genre, not a co-occurring secondary
        gov = sum(cg[g] for g in genres_l if g in cg) / (sum(cg.values()) or 1.0)   # weighted genre overlap
    else:
        gov = 0.0
    kov = (len(keywords_l & ck) / len(ck)) if ck else 0.0
    score = config.V2_CLUSTER_SIM_W_GENRE * gov + config.V2_CLUSTER_SIM_W_KEYWORD * kov
    if vertical and vertical == cluster.dominant_vertical:
        score += 0.10
    return min(1.0, score)


def _attrs(ds, eid: str, vertical: str):
    e = ds.get_entity(eid)
    genres = ds.get_podcast_categories(eid) if (e and vertical == "podcast") else (e.canonical_genres if e else [])
    keywords = e.bm25_keywords if e else []
    return {g.lower() for g in genres}, {k.lower() for k in keywords}


def build_trending_candidates(profile, trending, ds, now: datetime, exclude_ids: set
                              ) -> Tuple[Dict[int, List[Candidate]], float, Dict[int, float], List[Candidate]]:
    """Returns (per_cluster_candidates, niche_confidence, moment_velocity, flat_candidates).
       - per_cluster_candidates: {cluster_id: [trending Candidate]} → merged into the bundle's clusters.
       - niche_confidence [0,1]: drives the adaptive w_trending (LOW absolute activation threshold).
       - moment_velocity: {moment_id: niche-relative velocity [0,1]} → the blend's trending term.
       - flat_candidates: trending candidates ranked by velocity → the TRENDING carousel.
    Excludes followed/engaged/excluded properties (exclude_ids). seen_ids are moment-level (applied downstream)."""
    if trending is None or not profile.clusters:
        return {}, 0.0, {}, []
    scanned = trending.top_moments(now, config.V2_TREND_CAND_SCAN)   # [(moment_id, raw_velocity)] desc
    if not scanned:
        return {}, 0.0, {}, []

    # 1) map each scanned trending moment to a taste-matched property + cluster
    matched_prop: Dict[str, Tuple[Optional[int], float]] = {}   # entity_id -> (best_cluster_id|None, match)
    scope_moments: Dict[int, float] = {}                        # moment_id -> raw velocity (matched props only)
    prop_best: Dict[str, Tuple[int, float]] = {}               # entity_id -> (best_moment_id, best_raw)
    for mid, raw in scanned:
        m = ds.get_moment(mid)
        if not m or not m.entity_id or m.entity_id in exclude_ids:
            continue
        eid = m.entity_id
        if eid not in matched_prop:
            e = ds.get_entity(eid)
            if not e:
                matched_prop[eid] = (None, 0.0)
                continue
            genres_l, keywords_l = _attrs(ds, eid, e.vertical)
            best_cid, best_match = None, 0.0
            for c in profile.clusters:
                mt = _cluster_match(c, genres_l, keywords_l, e.vertical)
                if mt > best_match:
                    best_match, best_cid = mt, c.cluster_id
            matched_prop[eid] = (best_cid, best_match) if (best_cid is not None and best_match >= config.V2_TREND_MATCH_MIN) else (None, 0.0)
        cid, _ = matched_prop[eid]
        if cid is None:
            continue
        scope_moments[mid] = raw
        if eid not in prop_best or raw > prop_best[eid][1]:
            prop_best[eid] = (mid, raw)

    if not scope_moments:
        return {}, 0.0, {}, []

    # 2) niche-relative normalisation + confidence (NOT global volume; LOW threshold; sensitive exponent)
    scope_max = max(scope_moments.values())
    scope_mass = sum(scope_moments.values())
    conf = (min(1.0, scope_mass / config.V2_TREND_TASTE_CONFIDENCE_FULL)
            if config.V2_TREND_TASTE_CONFIDENCE_FULL > 0 else 0.0)
    if conf > 0 and config.V2_TREND_CONF_EXPONENT != 1.0:
        conf = conf ** config.V2_TREND_CONF_EXPONENT
    moment_velocity = {mid: (raw / scope_max if scope_max else 0.0) for mid, raw in scope_moments.items()}

    # 3) one trending Candidate per matched property (its strongest trending moment)
    per_cluster: Dict[int, List[Candidate]] = defaultdict(list)
    for eid, (mid, _raw) in prop_best.items():
        cid, match = matched_prop[eid]
        e = ds.get_entity(eid)
        per_cluster[cid].append(Candidate(
            entity_id=eid, name=(e.name if e else eid), vertical=(e.vertical if e else ""),
            score=round(match, 6), source_pool="trending", cluster_id=cid, paths=["trending"],
            trending_velocity=round(moment_velocity.get(mid, 0.0), 6), best_trending_moment_id=mid))

    flat: List[Candidate] = []
    for cid, cands in per_cluster.items():
        cands.sort(key=lambda c: -c.trending_velocity)
        per_cluster[cid] = cands[:config.V2_TREND_CANDIDATE_MAX]
        flat.extend(per_cluster[cid])
    flat.sort(key=lambda c: -c.trending_velocity)
    return dict(per_cluster), round(conf, 4), moment_velocity, flat
