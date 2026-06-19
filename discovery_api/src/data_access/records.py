"""Typed record dataclasses returned by the DataSource (CSV now, live SQL later — SAME types).

These are the clean read-models the engine consumes; neither the CSV nor the live reader leaks its
storage shape past this boundary. Moment carries `description` (the P4 feed item shows it); it is the
one heavy field — the live reader can omit it from list reads and fetch on demand if needed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


def parse_json_list(s) -> List[str]:
    """entities_dev genres/themes/keywords + podcast categories are JSON arrays ('[]' when empty,
    'null' string for missing). Defensive: returns [] on anything non-list."""
    if s is None:
        return []
    s = str(s).strip()
    if not s or s.lower() == "null":
        return []
    try:
        v = json.loads(s)
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def clean_scalar(s) -> Optional[str]:
    """'null'/'' -> None, else the trimmed string (franchise/developer/publisher columns)."""
    if s is None:
        return None
    s = str(s).strip()
    return s if s and s.lower() != "null" else None


@dataclass(slots=True)
class Entity:
    entity_id: str
    vertical: str
    name: str
    canonical_genres: List[str] = field(default_factory=list)  # game/movie/tv; podcasts use categories
    themes: List[str] = field(default_factory=list)
    franchise: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    release_date: Optional[str] = None
    release_date_int: Optional[int] = None
    bm25_keywords: List[str] = field(default_factory=list)


@dataclass(slots=True)
class Moment:
    moment_id: int
    entity_id: str
    property_id: int
    media_type_id: Optional[int] = None
    moment_type_id: Optional[int] = None
    title: str = ""
    description: str = ""                         # the feed item shows this (P4)
    event_starts_at: Optional[datetime] = None   # THE recency key
    event_ends_at: Optional[datetime] = None
    media_platform_id: Optional[int] = None
    profile_key: str = ""
    created_at: Optional[datetime] = None


@dataclass(slots=True)
class Cta:
    cta_id: int
    moment_id: int
    cta_action_id: Optional[int] = None
    region_id: Optional[int] = None
    media_platform_id: Optional[int] = None
    cta_button_text: str = ""
    url: str = ""


@dataclass(slots=True)
class GdsSignal:
    entity_id: str
    vertical: str
    influence: Optional[float] = None   # PageRank — the popularity/centrality scalar
    community: Optional[int] = None     # Louvain


@dataclass(slots=True)
class ReactionEvent:
    user_id: int
    moment_id: int
    reaction_type_id: int               # 1=heart 2=fire 3=confetti — ALL positive for v1
    created_at: Optional[datetime] = None
    entity_id: Optional[str] = None     # resolved via moments (moment_id -> entity)


@dataclass(slots=True)
class FollowEvent:
    """A timestamped follow (Discovery v2 engagement log). v1's get_followed_property_ids returns only
    the property_id and drops created_at; v2 needs the timestamp for recency-weighted taste."""
    user_id: int
    property_id: int
    created_at: Optional[datetime] = None
    entity_id: Optional[str] = None     # resolved via the bridge (property_id -> entity); None if unbridged


@dataclass(slots=True)
class User:
    id: int
    onboarding_status: Optional[str] = None
    account_status_id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Lookups:
    """Decode tables from lookups_dev.csv: {kind: {id: name}} (+ media_type->vertical convenience)."""
    by_kind: Dict[str, Dict[int, str]] = field(default_factory=dict)

    def name(self, kind: str, id_: Optional[int]) -> Optional[str]:
        if id_ is None:
            return None
        return self.by_kind.get(kind, {}).get(int(id_))

    def media_platform(self, id_: Optional[int]) -> Optional[str]:
        return self.name("media_platform", id_)

    def region(self, id_: Optional[int]) -> Optional[str]:
        return self.name("region", id_)
