"""Deterministic assembler: intent JSON -> bounded execution path.

VECTOR-PRIMARY architecture (07b, after the honest 06b eval showed graph-primary regressed against the
full vector pipeline). Reads an Intent and composes the blocks into ONE establish-then-refine path;
assembly is dynamic but every result is a NAMED, testable composition.

THE NEW DEFAULT — VECTOR establishes, GRAPH refines (vector has the semantic recall; graph does what
vector provably cannot: enforce relational/structural constraints, filter negations, contribute a
structural rerank). GRAPH establishes FIRST only for the proven structural niche.

Establisher selection (exactly one, runs first):
  1. seed(s) present:
       specific target vertical -> vector_seed / multiseed   (combined seed vector neighborhood; handles
                                                               single cross-vertical game->movie)
       vertical=any / multi-target -> vector_constrain(raw)   (/api/query NLU targets the right verticals)
  2. structural NICHE (franchise / developer_relation.also_made / explicit structural) -> graph_constrain
       (sparse-franchise safety: a tiny franchise node, e.g. "Warhammer", re-establishes via vector recall)
  3. negation present -> establish the BROAD POSITIVE set then graph apply_negations removes the category
       (concepts -> graph_constrain broad; else positive phrase -> vector; else vertical universe). The
       phrase sent to vector is POSITIVE-ONLY so the vector pipeline never over-negates to empty (07a).
  4. DEFAULT (anything with semantic/thematic/descriptive character) -> vector_constrain (full /api/query)
  5. bare "<vertical>" with no other signal -> vector on the vertical word, else graph vertical universe
  6. last resort (no signal but raw text) -> vector_constrain(raw_query); EMPTY only if truly nothing.

Refine the established set (refiners only reorder/shrink it): semantic rerank WITHIN a graph/seed set
(vector-established sets are already semantically ranked) -> vector_rerank_within; soft.structural_prefs
-> graph_rerank_within; negations -> apply_negations (final hard exclusion). Too-small -> anchored backfill.

INVARIANT (enforced structurally + at runtime): exactly one establisher runs first; every refiner is
called only on the handed set and its output is asserted ⊆ the established ids (a refiner can never
introduce a new entity / act as an establisher).

NAMED PATHS (path_taken): establisher token ∈ {VECTOR_CONSTRAIN, GRAPH_CONSTRAIN, GRAPH_VERTICAL,
SEED_VECTOR, MULTISEED}; only-name ∈ {VECTOR_ONLY, GRAPH_ONLY, GRAPH_VERTICAL_ONLY, SEED_VECTOR_ONLY,
MULTISEED_ONLY}; with refiners -> "TOKEN__VECTOR_RERANK", "TOKEN__GRAPH_RERANK",
"TOKEN__VECTOR_RERANK__GRAPH_RERANK"; + optional trailing "__BACKFILL". apply_negations runs on any path
when present (recorded in refinements_applied[], not a path token, so the named-path set stays bounded).
"""

import re
import statistics
from typing import List, Optional

import blocks as B
import config
from backfill import backfill
from intent import Intent

BACKFILL_THRESHOLD = 10   # "too small" -> backfill (CONTEXT §6, tunable)
VLABEL = {"game": "Games", "movie": "Movies", "tv": "TV Shows", "podcast": "Podcasts", "any": "All"}


def _has_structural(h) -> bool:
    return bool(h.concepts or h.franchise or (h.developer_relation or {}).get("also_made") or h.structural)


# vertical words + trivial framing words to strip when testing whether a raw query carries a topic the
# LLM may have dropped (safety net for the bare-vertical establish path).
_VERTICAL_FILLER = {
    "game", "games", "gaming", "movie", "movies", "film", "films", "tv", "show", "shows", "series",
    "podcast", "podcasts", "content", "something", "anything", "stuff", "recommend", "recommendation",
    "recommendations", "suggest", "suggestion", "suggestions", "show", "find", "want", "looking", "for",
    "me", "some", "any", "a", "an", "the", "give", "get", "please", "i", "to", "of", "on", "in",
}


