"""UC4/UC7 response envelope — predictions[0] with the exact field set both use-case docs specify."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

from . import config

try:
    from shared import identity as _ident                # repo-root layout (local dev tree)
except ImportError:
    try:
        from . import _identity as _ident                # vendored copy (serving bundle)
    except ImportError:
        import _identity as _ident

WHY_NAME = "Best match for '{q}'"
WHY_THEMATIC = "Matched to topic: {q}"
WHY_DEMOTED = "Named '{q}'"        # a twin-demoted name match: honest name match, NOT the confident "Best match" pin


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _composite(entity_id) -> dict:
    if not entity_id:
        return {}
    try:
        return _ident.composite_of(entity_id)
    except (ValueError, AttributeError):
        return {}


def _deep_link(r) -> str:
    """Deep link. POST composite-key migration the old `feeds://property/{PUBLIC property_id}` breaks (the
    id is dead). We keep the URL WORKING meanwhile by emitting the surviving source_id (= media_source_guid),
    but that value is AMBIGUOUS on the ~321 cross-vertical guid collisions.
    TODO(client sign-off — Michelle/Viaduct): finalise the composite deep-link form, proposed:
        feeds://property/{profile_key}/{media_source_guid}   (unambiguous), or
        feeds://property/{vertical}/{media_source_guid}      (unambiguous, shorter).
    Until signed off, keep the single-segment link below."""
    comp = _composite(r.entity_id)
    guid = comp.get("media_source_guid") or (str(r.property_id) if r.property_id else "")
    return f"feeds://property/{guid}"


def serialize_result(r, query: str, followed: Set[str], debug: bool) -> dict:
    name_path = r.match_type in ("exact", "prefix", "fuzzy_typo", "fuzzy")
    client_match_type = "fuzzy" if r.match_type == "fuzzy_typo" else r.match_type   # fuzzy_typo is an internal sub-tier
    comp = _composite(r.entity_id)
    return {
        "type": "property",
        "entity_id": r.entity_id,
        **comp,                                                 # profile_key + media_source_guid (composite key)
        # DEPRECATED: the old PUBLIC property_id is GONE. This now carries the surviving source_id
        # (== media_source_guid); clients should key on entity_id / the composite.
        "property_id": comp.get("media_source_guid") or (str(r.property_id) if r.property_id else None),
        "name": r.name,
        "vertical": r.vertical,
        "genres": r.genres or [],
        "thumbnail_url": None,                                   # no source on our data
        "deep_link": _deep_link(r),                             # TODO: composite form pending client sign-off (see _deep_link)
        "score": round(r.final_score, 4),
        "match_type": client_match_type,                         # HONEST: exact | prefix | fuzzy | thematic (fuzzy_typo→fuzzy for the client)
        "disambiguation_confidence": round(r.disambiguation_confidence, 4),
        # twin-demoted → "Named '{q}'" (honest name match, no false confidence); else name/thematic framing
        "why_string": (WHY_DEMOTED if r.twin_demoted else WHY_NAME if name_path else WHY_THEMATIC).format(q=query),
        "badge": None,
        "is_followed": r.entity_id in followed,                 # followed is now a set of entity_ids
        "follow_cta": True,
        "latest_moment": None,                                  # best-effort context; null at this stage
        "debug": ({"match_type_raw": r.match_type, "twin_demoted": r.twin_demoted, "cosine": r.cosine,
                   "signals": r.signals, "centrality_pct": round(r.centrality_pct, 4),
                   "popularity_pct": round(r.popularity_pct, 4)} if debug else None),
    }


def build_envelope(req, results: List, mode_taken: str, now: datetime, followed: Set[int],
                   total_candidates: int, extra_debug: dict) -> dict:
    res = [serialize_result(r, req.query, followed, req.debug) for r in results]
    prediction = {
        "version": config.VERSION,
        "endpoint": config.ENDPOINT_LABEL,
        "user_id": req.user_id,
        "generated_at": _iso(now),
        "query_echo": req.query,
        "results": res,
        "result_count": len(res),
        "has_more": total_candidates > len(res),
        "debug": ({"mode_taken": mode_taken, "engine": config.ENGINE_LABEL,
                   "source_context": req.source_context, "total_candidates": total_candidates,
                   **extra_debug} if req.debug else None),
        "session_id": req.session_id,                           # echoed unchanged (Viaduct owns the array)
    }
    return {"predictions": [prediction]}
