"""The E3 candidate shapes — the moment-level pool the ranker (next prompt) consumes.

NEW to E3: E2 ranks PROPERTIES; E3 ranks MOMENTS of followed properties. `CandidateMoment` mirrors the
verified :Moment node fields (Step 0) plus the property context needed to gate/rank/serialize (the
property's prefixed entity_id, vertical, name). `event_starts_at` is the recency key. Fields that are
all-null in staging (thumbnail_url, event_ends_at, views) are intentionally omitted — add them if/when
populated upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(slots=True)
class CandidateMoment:
    # identity + link. POST composite-key migration: entity_id is the STABLE link (the old PUBLIC
    # property_id is gone). property_id is retained as the entity's media_source_guid (int; 0 if
    # non-numeric) for legacy fields only — it is NOT collision-safe across verticals; key on entity_id.
    moment_id: int
    property_id: int
    # property context (from the :Entity the moment hangs off)
    entity_id: str                     # prefixed property id, e.g. 'Movie:1100083' — the stable identity
    profile_key: str = ""              # composite: per-vertical constant (watchmode_property_tv, …)
    media_source_guid: str = ""        # composite: the id suffix (STRING; never int-cast)
    vertical: str = ""                 # game | movie | tv | podcast
    property_name: str = ""
    # moment payload
    title: str = ""
    description: Optional[str] = None
    url: Optional[str] = None
    event_starts_at: Optional[datetime] = None     # THE recency key
    moment_kind: str = ""              # Moment.profile_key — the moment KIND (…_episode_released vs …_released/
                                       # …_trailer/…_reveal); classifies EVENT (decay) vs ANCHOR (proximity)
    media_type_id: Optional[int] = None
    moment_type_id: Optional[int] = None
    media_platform_id: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass(slots=True)
class CandidatePool:
    """The follow-gated, suppressed, capped candidate pool — the front-half output (NO ranking yet)."""
    user_id: int
    followed_property_ids: List[str]               # entity_ids — the hard boundary for the whole stream
    candidates: List[CandidateMoment]              # post-suppression, post-cap
    trace: Dict[str, object] = field(default_factory=dict)   # per-step counts (observability/dry-run)
    reason: Optional[str] = None                   # why empty, if empty: 'no_follows' | 'all_suppressed' | None

    @property
    def is_empty(self) -> bool:
        return not self.candidates

    @property
    def size(self) -> int:
        return len(self.candidates)