def _has_signal_beyond_vertical(raw_query: str, vertical: Optional[str]) -> bool:
    """True if the raw query carries retrievable content beyond the bare vertical word + trivial framing
    filler. Used to salvage a topic the LLM dropped (e.g. 'business podcasts' extracted as only
    verticals=[podcast]) — establish on the raw query instead of the meaningless bare vertical word."""
    toks = re.findall(r"[a-z0-9']+", (raw_query or "").lower())
    stop = _VERTICAL_FILLER | {(vertical or "").lower()}
    content = [t for t in toks if t not in stop and len(t) > 1]
    return len(content) >= 1


def _split_seeds(seed_entity) -> List[str]:
    """A seed_entity string may name MULTIPLE entities ('Hades II, Hollow Knight', 'X and Y').
    NOTE: do NOT split on '&' — it appears inside single titles ('Dungeons & Dragons')."""
    if not seed_entity:
        return []
    if isinstance(seed_entity, list):
        return [str(s).strip() for s in seed_entity if str(s).strip()]
    return [s.strip() for s in re.split(r",|\band\b", str(seed_entity)) if s.strip()]


# structural constraints split into the ENFORCEABLE graph niche vs preference-like mode/feature signals.
_ENFORCEABLE_STRUCT = ("developer", "publisher")


def _split_structural(structural):
    """(enforceable_dict, feature_terms_str). developer/publisher are real graph nodes graph_constrain
    enforces (the niche); everything else (mode, feature, multiplayer, crafting, player_count, …) is a
    preference-like signal — graph-establishing on it yields an influence dump, so it must drive VECTOR
    establishment + a graph rerank instead (07b v2 loss #100)."""
    structural = structural or {}
    enforceable = {k: v for k, v in structural.items() if k in _ENFORCEABLE_STRUCT and v}
    terms = []
    for k, v in structural.items():
        if k in _ENFORCEABLE_STRUCT:
            continue
        if isinstance(v, str) and v.strip():
            terms.append(v.strip())
        elif isinstance(v, bool) and v:
            terms.append(k.replace("_", " "))
        elif isinstance(v, (list, tuple)):
            terms += [str(x).strip() for x in v if str(x).strip()]
    return enforceable, ", ".join(dict.fromkeys(terms))


# ── selective-rerank GATE (07f) — decide per query whether the cross-encoder fires (RERANK=auto) ──
def _topk_cv(items, k: int = 10):
    """Coefficient of variation (std/mean — scale-free) of the top-K establisher scores. LOW CV = flat,
    uninformative ordering (cosine/influence bunched ≈ noise) → reranking helps; HIGH CV = a clear
    gradient → ordering already meaningful. None if too few / non-positive."""
    scores = [it.get("score") for it in items[:k] if isinstance(it.get("score"), (int, float))]
    if len(scores) < 3:
        return None
    m = statistics.mean(scores)
    if m <= 0:
        return None
    return statistics.pstdev(scores) / m


def should_rerank(intent, established, establisher, refiner_order, signal=None):
    """Per-query gate: fire the cross-encoder? Returns (fire: bool, reason: str).
    GUARD 3 (both signals): NEVER rerank where the establisher's ORDER encodes correctness the text-only
    cross-encoder can't see — negation (graph set-exclusion) and graph-established structural+semantic.
    Signal A (preferred, general): rerank when Stage-1 top-K scores are FLAT (low CV). Signal B (fallback):
    rerank the vector-established semantic paths only."""
    sig = (signal or config.RERANK_GATE_SIGNAL).upper()
    h = intent.hard_constraints
    if h.negations:
        return False, "guard3: negation (graph set-exclusion order is meaningful)"
    if establisher == "graph_constrain" and "VECTOR_RERANK" in (refiner_order or []):
        return False, "guard3: structural+semantic (already semantically reranked within a graph set)"
    if sig == "B":
        fire = establisher in ("vector_constrain", "vector_seed", "multiseed")
        return fire, f"signalB: {'vector' if fire else 'graph'}-established ({establisher})"
    cv = _topk_cv(established)
    if cv is None:
        return True, "signalA: scores degenerate → default rerank (assume recall-limited)"
    fire = cv < config.RERANK_GATE_CV
    return fire, f"signalA: top-K CV={cv:.3f} {'<' if fire else '>='} {config.RERANK_GATE_CV} ({'flat→rerank' if fire else 'separated→hold'})"


