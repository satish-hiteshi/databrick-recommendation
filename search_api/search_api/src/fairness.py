"""Cross-vertical fairness (UC7 Story 3) — no single vertical dominates a multi-vertical thematic result.

RULE (config-driven):
  - If the request pins exactly ONE vertical → no cap (explicit single-vertical intent).
  - Else if one vertical is ≥ FAIRNESS_SINGLE_VERTICAL_DOMINANCE (0.9) of the top probe window → the query
    is clearly single-vertical (e.g. a game-name search that's all games) → no cap.
  - Else cap each vertical at ceil(limit * FAIRNESS_MAX_VERTICAL_SHARE) (0.5 → ≤10 of 20). Walk the
    score-sorted list; overflow of a capped vertical is DEFERRED, and only used to backfill if there aren't
    enough other-vertical results to fill `limit` (never drop a result just to enforce the cap).
So "sci-fi" returns a games/tv/podcast/movie spread, not 20 movies; a single-vertical query is untouched.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import List, Sequence, Tuple

from . import config


def apply_fairness(scored_sorted: List, limit: int, requested_verticals: Sequence[str],
                   force_spread: bool = False) -> Tuple[List, dict]:
    if len(requested_verticals) == 1:                       # explicit filter always respected (even onboarding)
        out = scored_sorted[:limit]
        return out, {"applied": False, "reason": "single_vertical_filter",
                     "vertical_counts": dict(Counter(r.vertical for r in out))}

    probe = scored_sorted[: max(limit, 10)]
    # UC4: a one-vertical-dominant probe is a name/franchise query → keep it (no off-topic verticals injected).
    # UC7 onboarding (force_spread): skip this exemption so the cap applies and the feed spreads (Story 3).
    if probe and not force_spread:
        top_v, top_n = Counter(r.vertical for r in probe).most_common(1)[0]
        if top_n / len(probe) >= config.FAIRNESS_SINGLE_VERTICAL_DOMINANCE:
            out = scored_sorted[:limit]
            return out, {"applied": False, "reason": f"single_vertical_intent:{top_v}",
                         "vertical_counts": dict(Counter(r.vertical for r in out))}

    cap = max(1, math.ceil(limit * config.FAIRNESS_MAX_VERTICAL_SHARE))
    out: List = []
    counts: Counter = Counter()
    deferred: List = []
    for r in scored_sorted:
        if len(out) < limit and counts[r.vertical] < cap:
            out.append(r); counts[r.vertical] += 1
        else:
            deferred.append(r)
    if len(out) < limit:                          # not enough spread → backfill in score order (never drop)
        for r in deferred:
            if len(out) >= limit:
                break
            out.append(r)
    return out, {"applied": True, "cap_per_vertical": cap,
                 "vertical_counts": dict(Counter(r.vertical for r in out))}
