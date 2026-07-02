"""In-memory name index over the 44k deploy properties — IDENTITY-FIRST (v1.3.1 quality fix).

UC4 Story 1 requires the canonical entity to rank #1 for a clean name. So name relevance is TIERED:
  EXACT   — casefold + strip-punctuation string equality OR full token-SET equality → relevance 1.0,
            match_type "exact". (Word-order/punctuation invariant; a sequel/edition with extra tokens is
            NOT exact.) The engine ranks the exact tier ABOVE all non-exact, regardless of centrality.
  FUZZY   — token score = max(token_sort_ratio, token_set_ratio) with a LENGTH-AWARE GUARD: when the
            token-set "subset" bonus is not supported by the order-sensitive token_sort score
            (set − sort ≥ GAP and sort < GUARD_MIN), the subset is a partial-overlap (e.g. the single word
            "Ring" shared by "Elden Ring" and "Dark Side of the Ring") → distrust it, fall back to
            token_sort. Floor at NAME_FUZZY_MIN. This is what stops partial-word distractors.
ALIAS/slug remains reserved-not-implemented (no alias table; :Entity carries no slug).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from . import config

_NONALNUM = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    """casefold + non-alphanumeric→space + collapse whitespace (punctuation/spacing-invariant key)."""
    return " ".join(_NONALNUM.sub(" ", (s or "").casefold()).split())


@dataclass(slots=True)
class NameHit:
    property_id: int
    name: str
    vertical: str
    relevance: float          # 0..1 (exact = 1.0)
    match_type: str           # "exact" | "fuzzy"


class NameIndex:
    def __init__(self, entries: List[Tuple[int, str, str]]) -> None:
        """entries: (property_id, name, vertical) for the 44k deploy set."""
        self.exact_str: Dict[str, List[Tuple[int, str, str]]] = {}            # norm string → rows
        self.exact_set: Dict[frozenset, List[Tuple[int, str, str]]] = {}      # token-set → rows
        self.norm_names: List[str] = []
        self.meta: List[Tuple[int, str, str]] = []
        for pid, name, vert in entries:
            n = _norm(name)
            if not n:
                continue
            self.exact_str.setdefault(n, []).append((pid, name, vert))
            self.exact_set.setdefault(frozenset(n.split()), []).append((pid, name, vert))
            self.norm_names.append(n)
            self.meta.append((pid, name, vert))
        try:
            from rapidfuzz import fuzz, process
            self._fuzz, self._process = fuzz, process
        except Exception:
            self._fuzz = self._process = None

    @property
    def size(self) -> int:
        return len(self.meta)

    @property
    def backend(self) -> str:
        return "rapidfuzz" if self._fuzz else "difflib"

    def _ratio(self, a: str, b: str) -> float:
        if self._fuzz:
            return self._fuzz.ratio(a, b) / 100.0
        import difflib
        return difflib.SequenceMatcher(None, a, b).ratio()

    def _query_coverage(self, qtoks, ntoks) -> float:
        """Fraction of QUERY tokens that have a char-close (≥ token-min) match among the NAME tokens.
        Allows per-token misspelling ('eldn'~'elden') but rejects fragment matches where the name is
        missing query tokens ('Stardew Valley'→'Valley' covers only 1/2)."""
        if not qtoks:
            return 0.0
        covered = sum(1 for qt in qtoks
                      if any(self._ratio(qt, nt) >= config.NAME_COVERAGE_TOKEN_MIN for nt in ntoks))
        return covered / len(qtoks)

    def _fuzzy_score(self, qn: str, nn: str) -> float:
        """Token score, gated by query-coverage + the length-aware guard. Inputs already normalized."""
        qtoks, ntoks = qn.split(), nn.split()
        if self._query_coverage(qtoks, ntoks) < config.NAME_QUERY_COVERAGE_MIN:
            return 0.0                                    # name is a fragment of the query → not an identity match
        if self._fuzz:
            sort_r = self._fuzz.token_sort_ratio(qn, nn) / 100.0
            set_r = self._fuzz.token_set_ratio(qn, nn) / 100.0
        else:
            import difflib
            sort_r = difflib.SequenceMatcher(None, " ".join(sorted(qtoks)), " ".join(sorted(ntoks))).ratio()
            set_r = sort_r
        score = max(sort_r, set_r)
        # length-aware guard: a set-subset bonus the order-sensitive score doesn't support = partial overlap
        if set_r >= sort_r + config.FUZZY_SET_SORT_GAP and sort_r < config.FUZZY_GUARD_SORT_MIN:
            score = sort_r
        return score

    def lookup(self, query: str, pool: int = None) -> List[NameHit]:
        pool = pool or config.NAME_FUZZY_POOL
        qn = _norm(query)
        if len(qn) < config.NAME_MIN_QUERY_LEN:      # too short for an identity match (guards "a")
            return []
        best: Dict[int, NameHit] = {}
        # ── EXACT tier: normalized string equality OR token-set equality ──
        for pid, name, vert in self.exact_str.get(qn, []):
            best[pid] = NameHit(pid, name, vert, 1.0, "exact")
        for pid, name, vert in self.exact_set.get(frozenset(qn.split()), []):
            best.setdefault(pid, NameHit(pid, name, vert, 1.0, "exact"))
        # ── FUZZY tier: broad rapidfuzz pool, re-scored with the guarded fn, floored ──
        if self._process:
            for _n, _s, idx in self._process.extract(qn, self.norm_names,
                                                     scorer=self._fuzz.token_set_ratio, limit=pool):
                pid, name, vert = self.meta[idx]
                if pid in best and best[pid].match_type == "exact":
                    continue
                rel = self._fuzzy_score(qn, self.norm_names[idx])
                if rel < config.NAME_FUZZY_MIN:
                    continue
                if pid not in best or best[pid].relevance < rel:
                    best[pid] = NameHit(pid, name, vert, round(rel, 4), "fuzzy")
        else:
            import difflib
            for n in difflib.get_close_matches(qn, self.norm_names, n=pool, cutoff=config.NAME_FUZZY_MIN):
                idx = self.norm_names.index(n)
                pid, name, vert = self.meta[idx]
                if pid in best:
                    continue
                rel = self._fuzzy_score(qn, n)
                if rel >= config.NAME_FUZZY_MIN:
                    best[pid] = NameHit(pid, name, vert, round(rel, 4), "fuzzy")
        # exact tier first, then fuzzy by relevance
        return sorted(best.values(),
                      key=lambda h: (0 if h.match_type == "exact" else 1, -h.relevance, h.property_id))
