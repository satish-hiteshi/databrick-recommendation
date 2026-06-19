"""Per-vertical influence normalization (DATA PREP — not the scorer).

Raw PageRank `influence` scales differ per vertical (games higher; podcasts heavy-tailed, max ~6.46 vs
~3.0-3.3 for game/movie/tv). We convert raw influence to a 0-1 PER-VERTICAL PERCENTILE rank, after
clamping each vertical's upper tail at p95 (config.INFLUENCE_CLIP_PCT) so a handful of outliers can't
dominate a linear popularity term in P4.

Properties (verified by the unit test):
  - a vertical's MEDIAN raw influence maps to ~0.5 (percentile rank is symmetric),
  - the podcast tail is CLIPPED: the 6.46 outlier maps to the same top value as p95 (≈0.97), not to a
    value reflecting 6.46×.

Exposes normalized_influence(entity_id) -> 0..1 and community(entity_id).
"""

from __future__ import annotations

import bisect
from typing import Dict, Iterable, List, Optional

import numpy as np

from .. import config
from ..data_access.records import GdsSignal


class PopularityIndex:
    def __init__(self, signals: Iterable[GdsSignal], clip_pct: Optional[float] = None):
        self.clip_pct = clip_pct if clip_pct is not None else config.INFLUENCE_CLIP_PCT
        self._raw: Dict[str, float] = {}
        self._community: Dict[str, Optional[int]] = {}
        self._vertical: Dict[str, str] = {}
        by_vertical: Dict[str, List[float]] = {}
        for s in signals:
            self._community[s.entity_id] = s.community
            self._vertical[s.entity_id] = s.vertical
            if s.influence is not None:
                self._raw[s.entity_id] = float(s.influence)
                by_vertical.setdefault(s.vertical, []).append(float(s.influence))
        # per-vertical clip value (p95) + the clipped, sorted distribution for percentile-rank lookups
        self._clip_value: Dict[str, float] = {}
        self._sorted_clipped: Dict[str, np.ndarray] = {}
        for v, vals in by_vertical.items():
            arr = np.asarray(vals, dtype=float)
            cv = float(np.percentile(arr, self.clip_pct)) if arr.size else 0.0
            self._clip_value[v] = cv
            self._sorted_clipped[v] = np.sort(np.minimum(arr, cv))

    @classmethod
    def from_data_source(cls, data_source, clip_pct: Optional[float] = None) -> "PopularityIndex":
        return cls(data_source.iter_gds_signals(), clip_pct=clip_pct)

    # ── lookups ─────────────────────────────────────────────────────────
    def raw_influence(self, entity_id: str) -> Optional[float]:
        return self._raw.get(entity_id)

    def community(self, entity_id: str) -> Optional[int]:
        return self._community.get(entity_id)

    def normalized_influence(self, entity_id: str) -> Optional[float]:
        """0-1 per-vertical percentile rank of the (p95-clipped) influence. None if unknown/unscored."""
        v = self._vertical.get(entity_id)
        raw = self._raw.get(entity_id)
        if v is None or raw is None or v not in self._sorted_clipped:
            return None
        return self._rank(v, raw)

    def _rank(self, vertical: str, raw_value: float) -> float:
        arr = self._sorted_clipped[vertical]
        n = arr.size
        if n == 0:
            return 0.0
        clipped = min(raw_value, self._clip_value[vertical])
        lo = bisect.bisect_left(arr, clipped)
        hi = bisect.bisect_right(arr, clipped)
        return (lo + hi) / 2.0 / n         # midpoint rank → median ≈ 0.5

    # ── diagnostics (tests / report) ────────────────────────────────────
    def verticals(self) -> List[str]:
        return list(self._sorted_clipped.keys())

    def vertical_stats(self) -> Dict[str, dict]:
        """Per-vertical sanity numbers for the report/test (raw median, p95 clip, normalized median/max)."""
        out = {}
        for v, arr in self._sorted_clipped.items():
            raw_vals = [self._raw[e] for e, vv in self._vertical.items()
                        if vv == v and e in self._raw]
            raw_med = float(np.median(raw_vals)) if raw_vals else 0.0
            raw_max = float(np.max(raw_vals)) if raw_vals else 0.0
            out[v] = {
                "n": len(raw_vals),
                "raw_median": round(raw_med, 4),
                "raw_max": round(raw_max, 4),
                "clip_p{:.0f}".format(self.clip_pct): round(self._clip_value[v], 4),
                "norm_median": round(self._rank(v, raw_med), 4),
                "norm_max": round(self._rank(v, raw_max), 4),   # clipped → ~0.97, NOT reflecting the outlier
            }
        return out