def assemble(intent: Intent, top_k: int = 10, backfill_threshold: int = BACKFILL_THRESHOLD,
             recall_k: Optional[int] = None) -> dict:
    h, soft = intent.hard_constraints, intent.soft_intent
    vertical = intent.vertical
    hard_dict = h.model_dump()

    # ── Stage-1 recall depth (07e two-stage). recall_k>0 → establishers cast a WIDE pool for the
    #    cross-encoder to rerank; None/0 → current depth. Establisher calls below go through these
    #    wrappers so the depth threads through every establisher uniformly. ──
    rk = recall_k if recall_k is not None else (config.RECALL_K or None)
    _gk = rk or 500
    def _gconstrain(hard, vertical=None):
        return B.graph_constrain(hard, vertical=vertical, top_k=_gk)
    def _vconstrain(phrase, vertical=None):
        return B.vector_constrain(phrase, vertical=vertical, recall_k=rk)
    def _seed(seeds, vertical=None):
        return B.vector_seed_constrain(seeds, vertical=vertical, top_k=(rk or 200))

    # ── 0. NORMALISE concepts against the graph's REAL vocabulary (CONTEXT §3 hard-vs-soft, enforced
    #       deterministically). Graph-recognised terms stay HARD; mood/quality words the graph has no
    #       node for ("dark", "intense", "psychological") are folded into SOFT semantic so they REFINE
    #       instead of zeroing the universe — correcting the LLM's residual hard-vs-soft mis-bucketing. ──
    hard_concepts, leftover_soft = B.resolve_concepts(h.concepts)
    hard_dict["concepts"] = hard_concepts
    soft_semantic = soft.semantic
    if leftover_soft:
        extra = ", ".join(leftover_soft)
        soft_semantic = f"{soft_semantic}, {extra}" if soft_semantic else extra

    refinements = []          # human-readable log
    refiner_order = []        # distinct refiner TYPES in application order (for the path name)
    establisher = None
    semrefine = None          # SEMANTIC phrase to vector-rerank WITHIN a graph/seed-established set
    if leftover_soft:
        refinements.append(f"normalise: folded {leftover_soft} into soft.semantic (not graph concepts)")

    seeds = _split_seeds(intent.seed_entity)
    dev_rel = (h.developer_relation or {}).get("also_made")
    enforceable_struct, feature_terms = _split_structural(h.structural)
    # graph establishes ONLY for the PROVEN niche: franchise / developer-relation / developer-publisher.
    # Preference-like mode/feature structural (co-op, crafting…) does NOT graph-establish (#100) — it
    # folds into the vector establish phrase + a graph rerank below.
    graph_niche = bool(h.franchise or dev_rel or enforceable_struct)
    nonenf_struct = {k: v for k, v in (h.structural or {}).items() if k not in _ENFORCEABLE_STRUCT}
    if feature_terms:
        refinements.append(f"structural mode/feature {list(nonenf_struct)} → vector-establish + graph rerank")
    # POSITIVE establish phrase (NEVER includes negations — 07a: vector over-negates to empty).
    positive_phrase = ", ".join(dict.fromkeys(
        [t for t in (h.semantic_core, " ".join(hard_concepts) if hard_concepts else None,
                     feature_terms, soft_semantic) if t]))
    # SEMANTIC-only phrase for reranking a structural/seed set (concepts already hold in the set).
    sem_only = ", ".join(dict.fromkeys([t for t in (h.semantic_core, soft_semantic) if t]))

    # TEMPORAL handling: /api/query has no date parameter — the vector engine derives the date window from
    # the query TEXT (its NLU has the correct "today"). When a release-window constraint is present we must
    # NOT strip the date words: establish on the RAW QUERY so they survive and the vector NLU applies the
    # filter. This delegates date math to the one engine that owns it (the router's own date arithmetic has
    # no today-anchor and is unused). Graph is date-free, so this only affects the vector-establish path.
    temporal_present = bool(h.temporal)
    def _est_phrase(clean):
        return intent.raw_query if (temporal_present and intent.raw_query) else clean

    # ════════ 1. ESTABLISHER SELECTION — VECTOR-PRIMARY, graph for the structural niche ════════
    if seeds:
        # SEED / MULTI-SEED. For a SPECIFIC target vertical (incl. single cross-vertical "game→movie"),
        # use the combined seed neighborhood (/api/neighbors, vector recall). For vertical=any /
        # multi-target ("recommend movies AND TV based on X"), /api/neighbors would include the seeds'
        # OWN vertical — so defer to /api/query, whose NLU targets the right verticals natively.
        established = []
        if vertical and vertical != "any":
            established = _seed(seeds, vertical=vertical)
            establisher = "multiseed" if len(seeds) > 1 else "vector_seed"
            if established and soft_semantic:               # "…but more relaxing" reranks the neighbors
                semrefine = soft_semantic
        if not established:                                  # any/multi-target OR seed didn't resolve
            established = _vconstrain(intent.raw_query or positive_phrase or (vertical or ""),
                                      vertical=vertical)
            establisher = "vector_constrain"

    elif graph_niche:
        # GRAPH NICHE: franchise / developer-relation / explicit structural — graph establishes (precise).
        established = _gconstrain(hard_dict, vertical=vertical)
        establisher = "graph_constrain"
        # sparse-franchise safety (06b/07a: a sparse franchise node like "Warhammer" loses to vector
        # recall) — if a franchise anchor yields a tiny set, re-establish via vector on the franchise term.
        if h.franchise and len(established) < backfill_threshold:
            alt = _vconstrain(h.franchise, vertical=vertical)
            if len(alt) > len(established):
                established, establisher = alt, "vector_constrain"
                refinements.append(f"sparse-franchise: re-established '{h.franchise}' via vector recall")
        if establisher == "graph_constrain" and sem_only:
            semrefine = sem_only                            # reorder the structural set by semantics

    elif h.negations:
        # NEGATION (router WIN archetype): establish the BROAD POSITIVE set, then graph removes the negated
        # category — do NOT let the over-negating vector pipeline establish (07a: returns no_results).
        if hard_concepts:
            established = _gconstrain(hard_dict, vertical=vertical)   # broad concept set
            establisher = "graph_constrain"
            # rerank by semantics (or the concept itself) so the kept set is relevance-ordered, not the
            # raw influence dump graph_constrain returns.
            semrefine = sem_only or ", ".join(hard_concepts)
        elif positive_phrase:                               # semantic positive (negation stripped) → vector
            established = _vconstrain(positive_phrase, vertical=vertical)
            establisher = "vector_constrain"
        elif vertical and vertical != "any":                # bare "vertical but not X" → vertical universe
            established = _gconstrain({"vertical": vertical}, vertical=vertical)
            establisher = "graph_vertical"
        else:
            established = []

    elif positive_phrase:
        # DEFAULT (most queries): vector establishes the semantic/thematic/descriptive universe — already
        # semantically ranked, so no extra vector rerank. graph refines (prefs / negations) within.
        # When a temporal window is present, establish on the raw query (date words intact) so the vector
        # NLU applies the date filter — otherwise the stripped phrase loses the date (e.g. "thriller from
        # the last 2 years" → "thriller" → no date → 1980s results).
        established = _vconstrain(_est_phrase(positive_phrase), vertical=vertical)
        establisher = "vector_constrain"
        if temporal_present and intent.raw_query:
            refinements.append("temporal present → established on raw query (vector applies the date filter)")

    elif vertical and vertical != "any":
        # bare "<vertical>" — BUT the LLM may have dropped a topic/subject (e.g. "business podcasts" →
        # only verticals=[podcast], no concept/semantic). If the raw query carries content beyond the
        # vertical word, establish on the RAW QUERY so the dropped topic still drives retrieval; only
        # fall back to the bare vertical word when there is genuinely no other signal.
        rawq = (intent.raw_query or "").strip()
        if rawq and _has_signal_beyond_vertical(rawq, vertical):
            established = _vconstrain(rawq, vertical=vertical)
            establisher = "vector_constrain"
            refinements.append("bare-vertical safety net: established on raw query (topic beyond vertical word)")
        else:
            established = _vconstrain(vertical, vertical=vertical)
            establisher = "vector_constrain"
        if not established:
            established = _gconstrain({"vertical": vertical}, vertical=vertical)
            establisher = "graph_vertical"
    else:
        established = []

    # last resort — never EMPTY when there is ANY text to retrieve on (graceful; vector recall)
    if not established and (intent.raw_query or positive_phrase):
        established = _vconstrain(intent.raw_query or positive_phrase, vertical=vertical)
        establisher = "vector_constrain"

    if not established:
        return {"path_taken": "EMPTY", "universe_establisher": establisher,
                "refinements_applied": refinements, "results": [],
                "exact_vs_related": {"exact": 0, "related": 0, "backfill": False},
                "intent": intent.model_dump()}

    established_ids = {it["entity_id"] for it in established}
    exact_count = len(established)
    needs_backfill = exact_count < backfill_threshold

    # ── 2. REFINE the established set (refiners only touch the handed set) ──────
    working = list(established)

    def _refine(label, new_set, kind):
        """Apply a refiner result, asserting the invariant (output ⊆ established set)."""
        out_ids = {it["entity_id"] for it in new_set}
        assert out_ids <= established_ids, f"INVARIANT VIOLATED: {label} introduced new entities"
        refinements.append(label)
        if kind and kind not in refiner_order:
            refiner_order.append(kind)
        return new_set

    # 2a. semantic rerank WITHIN a graph/seed-established set (vector-established sets are already ranked
    #     by the semantic phrase, so semrefine is only set for graph/seed establishers).
    if semrefine:
        working = _refine(f"vector_rerank_within(semantic='{semrefine}')",
                          B.vector_rerank_within(working, semrefine), "VECTOR_RERANK")
    # 2c. structural preferences -> graph rerank within. Includes soft.structural_prefs AND the
    #     non-enforceable hard structural (mode/feature like co-op/crafting), which graph boosts within
    #     the vector-established set rather than (wrongly) establishing on.
    refine_prefs = dict(nonenf_struct)
    refine_prefs.update(soft.structural_prefs or {})
    if refine_prefs:
        working = _refine(f"graph_rerank_within(prefs={refine_prefs})",
                          B.graph_rerank_within(working, refine_prefs,
                                                seed_entity=intent.seed_entity), "GRAPH_RERANK")

    # ── 3. NEGATIONS — hard exclusion on the final set (graph CONTRIBUTES here) ─────────────────
    if h.negations:
        before = len(working)
        working = B.apply_negations(working, h.negations)
        assert {it["entity_id"] for it in working} <= established_ids
        refinements.append(f"apply_negations({h.negations}) [{before}->{len(working)}]")
        # honest labelling (07f-fix #3): graph DID act (set-exclusion) — credit it in the path even when
        # no other graph refinement ran, so the label reflects every engine that contributed.
        if "GRAPH_NEGATE" not in refiner_order:
            refiner_order.append("GRAPH_NEGATE")

    # ── 3b. LEARNED RERANK — the FINAL refiner (flag-gated). Reorders whatever survived (after graph/
    #        negation refinement) by learned query↔candidate relevance. Refiner invariant enforced by
    #        _refine (output ⊆ established). Off unless RERANK=learned (proven on the honest harness). ──
    if config.RERANK == "cross_encoder" and working:
        working = _refine(f"rerank_cross_encoder(top_k={top_k})",
                          B.rerank_cross_encoder(intent.raw_query or positive_phrase, working, top_k=top_k),
                          "RERANK_XENC")
    elif config.RERANK == "auto" and working:
        fire, reason = should_rerank(intent, established, establisher, refiner_order)
        refinements.append(f"gate[{config.RERANK_GATE_SIGNAL}]: {'FIRE' if fire else 'hold'} — {reason}")
        if fire:
            working = _refine(f"rerank_cross_encoder(top_k={top_k})",
                              B.rerank_cross_encoder(intent.raw_query or positive_phrase, working, top_k=top_k),
                              "RERANK_XENC")
    elif config.RERANK == "learned" and working:
        working = _refine(f"rerank_learned(top_k={top_k})",
                          B.rerank_learned(intent.raw_query or positive_phrase, working, top_k=top_k),
                          "RERANK_LEARNED")

    # ── 4. BACKFILL (anchored, §6) if the established universe is too small ─────
    related = []
    if needs_backfill:
        related = backfill(established, intent, top_k=top_k, exclude=established_ids)
        refinements.append(f"backfill(anchored) [{exact_count} exact < {backfill_threshold}] "
                           f"-> {len(related)} related")

    # ── path name ──────────────────────────────────────────────────────────────
    est_token = {"graph_constrain": "GRAPH_CONSTRAIN", "vector_constrain": "VECTOR_CONSTRAIN",
                 "graph_vertical": "GRAPH_VERTICAL", "vector_seed": "SEED_VECTOR",
                 "multiseed": "MULTISEED"}[establisher]
    only_name = {"graph_constrain": "GRAPH_ONLY", "vector_constrain": "VECTOR_ONLY",
                 "graph_vertical": "GRAPH_VERTICAL_ONLY", "vector_seed": "SEED_VECTOR_ONLY",
                 "multiseed": "MULTISEED_ONLY"}[establisher]
    path = only_name if not refiner_order else "__".join([est_token] + refiner_order)
    if needs_backfill:
        path += "__BACKFILL"

    results = [dict(it, result_type="exact") for it in working[:top_k]] + \
              [dict(it, result_type="related") for it in related]

    return {
        "path_taken": path,
        "universe_establisher": establisher,
        "refinements_applied": refinements,
        "results": results,
        "exact_vs_related": {"exact": len(working), "related": len(related),
                             "backfill": needs_backfill},
        "intent": intent.model_dump(),
    }


