"""End-to-end query router for the Feeds.ai graph PoC.

Takes a natural-language query, classifies it into an archetype using the rules learned in
PROMPT 06 (the routing matrix), and dispatches to the matching graph query function — applying
the reranker where useful. For archetypes the matrix assigned to vectors (fuzzy/mood, date,
podcast-seeded), it returns an explicit `route="vector"` signal instead of forcing a weak graph
answer, honestly reflecting the complementary design.

Governing principle: **graph owns the EXPLICIT** (named relationships, exact attributes, structure
you can traverse), **vectors own the IMPLICIT** (mood, vibe, meaning, paraphrase). Every routing
decision is an instance of that split.

Classification is rule-based (regex + a concept/mood lexicon) — no LLM, no embeddings, consistent
with the PoC's constraint. Run the end-to-end demo:  ./.venv/bin/python src/router.py
"""

import re

from connection import get_driver, NEO4J_DATABASE
import query as Q
import rerank as R

_DRIVER = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = get_driver()
    return _DRIVER


# ───────────────────────── lexicons ─────────────────────────

def _load_concepts():
    with _driver().session(database=NEO4J_DATABASE) as s:
        return {r["k"] for r in s.run("MATCH (c:Concept) RETURN c.key AS k")}


_CONCEPTS = None
# common surface forms -> concept key (the NLU we don't have an LLM for)
_CONCEPT_SYNONYMS = {
    "sci-fi": "science fiction", "scifi": "science fiction", "sci fi": "science fiction",
    "rpg": "role-playing", "rpgs": "role-playing", "roguelike": "adventure",
    "soulslike": "role-playing", "platformer": "platform", "shooter": "action",
    "true crime": "crime", "docs": "documentary", "documentaries": "documentary",
}
_MOOD_WORDS = {
    "cozy", "cosy", "relaxing", "relax", "chill", "wholesome", "comfort", "comforting",
    "atmospheric", "vibe", "vibes", "mood", "melancholy", "melancholic", "feel-good",
    "feelgood", "uplifting", "soothing", "gentle", "heartwarming", "nostalgic", "dread",
    "slow-burn", "slow burn", "slow-building", "moody", "immersive", "haunting", "eerie",
    "bittersweet", "comfy", "laid-back", "feel like", "in the mood", "something that",
    "stressful", "cathartic", "escapist",
}
_NEG_MARKERS = [r"\bbut not\b", r"\bbut no\b", r"\bnothing\b", r"\bno\s+\w+\s+(?:games|shows|movies|content)",
                r"\bhate\b", r"\bdislike\b", r"\bdon'?t (?:like|want)\b", r"\bexcept\b",
                r"\bwithout\b", r"\bavoid\b", r"\bnot\s+\w+\s+(?:films|shows|games)"]
_DATE_MARKERS = [r"\b(19|20)\d\d\b", r"\brecent\b", r"\bnew(est)?\b", r"\bcoming out\b",
                 r"\bupcoming\b", r"\bthis year\b", r"\blast year\b", r"\bfrom the last\b",
                 r"\blatest\b", r"\breleased?\b", r"\bthis (week|month)\b"]
_MULTIHOP = [r"that also (?:make|made|makes|develop|developed|produce)",
             r"(?:developer|studio|publisher) (?:that|who|also)"]
_LANDMARK = [r"\bdefining\b", r"\blandmark\b", r"\biconic\b", r"\bmost (?:important|influential)\b",
             r"\bbest\b", r"\bessential\b", r"\bseminal\b", r"\bgenre-defining\b"]
