"""exclude_followed — over the vendored CsvFollowSource (see _vendored.py), behind a try/fallback that
degrades to no-exclusion.

UC7 (onboarding) is pre-auth: null user_id → no exclusion (handled in request.py). When authed + exclude
is on, we read active follows from the public_property_followers export (active = deleted_at IS NULL).
If the source is missing/unreadable, we LOG and degrade to no-exclusion rather than fail search.

POST composite-key migration — FOLLOW KEY: a follow is keyed on the stable **entity_id** (or composite),
NOT the old PUBLIC property_id. This gate returns RAW follow keys (entity_id strings if the followers
export carries them; else legacy bare source_id ints). The engine resolves them to entity_ids against the
bridge and excludes on entity_id (collision-safe). The legacy PUBLIC-id CSV DOES NOT resolve on the new
graph → the followers export MUST be re-supplied with entity_id (or profile_key + media_source_guid).
"""

from __future__ import annotations

import os
from typing import Optional, Set, Tuple

from . import config

# ── Databricks live source (env-gated; INERT for local CSV runs) ─────────────────────────────────
# When SEARCH_DATA_SOURCE=live, FollowGate reads active follows from Silver `public_property_followers`
# via LiveFollowSource (the same E3 seam E4 reuses) using an injected query_fn (databricks-sql-connector
# in serving) instead of the dev CSV. The pyfunc calls set_query_fn(...) BEFORE constructing SearchEngine.
_LIVE = os.getenv("SEARCH_DATA_SOURCE", "").lower() == "live"
_SILVER_CAT = os.getenv("SEARCH_SILVER_CATALOG", "stg_feeds_silver")
_QUERY_FN = None


def set_query_fn(fn):
    """Inject the Silver query function (serving). MUST be called before FollowGate() when live."""
    global _QUERY_FN
    _QUERY_FN = fn


class FollowGate:
    def __init__(self) -> None:
        self._src = None
        self._error: Optional[str] = None
        self._backend = "csv:public_property_followers"
        try:
            if _LIVE and _QUERY_FN is not None:             # deploy: Silver public_property_followers
                from .reuse import LiveFollowSource
                self._src = LiveFollowSource(_QUERY_FN, catalog=_SILVER_CAT)
                self._backend = "silver:public_property_followers"
            else:
                from .reuse import CsvFollowSource
                self._src = CsvFollowSource(config.FOLLOWERS_CSV)
        except Exception as e:                              # pragma: no cover - defensive
            self._error = f"{type(e).__name__}: {e}"

    def followed(self, user_id: Optional[int], exclude_followed: bool) -> Tuple[Set, dict]:
        """Return (raw_follow_keys, info). Keys are entity_id strings (preferred) or legacy bare source_id
        ints — the engine normalises them to entity_ids via the bridge before excluding."""
        if not exclude_followed or user_id is None:
            return set(), {"applied": False, "reason": "disabled_or_anon"}
        if self._src is None:
            return set(), {"applied": False, "reason": "source_unavailable", "error": self._error}
        try:
            ids = self._src.active_followed_property_ids(int(user_id))
            return set(ids), {"applied": True, "source": self._backend, "count": len(ids), "key": "entity_id|legacy_source_id"}
        except Exception as e:                              # degrade, never fail search
            return set(), {"applied": False, "reason": "lookup_failed", "error": f"{type(e).__name__}: {e}"}