def _parallel_assemble(jobs):
    """Run several assemble() sub-plans CONCURRENTLY — they're I/O-bound on the engines (Voyage + Vector
    Search + Neo4j), so wall-clock ≈ the SLOWEST sub-plan, not the sum. Input order is preserved. A
    single job runs inline (no thread overhead)."""
    if len(jobs) <= 1:
        return [assemble(*j) for j in jobs]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(jobs), 4)) as ex:
        return list(ex.map(lambda j: assemble(*j), jobs))


def assemble_multi(intents, top_k: int = 10, backfill_threshold: int = BACKFILL_THRESHOLD) -> dict:
    """Independent multi-intent (CONTEXT §7) — the RARE case where extraction emits >1 intent object
    (two genuinely independent universes, e.g. 'horror games AND cozy podcasts'). Run each as its own
    establish→refine sub-plan and MERGE into clearly-grouped sections. Distinct from the default
    single-universe path."""
    subs = _parallel_assemble([(it, top_k, backfill_threshold) for it in intents])
    groups, merged = [], []
    seen_labels = {}
    for i, (intent, sub) in enumerate(zip(intents, subs)):
        label = VLABEL.get(intent.vertical, (intent.vertical or "Group").title())
        seen_labels[label] = seen_labels.get(label, 0) + 1
        if seen_labels[label] > 1:               # disambiguate two intents of the same vertical
            label = f"{label} ({seen_labels[label]})"
        groups.append({"group": label, "intent_index": i, "path_taken": sub["path_taken"],
                       "universe_establisher": sub["universe_establisher"],
                       "refinements_applied": sub["refinements_applied"],
                       "exact_vs_related": sub["exact_vs_related"], "results": sub["results"]})
        for r in sub["results"]:
            merged.append(dict(r, group=label))
    return {"path_taken": "MULTI_INTENT", "n_intents": len(intents), "groups": groups,
            "results": merged, "intent": [it.model_dump() for it in intents]}


