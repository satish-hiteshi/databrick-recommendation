"""UC3 v1.0 home-feed envelope serializer.

Turns the ranked candidates (prompt 4) into the UC3 `predictions[]` envelope. The discipline here:
populate EVERY field we have a real source for, and NULL — honestly, deliberately — every field we do
not (see the field-gap list in the report). Carousels are phase two → always []. Mirrors E2's
feed_models envelope/pagination shape, built to UC3's exact field set.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import config
from .candidate import CandidatePool
from .ranker import ScoredCandidate
from .request import HomeFeedRequest
from .scorer import HomeWeights
from .why import badge, dominant_signal, why_string

# central identity (namespace import from repo root). src → home_feed → local_code → endpoint_3_home_feed → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from shared import identity as _ident   # noqa: E402


def _composite(entity_id: str) -> dict:
    """entity_id → {profile_key, media_source_guid} for the response; {} if not derivable."""
    try:
        return _ident.composite_of(entity_id)
    except (ValueError, AttributeError):
        return {}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def signal_strength(follow_count: int) -> float:
    """min(1, follow_count / FULL) — saturating proxy for personalization confidence (thin → low)."""
    full = max(1, config.HOME_SIGNAL_STRENGTH_FULL_FOLLOWS)
    return round(min(1.0, follow_count / full), 2)


def serialize_item(sc: ScoredCandidate, now: datetime, weights: HomeWeights, debug: bool) -> dict:
    c, b = sc.candidate, sc.breakdown
    return {
        "type": "moment",
        "moment_id": c.moment_id,
        "entity_id": c.entity_id,
        # composite key (the stable identity post-migration) — derive from entity_id, fall back to the
        # fields the graph traversal set.
        **({**_composite(c.entity_id)} or
           {"profile_key": c.profile_key, "media_source_guid": c.media_source_guid}),
        # DEPRECATED: the old PUBLIC property_id is GONE. This now carries the surviving source_id
        # (== media_source_guid) for backward-compat; clients should key on entity_id / the composite.
        "property_id": (c.media_source_guid or (str(c.property_id) if c.property_id else None)),
        "property_name": c.property_name,
        "property_handle": None,            # NO SOURCE — we have no @handle
        "property_thumbnail_url": None,     # NO SOURCE — no property icon in our data
        "vertical": c.vertical,             # game | movie | tv | podcast (only four we have)
        "title": c.title,
        "description": c.description,
        "thumbnail_url": None,              # ALL-NULL on our nodes (Neo4j dropped it on load)
        "media_url": c.url,
        "media_platform_id": c.media_platform_id,
        "media_platform": None,             # NO SOURCE — int id only, no id→name map
        "event_starts_at": _iso(c.event_starts_at),
        "is_live": False,                   # NO SIGNAL — constant false
        "viewer_count": None,               # live-only — no source
        "score": round(b.blended, 4),
        "why_string": why_string(c, b, weights),    # REQUIRED, never null
        "badge": badge(c, now),             # "NEW" or null (never LIVE/TRENDING)
        "is_followed": True,                # every main-stream item is followed by definition
        "debug_meta": ({**asdict(b), "dominant_signal": dominant_signal(b, weights), "rank": sc.rank}
                       if debug else None),
    }


def build_envelope(req: HomeFeedRequest, pool: CandidatePool, ranked: List[ScoredCandidate],
                   now: datetime, weights: HomeWeights) -> dict:
    """Assemble the full UC3 predictions[] envelope (one prediction). Pagination slices `ranked`."""
    total = len(ranked)
    page = ranked[req.offset: req.offset + req.limit]
    items = [serialize_item(sc, now, weights, req.debug) for sc in page]
    has_more = (req.offset + len(items)) < total
    follow_count = len(pool.followed_property_ids)

    prediction = {
        "version": config.HOME_VERSION,
        "endpoint": config.HOME_ENDPOINT_LABEL,
        "user_id": req.user_id,
        "generated_at": _iso(now),
        "context": {
            "mode": config.HOME_CONTEXT_MODE,
            "signal_strength": signal_strength(follow_count),
            "engine": config.HOME_ENGINE_LABEL,
            "path": config.HOME_PATH_LABEL,
            "follow_count": follow_count,
        },
        "request_echo": {                   # COUNTS, not the arrays
            "sort_order": req.sort_order,
            "time_window": req.time_window,
            "limit": req.limit,
            "offset": req.offset,
            "seen_ids": len(req.seen_ids),
            "done_ids": len(req.done_ids),
            "dismissed_property_ids": len(req.dismissed_property_ids),
            "blocked_property_ids": len(req.blocked_property_ids),
        },
        "main_feed": {
            "items": items,
            "count": len(items),
            "next_offset": (req.offset + req.limit) if has_more else None,
        },
        "carousels": [],                    # PHASE TWO — structure: [{carousel_id, reason_type, reason_string, items:[...]}]
        "pagination": {
            "offset": req.offset,
            "limit": req.limit,
            "total_available": total,
            "has_more": has_more,
        },
        "debug": ({
            "pool_reason": pool.reason,
            "pool_trace": pool.trace,
            "n_ranked": total,
            "sort_order": req.sort_order,
            "weights": asdict(weights),
            "signal_strength_inputs": {"follow_count": follow_count,
                                       "full_follows": config.HOME_SIGNAL_STRENGTH_FULL_FOLLOWS},
        } if req.debug else None),
    }
    return {"predictions": [prediction]}
