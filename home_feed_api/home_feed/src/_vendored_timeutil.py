"""Time parsing + soft-recency helpers — VENDORED from Endpoint 2 to DECOUPLE E3 from E2.

Provenance: copied from endpoint_2_discovery_api/local_code/discovery_api/src/timeutil.py. The E2
original is NOT byte-verbatim importable here because it does `from . import config` — i.e. it depends
on E2's config object (for `config.RECENCY_HALFLIFE_DAYS` in recency_score's fallback arm and
`config.DEFAULT_NOW_ISO` in now()). To keep E3 self-contained (importing NOTHING from
endpoint_2/discovery_api), the ONLY change vs the original is repointing that import to E3's own config
(`from . import config`, resolving to home_feed.src.config), which now carries the two mirrored
constants (RECENCY_HALFLIFE_DAYS, DEFAULT_NOW_ISO) with E2's exact defaults. Every function body is
otherwise identical. E3 uses only parse_ts() and recency_score() (and always passes an explicit
halflife), so behaviour is unchanged.

event_starts_at is the ONLY recency key (ISO-8601, 'Z')."""

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from . import config


def parse_ts(s) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp like '2026-05-29T07:35:18.000Z' -> aware datetime (UTC).
    Returns None for '', 'null', None, or anything unparseable (defensive: dev data has 'null' strings)."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() == "null":
        return None
    try:
        # Python 3.10's fromisoformat doesn't accept a trailing 'Z'
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def now() -> datetime:
    """Reference 'now' — config.DEFAULT_NOW_ISO if set (reproducible dev runs over June-2026 data),
    else the wall clock. Always UTC-aware."""
    if config.DEFAULT_NOW_ISO:
        ts = parse_ts(config.DEFAULT_NOW_ISO)
        if ts is not None:
            return ts
    return datetime.now(timezone.utc)


def age_days(ts: Optional[datetime], ref: Optional[datetime] = None) -> Optional[float]:
    """Signed age in days: positive = in the past, negative = upcoming. None if ts is None."""
    if ts is None:
        return None
    ref = ref or now()
    return (ref - ts).total_seconds() / 86400.0


def recency_score(ts: Optional[datetime], ref: Optional[datetime] = None,
                  halflife_days: Optional[float] = None) -> float:
    """Soft freshness in (0,1], peaking at `ref` and decaying smoothly in BOTH directions (recent-past
    AND near-future both count as fresh — a discovery feed surfaces just-dropped and imminent events).
    No hard cutoff: old moments score low but are never dropped here. Returns 0.0 for an unknown ts."""
    if ts is None:
        return 0.0
    hl = halflife_days or config.RECENCY_HALFLIFE_DAYS
    a = abs(age_days(ts, ref) or 0.0)
    return math.exp(-math.log(2) * a / hl) if hl > 0 else (1.0 if a == 0 else 0.0)


def within_window(ts: Optional[datetime], window_days: Optional[float], ref: Optional[datetime] = None) -> bool:
    """True if ts is within the last `window_days` up to `ref` (for velocity counts). window_days None = all-time."""
    if ts is None:
        return False
    if window_days is None:
        return True
    ref = ref or now()
    return timedelta(0) <= (ref - ts) <= timedelta(days=window_days)