def _vertical_subintent(intent: Intent, v: str) -> Intent:
    """Derive a single-vertical sub-intent for vertical `v` from a multi-vertical intent (07f Fix 2).
    Seeds tagged for `v` are used same-vertical; if none are tagged for `v` but seeds exist, ALL seeds are
    used as cross-vertical anchors (recommend `v` based on the user's seeds); shared hard/soft (incl.
    negations) are carried so EVERY vertical's sub-plan is negation-filtered."""
    d = intent.model_dump()
    seeds = [s for s in d["seed_entities"] if s.get("vertical") == v] or list(d["seed_entities"])
    d["verticals"] = [v]
    d["vertical"] = v
    d["seed_entities"] = [{"name": s["name"], "vertical": v} for s in seeds]   # pin to this sub-plan's vertical
    d["seed_entity"] = ", ".join(s["name"] for s in seeds) if seeds else None
    return Intent.model_validate(d)


def assemble_multivertical(intent: Intent, top_k: int = 10,
                           backfill_threshold: int = BACKFILL_THRESHOLD) -> dict:
    """Multi-vertical coverage (07f Fix 2): a request spanning >1 vertical runs ONE establish→refine
    sub-plan PER requested vertical (so every vertical is represented, instead of one blended universe the
    largest seed-group dominates), merged into vertical-grouped sections. Reuses the MULTI_INTENT merge
    shape."""
    verticals = list(intent.verticals)
    subs = _parallel_assemble(
        [(_vertical_subintent(intent, v), top_k, backfill_threshold) for v in verticals])
    groups, merged = [], []
    for v, sub in zip(verticals, subs):
        label = VLABEL.get(v, v.title())
        groups.append({"group": label, "vertical": v, "path_taken": sub["path_taken"],
                       "universe_establisher": sub["universe_establisher"],
                       "refinements_applied": sub["refinements_applied"],
                       "exact_vs_related": sub["exact_vs_related"], "results": sub["results"]})
        for r in sub["results"]:
            merged.append(dict(r, group=label))
    return {"path_taken": "MULTIVERTICAL[" + ",".join(intent.verticals) + "]",
            "multi_vertical": True, "n_verticals": len(intent.verticals), "groups": groups,
            "results": merged, "intent": intent.model_dump()}