_SIMILAR_PATTERNS = [
    r"similar to (.+)", r"more (?:games|movies|shows|titles|podcasts) like (.+)",
    r"\blike (.+)", r"based on (?:the )?(?:game|movie|tv show|show|film|podcast )?(.+)",
    r"if i (?:liked|loved|enjoyed) (.+)", r"fans? of (.+)",
    r"i (?:love|loved|enjoy|enjoyed|like|liked) (?:the )?(?:game|movie|tv show|show|film|podcast )(.+)",
]
_VERTICAL_WORDS = [
    (r"\b(movies?|films?)\b", "movie"), (r"\b(tv shows?|tv|series|shows?)\b", "tv"),
    (r"\b(games?|video games?)\b", "game"), (r"\b(podcasts?)\b", "podcast"),
]
_FRANCHISES = ["Final Fantasy", "Warhammer", "Star Wars", "Mario", "Zelda", "Pokemon",
               "Resident Evil", "Call of Duty", "Assassin's Creed", "Dragon Quest"]


def _concepts_in(text):
    global _CONCEPTS
    if _CONCEPTS is None:
        _CONCEPTS = _load_concepts()
    t = text.lower()
    found = set()
    for surf, key in _CONCEPT_SYNONYMS.items():
        if surf in t:
            found.add(key)
    for key in _CONCEPTS:
        if re.search(r"\b" + re.escape(key) + r"\b", t):
            found.add(key)
    return found


def _verticals_in(text):
    out = []
    for pat, v in _VERTICAL_WORDS:
        if re.search(pat, text.lower()) and v not in out:
            out.append(v)
    return out


def _has(text, markers):
    return any(re.search(m, text.lower()) for m in markers)


def _resolve_anchor(query):
    """Extract a named entity from 'like/similar to/based on X' patterns and resolve it."""
    for pat in _SIMILAR_PATTERNS:
        m = re.search(pat, query, re.IGNORECASE)
        if not m:
            continue
        cand = m.group(1).strip().strip(".?!,")
        # trim trailing clauses
        cand = re.split(r",| but | and recommend | recommend | suggest | from \d", cand)[0].strip()
        for strip_v, _ in _VERTICAL_WORDS:
            pass
        sid = Q.resolve(cand)
        if not sid:  # fuzzy contains fallback
            with _driver().session(database=NEO4J_DATABASE) as s:
                r = s.run("MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($n) "
                          "RETURN e.entity_id AS id ORDER BY e.influence DESC LIMIT 1", n=cand).single()
                sid = r["id"] if r else None
        if sid:
            with _driver().session(database=NEO4J_DATABASE) as s:
                rec = s.run("MATCH (e:Entity {entity_id:$id}) RETURN e.name AS name, e.vertical AS v, "
                            "size([(e)-[:HAS_CONCEPT]->()|1]) AS cc", id=sid).single()
            return {"id": sid, "name": rec["name"], "vertical": rec["v"], "concepts": rec["cc"]}, cand
    return None, None


# ───────────────────────── classify + route ─────────────────────────

P_EXPLICIT = "EXPLICIT (relationships/attributes/structure) → graph"
P_IMPLICIT = "IMPLICIT (mood/meaning/paraphrase) → vector"


