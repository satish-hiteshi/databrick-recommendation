"""In-memory name index over the deploy properties — IDENTITY-FIRST, now with PREFIX (search-as-you-type).

Keyed on **entity_id** (collision-safe: the ~321 cross-vertical guid twins — Game:119163 vs Movie:119163 —
are DISTINCT names, both findable). Each row also carries the numeric ``property_id`` (=source_id) purely for
the engine's source_id-space heuristics (exact-tie-break) and the response — it is NOT the dedup key.

TIERS (the engine ranks them in this order): EXACT (0) > PREFIX (1) > FUZZY (2).
  EXACT   — casefold + strip-punctuation string equality OR full token-SET equality → relevance 1.0.
  PREFIX  — match-boolean-prefix (how ES/Algolia do multi-word autocomplete): every query token but the
            LAST must be a name token; the LAST token is a PREFIX of a name token. Single-token queries
            prefix-match a name's LEADING token. Ranked by a high base + a COMPLETENESS factor (how much of
            the name the query covers) so a near-complete match ("fortni"→Fortnite) beats a longer partial.
            ADMISSION GATE: a candidate enters this tier only if completeness ≥ PREFIX_MIN_COMPLETENESS, so a
            short CONCEPT word that coincidentally prefixes a name ("sci-fi" in "Sci-Fi Radio") does NOT get
            boosted above thematic genre results — it falls through to fuzzy/thematic instead.
            Built from edge-token structures at startup (bisect over sorted distinct tokens; no per-query DB).
  FUZZY   — token score (max of token_sort/token_set) with a query-coverage + length-aware guard; typo
            tolerance for fully-typed words. Floored at NAME_FUZZY_MIN.
ALIAS/slug remains reserved-not-implemented (no alias table; :Entity carries no slug).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from . import config

_NONALNUM = re.compile(r"[^a-z0-9]+")
_TIER = {"exact": 0, "prefix": 1, "fuzzy_typo": 2, "fuzzy": 2}   # fuzzy_typo = a whole-name typo (Fix 2)


def _norm(s: str) -> str:
    """casefold + non-alphanumeric→space + collapse whitespace (punctuation/spacing-invariant key)."""
    return " ".join(_NONALNUM.sub(" ", (s or "").casefold()).split())


def _fuzzy_kind(qn: str, nn: str, allow_typo: bool) -> str:
    """Whole-name TYPO (promotable above thematic, Fix 2) vs plain fuzzy. Two structural conditions:
      • allow_typo: the query prefixes NO real name (so a fuzzy near-match is a genuine misspelling, not a
        partial/concept). "fortnight" prefixes no name → allowed; "elden" prefixes "Elden Ring" and "cooking"
        prefixes "Cooking Companions" → NOT allowed, so coincidental near-words ("Eden","Looking") stay plain
        fuzzy. This is what separates a typo from a coincidence — a numeric gate cannot (Eden pop 0.966/rel 0.889
        DOMINATES the real Fortnite 0.846/0.824 on every axis).
      • completeness: the query covers ~the whole name (a typo of the whole title, not a token inside it)."""
    if not allow_typo:
        return "fuzzy"
    completeness = min(1.0, len(qn) / max(1, len(nn)))
    return "fuzzy_typo" if completeness >= config.FUZZY_TYPO_MIN_COMPLETENESS else "fuzzy"


@dataclass(slots=True)
class NameHit:
    entity_id: str            # PRIMARY identity + the index dedup key (collision-safe)
    property_id: int          # source_id (=media_source_guid); source_id-space heuristics + response only, NOT the key
    name: str
    vertical: str
    relevance: float          # 0..1 (exact = 1.0; prefix ~0.7..1.0; fuzzy ≥ floor)
    match_type: str           # "exact" | "prefix" | "fuzzy"


# a stored row: (entity_id, source_id, name, vertical)
_Row = Tuple[str, int, str, str]


class NameIndex:
    def __init__(self, entries: List[_Row], pop_map: Optional[Dict[str, float]] = None) -> None:
        """entries: (entity_id, source_id, name, vertical) for the deploy set — keyed on entity_id.
        pop_map: optional {entity_id: popularity_pct} used ONLY to cap the prefix pool by popularity."""
        self._pop_map = pop_map or {}
        self.exact_str: Dict[str, List[_Row]] = {}            # norm string → rows
        self.exact_set: Dict[frozenset, List[_Row]] = {}      # token-set → rows
        self.norm_names: List[str] = []
        self.meta: List[_Row] = []
        self._token_to_idx: Dict[str, List[int]] = {}                        # name token → meta indices
        self._first_to_idx: Dict[str, List[int]] = {}                        # leading token → meta indices
        for eid, sid, name, vert in entries:
            n = _norm(name)
            if not n:
                continue
            idx = len(self.meta)
            row: _Row = (eid, sid, name, vert)
            self.exact_str.setdefault(n, []).append(row)
            self.exact_set.setdefault(frozenset(n.split()), []).append(row)
            self.norm_names.append(n)
            self.meta.append(row)
            toks = n.split()
            for t in set(toks):
                self._token_to_idx.setdefault(t, []).append(idx)
            self._first_to_idx.setdefault(toks[0], []).append(idx)
        # sorted distinct tokens for prefix bisect (radix-style range scan)
        self._sorted_tokens: List[str] = sorted(self._token_to_idx.keys())
        self._sorted_first: List[str] = sorted(self._first_to_idx.keys())
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

    # ── fuzzy helpers (unchanged) ──────────────────────────────────────────────
    def _ratio(self, a: str, b: str) -> float:
        if self._fuzz:
            return self._fuzz.ratio(a, b) / 100.0
        import difflib
        return difflib.SequenceMatcher(None, a, b).ratio()

    def _query_coverage(self, qtoks, ntoks) -> float:
        if not qtoks:
            return 0.0
        covered = sum(1 for qt in qtoks
                      if any(self._ratio(qt, nt) >= config.NAME_COVERAGE_TOKEN_MIN for nt in ntoks))
        return covered / len(qtoks)

    def _fuzzy_score(self, qn: str, nn: str) -> float:
        qtoks, ntoks = qn.split(), nn.split()
        if self._query_coverage(qtoks, ntoks) < config.NAME_QUERY_COVERAGE_MIN:
            return 0.0
        if self._fuzz:
            sort_r = self._fuzz.token_sort_ratio(qn, nn) / 100.0
            set_r = self._fuzz.token_set_ratio(qn, nn) / 100.0
        else:
            import difflib
            sort_r = difflib.SequenceMatcher(None, " ".join(sorted(qtoks)), " ".join(sorted(ntoks))).ratio()
            set_r = sort_r
        score = max(sort_r, set_r)
        if set_r >= sort_r + config.FUZZY_SET_SORT_GAP and sort_r < config.FUZZY_GUARD_SORT_MIN:
            score = sort_r
        return score

    # ── prefix helpers ─────────────────────────────────────────────────────────
    def _idxs_with_token_prefix(self, sorted_tokens: List[str], token_map: Dict[str, List[int]],
                                prefix: str) -> Set[int]:
        """Meta indices of names having a (leading, if token_map is first-token) token starting with `prefix`."""
        out: Set[int] = set()
        i = bisect.bisect_left(sorted_tokens, prefix)
        while i < len(sorted_tokens) and sorted_tokens[i].startswith(prefix):
            out.update(token_map[sorted_tokens[i]])
            i += 1
        return out

    def _prefix_candidate_idxs(self, qn: str) -> Set[int]:
        qtoks = qn.split()
        if not qtoks:
            return set()
        last = qtoks[-1]
        if len(qtoks) == 1:                                   # single token → prefix of the name's LEADING token
            return self._idxs_with_token_prefix(self._sorted_first, self._first_to_idx, last)
        # multi-token: names containing ALL non-last tokens (exact) AND a token starting with `last`
        non_last_sets = [set(self._token_to_idx.get(t, ())) for t in qtoks[:-1]]
        if any(not s for s in non_last_sets):                 # a completed token isn't a name token anywhere
            return set()
        common = set.intersection(*non_last_sets)
        if not common:
            return set()
        last_idxs = self._idxs_with_token_prefix(self._sorted_tokens, self._token_to_idx, last)
        return common & last_idxs

    # ── lookup ──────────────────────────────────────────────────────────────────
    def lookup(self, query: str, pool: int = None) -> List[NameHit]:
        pool = pool or config.NAME_FUZZY_POOL
        qn = _norm(query)
        if len(qn) < config.NAME_MIN_QUERY_LEN:              # too short (guards "a"); also the prefix floor
            return []
        best: Dict[str, NameHit] = {}                        # entity_id → hit (collision-safe dedup)
        # ── EXACT (tier 0) ──
        for eid, sid, name, vert in self.exact_str.get(qn, []):
            best[eid] = NameHit(eid, sid, name, vert, 1.0, "exact")
        for eid, sid, name, vert in self.exact_set.get(frozenset(qn.split()), []):
            best.setdefault(eid, NameHit(eid, sid, name, vert, 1.0, "exact"))
        # ── PREFIX (tier 1) — completeness-ranked, popularity-capped ──
        prefix_rows = []
        has_leading_name = False                              # does the query genuinely prefix ANY real name? (Fix 2 typo-gate)
        for idx in self._prefix_candidate_idxs(qn):
            nn = self.norm_names[idx]
            if not nn.startswith(qn):                          # TRUE leading prefix only (search-as-you-type): the name must
                continue                                       # START WITH the query. Kills "the godfather"→"the black godfather"
            has_leading_name = True                            # (a token-subset the match-boolean-prefix logic would otherwise admit).
            eid, sid, name, vert = self.meta[idx]
            if eid in best:                                   # already exact → exact wins
                continue
            completeness = min(1.0, len(qn) / max(1, len(nn)))
            if completeness < config.PREFIX_MIN_COMPLETENESS:  # concept-word coincidentally a name-prefix → keep OUT of the prefix tier
                continue                                       # (may still surface via fuzzy/thematic, just not boosted above genre)
            rel = round(config.PREFIX_BASE_RELEVANCE + config.PREFIX_COMPLETENESS_WEIGHT * completeness, 4)
            prefix_rows.append((self._pop_map.get(eid, 0.0), rel, eid, sid, name, vert))
        prefix_rows.sort(key=lambda r: (-r[0], -r[1], r[2]))  # keep the most POPULAR (then most complete), tie → entity_id
        for _pop, rel, eid, sid, name, vert in prefix_rows[: config.PREFIX_POOL]:
            best.setdefault(eid, NameHit(eid, sid, name, vert, rel, "prefix"))
        # ── FUZZY (tier 2) — never overrides an exact/prefix hit ──
        allow_typo = not has_leading_name                    # a query that prefixes a real name is a partial/concept, not a typo
        if self._process:
            for _n, _s, idx in self._process.extract(qn, self.norm_names,
                                                     scorer=self._fuzz.token_set_ratio, limit=pool):
                eid, sid, name, vert = self.meta[idx]
                if eid in best and best[eid].match_type in ("exact", "prefix"):
                    continue
                nn = self.norm_names[idx]
                rel = self._fuzzy_score(qn, nn)
                if rel < config.NAME_FUZZY_MIN:
                    continue
                mt = _fuzzy_kind(qn, nn, allow_typo)            # "fuzzy_typo" (whole-name typo) vs "fuzzy" (Fix 2)
                if eid not in best or best[eid].relevance < rel:
                    best[eid] = NameHit(eid, sid, name, vert, round(rel, 4), mt)
        else:
            import difflib
            for n in difflib.get_close_matches(qn, self.norm_names, n=pool, cutoff=config.NAME_FUZZY_MIN):
                idx = self.norm_names.index(n)
                eid, sid, name, vert = self.meta[idx]
                if eid in best:
                    continue
                rel = self._fuzzy_score(qn, n)
                if rel >= config.NAME_FUZZY_MIN:
                    best[eid] = NameHit(eid, sid, name, vert, round(rel, 4), _fuzzy_kind(qn, n, allow_typo))
        # BREAK-3 FIX (dominance): a genuine whole-name TYPO resolves to ONE title; a coincidental token-overlap
        # ("the last of us"→{The Story of Us, The Rest of Us}, "the bear movie"→{X/ABBA/Bluey: The Movie}) marks
        # SEVERAL distinct names as fuzzy_typo. If more than the allowed number of DISTINCT names carry the mark,
        # none earn promotion above thematic → demote them all back to plain fuzzy.
        typo_names = {_norm(h.name) for h in best.values() if h.match_type == "fuzzy_typo"}
        if len(typo_names) > config.FUZZY_TYPO_MAX_DISTINCT_NAMES:
            for h in best.values():
                if h.match_type == "fuzzy_typo":
                    h.match_type = "fuzzy"
        # tier order (exact > prefix > fuzzy), then relevance, then a DETERMINISTIC entity_id tie-break
        # (was source_id; entity_id also distinguishes the collision twins that share a source_id).
        return sorted(best.values(),
                      key=lambda h: (_TIER.get(h.match_type, 2), -h.relevance, h.entity_id))
