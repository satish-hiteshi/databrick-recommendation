"""Recency + proximity — the real clamp that replaces prompt-3's blunt "drop all future".

event_starts_at spans 1902→2028 with junk at both tails. We split time into:
  PAST (esa <= now)              → recency: smooth exp decay (~30-day half-life). Ancient (1902) decays
                                    to ~0, never negative, never errors. Reuses E2 timeutil's decay shape.
  NEAR-FUTURE ((now, horizon])   → recency≈0 (a future event is not "recent"); PROXIMITY carries it,
                                    peaking ~1-7 days out and tapering to 0 by the horizon.
  JUNK-FUTURE (> horizon, e.g. 2028) → both 0 (clamped, never "freshest").
  NULL esa                       → recency = HOME_RECENCY_NULL (defensive; our nodes are populated).

COORDINATION WITH PROMPT-3 SUPPRESSION (no double-handling): suppression now drops the calendar window
[now, now+TODAY_WINDOW] and junk-future (esa > now+HORIZON) BEFORE ranking. So at ranking time the pool
is {past} ∪ {near-future in (TODAY_WINDOW, HORIZON]}. The clamps below are still applied defensively so
recency/proximity are correct even if suppression is reconfigured.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from . import config
from .reuse import timeutil   # E2 exp-decay recency (past arm) + age helpers


def recency_score(event_starts_at: Optional[datetime], now: datetime,
                  halflife_days: Optional[float] = None) -> float:
    """Past-recency in [0,1]: 0.5 ** (age_days / halflife). Future/null clamped (proximity owns future)."""
    if event_starts_at is None:
        return config.HOME_RECENCY_NULL
    if event_starts_at > now:
        return config.HOME_RECENCY_FUTURE
    hl = config.HOME_RECENCY_HALFLIFE_DAYS if halflife_days is None else halflife_days
    return float(timeutil.recency_score(event_starts_at, now, hl))     # exp decay; ancient → ~0, never <0


def is_anchor_moment(vertical: Optional[str], moment_kind: Optional[str]) -> bool:
    """Is this moment a RELEASE ANCHOR (release/trailer/reveal) rather than a genuine EVENT (episode drop,
    video publish)? Anchors get symmetric proximity + no age gate; events keep decay + the gate.
    Gated by HOME_VERTICAL_AWARE_RECENCY — OFF ⇒ always False ⇒ current behaviour (byte-identical).
    Classify by the moment KIND (Moment.profile_key): a kind containing an event marker ('episode'/'video')
    is an EVENT; else an ANCHOR. If the kind is missing, fall back to vertical (podcast ⇒ event, else anchor)."""
    if not config.HOME_VERTICAL_AWARE_RECENCY:
        return False
    kind = (moment_kind or "").lower()
    if kind:
        return not any(mk in kind for mk in config.HOME_EVENT_MOMENT_MARKERS)
    return (vertical or "").lower() != "podcast"


def anchor_proximity_score(event_starts_at: Optional[datetime], now: datetime) -> float:
    """Symmetric proximity to a release ANCHOR, in [floor, 1]. Peaks (→1) at the anchor date and decays
    BOTH ways with HOME_ANCHOR_HALFLIFE_DAYS — a recently-released OR soon-upcoming title scores high; a
    distant-past catalog title (e.g. a 1946 movie) decays to HOME_ANCHOR_FLOOR (non-zero → ranked DOWN, never
    deleted). Replaces decay-since-release for anchor moments so their temporal signal isn't a flat ~0."""
    if event_starts_at is None:
        return config.HOME_ANCHOR_NULL
    hl = config.HOME_ANCHOR_HALFLIFE_DAYS
    if hl <= 0:
        return 1.0
    delta_days = abs((event_starts_at - now).total_seconds()) / 86400.0
    floor = config.HOME_ANCHOR_FLOOR
    return floor + (1.0 - floor) * (0.5 ** (delta_days / hl))


def proximity_score(event_starts_at: Optional[datetime], now: datetime) -> float:
    """Near-future bump in [0,1]: ramp 0→1 over [0,LO], plateau over [LO,HI], taper 1→0 over [HI,HORIZON].
    Past/null/junk-future → 0."""
    if event_starts_at is None or event_starts_at <= now:
        return 0.0
    d = (event_starts_at - now).total_seconds() / 86400.0
    lo, hi, horizon = (config.HOME_PROXIMITY_PEAK_LO_DAYS, config.HOME_PROXIMITY_PEAK_HI_DAYS,
                       config.HOME_FUTURE_HORIZON_DAYS)
    if d > horizon:
        return 0.0                              # junk-future (defensive; usually already suppressed)
    if d < lo:
        return d / lo if lo > 0 else 1.0        # ramp up to the peak
    if d <= hi:
        return 1.0                              # peak plateau (~1-7 days out)
    return max(0.0, (horizon - d) / (horizon - hi)) if horizon > hi else 0.0   # taper to the horizon