def route(query, k=10):
    """Classify `query` -> archetype, dispatch to the graph (or signal route-to-vector)."""
    verts = _verticals_in(query)
    single_vert = verts[0] if len(verts) == 1 else None
    concepts = _concepts_in(query)
    has_neg = _has(query, _NEG_MARKERS)
    has_date = _has(query, _DATE_MARKERS)
    has_mood = any(w in query.lower() for w in _MOOD_WORDS)
    anchor, raw = _resolve_anchor(query)

    def pack(arch, route_to, method, results, rationale, **extra):
        return {"query": query, "archetype": arch, "route": route_to, "method": method,
                "principle": P_EXPLICIT if route_to in ("graph", "both") else P_IMPLICIT,
                "rationale": rationale, "vector_also": route_to in ("vector", "both"),
                "results": results or [], **extra}

    # 1. structured / multi-hop relational — the clearest graph-only win
    if _has(query, _MULTIHOP):
        # demo-grade extraction: first concept = seed genre, an RPG/other named genre = the join
        base = next(iter(concepts - {"role-playing"}), None) or (list(concepts)[0] if concepts else None)
        res = Q.cypher_structured({"vertical": single_vert or "game", "concept": base,
                                   "developer_also_made": "Role-Playing"}, limit=k) if base else []
        return pack("structured_multihop", "graph", "cypher_structured(multi-hop)", res,
                    "named relational join across DEVELOPED_BY — vectors cannot express this.")

    # 2. landmark / important
    if _has(query, _LANDMARK) and concepts:
        res = Q.top_by_influence({"vertical": single_vert, "concept": list(concepts)}, limit=k)
        return pack("landmark", "graph", "top_by_influence", res,
                    "importance ranking (PageRank) within an explicit filter — a graph-only archetype.")

    # 3. entity-seeded: similar (same vertical) or cross-vertical
    if anchor:
        if anchor["concepts"] == 0:  # podcast / attribute-less seed
            return pack("similar(podcast-seed)", "vector", None, [],
                        f"seed '{anchor['name']}' has no concept coverage (podcast/attribute-less) — "
                        "graph similarity is blind here; vector owns it.")
        targets = [v for v in verts if v != anchor["vertical"]]
        if targets:  # cross-vertical
            lists = [Q.cross_vertical(anchor["id"], tv) for tv in targets]
            merged = {}
            for lst in lists:
                if isinstance(lst, dict):
                    continue
                for r in lst:
                    merged.setdefault(r["name"].lower(), r)
            res = list(merged.values())[:k]
            note = f"seed {anchor['name']} [{anchor['vertical']}] → {targets} via shared Concept paths (explainable)."
            return pack("cross_vertical", "both", "cross_vertical", res, note,
                        also="vector adds semantic cross-vertical matches; merge.")
        # same-vertical similar (apply reranker)
        sim = Q.similar_by_attributes(anchor["id"], vertical=single_vert)
        if isinstance(sim, dict):
            return pack("similar(no-signal)", "vector", None, [], sim.get("reason", "no graph signal."))
        reranked = R.rerank(sim, seed=anchor["id"])[:k]
        return pack("similar_same_vertical", "both", "similar_by_attributes + rerank", reranked,
                    f"more-like-{anchor['name']} via :SIMILAR_TO (explainable shared attributes).",
                    also="vector adds semantic neighbours; merge.")

    # 3.5 mood-dominated (no nameable concept/entity) → vector, even with a 'not' qualifier
    if has_mood and not concepts and not anchor:
        return pack("descriptive_mood", "vector", None, [],
                    "implicit mood/paraphrase with no nameable structure; graph BM25 matches tokens "
                    "not meaning — vector owns it.")

    # 4. negative filtering (structured exclusion) — graph strength.
    # Separate the negated concept(s) from the positive intent FIRST.
    if has_neg:
        neg_terms = set(re.findall(r"(?:not|no|hate|dislike|without|avoid|except)\s+([a-z\- ]+)", query.lower()))
        neg_concepts = set()
        for t in neg_terms:
            neg_concepts |= _concepts_in(t)
        pos = list(concepts - neg_concepts)  # don't filter ON the thing we're excluding
        if pos:
            cand = Q.cypher_structured({"vertical": single_vert, "concept": pos}, limit=40)
        elif single_vert:
            cand = Q.top_by_influence({"vertical": single_vert}, limit=40)
        else:
            cand = Q.fulltext_search(query, vertical=single_vert, limit=40)
        with _driver().session(database=NEO4J_DATABASE) as s:
            res = []
            for r in cand:
                cs = {x["k"] for x in s.run(
                    "MATCH (e:Entity {name:$n})-[:HAS_CONCEPT]->(c) RETURN c.key AS k", n=r["name"])}
                if cs & neg_concepts:
                    continue
                res.append(r)
                if len(res) >= k:
                    break
        return pack("negative_filter", "graph", "cypher_structured(NOT)", res,
                    "precise exclusion via Cypher — graph expresses 'not X' exactly (vector NLU often drops it).")

    # 5. franchise / keyword
    fr = next((f for f in _FRANCHISES if f.lower() in query.lower()), None)
    if fr:
        res = Q.cypher_structured({"vertical": single_vert, "franchise": fr}, limit=k)
        if res:
            return pack("franchise", "graph", "cypher_structured(franchise)", res,
                        f"exact franchise membership ('{fr}') — no semantic drift (vector drifts to neighbours).",
                        also="vector fallback if franchise under-tagged.")

    # 6. date — graph is date-blind (no release_date loaded)
    if has_date and not concepts and not anchor:
        return pack("date_based", "vector", None, [],
                    "temporal filtering; the graph has no release_date property loaded — vector/SQL owns it.")

    # 7. mood / fuzzy — graph's core weakness
    if has_mood and not concepts:
        return pack("descriptive_mood", "vector", None, [],
                    "implicit mood/paraphrase; graph BM25 matches literal tokens, not meaning — vector owns it.")

    # 8. theme / keyword (concept-structured graph path + vector)
    if concepts:
        res = Q.cypher_structured({"vertical": single_vert, "concept": list(concepts)}, limit=k)
        if not res:
            res = Q.fulltext_search(query, vertical=single_vert, limit=k)
        return pack("theme_keyword", "both", "cypher_structured(concept)", res,
                    f"explicit concept membership ({', '.join(sorted(concepts))}).",
                    also="vector for nuance/synonymy; merge.")

    # 9. fallback: full-text keyword path; if it reads fuzzy, defer to vector
    if has_mood or has_date:
        return pack("fuzzy_fallback", "vector", None, [],
                    "no nameable structure detected — implicit query, vector owns it.")
    res = Q.fulltext_search(query, vertical=single_vert, limit=k)
    return pack("keyword_fallback", "both", "fulltext_search", res,
                "literal keyword match (BM25); vector for semantic coverage; merge.")


