"""The v1.0 discovery FEED output object (plain dataclasses — NOT HTTP; P5 serializes these).

Shape: a vertical MAIN FEED of moment items + horizontal CAROUSELS of property items, each item with a
templated why_string, each carousel a reason_string, plus a per-item debug breakdown (source_pool + raw
signals + final score) the API surfaces only when debug=true.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

# central identity: derive the composite (profile_key + media_source_guid) from entity_id on every item.
_REPO_ROOT = Path(__file__).resolve().parents[5]     # feed → src → discovery_api → local_code → E2 → ROOT
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from shared import identity as _ident   # noqa: E402


def _composite(entity_id: Optional[str]) -> dict:
    """entity_id → {"profile_key", "media_source_guid"} for the response; {} if it can't be derived."""
    if not entity_id:
        return {}
    try:
        return _ident.composite_of(entity_id)
    except ValueError:
        return {}


class ReasonType(str, Enum):
    trending = "trending"
    similar_to_followed = "similar_to_followed"
    new_in_vertical = "new_in_vertical"
    popular_with_fans_of = "popular_with_fans_of"
    popular_with_similar_users = "popular_with_similar_users"   # V2-P9 collaborative (similar-taste neighborhood)
    new_in_genre = "new_in_genre"
    new_on_platform = "new_on_platform"
    happening_today = "happening_today"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


@dataclass
class FeedItem:
    """A MAIN-FEED moment (a dated content event from an unfollowed property)."""
    moment_id: int
    entity_id: str
    property_name: str
    vertical: str
    title: str
    description: str
    event_starts_at: Optional[str]
    media_platform_id: Optional[int]
    score: float
    why_string: str
    source_pool: str
    debug: dict = field(default_factory=dict)
    type: str = "moment"

    def to_dict(self, debug: bool = False) -> dict:
        d = {"type": self.type, "moment_id": self.moment_id, "entity_id": self.entity_id,
             **_composite(self.entity_id),                # profile_key + media_source_guid (composite key)
             "property_name": self.property_name, "vertical": self.vertical, "title": self.title,
             "description": self.description, "event_starts_at": self.event_starts_at,
             "media_platform_id": self.media_platform_id, "score": round(self.score, 4),
             "why_string": self.why_string}
        if debug:
            d["debug"] = {"source_pool": self.source_pool, **self.debug}
        return d


@dataclass
class LatestMoment:
    moment_id: int
    title: str
    event_starts_at: Optional[str]

    def to_dict(self) -> dict:
        return {"moment_id": self.moment_id, "title": self.title, "event_starts_at": self.event_starts_at}


@dataclass
class CarouselItem:
    """A property recommended in a carousel, with a hook to its latest moment."""
    entity_id: str
    property_name: str
    vertical: str
    score: float
    why_string: str
    source_pool: str
    latest_moment: Optional[LatestMoment] = None
    debug: dict = field(default_factory=dict)
    type: str = "property"

    def to_dict(self, debug: bool = False) -> dict:
        d = {"type": self.type, "entity_id": self.entity_id, **_composite(self.entity_id),
             "property_name": self.property_name,
             "vertical": self.vertical, "score": round(self.score, 4), "why_string": self.why_string,
             "latest_moment": self.latest_moment.to_dict() if self.latest_moment else None}
        if debug:
            d["debug"] = {"source_pool": self.source_pool, **self.debug}
        return d


@dataclass
class Carousel:
    carousel_id: str
    reason_type: ReasonType
    reason_string: str
    item_type: str                       # "property" | "moment"
    items: List[CarouselItem] = field(default_factory=list)

    def to_dict(self, debug: bool = False) -> dict:
        return {"carousel_id": self.carousel_id, "reason_type": self.reason_type.value,
                "reason_string": self.reason_string, "item_type": self.item_type,
                "size": len(self.items), "items": [i.to_dict(debug) for i in self.items]}


@dataclass
class Pagination:
    limit: int
    offset: int
    returned: int
    next_offset: Optional[int]
    pool_total: int

    def to_dict(self) -> dict:
        return {"limit": self.limit, "offset": self.offset, "returned": self.returned,
                "next_offset": self.next_offset, "pool_total": self.pool_total}


@dataclass
class DiscoveryFeed:
    user_id: int
    mode: str
    signal_strength: float
    now: Optional[str]
    main_feed: List[FeedItem] = field(default_factory=list)
    carousels: List[Carousel] = field(default_factory=list)
    pagination: Optional[Pagination] = None

    def to_dict(self, debug: bool = False) -> dict:
        return {"user_id": self.user_id, "mode": self.mode, "signal_strength": self.signal_strength,
                "now": self.now,
                "main_feed": [i.to_dict(debug) for i in self.main_feed],
                "carousels": [c.to_dict(debug) for c in self.carousels],
                "pagination": self.pagination.to_dict() if self.pagination else None}
