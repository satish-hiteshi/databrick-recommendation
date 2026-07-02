"""SearchRequest — the POST /search contract for BOTH UC4 (in-app) and UC7 (onboarding)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from . import config


@dataclass(slots=True)
class SearchRequest:
    query: str
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    mode: str = "auto"                       # auto | name | thematic
    limit: int = config.DEFAULT_LIMIT
    verticals: List[str] = field(default_factory=list)
    exclude_followed: bool = True
    source_context: Optional[str] = None
    disambiguation: bool = False
    debug: bool = False

    @staticmethod
    def from_dict(d: dict) -> "SearchRequest":
        req = SearchRequest(
            query=(d.get("query") or "").strip(),
            user_id=d.get("user_id"),
            session_id=d.get("session_id"),
            mode=(d.get("mode") or "auto").lower(),
            limit=int(d.get("limit") or config.DEFAULT_LIMIT),
            verticals=[str(v).lower() for v in (d.get("verticals") or [])],
            exclude_followed=bool(d.get("exclude_followed", True)),
            source_context=d.get("source_context"),
            disambiguation=bool(d.get("disambiguation", False)),
            debug=bool(d.get("debug", False)),
        )
        # null user_id (onboarding pre-auth) -> exclude_followed is meaningless -> force false
        if req.user_id is None:
            req.exclude_followed = False
        # source_context == onboarding_search forces onboarding semantics (no follow exclusion)
        if req.source_context == config.ONBOARDING_SOURCE_CONTEXT:
            req.exclude_followed = False
        return req
