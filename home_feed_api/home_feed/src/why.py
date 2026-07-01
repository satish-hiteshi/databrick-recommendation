"""why_string + badge — the human-facing "why this moment" line and freshness badge.

why_string is REQUIRED (never null). It's built from the DOMINANT signal in the candidate's score
breakdown: whichever of taste / recency / proximity contributed most (weight × signal). Stubs
(trending/richness) never drive it. A small varied template set per signal avoids a templated feel;
selection is deterministic (moment_id % n) so output is reproducible. Mirrors E2's why/templates idea.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import config
from .candidate import CandidateMoment
from .scorer import HomeWeights, ScoreBreakdown

# Template sets per dominant signal (varied, not random).
_TASTE = ["Because you follow {property}", "Right up your alley: {Vertical}", "From {property}, in your follows"]
_RECENCY = ["New from {property}", "Fresh from {property}", "Just in from {property}"]
_PROXIMITY = ["Coming up from {property}", "Upcoming from {property}", "Soon from {property}"]
_TEMPLATES = {"taste": _TASTE, "recency": _RECENCY, "proximity": _PROXIMITY}


def dominant_signal(b: ScoreBreakdown, weights: HomeWeights) -> str:
    """The signal with the largest weighted contribution among the REAL signals (stubs excluded).
    In 'recent' mode the blend IS recency, so recency dominates by definition."""
    if b.sort_mode == "recent":
        return "recency"
    contrib = {"taste": weights.taste * b.taste,
               "recency": weights.recency * b.recency,
               "proximity": weights.proximity * b.proximity}
    return max(contrib, key=contrib.get)


def why_string(candidate: CandidateMoment, b: ScoreBreakdown, weights: HomeWeights) -> str:
    sig = dominant_signal(b, weights)
    templates = _TEMPLATES[sig]
    tmpl = templates[candidate.moment_id % len(templates)]   # deterministic variety
    return tmpl.format(property=candidate.property_name or "this", Vertical=(candidate.vertical or "").capitalize())


def badge(candidate: CandidateMoment, now: datetime) -> Optional[str]:
    """"NEW" for a genuinely-recent PAST moment (within HOME_BADGE_NEW_DAYS); else None.
    Never "LIVE" (no live signal) or "TRENDING" (trending is a stub)."""
    esa = candidate.event_starts_at
    if esa is None or esa > now:
        return None
    age_days = (now - esa).total_seconds() / 86400.0
    return "NEW" if age_days <= config.HOME_BADGE_NEW_DAYS else None
