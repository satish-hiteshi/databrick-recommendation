"""SearchEngine — the orchestrator for UC4 + UC7.

startup (once): bridge (44k property_id<->entity_id), Postgres store (popularity+centrality), thematic
ANN index (parquet matrix), Qwen embedder, follow gate, and the in-memory NAME index.
per request: route (name | thematic | auto[both]) -> score (per-(mode,vertical) weights) -> exclude
followed -> dedup (composite) -> sort -> cross-vertical fairness -> serialize. Properties only.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set, Tuple

try:
    from shared import identity as _ident                # repo-root layout (local dev tree)
except ImportError:
    try:
        from . import _identity as _ident                # vendored copy (serving bundle)
    except ImportError:
        import _identity as _ident

_log = logging.getLogger("search_api.engine")

from . import config
from .bridge import build_bridge
from .dedup import collapse_duplicates
from .embed import EmbedUnavailable, QwenQueryEmbedder
from .fairness import apply_fairness
from .follows import FollowGate
from .name_index import NameIndex, _norm
from .ranking import SearchResult, minmax_relevance, score_result
from .serializer import build_envelope
from .store import load_store
from .thematic import ThematicIndex
from .vertical_intent import detect_verticals


class SearchEngine:
    def __init__(self) -> None:
        self.bridge = build_bridge(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD,
                                   config.NEO4J_DATABASE)
        self.store = load_store()
        self.thematic = ThematicIndex().load()
        self.embedder = QwenQueryEmbedder()
        self.follow_gate = FollowGate()
        # NAME index over the bridge properties, keyed on ENTITY_ID (collision-safe: every entity in the
        # bridge is searchable — the ~321 cross-vertical guid twins are distinct names, both findable; the old
        # source_id key silently dropped one of each pair). source_id is carried per row for the engine's
        # source_id-space tie-break + the response. Names from property_popularity (entity_id-keyed), fallback graph.
        entries: List[Tuple[str, int, str, str]] = []
        pop_map: dict = {}
        for eid, meta in self.bridge.meta.items():
            pr = self.store.popularity.get(eid)          # entity_id-keyed store (collision-safe)
            name = (pr.name if pr else None) or meta.get("name")
            vert = (pr.vertical if pr else None) or meta.get("vertical") or "unknown"
            if name:
                entries.append((eid, self.bridge.eid2guid.get(eid, 0), name, vert))
                pop_map[eid] = self.store.popularity_pct(eid)   # caps the prefix pool by popularity
        self.name_index = NameIndex(entries, pop_map=pop_map)
        # CATALOG CROSS-CHECK signal (Fix 1c): norm_name → max popularity_pct among UNBRIDGED catalog entities
        # (the 9,562 in property_popularity but not bridged). Used ONLY to suppress a coincidental confident
        # PREFIX pin when the user clearly typed a famous title we can't serve. These entities NEVER enter results.
        bridged_eids = set(self.bridge.meta.keys())
        self.catalog_unbridged_pop: dict = {}
        for eid, row in self.store.popularity.items():   # entity_id-keyed store (unbridged catalog cross-check)
            if eid in bridged_eids or not row.name:
                continue
            nm = _norm(row.name)
            if nm and row.popularity_pct > self.catalog_unbridged_pop.get(nm, -1.0):
                self.catalog_unbridged_pop[nm] = row.popularity_pct

    # ── health ────────────────────────────────────────────────────────────────
    def health(self) -> dict:
        return {"status": "ok", "endpoint": config.ENDPOINT_LABEL, "engine": config.ENGINE_LABEL,
                "bridge_properties": self.bridge.size, "name_index_size": self.name_index.size,
                "name_backend": self.name_index.backend, "thematic_vectors": self.thematic.size,
                "popularity_rows": len(self.store.popularity_by_sid), "centrality_rows": len(self.store.centrality_by_sid),
                "qwen_embed_available": self.embedder.available, **config.summary()}

    # ── follow-set resolution (raw follow keys → served entity_ids, collision-safe) ──────────────
    def _resolve_followed_entity_ids(self, raw_keys) -> Set[str]:
        """Normalise raw follow keys → SERVED entity_ids. entity_id/composite is coerced (no I/O) and kept
        iff bridged; a bare source_id is resolved via the bridge's source_id→entity_id map (collision-lossy
        — the shim keeps the last vertical). Legacy PUBLIC ids simply won't resolve (dropped)."""
        out: Set[str] = set()
        for k in (raw_keys or []):
            eid = _ident.coerce_to_entity_id(k)
            if eid is not None:
                if eid in self.bridge.meta:
                    out.add(eid)
                continue
            try:
                gi = int(str(k).strip())
            except (TypeError, ValueError):
                continue
            # bare source_id: resolve against the SERVED candidate entity_ids. A bare guid that maps to >1
            # served vertical (the ~321 cross-vertical collisions) is AMBIGUOUS → warn + drop so the caller
            # re-supplies the entity_id/composite (matches E3/E6/E8). Exactly one served vertical → resolve it.
            served = [c for c in _ident.candidate_entity_ids(gi) if c in self.bridge.meta]
            if len(served) == 1:
                out.add(served[0])
            elif len(served) > 1:
                _log.warning("ambiguous bare follow id %r resolves to %s across verticals; send the "
                             "entity_id/composite form to disambiguate — dropped", gi, served)
            else:
                hit = self.bridge.guid2eid.get(gi)   # legacy last-write-wins shim (no served candidate found)
                if hit:
                    out.add(hit)
        return out

    # ── candidate builders ─────────────────────────────────────────────────────
    def _name_to_results(self, hits, req) -> List[SearchResult]:
        vset = set(req.verticals)
        out: List[SearchResult] = []
        for h in hits:
            if vset and h.vertical.lower() not in vset:
                continue
            meta = self.bridge.meta.get(h.entity_id, {})   # entity_id-keyed (collision-safe; both twins resolve)
            r = SearchResult(property_id=h.property_id, entity_id=h.entity_id,
                             name=h.name, vertical=h.vertical, match_type=h.match_type,
                             relevance=h.relevance, genres=meta.get("genres", []))
            r.disambiguation_confidence = round(h.relevance, 4)
            # DEMOTE framing: a name match whose title has a much-more-popular UNBRIDGED twin (gap≥0.6) is a
            # coincidental namesake ("Loki" game for a Marvel-show search) — keep it, but flag it so it is framed
            # "Named '{q}'", never "Best match", and (routing) never MLT-amplified. Signal only; no unbridged entity.
            r.twin_demoted = self._twin_gap_exceeds(h.name, self.store.popularity_pct(h.entity_id))
            out.append(r)
        return out

    def _thematic_results(self, req, route: dict, embed_text: Optional[str] = None,
                          source_vector=None) -> List[SearchResult]:
        if source_vector is not None:
            qvec = source_vector                                  # "more like this": the matched entity's stored vector
            route["thematic_embed"] = "entity_vector (no embed call)"
        else:
            try:
                qvec = self.embedder.embed(embed_text or req.query)   # vertical-word stripped topic text
            except EmbedUnavailable as e:
                route["thematic_embed"] = f"unavailable ({e})"
                return []
            route["thematic_embed"] = "ok"
        hits = self.thematic.search(qvec, req.verticals or None, config.THEMATIC_K_PER_VERTICAL)
        rows, cosines, orphans = [], [], 0
        for h in hits:
            pid = self.bridge.eid2pid.get(h.entity_id)
            if pid is None:                          # parquet orphan vector (no graph entity, ~284) → skip
                orphans += 1
                continue
            rows.append((pid, h)); cosines.append(h.cosine)
        route["thematic_orphans_skipped"] = orphans
        rels = minmax_relevance(cosines)
        out: List[SearchResult] = []
        for (pid, h), rel in zip(rows, rels):
            meta = self.bridge.meta.get(h.entity_id, {})   # entity_id-keyed (collision-safe; thematic path untestable)
            out.append(SearchResult(property_id=pid, entity_id=h.entity_id,
                                    name=meta.get("name") or h.name,
                                    vertical=meta.get("vertical") or h.vertical,
                                    match_type="thematic", relevance=round(rel, 6),
                                    genres=meta.get("genres", []), cosine=round(h.cosine, 6)))
        return out

    def _merge_both(self, req, name_hits, route: dict, embed_text: Optional[str] = None,
                    source_vector=None) -> List[SearchResult]:
        by_eid = {}
        for r in self._name_to_results(name_hits, req):   # name first → preferred (the exact-tier instance wins on dedup)
            by_eid[r.entity_id] = r
        for r in self._thematic_results(req, route, embed_text, source_vector):
            by_eid.setdefault(r.entity_id, r)             # neighbour backfill; dedup vs the pinned entity + each other (entity_id = collision-safe)
        return list(by_eid.values())

    def _mlt_route(self, req, matched, name_hits, route: dict, embed_text):
        """Pin `matched` #1 + backfill from ITS stored vector (no live embed). Edge: no parquet row →
        live-embed fallback, still pinned. Used by the exact/highest-pop path AND the unique-prefix path."""
        eid = matched.entity_id                           # NameHit carries entity_id (collision-safe)
        vec = self.thematic.vector_for(eid) if eid else None
        route["mlt"] = {"matched_pid": matched.property_id, "matched_vertical": matched.vertical,
                        "matched_name": matched.name, "matched_match_type": matched.match_type,
                        "source": "entity_vector" if vec is not None else "live_embed_fallback(no parquet row)"}
        return "auto_mlt", self._merge_both(req, name_hits, route, embed_text, source_vector=vec), route

    def _prefix_blend(self, h) -> float:
        """Lightweight dominance score for prefix resolution: completeness-relevance + popularity + centrality."""
        return (0.5 * h.relevance + 0.35 * self.store.popularity_pct(h.entity_id)
                + 0.15 * self.store.centrality_pct(h.entity_id))

    def _twin_gap_exceeds(self, name: str, pin_pop: float) -> bool:
        """Structural suppression SIGNAL keyed on the MATCHED ENTITY name (not the raw query), so a PARTIAL that
        resolves to a twinned title ("game of t"→"Game of Thrones") fires consistently with the full exact query:
        does `name` have a same-name UNBRIDGED catalog twin MORE popular than `pin_pop` by ≥ EXACT_TWIN_GAP_MARGIN?
        Signal only — never surfaces the unbridged entity. The 0.6 gap spares genuine low-gap pins ("Elden Ring"→
        movie, twin 0.974, gap 0.392) while catching pop-0 namesakes ("Game of Thrones"→game, gap 0.999)."""
        twin_pop = self.catalog_unbridged_pop.get(_norm(name))
        return twin_pop is not None and (twin_pop - pin_pop) >= config.EXACT_TWIN_GAP_MARGIN

    # ── routing ─────────────────────────────────────────────────────────────────
    def _route(self, req, embed_text: Optional[str] = None) -> Tuple[str, List[SearchResult], dict]:
        route: dict = {}
        # Explicit modes are PURE (owner decision): "name" = name lookup only (UI "look up a name, no
        # neighbours"); "thematic" = vector only. Only "auto" runs both.
        if req.mode == "name":
            return "name", self._name_to_results(self.name_index.lookup(req.query), req), route
        if req.mode == "thematic":
            return "thematic", self._thematic_results(req, route, embed_text), route
        # AUTO — ALWAYS run BOTH paths, one ranked list filled to `limit`: the name/exact tier is pinned on
        # top (exact dominates all thematic, UC4 Story 1) and the thematic vector path backfills BELOW it to
        # `limit`. Never suppress thematic when an exact exists (this is the "fortnite → only 2 results" fix).
        name_hits = self.name_index.lookup(req.query)
        # DEMOTE-not-DROP: a twinned fuzzy hit ("Game of Thrones" game for "game of") is KEPT (no longer filtered
        # out) — it sits at its natural fuzzy tier, is flagged twin_demoted in _name_to_results ("Named …", no MLT),
        # and leads only if its score wins. Exact/prefix twins are likewise kept + demoted in their branches below.
        qn = _norm(req.query)
        can_mlt = len(qn) >= config.MLT_MIN_QUERY_LEN         # Fix 1b: never SEED more-like-this from an ultra-short query
        exacts = [h for h in name_hits if h.match_type == "exact"]
        prefixes = [h for h in name_hits if h.match_type == "prefix"]
        route.update(name_best=round(name_hits[0].relevance, 4) if name_hits else 0.0, n_exact=len(exacts),
                     n_prefix=len(prefixes), query_len=len(qn), can_mlt=can_mlt,
                     n_strong_fuzzy=sum(1 for h in name_hits if h.match_type in ("fuzzy", "fuzzy_typo")
                                        and h.relevance >= config.AUTO_AMBIGUOUS_MIN))
        gate = (not req.disambiguation and req.source_context != config.ONBOARDING_SOURCE_CONTEXT)
        # CHANGE 3: with ≥1 exact, the HIGHEST-popularity same-name entity is the primary pin + MLT seed
        # (max(popularity_pct) is seed-safe: a pop-0/null_source seed can never outrank a real pop>0 entity).
        # Ultra-short exacts skip MLT but the exact still leads via the exact tier.
        if exacts and gate and can_mlt:
            # popularity keyed on entity_id (collision-safe); -property_id kept as the deterministic source_id
            # tie-break among equally-popular exacts (genuine source_id-space ordering, not an entity lookup).
            matched = max(exacts, key=lambda h: (self.store.popularity_pct(h.entity_id), -h.property_id))
            # BREAK-1 FIX: the exact branch is NO LONGER blanket-spared. When a same-name UNBRIDGED twin is MUCH more
            # popular (RELATIVE gap ≥ margin), the query names a famous title we can't serve, so the obscure bridged
            # namesake ("Game of Thrones"→pop-0 game) must NOT get the confident pin. The GAP spares the genuine
            # "Elden Ring"→movie (gap 0.392) and "mine"→"Mine" (no twin). DEMOTE-not-DROP: KEEP the namesake (it is a
            # real name match, flagged twin_demoted → framed "Named …") but route auto_both so NO MLT fires; it leads
            # #1 by tier with thematic below, honoring UC4 "never leave a name query with nothing relevant".
            twin_pop = self.catalog_unbridged_pop.get(qn)
            if twin_pop is not None and (twin_pop - self.store.popularity_pct(matched.entity_id)) >= config.EXACT_TWIN_GAP_MARGIN:
                route["mlt_suppressed"] = "exact_famous_unbridged_twin"
                route["exact_twin"] = {"pin_pop": round(self.store.popularity_pct(matched.entity_id), 3),
                                       "twin_pop": round(twin_pop, 3),
                                       "gap": round(twin_pop - self.store.popularity_pct(matched.entity_id), 3)}
                return "auto_both", self._merge_both(req, name_hits, route, embed_text), route
            return self._mlt_route(req, matched, name_hits, route, embed_text)
        if exacts:                                            # disambiguation / onboarding / too-short → breadth, no MLT
            return "auto_both", self._merge_both(req, name_hits, route, embed_text), route
        # CHANGE 2: a PREFIX that uniquely resolves → pin + MLT like exact — UNLESS (Fix 1) the query is ultra-short
        # OR it exactly names a MORE-popular UNBRIDGED entity (user is after a famous title we can't serve → don't
        # confidently pin bridged junk). Suppressed → honest thematic backfill (no misleading pin, no MLT).
        if prefixes and gate:
            ranked_p = sorted(prefixes, key=lambda h: -self._prefix_blend(h))
            top = ranked_p[0]
            runner = self._prefix_blend(ranked_p[1]) if len(ranked_p) > 1 else 0.0
            margin = round(self._prefix_blend(top) - runner, 4)
            twin = self._twin_gap_exceeds(top.name, self.store.popularity_pct(top.entity_id))  # keyed on ENTITY name + 0.6 gap
            route["prefix_resolve"] = {"top": top.name, "margin": margin, "threshold": config.PREFIX_MLT_MARGIN,
                                       "runner_up": ranked_p[1].name if len(ranked_p) > 1 else None,
                                       "n_prefix": len(prefixes), "unbridged_twin": twin, "can_mlt": can_mlt}
            if margin >= config.PREFIX_MLT_MARGIN and can_mlt and not twin:   # uniquely dominant AND confident
                return self._mlt_route(req, top, name_hits, route, embed_text)
            reason = ("ambiguous_prefix" if margin < config.PREFIX_MLT_MARGIN
                      else f"query_len<{config.MLT_MIN_QUERY_LEN}" if not can_mlt else "famous_unbridged_twin")
            route["mlt_suppressed"] = reason
            # DEMOTE-not-DROP: all three sub-cases now KEEP their name hits (no prefix drop). famous-unbridged-twin
            # keeps the prefix completion as a demoted name match (flagged twin_demoted → "Named …", no MLT); it leads
            # #1 by tier with thematic below. MLT is still suppressed (auto_both) for every fired-twin case.
            return "auto_both", self._merge_both(req, name_hits, route, embed_text), route
        # no exact/prefix → live-embed thematic + fuzzy (unchanged)
        return "auto_both", self._merge_both(req, name_hits, route, embed_text), route

    # ── main entry ──────────────────────────────────────────────────────────────
    def handle(self, req) -> dict:
        now = datetime.now(timezone.utc)
        if not (req.query or "").strip():
            return build_envelope(req, [], "empty", now, set(), 0, {"reason": "empty_query"})
        raw_followed, follow_info = self.follow_gate.followed(req.user_id, req.exclude_followed)
        followed = self._resolve_followed_entity_ids(raw_followed)   # entity_ids (collision-safe exclusion)
        if raw_followed:
            follow_info["resolved_entity_ids"] = len(followed)
        # Vertical-word stripping happens in _route (embed text). The BOOST source is decided here AFTER
        # routing, so "more like this" can boost the MATCHED entity's own vertical. Explicit `verticals`
        # filter wins (no soft boost).
        detected, embed_text = detect_verticals(req.query)
        mode_taken, candidates, route = self._route(req, embed_text)

        mlt = route.get("mlt")
        boosted, boost_value = set(), 0.0
        if req.verticals:
            pass
        elif mlt and mlt.get("matched_vertical"):           # more-like-this → boost the matched entity's vertical
            boosted, boost_value = {mlt["matched_vertical"]}, config.MLT_SAME_VERTICAL_BOOST
        elif detected and req.mode != "name":               # vertical-word → boost the named vertical(s)
            boosted, boost_value = detected, config.VERTICAL_WORD_BOOST
        route["vertical_intent"] = {"detected": sorted(detected), "embed_text": embed_text,
                                    "boosted": sorted(boosted), "boost": round(boost_value, 4)}

        for r in candidates:
            score_result(r, self.store, now)
            if r.vertical in boosted:                       # soft additive boost — the exact tier still dominates
                r.final_score = round(r.final_score + boost_value, 6)
                r.signals["vertical_boost"] = boost_value
        if followed:
            candidates = [r for r in candidates if r.entity_id not in followed]   # exclude on entity_id

        n_collapsed = 0
        if config.DEDUP_ENABLED:
            candidates, n_collapsed = collapse_duplicates(candidates, self.store)

        # TIERED: exact-identity tier (tier 0) ranks above all non-exact (tier 1) regardless of centrality;
        # WITHIN a tier, the weighted blend (+ any vertical boost) orders. UC4 Story 1.
        candidates.sort(key=lambda r: (r.tier, -r.final_score, -r.relevance, -r.centrality_pct, r.property_id))
        total = len(candidates)

        if boosted:
            # soft vertical preference (more-like-this OR vertical-word): the boosted vertical LEADS (via the
            # boost); other verticals BACKFILL the tail — never hard-filtered, so results are never emptied.
            # The cross-vertical cap is skipped (a specific vertical is intended).
            ranked = candidates[: req.limit]
            fairness_info = {"applied": False,
                             "reason": f"{'more_like_this' if mlt else 'vertical_word'}_boost:{sorted(boosted)}",
                             "vertical_counts": _counts([r.vertical for r in candidates[: req.limit]])}
        elif mode_taken in ("thematic", "auto_both", "auto_thematic", "auto_mlt"):
            force_spread = (config.FAIRNESS_ONBOARDING_FORCES_SPREAD
                            and req.source_context == config.ONBOARDING_SOURCE_CONTEXT)
            ranked, fairness_info = apply_fairness(candidates, req.limit, req.verticals, force_spread=force_spread)
        else:
            ranked = candidates[: req.limit]
            fairness_info = {"applied": False, "reason": "name_mode"}

        # MLT pin: guarantee the matched entity (highest-pop exact OR uniquely-resolved prefix) is #1,
        # even if it sits in the prefix tier or the boost lifted a neighbour.
        if mlt and mlt.get("matched_pid") is not None:
            mp = mlt["matched_pid"]
            pin = next((r for r in candidates if r.property_id == mp), None)
            if pin:
                ranked = [pin] + [r for r in ranked if r.property_id != mp]
                ranked = ranked[: req.limit]

        # disambiguation: pin the highest-confidence exact match on top
        if req.disambiguation:
            exacts = [r for r in candidates if r.match_type == "exact"]
            if exacts:
                pin = max(exacts, key=lambda r: (r.relevance, r.final_score))
                pin.disambiguation_confidence = 1.0
                ranked = [pin] + [r for r in ranked if r.property_id != pin.property_id]
                ranked = ranked[: req.limit]

        extra_debug = {"route": route, "follows": follow_info, "fairness": fairness_info,
                       "dedup": {"enabled": config.DEDUP_ENABLED, "collapsed": n_collapsed},
                       "candidate_count": total,
                       "result_verticals": _counts([r.vertical for r in ranked])}
        return build_envelope(req, ranked, mode_taken, now, followed, total, extra_debug)


def _counts(xs) -> dict:
    out: dict = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out
