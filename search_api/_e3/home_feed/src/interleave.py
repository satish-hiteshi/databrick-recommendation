"""Cross-property diversity interleave — the feed-assembly reorder that breaks the monopoly problem.

Operates on the post-scoring, post-cap ranked list (the cap already bounds how many of a property's
moments are eligible; interleave only REORDERS across properties — it never re-scores and never caps
again). Each item keeps its true blended score; only its final position changes.

Duck-typed on the ScoredCandidate shape (`.candidate.property_id`, `.breakdown.blended`) so this module
has no dependency on ranker (avoids a cycle). Deterministic: ties resolved by the input score order.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import List, Optional

SCORE_ONLY = "score_only"
STRICT_ROUND_ROBIN = "strict_round_robin"
WEIGHTED_INTERLEAVE = "weighted_interleave"
FRESHNESS_TIERED = "freshness_tiered"


def _grouped_in_score_order(scored: List) -> dict:
    """{property_id: [items in score-desc order]} — input is already globally score-sorted."""
    groups: dict = {}
    for sc in scored:
        groups.setdefault(sc.candidate.property_id, []).append(sc)
    return groups


def _cycle_order(groups: dict) -> List[int]:
    """Property cycle order = by each property's BEST moment's blended score (desc), tie property_id."""
    return sorted(groups, key=lambda pid: (-groups[pid][0].breakdown.blended, pid))


def strict_round_robin(scored: List) -> List:
    groups = _grouped_in_score_order(scored)
    order = _cycle_order(groups)
    out: List = []
    depth = max((len(g) for g in groups.values()), default=0)
    for r in range(depth):                       # round r = the r-th best of each property
        for pid in order:
            if r < len(groups[pid]):
                out.append(groups[pid][r])
    return out


def weighted_interleave(scored: List, margin: float) -> List:
    groups = {pid: deque(g) for pid, g in _grouped_in_score_order(scored).items()}
    order = _cycle_order(groups)
    prio = {id(sc): i for i, sc in enumerate(scored)}    # global score priority (smaller = stronger)
    out: List = []
    rr = 0
    while any(groups[pid] for pid in order):
        # next round-robin property (skip exhausted)
        for _ in range(len(order)):
            if groups[order[rr % len(order)]]:
                break
            rr += 1
        rr_pid = order[rr % len(order)]
        rr_cand = groups[rr_pid][0]
        # strongest remaining head anywhere
        best_pid = min((pid for pid in order if groups[pid]), key=lambda p: prio[id(groups[p][0])])
        best_cand = groups[best_pid][0]
        if best_pid != rr_pid and best_cand.breakdown.blended > rr_cand.breakdown.blended + margin:
            out.append(best_cand); groups[best_pid].popleft()     # jump; rr pointer stays (rr_pid still owed)
        else:
            out.append(rr_cand); groups[rr_pid].popleft(); rr += 1
    return out


def _bucket_by_band(scored: List, now: datetime, bands: List[float]) -> List[list]:
    uppers = sorted(bands) + [float("inf")]                  # final band = everything up to the hard gate
    buckets: List[list] = [[] for _ in uppers]
    for sc in scored:                                        # scored is score-desc; preserved within band
        esa = sc.candidate.event_starts_at
        age = (now - esa).total_seconds() / 86400.0 if esa is not None else float("inf")
        for i, u in enumerate(uppers):
            if age <= u:
                buckets[i].append(sc); break
    return buckets


def compute_fairness_quota(active_properties: int, window: int, factor: float,
                           min_quota: int, free_below_active: int = 1) -> Optional[int]:
    """E4 SMOOTHLY-SCALED per-property quota — a continuous function of ACTIVE-property count, no cliff.

    quota = max(min, ceil(window / active · factor)). Monotonic in active: FEWER active properties → LARGER
    quota → looser (a 3-property thin user is barely constrained, Story 4 preserved); MORE active → smaller
    quota → tighter rotation. A one-property difference never flips behavior by more than ±1 (the old
    disable-below-8 cliff that flooded the 7-follow generalist is gone). Returns None only when there is
    nothing to spread (active <= free_below_active, default 1 = a single property)."""
    import math
    if factor <= 0 or active_properties <= max(1, free_below_active):
        return None
    return max(min_quota, math.ceil(window / active_properties * factor))


def _e2_tiered_order(buckets: List[list], band_mode: str, margin: float) -> List:
    """E2 order: within-band spread (taste-safe weighted, or strict), bands freshest-first."""
    spread = strict_round_robin if band_mode == STRICT_ROUND_ROBIN else (lambda b: weighted_interleave(b, margin))
    out: List = []
    for bucket in buckets:
        if bucket:
            out.extend(spread(bucket))
    return out


def _apply_quota_deferral(ordered: List, quota: int, window: int) -> List:
    """E3 fairness quota as a DEFERRAL over the E2 order (Story 3 = quota, not penalty; scores untouched).
    Walk the taste-safe order in windows of `window`; within a window a property may place at most `quota`
    moments — its EXCESS is DEFERRED to lead the next window (spread DOWN the feed), while other properties'
    moments take the freed slots. Relative order is otherwise preserved (so taste/freshness order holds);
    nothing is dropped (deferred items always reappear), so presence is never traded for fairness."""
    pending = deque(ordered)
    out: List = []
    while pending:
        qcount: dict = {}
        placed = 0
        carry: deque = deque()
        while pending and placed < window:
            sc = pending.popleft()
            pid = sc.candidate.property_id
            if qcount.get(pid, 0) < quota:
                out.append(sc); qcount[pid] = qcount.get(pid, 0) + 1; placed += 1
            else:
                carry.append(sc)                             # over quota this window → defer to next
        carry.extend(pending)                                # deferred items lead the next window
        pending = carry
    return out


def freshness_tiered(scored: List, now: datetime, bands: List[float], band_mode: str, margin: float,
                     quota: Optional[int] = None, window: int = 20) -> List:
    """E2 core + E3 fairness quota: spread WITHIN freshness bands, freshest band first (a stale moment is
    never promoted above a fresh one; empty bands skipped = relaxing floor, never empty while scored is
    non-empty). E3: a per-property QUOTA bounds how many moments one property contributes to each visible
    `window`, WITHOUT touching scores (Story 3) — a chatty property's fresh moments spread DOWN the feed
    rather than clustering. Quota=None (thin follows) → pure E2 behavior. Never drops a moment."""
    ordered = _e2_tiered_order(_bucket_by_band(scored, now, bands), band_mode, margin)
    return ordered if quota is None else _apply_quota_deferral(ordered, quota, window)


def interleave(scored: List, mode: str, margin: float = 0.05, *, now: Optional[datetime] = None,
               bands: Optional[List[float]] = None, band_mode: str = STRICT_ROUND_ROBIN,
               quota: Optional[int] = None, window: int = 20) -> List:
    """Reorder the capped ranked list per mode. score_only / empty / singleton → unchanged."""
    if not scored or len(scored) == 1 or mode == SCORE_ONLY:
        return list(scored)
    if mode == STRICT_ROUND_ROBIN:
        return strict_round_robin(scored)
    if mode == WEIGHTED_INTERLEAVE:
        return weighted_interleave(scored, margin)
    if mode == FRESHNESS_TIERED:
        return freshness_tiered(scored, now, bands or [30.0, 90.0, 365.0], band_mode, margin, quota, window)
    return list(scored)                          # unknown mode → safe passthrough (score order)
