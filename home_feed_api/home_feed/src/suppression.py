"""Suppression — all HARD filters applied to the candidate pool BEFORE any ranking.

Each filter is a pure function (list in → list out) so the order is explicit and every step is traceable
(the dry-run prints before/after counts). Suppression removes:
  1. future-dated moments (the "today and not-yet" cut — calendar surface owns those),
  2. seen_ids   (moment ids already shown),
  3. done_ids   (moment ids marked done),
  4. moments of any dismissed_property_id or blocked_property_id,
  5. reacted moments (moment ids the user already reacted to).

Identity seam (filter 5): reaction identity is unresolved (follower user_id INT vs reaction user_id
STRING). So the MECHANISM lives here and is wired to the REQUEST-supplied `reacted_moment_ids`; it
COMPLETES when identity.resolve_user starts returning reaction_user_keys and a resolver populates that
list from public_user_reactions. The filter itself does not change when that lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Set, Tuple

from .candidate import CandidateMoment

_AWARE_MIN = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class SuppressionInputs:
    """All request-supplied suppression signals (moment ids unless noted)."""
    seen_ids: Set[int] = field(default_factory=set)
    done_ids: Set[int] = field(default_factory=set)
    dismissed_property_ids: Set[int] = field(default_factory=set)
    blocked_property_ids: Set[int] = field(default_factory=set)
    reacted_moment_ids: Set[int] = field(default_factory=set)   # request-supplied until identity lands

    @staticmethod
    def from_request(d: dict) -> "SuppressionInputs":
        g = lambda k: {int(x) for x in (d.get(k) or [])}
        return SuppressionInputs(seen_ids=g("seen_ids"), done_ids=g("done_ids"),
                                 dismissed_property_ids=g("dismissed_property_ids"),
                                 blocked_property_ids=g("blocked_property_ids"),
                                 reacted_moment_ids=g("reacted_moment_ids"))


def drop_calendar_and_junk_future(cands: List[CandidateMoment], now: datetime,
                                  today_window_hours: float, horizon_days: float,
                                  max_age_days: float = 0) -> List[CandidateMoment]:
    """The horizon-aware "today and not-yet" + junk-tail cut. ONE pass over BOTH tails + the calendar
    window — no double-handling.

    Drops: the calendar window [now, now+today_window] (surface owns today/not-yet); junk-FUTURE
    (esa > now+horizon, e.g. 2028); and — the E2 hard gate — junk-ANCIENT (esa < now-max_age_days,
    e.g. 1938/1989/old "Launched" moments) when max_age_days > 0. KEEPS: near-future in
    (today_window, horizon] (proximity) and past within the age gate. Null-dated kept.

    The recency clamp only DEPRIORITIZES old moments; THIS gate EXCLUDES the genuinely-junk tail, so a
    property whose only moments are decade-old never lifts one into view (the strict-interleave risk)."""
    today_end = now + timedelta(hours=today_window_hours)
    horizon = now + timedelta(days=horizon_days)
    floor = (now - timedelta(days=max_age_days)) if max_age_days and max_age_days > 0 else None
    out = []
    for c in cands:
        esa = c.event_starts_at
        if esa is None:
            out.append(c); continue
        if now <= esa <= today_end:        # today / not-yet → calendar surface
            continue
        if esa > horizon:                  # junk-future → drop
            continue
        if floor is not None and esa < floor:   # junk-ancient (hard age-gate) → drop
            continue
        out.append(c)                      # past within gate, or near-future (today_end, horizon]
    return out


def drop_moment_ids(cands: List[CandidateMoment], ids: Set[int]) -> List[CandidateMoment]:
    return [c for c in cands if c.moment_id not in ids] if ids else cands


def drop_by_property(cands: List[CandidateMoment], property_ids: Set[int]) -> List[CandidateMoment]:
    return [c for c in cands if c.property_id not in property_ids] if property_ids else cands


def apply_suppression(cands: List[CandidateMoment], inputs: SuppressionInputs, now: datetime,
                      today_window_hours: float, horizon_days: float,
                      max_age_days: float = 0) -> Tuple[List[CandidateMoment], List[dict]]:
    """Apply every hard filter in order; return (kept, trace) where trace is one entry per step."""
    trace: List[dict] = []
    cur = cands

    def step(name: str, kept: List[CandidateMoment]):
        trace.append({"step": name, "removed": len(cur) - len(kept), "remaining": len(kept)})
        return kept

    cur = step("calendar_junk_age_gate", drop_calendar_and_junk_future(cur, now, today_window_hours, horizon_days, max_age_days))
    cur = step("seen_ids", drop_moment_ids(cur, inputs.seen_ids))
    cur = step("done_ids", drop_moment_ids(cur, inputs.done_ids))
    cur = step("dismissed_or_blocked_property",
               drop_by_property(cur, inputs.dismissed_property_ids | inputs.blocked_property_ids))
    cur = step("reacted", drop_moment_ids(cur, inputs.reacted_moment_ids))
    return cur, trace


def cap_per_property(cands: List[CandidateMoment], cap: int) -> Tuple[List[CandidateMoment], int]:
    """Keep at most `cap` moments per property so no property floods the pool. cap<=0 disables.

    INTERIM ORDERING: keeps the most-recent N (event_starts_at desc, moment_id desc) since no ranking
    exists yet. Once the ranker lands, this cap must move to AFTER scoring so we keep a property's BEST
    N, not its newest N (see config.HOME_PER_PROPERTY_CAP)."""
    if cap is None or cap <= 0:
        return list(cands), 0
    by_prop: dict = {}
    for c in cands:
        by_prop.setdefault(c.property_id, []).append(c)
    kept: List[CandidateMoment] = []
    for pid, group in by_prop.items():
        group.sort(key=lambda c: (c.event_starts_at or _AWARE_MIN, c.moment_id), reverse=True)
        kept.extend(group[:cap])
    return kept, len(cands) - len(kept)
