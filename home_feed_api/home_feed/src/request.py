"""HomeFeedRequest — the decoded request the engine consumes (FastAPI-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union

from . import config


@dataclass(slots=True)
class HomeFeedRequest:
    user_id: int
    sort_order: str = config.HOME_SORT_MODE          # "relevance" | "recent"
    time_window: Optional[str] = None                # echoed; not yet a hard filter (recency is soft)
    limit: int = config.HOME_DEFAULT_LIMIT
    offset: int = config.HOME_DEFAULT_OFFSET
    seen_ids: List[int] = field(default_factory=list)
    done_ids: List[int] = field(default_factory=list)
    # POST composite-key migration: property suppression refs are entity_id | composite | bare source_id
    # (resolved to entity_ids in the engine). Kept as raw refs here (NOT int-cast).
    dismissed_property_ids: List[Union[int, str, dict]] = field(default_factory=list)
    blocked_property_ids: List[Union[int, str, dict]] = field(default_factory=list)
    reacted_moment_ids: List[int] = field(default_factory=list)   # request-supplied until identity lands
    debug: bool = False

    @staticmethod
    def from_dict(d: dict) -> "HomeFeedRequest":
        il = lambda k: [int(x) for x in (d.get(k) or [])]
        return HomeFeedRequest(
            user_id=int(d["user_id"]),
            sort_order=str(d.get("sort_order") or config.HOME_SORT_MODE).lower(),
            time_window=d.get("time_window"),
            limit=int(d.get("limit", config.HOME_DEFAULT_LIMIT)),
            offset=int(d.get("offset", config.HOME_DEFAULT_OFFSET)),
            seen_ids=il("seen_ids"), done_ids=il("done_ids"),
            dismissed_property_ids=list(d.get("dismissed_property_ids") or []),   # raw refs (resolved in engine)
            blocked_property_ids=list(d.get("blocked_property_ids") or []),
            reacted_moment_ids=il("reacted_moment_ids"),
            debug=bool(d.get("debug", False)))
