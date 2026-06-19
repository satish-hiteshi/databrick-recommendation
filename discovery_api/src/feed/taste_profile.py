"""Discovery v2 — ENGAGEMENT LOG + TIME-DECAYED, CLUSTERED TASTE PROFILE (V2-P2, Source 1).

ADDITIVE: this is the v2 personalization heart and does NOT touch v1's profile.py. v1's UserProfile
stays the working baseline; this TasteProfile is the richer, recency-aware, clustered alternative.

Pipeline (all knobs in config.V2_* — no magic numbers here):
  build_engagement_log(user_id, now) -> [Engagement]   # signal-agnostic; follows + reactions, timestamped
  build_taste_profile(user_id, now)  -> TasteProfile    # decay + bands + attribute aggregation
                                                        #   + vertical % (smoothed) + taste clusters

Attributes come from the CSVs (entities_dev: canonical_genres + bm25_keywords; gds_signals: influence +
community) — NEVER per-entity graph/vector calls (those belong to retrieval, V2-P3). Cast is NOT in the
production graph (deferred); themes are sparse (not primary). Genres + keywords are the rich signals.

Cold-start (no resolved signal) returns a clean empty/low-confidence profile so the caller falls back to
the global feed.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .. import config
from ..data_access.base import DataSource
from .clustering import EngagedEntity, TasteCluster, cluster_engaged_entities

# ── signal types (the engagement log is signal-agnostic) ─────────────────────────
SIGNAL_FOLLOW = "follow"
SIGNAL_REACTION = "reaction"
# ── EXTENSION POINT — future signal types (NOT built now) ────────────────────────
# The log accepts any signal_type with its own base weight; nothing downstream changes. To add one:
#   (1) add a V2_BASE_WEIGHT_<X> in config, (2) register it in _BASE_WEIGHTS below, (3) append a loader
#   in build_engagement_log that yields make_engagement(eid, "<x>", ts, now). Planned (dormant):
#     SIGNAL_DWELL = "dwell"                     # high-volume implicit interest (RudderStack dwell events;
#                                                #   keyed by Frontegg UUID → needs user-id resolution)
#     SIGNAL_NOT_INTERESTED = "not_interested"   # explicit negative (suppression), dormant until instrumented
_BASE_WEIGHTS = {
    SIGNAL_FOLLOW: lambda: config.V2_BASE_WEIGHT_FOLLOW,
    SIGNAL_REACTION: lambda: config.V2_BASE_WEIGHT_REACTION,
}


def _base_weight(signal_type: str) -> float:
    fn = _BASE_WEIGHTS.get(signal_type)
    return fn() if fn else 1.0


# ── decay + band helpers ─────────────────────────────────────────────────────────

def _decay(age_seconds: Optional[float], halflife_seconds: float) -> float:
    """Exponential recency decay: 0.5 ** (age / half_life). Future-dated (negative age) clamps to 1.0;
    unknown timestamp → a small flat floor (config). Recent engagement outweighs old."""
    if age_seconds is None:
        return config.V2_UNKNOWN_TS_DECAY
    a = max(0.0, age_seconds)
    if halflife_seconds <= 0:
        return 1.0 if a == 0 else 0.0
    return math.pow(0.5, a / halflife_seconds)


def _band(age_seconds: Optional[float]) -> str:
    """Disjoint recency band for the explainability view — each engagement in EXACTLY one band."""
    bands = config.V2_RECENCY_BANDS
    if age_seconds is None:
        return bands[-1][0]
    a = max(0.0, age_seconds)
    for label, upper in bands:
        if upper is None or a < upper:
            return label
    return bands[-1][0]


# ── engagement log ───────────────────────────────────────────────────────────────

@dataclass(slots=True)
class Engagement:
    target_entity_id: str
    signal_type: str
    base_weight: float
    timestamp: Optional[datetime]
    age_seconds: Optional[float]
    effective_weight: float          # base_weight * decay(age)
    band: str


def make_engagement(target_entity_id: str, signal_type: str,
                    timestamp: Optional[datetime], now: datetime) -> Engagement:
    """Build one engagement, computing age/decay/band from `now` (also used to inject synthetic users)."""
    hl_s = config.V2_RECENCY_HALFLIFE_DAYS * 86400.0
    base = _base_weight(signal_type)
    age_s = (now - timestamp).total_seconds() if timestamp else None
    return Engagement(target_entity_id, signal_type, base, timestamp, age_s,
                      round(base * _decay(age_s, hl_s), 6), _band(age_s))


def build_engagement_log(user_id: int, now: datetime,
                         data_source: DataSource) -> Tuple[List[Engagement], Dict[str, int]]:
    """Signal-agnostic log of a user's POSITIVE engagements (follows + reactions), each resolved to a
    SERVED entity and timestamped. Returns (log, resolution_stats). Unresolved/unserved are dropped + counted."""
    log: List[Engagement] = []
    stats = {"follows_seen": 0, "follows_unresolved": 0,
             "reactions_seen": 0, "reactions_unresolved": 0, "reactions_nonpositive": 0}

    # follows: property_id -> entity (bridge), keep only SERVED entities
    for fe in data_source.get_user_follow_events(user_id):
        stats["follows_seen"] += 1
        eid = fe.entity_id
        if not eid or data_source.get_entity(eid) is None:
            stats["follows_unresolved"] += 1
            continue
        log.append(make_engagement(eid, SIGNAL_FOLLOW, fe.created_at, now))

    # reactions: moment -> entity (resolved on the event); all 3 types positive
    for ev in data_source.get_user_reactions(user_id):
        stats["reactions_seen"] += 1
        if ev.reaction_type_id not in config.POSITIVE_REACTION_TYPE_IDS:
            stats["reactions_nonpositive"] += 1
            continue
        eid = ev.entity_id
        if not eid or data_source.get_entity(eid) is None:
            stats["reactions_unresolved"] += 1
            continue
        log.append(make_engagement(eid, SIGNAL_REACTION, ev.created_at, now))

    return log, stats


# ── taste profile ────────────────────────────────────────────────────────────────

@dataclass
class TasteProfile:
    user_id: Optional[int]
    mode: str                                   # "cold_start" | "personalized"
    signal_strength: float                      # 0..1 (amount + recency of resolved signal)
    n_engagements: int                          # resolved engagements used
    n_follows: int
    n_reactions: int
    total_effective_weight: float
    resolution_stats: Dict[str, int] = field(default_factory=dict)
    band_view: Dict[str, Dict[str, float]] = field(default_factory=dict)   # {band: {count, weight}}
    genre_weights: Dict[str, float] = field(default_factory=dict)          # normalized
    keyword_weights: Dict[str, float] = field(default_factory=dict)        # normalized
    community_support: List[Tuple[int, float]] = field(default_factory=list)   # normalized, top few
    mean_influence: Optional[float] = None
    raw_vertical_weights: Dict[str, float] = field(default_factory=dict)   # effective weight per vertical
    vertical_percentages_true: Dict[str, float] = field(default_factory=dict)   # unsmoothed
    vertical_percentages: Dict[str, float] = field(default_factory=dict)   # SMOOTHED (the one to allocate by)
    dominant_verticals: List[Tuple[str, float]] = field(default_factory=list)   # by smoothed pct, desc
    clusters: List[TasteCluster] = field(default_factory=list)
    engagements: List[Engagement] = field(default_factory=list)

    @property
    def top_genres(self) -> List[Tuple[str, float]]:
        return sorted(self.genre_weights.items(), key=lambda kv: (-kv[1], kv[0]))[:config.V2_TOP_ATTRIBUTES_K]

    @property
    def top_keywords(self) -> List[Tuple[str, float]]:
        return sorted(self.keyword_weights.items(), key=lambda kv: (-kv[1], kv[0]))[:config.V2_TOP_ATTRIBUTES_K]


def _entity_attrs(data_source: DataSource, eid: str):
    """Genres + keywords + community/influence for one entity, FROM CSVs (no graph/vector calls).
    Podcasts have no canonical_genres → fall back to podcast categories as the genre source."""
    e = data_source.get_entity(eid)
    if e is None:
        return None
    genres = list(e.canonical_genres)
    if not genres and e.vertical == "podcast":
        genres = data_source.get_podcast_categories(eid)
    g = data_source.get_gds_signal(eid)
    return (e, genres, list(e.bm25_keywords),
            (g.community if g else None), (g.influence if g else None))


def _smoothed_vertical_percentages(raw: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """(true_pct, smoothed_pct) over ALL verticals. Smoothing = Dirichlet pseudocount toward uniform:
    a sparse user is pulled to neutral; as effective weight grows the prior washes out and % sharpen."""
    verts = config.VERTICALS
    total = sum(raw.get(v, 0.0) for v in verts)
    neutral = 1.0 / len(verts)
    k = config.V2_VERTICAL_SMOOTHING_STRENGTH
    true_pct = {v: (raw.get(v, 0.0) / total if total else 0.0) for v in verts}
    smoothed = {v: (raw.get(v, 0.0) + k * neutral) / (total + k) for v in verts}
    return true_pct, smoothed


def _empty_profile(user_id: Optional[int], stats: Dict[str, int]) -> TasteProfile:
    _, smoothed = _smoothed_vertical_percentages({})
    return TasteProfile(
        user_id=user_id, mode="cold_start", signal_strength=0.0,
        n_engagements=0, n_follows=0, n_reactions=0, total_effective_weight=0.0,
        resolution_stats=stats,
        vertical_percentages_true={v: 0.0 for v in config.VERTICALS},
        vertical_percentages=smoothed,
        dominant_verticals=sorted(smoothed.items(), key=lambda kv: (-kv[1], kv[0])),
    )


def build_taste_profile_from_log(engagements: List[Engagement], data_source: DataSource, now: datetime,
                                 user_id: Optional[int] = None,
                                 resolution_stats: Optional[Dict[str, int]] = None) -> TasteProfile:
    """Core: turn a resolved engagement log into a TasteProfile. Exposed so synthetic users (hand-built
    logs over real served entities) exercise the SAME math as real users."""
    stats = resolution_stats or {}
    if not engagements:
        return _empty_profile(user_id, stats)

    # ── per-entity aggregation (dedup across a user's engagements; weight accumulates = intensity) ──
    ent_weight: Dict[str, float] = defaultdict(float)
    ent_newest_age: Dict[str, Optional[float]] = {}
    ent_band: Dict[str, str] = {}
    total_eff = 0.0
    n_follows = n_reactions = 0
    for g in engagements:
        ent_weight[g.target_entity_id] += g.effective_weight
        total_eff += g.effective_weight
        n_follows += (g.signal_type == SIGNAL_FOLLOW)
        n_reactions += (g.signal_type == SIGNAL_REACTION)
        age_d = (g.age_seconds / 86400.0) if g.age_seconds is not None else None
        prev = ent_newest_age.get(g.target_entity_id, math.inf)
        cur = age_d if age_d is not None else math.inf
        if g.target_entity_id not in ent_newest_age or cur < prev:
            ent_newest_age[g.target_entity_id] = age_d
            ent_band[g.target_entity_id] = g.band

    # ── band view (per-ENGAGEMENT; disjoint → no double-count) ──
    band_view: Dict[str, Dict[str, float]] = {label: {"count": 0, "weight": 0.0}
                                              for label, _ in config.V2_RECENCY_BANDS}
    for g in engagements:
        band_view[g.band]["count"] += 1
        band_view[g.band]["weight"] = round(band_view[g.band]["weight"] + g.effective_weight, 6)

    # ── attribute aggregation (genres + keywords) + community/influence support ──
    genre_raw: Dict[str, float] = defaultdict(float)
    kw_raw: Dict[str, float] = defaultdict(float)
    comm_raw: Dict[int, float] = defaultdict(float)
    vert_raw: Dict[str, float] = defaultdict(float)
    infl_num = infl_den = 0.0
    engaged: List[EngagedEntity] = []
    for eid, w in ent_weight.items():
        attrs = _entity_attrs(data_source, eid)
        if attrs is None:
            continue
        e, genres, keywords, community, influence = attrs
        for gname in genres:
            genre_raw[gname] += w
        for kw in keywords:
            kw_raw[kw] += w
        if community is not None:
            comm_raw[community] += w
        vert_raw[e.vertical] += w
        if influence is not None:
            infl_num += w * influence
            infl_den += w
        engaged.append(EngagedEntity(
            entity_id=eid, name=e.name, vertical=e.vertical, weight=round(w, 6),
            genres=set(genres), keywords=set(keywords), community=community, influence=influence,
            newest_age_days=ent_newest_age.get(eid), band=ent_band.get(eid, "older")))

    def _norm(d: Dict) -> Dict:
        s = sum(d.values())
        return {k: round(v / s, 6) for k, v in sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0])))} if s else {}

    genre_weights = _norm(genre_raw)
    keyword_weights = _norm(kw_raw)
    community_support = [(c, round(w, 6)) for c, w in
                         sorted(_norm(comm_raw).items(), key=lambda kv: -kv[1])][:5]
    mean_influence = round(infl_num / infl_den, 6) if infl_den else None

    true_pct, smoothed = _smoothed_vertical_percentages(vert_raw)

    signal_strength = min(1.0, total_eff / config.V2_SIGNAL_FULL_EFFECTIVE_WEIGHT) \
        if config.V2_SIGNAL_FULL_EFFECTIVE_WEIGHT else 0.0
    n_resolved = len(engagements)
    mode = "cold_start" if n_resolved < config.V2_COLD_START_THRESHOLD else "personalized"

    clusters = cluster_engaged_entities(engaged, genre_weights)

    return TasteProfile(
        user_id=user_id, mode=mode, signal_strength=round(signal_strength, 4),
        n_engagements=n_resolved, n_follows=n_follows, n_reactions=n_reactions,
        total_effective_weight=round(total_eff, 4), resolution_stats=stats,
        band_view=band_view, genre_weights=genre_weights, keyword_weights=keyword_weights,
        community_support=community_support, mean_influence=mean_influence,
        raw_vertical_weights={v: round(vert_raw.get(v, 0.0), 4) for v in config.VERTICALS},
        vertical_percentages_true={v: round(true_pct[v], 4) for v in config.VERTICALS},
        vertical_percentages={v: round(smoothed[v], 4) for v in config.VERTICALS},
        dominant_verticals=sorted(((v, round(smoothed[v], 4)) for v in config.VERTICALS),
                                  key=lambda kv: (-kv[1], kv[0])),
        clusters=clusters, engagements=engagements,
    )


def build_taste_profile(user_id: int, now: datetime, data_source: DataSource) -> TasteProfile:
    """End-to-end: resolve the user's engagement log, then build the time-decayed clustered taste profile."""
    log, stats = build_engagement_log(user_id, now, data_source)
    return build_taste_profile_from_log(log, data_source, now, user_id=user_id, resolution_stats=stats)