def assemble_query(intents, top_k: int = 10, backfill_threshold: int = BACKFILL_THRESHOLD) -> dict:
    """Dispatcher: >1 intent object -> independent multi-intent merge (CONTEXT §7); 1 intent spanning
    >1 vertical -> per-vertical coverage merge (07f); else the default single-universe assemble."""
    if not intents:
        return {"path_taken": "EMPTY", "universe_establisher": None, "refinements_applied": [],
                "results": [], "exact_vs_related": {"exact": 0, "related": 0, "backfill": False},
                "intent": []}
    if len(intents) > 1:
        return assemble_multi(intents, top_k=top_k, backfill_threshold=backfill_threshold)
    intent = intents[0]
    if len(intent.verticals) > 1:                       # multi-vertical single ask → per-vertical coverage
        return assemble_multivertical(intent, top_k=top_k, backfill_threshold=backfill_threshold)
    return assemble(intent, top_k=top_k, backfill_threshold=backfill_threshold)


if __name__ == "__main__":
    import json
    from extract import extract
    import sys
    q = " ".join(sys.argv[1:]) or "Horror games by a developer that also makes RPGs, atmospheric"
    out = assemble_query(extract(q))
    out["results"] = out["results"][:5]
    print(json.dumps(out, indent=2, ensure_ascii=False)[:2200])