# ───────────────────────── demo ─────────────────────────

DEMO = [
    "Games similar to Hades II",
    "TV shows similar to Severance",
    "I love the game Hades II, recommend me movies",
    "Based on the TV show The Last of Us, what games would I enjoy",
    "Horror games by a developer that also makes RPGs",
    "The defining horror games",
    "Action games but nothing turn-based",
    "Recommend games but I hate sports games",
    "Final Fantasy games",
    "Dark fantasy games with challenging combat",
    "Horror content across all categories",
    "Games coming out in 2026",
    "Podcasts like Crime Junkie",
    "I'm in the mood for something cozy and relaxing that isn't stressful",
    "Something scary but not gory, slow-building dread",
]


def main():
    print("END-TO-END ROUTER DEMO\n" + "=" * 78)
    tally = {"graph": 0, "vector": 0, "both": 0}
    for q in DEMO:
        r = route(q)
        tally[r["route"]] += 1
        head = f"[{r['route'].upper():6}] {r['archetype']:<22} {q}"
        print("\n" + head)
        print(f"   method: {r['method'] or '— (route-to-vector)'}")
        print(f"   why: {r['rationale']}")
        if r["route"] == "vector":
            print("   → ROUTE-TO-VECTOR (no forced graph answer)")
        else:
            for x in r["results"][:5]:
                extra = f"  {x.get('why','')}" if x.get("why") else ""
                print(f"      • [{x['vertical']}] {x['name']}{extra}")
            if not r["results"]:
                print("      (no graph results)")
            if r.get("vector_also"):
                print("   + also route to VECTOR and merge")
    print("\n" + "=" * 78)
    print(f"Routing tally over {len(DEMO)} queries: {tally}")
    if _DRIVER is not None:
        _DRIVER.close()


if __name__ == "__main__":
    main()