# ── reporting helper ─────────────────────────────────────────────────────────────

def profile_to_dict(p: TasteProfile) -> dict:
    """JSON-friendly view (clusters flattened) for the test report / future /debug surface."""
    return {
        "user_id": p.user_id, "mode": p.mode, "signal_strength": p.signal_strength,
        "n_engagements": p.n_engagements, "n_follows": p.n_follows, "n_reactions": p.n_reactions,
        "total_effective_weight": p.total_effective_weight, "resolution_stats": p.resolution_stats,
        "band_view": p.band_view, "mean_influence": p.mean_influence,
        "top_genres": p.top_genres, "top_keywords": p.top_keywords,
        "community_support": p.community_support,
        "raw_vertical_weights": p.raw_vertical_weights,
        "vertical_percentages_true": p.vertical_percentages_true,
        "vertical_percentages": p.vertical_percentages,
        "dominant_verticals": p.dominant_verticals,
        "clusters": [{
            "cluster_id": c.cluster_id, "label": c.label, "size": c.size,
            "cluster_weight": c.cluster_weight, "cluster_share": c.cluster_share,
            "dominant_vertical": c.dominant_vertical, "dominant_verticals": c.dominant_verticals,
            "top_genres": c.top_genres, "top_keywords": c.top_keywords,
            "top_representative_member_entity_ids": c.top_representative_member_entity_ids,
            "member_entity_ids": c.member_entity_ids, "recency_summary": c.recency_summary,
        } for c in p.clusters],
    }
