"""build_candidate_pool — the front half of the E3 pipeline (NO ranking).

    resolve follows (follow-gate)  →  traverse to moments  →  suppress (hard filters)

Returns a CandidatePool that is always valid, never raises on empty: a user with no follows, or whose
moments are all suppressed, yields an empty-but-valid pool with a `reason`. The ranker (ranker.rank_pool)
consumes pool.candidates.

P4 CHANGE: the per-property cap has been RELOCATED to ranking (best-N by score), so the front half no
longer caps (apply_cap defaults False). The future cut is now the horizon-aware
suppression.drop_calendar_and_junk_future (keeps near-future for proximity); see recency.py for how the
two coordinate without double-handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from . import config
from .candidate import CandidatePool
from .candidates.followed_moments import generate_followed_candidates
from .follow_gate import resolve_followed_property_ids
from .follow_source import FollowSource
from .graph_moments import GraphMoments
from .reuse import timeutil
from .suppression import SuppressionInputs, apply_suppression, cap_per_property


def resolve_now(now: Optional[datetime] = None) -> datetime:
    """The reference 'now' (UTC, tz-aware). Explicit arg > config.HOME_NOW_ISO > wall clock."""
    if now is not None:
        return now
    if config.HOME_NOW_ISO:
        return timeutil.parse_ts(config.HOME_NOW_ISO)
    return datetime.now(timezone.utc)


def build_candidate_pool(user_id: int,
                         suppression: SuppressionInputs,
                         *,
                         follow_source: FollowSource,
                         graph: GraphMoments,
                         now: Optional[datetime] = None,
                         apply_cap: bool = False,
                         max_moment_age_days: Optional[float] = None) -> CandidatePool:
    now = resolve_now(now)
    today_window = config.HOME_TODAY_WINDOW_HOURS
    horizon = config.HOME_FUTURE_HORIZON_DAYS
    max_age = config.HOME_MAX_MOMENT_AGE_DAYS if max_moment_age_days is None else max_moment_age_days

    # 1. follow-gate — the hard boundary
    followed = resolve_followed_property_ids(user_id, follow_source)
    followed_sorted = sorted(followed)
    trace: dict = {"followed_property_ids": len(followed), "now": now.isoformat(),
                   "today_window_hours": today_window, "future_horizon_days": horizon,
                   "max_moment_age_days": max_age}
    if not followed:
        return CandidatePool(user_id=user_id, followed_property_ids=[], candidates=[],
                             trace={**trace, "raw_pool": 0, "steps": [], "final_pool": 0}, reason="no_follows")

    # 2. traverse to the raw candidate pool (followed → HAS_MOMENT → :Moment)
    raw = generate_followed_candidates(followed, graph)
    trace["raw_pool"] = len(raw)

    # 3. suppression (all hard filters; the calendar/junk cut now also applies the E2 ancient age-gate)
    kept, steps = apply_suppression(raw, suppression, now, today_window, horizon, max_age)

    # 4. per-property cap — RELOCATED to ranking (best-N by score). Default: not applied here.
    if apply_cap:   # legacy/escape hatch only; the ranker owns the cap at launch
        kept, cap_removed = cap_per_property(kept, config.HOME_PER_PROPERTY_CAP)
        steps.append({"step": "per_property_cap(legacy)", "removed": cap_removed, "remaining": len(kept)})
    else:
        steps.append({"step": "per_property_cap", "removed": 0, "remaining": len(kept),
                      "note": "relocated to ranking (best-N by score)"})
    trace["steps"] = steps
    trace["final_pool"] = len(kept)

    reason = None if kept else ("all_suppressed" if raw else "no_moments")
    return CandidatePool(user_id=user_id, followed_property_ids=followed_sorted,
                         candidates=kept, trace=trace, reason=reason)
