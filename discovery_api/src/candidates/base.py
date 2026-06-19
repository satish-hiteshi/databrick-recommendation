"""Candidate-pool contract + shared helpers.

A provider turns (UserProfile, RequestContext) into a list of Candidate STUBS — each carrying its
RAW signals (semantic / recency / normalized-influence / velocity / …) but NO final blended score. The
P4 scorer blends them; the P5 assembler shapes feed + carousels. Providers are independent + individually
testable, and every one applies the SAME exclusions (followed + dormant-blocked + seen + the request's
property_ids exclusion list) and dedupes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from .. import config
from .. import timeutil
from ..data_access.base import DataSource
from ..data_access.records import Moment
from ..feed.profile import UserProfile


@dataclass
class Candidate:
    source_pool: str
    entity_id: Optional[str] = None          # property-level candidate (carousels, similarity)
    moment_id: Optional[int] = None          # moment-level candidate (main feed, fresh)
    vertical: Optional[str] = None
    property_id: Optional[int] = None
    raw_signals: Dict[str, object] = field(default_factory=dict)   # NO final score — P4 blends these

    @property
    def key(self) -> Tuple:
        return ("m", self.moment_id) if self.moment_id is not None else ("e", self.entity_id)


@dataclass
class RequestContext:
    """The discovery request envelope (what the open-feed call carries besides the user)."""
    now: Optional[datetime] = None
    seen_entity_ids: Set[str] = field(default_factory=set)
    seen_moment_ids: Set[int] = field(default_factory=set)
    excluded_property_ids: Set[int] = field(default_factory=set)   # the request's property_ids EXCLUSION list
    vertical: Optional[str] = None                                 # optional single-vertical request
    limit: int = config.CANDIDATE_POOL_SIZE                         # main-feed page size (P4 pagination)
    offset: int = 0                                                 # main-feed page offset (P4 pagination)

    def __post_init__(self):
        if self.now is None:
            self.now = timeutil.now()


# ── shared exclusion / dedupe ───────────────────────────────────────────

def excluded_entity_ids(profile: UserProfile, context: RequestContext, ds: DataSource) -> Set[str]:
    """The full set of entity_ids a pool must NOT surface: followed + dormant(blocked/done/not_interested)
    + seen(context) + entity_ids(request property_ids exclusion list)."""
    excl: Set[str] = set(profile.followed_entity_ids)
    excl |= set(profile.blocked_entity_ids)            # dormant (empty now)
    excl |= set(profile.done_entity_ids)               # dormant
    excl |= set(profile.not_interested_entity_ids)     # dormant
    excl |= set(context.seen_entity_ids)
    for pid in context.excluded_property_ids:
        eid = ds.property_id_to_entity_id(pid)
        if eid:
            excl.add(eid)
    return excl


def dedupe(cands: List[Candidate]) -> List[Candidate]:
    """Keep the FIRST candidate per key (entity_id or moment_id); order-stable."""
    seen, out = set(), []
    for c in cands:
        if c.key in seen:
            continue
        seen.add(c.key); out.append(c)
    return out


# ── shared fresh-moment selection (FreshMoments + NewInGenre + NewOnPlatform reuse this) ──

def select_fresh_moments(ds: DataSource, context: RequestContext, excl_eids: Set[str],
                         cap: Optional[int] = None, limit: Optional[int] = None,
                         vertical: Optional[str] = None) -> List[Tuple[Moment, float]]:
    """Freshest moments (soft-recency around context.now) from UNFOLLOWED/allowed properties, with the
    PER-PROPERTY moment cap applied (so episode-heavy podcasts can't flood). Excludes seen moments + any
    moment whose property is excluded. Returns [(moment, recency_score)] newest-first."""
    cap = cap if cap is not None else config.MOMENT_CAP_PER_PROPERTY
    limit = limit if limit is not None else config.CANDIDATE_POOL_SIZE
    vertical = vertical or context.vertical
    # generous oversample: we filter exclusions + cap, so pull many more than `limit` raw moments
    oversample = max(limit * 50, 10_000)
    per_property: Dict[str, int] = {}
    out: List[Tuple[Moment, float]] = []
    for m in ds.get_recent_moments(context.now, oversample, vertical):
        if m.entity_id in excl_eids:
            continue
        if m.moment_id in context.seen_moment_ids:
            continue
        if per_property.get(m.entity_id, 0) >= cap:
            continue
        per_property[m.entity_id] = per_property.get(m.entity_id, 0) + 1
        out.append((m, timeutil.recency_score(m.event_starts_at, context.now)))
        if len(out) >= limit:
            break
    return out


def _moment_candidate(ds: DataSource, m: Moment, recency: float, pool: str,
                      popularity=None, extra: Optional[dict] = None) -> Candidate:
    ent = ds.get_entity(m.entity_id)
    sig: Dict[str, object] = {
        "recency": round(recency, 4),
        "event_starts_at": m.event_starts_at.isoformat() if m.event_starts_at else None,
        "age_days": round(timeutil.age_days(m.event_starts_at) or 0.0, 2) if m.event_starts_at else None,
        "moment_type_id": m.moment_type_id,
    }
    if popularity is not None:
        sig["influence_norm"] = popularity.normalized_influence(m.entity_id)
    if extra:
        sig.update(extra)
    return Candidate(source_pool=pool, moment_id=m.moment_id, entity_id=m.entity_id,
                     property_id=m.property_id, vertical=(ent.vertical if ent else None), raw_signals=sig)


class CandidateProvider(ABC):
    """Common provider interface. Subclasses get the data source + (optional) substrate client + popularity."""
    name: str = "candidate_provider"

    def __init__(self, data_source: DataSource, substrate=None, popularity=None):
        self.ds = data_source
        self.substrate = substrate
        self.popularity = popularity

    @abstractmethod
    def generate(self, profile: UserProfile, context: RequestContext) -> List[Candidate]:
        ...
