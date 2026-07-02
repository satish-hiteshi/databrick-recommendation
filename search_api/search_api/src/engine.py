"""SearchEngine — the orchestrator for UC4 + UC7.

startup (once): bridge (44k property_id<->entity_id), Postgres store (popularity+centrality), thematic
ANN index (parquet matrix), Qwen embedder, follow gate, and the in-memory NAME index.
per request: route (name | thematic | auto[both]) -> score (per-(mode,vertical) weights) -> exclude
followed -> dedup (composite) -> sort -> cross-vertical fairness -> serialize. Properties only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import config
from .bridge import build_bridge
from .dedup import collapse_duplicates
from .embed import EmbedUnavailable, QwenQueryEmbedder
from .fairness import apply_fairness
from .follows import FollowGate
from .name_index import NameIndex
from .ranking import SearchResult, minmax_relevance, score_result
from .serializer import build_envelope
from .store import load_store
from .thematic import ThematicIndex


class SearchEngine:
    def __init__(self) -> None:
        self.bridge = build_bridge(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD,
                                   config.NEO4J_DATABASE)
        self.store = load_store()
        self.thematic = ThematicIndex().load()
        self.embedder = QwenQueryEmbedder()
        self.follow_gate = FollowGate()
        # NAME index over the 44k bridge properties; names from property_popularity, fallback graph name.
        entries: List[Tuple[int, str, str]] = []
        for pid, meta in self.bridge.meta.items():
            pr = self.store.popularity.get(pid)
            name = (pr.name if pr else None) or meta.get("name")
            vert = (pr.vertical if pr else None) or meta.get("vertical") or "unknown"
            if name:
                entries.append((pid, name, vert))
        self.name_index = NameIndex(entries)

    # ── health ────────────────────────────────────────────────────────────────
    def health(self) -> dict:
        return {"status": "ok", "endpoint": config.ENDPOINT_LABEL, "engine": config.ENGINE_LABEL,
                "bridge_properties": self.bridge.size, "name_index_size": self.name_index.size,
                "name_backend": self.name_index.backend, "thematic_vectors": self.thematic.size,
                "popularity_rows": len(self.store.popularity), "centrality_rows": len(self.store.centrality),
                "qwen_embed_available": self.embedder.available, **config.summary()}

    # ── candidate builders ─────────────────────────────────────────────────────
    def _name_to_results(self, hits, req) -> List[SearchResult]:
        vset = set(req.verticals)
        out: List[SearchResult] = []
        for h in hits:
            if vset and h.vertical.lower() not in vset:
                continue
            meta = self.bridge.meta.get(h.property_id, {})
            r = SearchResult(property_id=h.property_id, entity_id=self.bridge.pid2eid.get(h.property_id),
                             name=h.name, vertical=h.vertical, match_type=h.match_type,
                             relevance=h.relevance, genres=meta.get("genres", []))
            r.disambiguation_confidence = round(h.relevance, 4)
            out.append(r)
        return out

    def _thematic_results(self, req, route: dict) -> List[SearchResult]:
        try:
            qvec = self.embedder.embed(req.query)
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
            meta = self.bridge.meta.get(pid, {})
            out.append(SearchResult(property_id=pid, entity_id=h.entity_id,
                                    name=meta.get("name") or h.name,
                                    vertical=meta.get("vertical") or h.vertical,
                                    match_type="thematic", relevance=round(rel, 6),
                                    genres=meta.get("genres", []), cosine=round(h.cosine, 6)))
        return out

    def _merge_both(self, req, name_hits, route: dict) -> List[SearchResult]:
        by_pid = {}
        for r in self._name_to_results(name_hits, req):   # name first → preferred (intent)
            by_pid[r.property_id] = r
        for r in self._thematic_results(req, route):
            by_pid.setdefault(r.property_id, r)
        return list(by_pid.values())

    # ── routing ─────────────────────────────────────────────────────────────────
    def _route(self, req) -> Tuple[str, List[SearchResult], dict]:
        route: dict = {}
        if req.mode == "name":
            return "name", self._name_to_results(self.name_index.lookup(req.query), req), route
        if req.mode == "thematic":
            return "thematic", self._thematic_results(req, route), route
        # auto — EXACT-AWARE: a clean unique exact routes to name (pinned); ambiguity runs both
        name_hits = self.name_index.lookup(req.query)
        exacts = [h for h in name_hits if h.match_type == "exact"]
        strong_fuzzy = [h for h in name_hits if h.match_type == "fuzzy" and h.relevance >= config.AUTO_AMBIGUOUS_MIN]
        best = name_hits[0].relevance if name_hits else 0.0
        route.update(name_best=round(best, 4), n_exact=len(exacts), n_strong_fuzzy=len(strong_fuzzy))
        if req.disambiguation:
            return "auto_both", self._merge_both(req, name_hits, route), route
        if len(exacts) >= 2:                                                   # ambiguous: a title shared by ≥2 props
            return "auto_both", self._merge_both(req, name_hits, route), route
        if len(exacts) == 1 and len(strong_fuzzy) >= config.AUTO_AMBIGUOUS_COUNT:
            return "auto_both", self._merge_both(req, name_hits, route), route  # one exact + a crowd of variants/topic
        if len(exacts) == 1:
            return "name", self._name_to_results(name_hits, req), route         # clean unique name → pinned exact
        if len(strong_fuzzy) >= config.AUTO_AMBIGUOUS_COUNT:
            return "auto_both", self._merge_both(req, name_hits, route), route  # no exact, a CROWD of variants → ambiguous (Battlefield)
        if strong_fuzzy:
            return "name", self._name_to_results(name_hits, req), route         # no exact, a FEW strong name matches → name (eldn ring)
        return "auto_thematic", self._thematic_results(req, route), route       # no name signal → pure concept

    # ── main entry ──────────────────────────────────────────────────────────────
    def handle(self, req) -> dict:
        now = datetime.now(timezone.utc)
        if not (req.query or "").strip():
            return build_envelope(req, [], "empty", now, set(), 0, {"reason": "empty_query"})
        followed, follow_info = self.follow_gate.followed(req.user_id, req.exclude_followed)
        mode_taken, candidates, route = self._route(req)

        for r in candidates:
            score_result(r, self.store, now)
        if followed:
            candidates = [r for r in candidates if r.property_id not in followed]

        n_collapsed = 0
        if config.DEDUP_ENABLED:
            candidates, n_collapsed = collapse_duplicates(candidates, self.store)

        # TIERED: exact-identity tier (tier 0) ranks above all non-exact (tier 1) regardless of centrality;
        # WITHIN a tier, the weighted blend orders (centrality/popularity break ties). UC4 Story 1.
        candidates.sort(key=lambda r: (r.tier, -r.final_score, -r.relevance, -r.centrality_pct, r.property_id))
        total = len(candidates)

        if mode_taken in ("thematic", "auto_both", "auto_thematic"):
            force_spread = (config.FAIRNESS_ONBOARDING_FORCES_SPREAD
                            and req.source_context == config.ONBOARDING_SOURCE_CONTEXT)
            ranked, fairness_info = apply_fairness(candidates, req.limit, req.verticals, force_spread=force_spread)
        else:
            ranked = candidates[: req.limit]
            fairness_info = {"applied": False, "reason": "name_mode"}

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
