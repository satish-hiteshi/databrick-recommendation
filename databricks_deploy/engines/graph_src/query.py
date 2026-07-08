from contextlib import contextmanager

from connection import get_driver, NEO4J_DATABASE

_DRIVER = None
NO_GRAPH_SIGNAL = {"status": "no_graph_signal",
                   "reason": "no concept coverage — vector territory"}

# filter key -> (relationship, attribute label, match-property)
_ATTR = {
    "concept": ("HAS_CONCEPT", "Concept", "key"),     # unified genre∪theme (match lowercased)
    "genre": ("HAS_GENRE", "Genre", "name"),
    "theme": ("HAS_THEME", "Theme", "name"),
    "keyword": ("HAS_KEYWORD", "Keyword", "name"),
    "franchise": ("IN_FRANCHISE", "Franchise", "name"),
    "developer": ("DEVELOPED_BY", "Developer", "name"),
    "publisher": ("PUBLISHED_BY", "Publisher", "name"),
}


def _driver():
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = get_driver()
    return _DRIVER


@contextmanager
def _session():
    with _driver().session(database=NEO4J_DATABASE) as s:
        yield s


def _rows(session, cypher, **params):
    return [r.data() for r in session.run(cypher, **params)]


# ───────────────────────── shared filter builder ─────────────────────────

def _build_match(filters):
    patterns = ["(e:Entity)"]
    where, params, desc = [], {}, []
    if filters.get("vertical"):
        where.append("e.vertical = $vertical")
        params["vertical"] = filters["vertical"]
        desc.append(f"vertical={filters['vertical']}")
    i = 0
    for key, (rel, lbl, prop) in _ATTR.items():
        vals = filters.get(key)
        if not vals:
            continue
        vals = [vals] if isinstance(vals, str) else vals
        for v in vals:
            i += 1
            pv = f"a{i}"
            patterns.append(f"(e)-[:{rel}]->(:{lbl} {{{prop}: ${pv}}})")
            params[pv] = v.lower() if prop == "key" else v
            desc.append(f"{key}={v}")
    return patterns, where, params, "; ".join(desc)


# ───────────────────────── 1. structured / relational (+ multi-hop) ─────────────────────────

def cypher_structured(filters, limit=10):
    patterns, where, params, desc = _build_match(filters)
    params["limit"] = limit
    dam = filters.get("developer_also_made")
    if dam:
        params["dam"] = dam.lower()
        cypher = (
            "MATCH " + ", ".join(patterns) +
            (" WHERE " + " AND ".join(where) if where else "") +
            " MATCH (e)-[:DEVELOPED_BY]->(dev:Developer)<-[:DEVELOPED_BY]-(other:Entity) "
            " WHERE other <> e AND (other)-[:HAS_CONCEPT]->(:Concept {key:$dam}) "
            " WITH e, dev, collect(DISTINCT other.name)[..2] AS examples "
            " RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical, "
            "        round(COALESCE(e.influence, e.pagerank, 0.0),4) AS score, dev.name AS developer, examples "
            " ORDER BY score DESC LIMIT $limit")
        out = []
        with _session() as s:
            for r in _rows(s, cypher, **params):
                r["why"] = (f"{desc}; developer {r['developer']} also made a "
                            f"{dam} title (e.g. {', '.join(r['examples'])})")
                out.append(r)
        return out

    cypher = (
        "MATCH " + ", ".join(patterns) +
        (" WHERE " + " AND ".join(where) if where else "") +
        " RETURN DISTINCT e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical, "
        "        round(COALESCE(e.influence, e.pagerank, 0.0),4) AS score "
        " ORDER BY score DESC LIMIT $limit")
    with _session() as s:
        out = _rows(s, cypher, **params)
    for r in out:
        r["why"] = f"matches {desc}"
    return out


# ───────────────────────── 2. full-text / keyword (BM25) ─────────────────────────

def fulltext_search(text, vertical=None, limit=10):
    cypher = (
        "CALL db.index.fulltext.queryNodes('entityText', $q) YIELD node, score "
        "WHERE $vertical IS NULL OR node.vertical = $vertical "
        "RETURN node.entity_id AS entity_id, node.name AS name, node.vertical AS vertical, "
        "       round(score,4) AS score "
        "LIMIT $limit")
    with _session() as s:
        out = _rows(s, cypher, q=text, vertical=vertical, limit=limit)
    for r in out:
        r["why"] = f"BM25 match for '{text}'"
    return out


# ───────────────────────── seed coverage helper (podcast blind spot) ─────────────────────────

def _concept_coverage(session, entity_id):
    rec = session.run(
        "MATCH (e:Entity {entity_id:$id}) "
        "RETURN size([(e)-[:HAS_CONCEPT]->()|1]) AS c, "
        "       size([(e)-[:IN_FRANCHISE]->()|1]) AS f", id=entity_id).single()
    return (rec["c"], rec["f"]) if rec else (None, None)


# ───────────────────────── 3. similar-by-attributes (:SIMILAR_TO) ─────────────────────────

def similar_by_attributes(entity_id, vertical=None, limit=10):
    with _session() as s:
        c, _f = _concept_coverage(s, entity_id)
        if c is None:
            return {"status": "not_found", "reason": f"no entity {entity_id}"}
        if c == 0:
            return dict(NO_GRAPH_SIGNAL)
        cypher = (
            "MATCH (a:Entity {entity_id:$id})-[r:SIMILAR_TO]->(b:Entity) "
            "WHERE $vertical IS NULL OR b.vertical = $vertical "
            "WITH a, b, r "
            "RETURN b.entity_id AS entity_id, b.name AS name, b.vertical AS vertical, "
            "       round(r.score,3) AS score, "
            "       [(a)-[:HAS_CONCEPT]->(c)<-[:HAS_CONCEPT]-(b) | c.name] AS shared_concepts, "
            "       [(a)-[:IN_FRANCHISE]->(f)<-[:IN_FRANCHISE]-(b) | f.name] AS shared_franchise "
            "ORDER BY r.score DESC LIMIT $limit")
        out = _rows(s, cypher, id=entity_id, vertical=vertical, limit=limit)
    for r in out:
        bits = []
        if r["shared_concepts"]:
            bits.append("connected via " + ", ".join(r["shared_concepts"][:4]))
        if r["shared_franchise"]:
            bits.append("same franchise: " + ", ".join(r["shared_franchise"]))
        r["why"] = "; ".join(bits) or "shared attributes"
    return out


# ───────────────────────── 4. landmark / important (PageRank) ─────────────────────────

def top_by_influence(filters, limit=10):
    patterns, where, params, desc = _build_match(filters)
    params["limit"] = limit
    cypher = (
        "MATCH " + ", ".join(patterns) +
        (" WHERE " + " AND ".join(where) if where else "") +
        " RETURN DISTINCT e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical, "
        "        round(COALESCE(e.influence, e.pagerank, 0.0),4) AS score "
        " ORDER BY score DESC LIMIT $limit")
    with _session() as s:
        out = _rows(s, cypher, **params)
    for r in out:
        r["why"] = f"PageRank landmark within [{desc}]"
    return out


# ───────────────────────── 5. neighborhood / browse (Louvain) ─────────────────────────

def community_browse(entity_id=None, community_id=None, limit=10):
    with _session() as s:
        if community_id is None:
            if entity_id is None:
                raise ValueError("provide entity_id or community_id")
            rec = s.run("MATCH (e:Entity {entity_id:$id}) RETURN e.community AS c", id=entity_id).single()
            if not rec or rec["c"] is None:
                return {"status": "not_found", "reason": f"no community for {entity_id}"}
            community_id = rec["c"]
        label = [r["name"] for r in s.run(
            "MATCH (e:Entity {community:$c})-[:HAS_GENRE]->(g:Genre) "
            "RETURN g.name AS name, count(*) AS n ORDER BY n DESC LIMIT 3", c=community_id)]
        size = s.run("MATCH (e:Entity {community:$c}) RETURN count(*) AS n", c=community_id).single()["n"]
        out = _rows(s,
            "MATCH (e:Entity {community:$c}) "
            "RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical, "
            "       round(COALESCE(e.influence, e.pagerank, 0.0),4) AS score "
            "ORDER BY COALESCE(e.influence, e.pagerank, 0.0) DESC LIMIT $limit", c=community_id, limit=limit)
    lbl = "/".join(label) if label else "(no dominant genres)"
    for r in out:
        r["why"] = f"community {community_id} [{lbl}], size {size}"
    return out


# ───────────────────────── 6. KNN ANN (:KNN_SIMILAR) ─────────────────────────

def knn_ann(entity_id, vertical=None, limit=10):
    with _session() as s:
        c, _f = _concept_coverage(s, entity_id)
        if c is None:
            return {"status": "not_found", "reason": f"no entity {entity_id}"}
        if c == 0:
            return dict(NO_GRAPH_SIGNAL)
        cypher = (
            "MATCH (a:Entity {entity_id:$id})-[r:KNN_SIMILAR]->(b:Entity) "
            "WHERE $vertical IS NULL OR b.vertical = $vertical "
            "RETURN b.entity_id AS entity_id, b.name AS name, b.vertical AS vertical, "
            "       round(r.score,3) AS score, "
            "       [(a)-[:HAS_CONCEPT]->(c)<-[:HAS_CONCEPT]-(b) | c.name] AS shared_concepts "
            "ORDER BY r.score DESC LIMIT $limit")
        out = _rows(s, cypher, id=entity_id, vertical=vertical, limit=limit)
    for r in out:
        r["why"] = ("connected via " + ", ".join(r["shared_concepts"][:4])) if r["shared_concepts"] else "attribute-vector neighbor"
    return out


# ───────────────────────── 7. cross-vertical via shared attributes ─────────────────────────

def cross_vertical(entity_id, target_vertical, limit=10):
    with _session() as s:
        c, f = _concept_coverage(s, entity_id)
        if c is None:
            return {"status": "not_found", "reason": f"no entity {entity_id}"}
        if c == 0 and f == 0:
            return dict(NO_GRAPH_SIGNAL)
        cypher = (
            "MATCH (a:Entity {entity_id:$id}) "
            "MATCH (a)-[:HAS_CONCEPT|IN_FRANCHISE]->(shared)<-[:HAS_CONCEPT|IN_FRANCHISE]-(b:Entity) "
            "WHERE b <> a AND b.vertical = $tv "
            "WITH b, "
            "  [x IN collect(DISTINCT shared) WHERE x:Concept   | x.name] AS concepts, "
            "  [x IN collect(DISTINCT shared) WHERE x:Franchise | x.name] AS franchises "
            "RETURN b.entity_id AS entity_id, b.name AS name, b.vertical AS vertical, "
            "       size(concepts) + 5*size(franchises) AS score, concepts, franchises, b.influence AS influence "
            "ORDER BY score DESC, influence DESC LIMIT $limit")
        out = _rows(s, cypher, id=entity_id, tv=target_vertical, limit=limit)
    for r in out:
        bits = []
        if r["franchises"]:
            bits.append("same franchise: " + ", ".join(r["franchises"]))
        if r["concepts"]:
            bits.append("connected via " + ", ".join(r["concepts"][:4]))
        r["why"] = "; ".join(bits) or "shared attribute"
    return out


# ───────────────────────── helpers + CLI demo ─────────────────────────

def resolve(name, vertical=None):
    with _session() as s:
        rec = s.run(
            "MATCH (e:Entity) WHERE toLower(e.name) = toLower($n) "
            "AND ($v IS NULL OR e.vertical = $v) "
            "RETURN e.entity_id AS id ORDER BY COALESCE(e.influence, e.pagerank, 0.0) DESC LIMIT 1",
            n=name, v=vertical).single()
        return rec["id"] if rec else None


def _show(title, results, n=6):
    print(f"\n### {title}")
    if isinstance(results, dict):  # status signal
        print(f"   -> {results}")
        return
    if not results:
        print("   (no results)")
        return
    for r in results[:n]:
        why = f"   — {r['why']}" if r.get("why") else ""
        print(f"   {r.get('score'):>8}  [{r['vertical']}] {r['name']}{why}")


def main():
    # ── 1. structured + the headline MULTI-HOP (graph-only) ──
    _show("cypher_structured — horror movies (concept), landmark-first",
          cypher_structured({"vertical": "movie", "concept": "Horror"}))
    _show("cypher_structured — MULTI-HOP: horror GAMES by a developer that ALSO made an RPG "
          "(vectors cannot express this)",
          cypher_structured({"vertical": "game", "concept": "Horror",
                             "developer_also_made": "Role-Playing"}))

    # ── 2. full-text BM25 ──
    _show("fulltext_search — 'post-apocalyptic survival' (all verticals)",
          fulltext_search("post-apocalyptic survival"))
    _show("fulltext_search — 'true crime' restricted to podcasts (graph's only podcast play)",
          fulltext_search("true crime", vertical="podcast"))

    # ── 3 & 6. similar_by_attributes vs knn_ann on the same seed ──
    seed = resolve("7 Days to Die", "game")
    _show("similar_by_attributes — '7 Days to Die' [game] (:SIMILAR_TO, explainable)",
          similar_by_attributes(seed))
    _show("knn_ann — '7 Days to Die' [game] (:KNN_SIMILAR, ANN-on-attributes)",
          knn_ann(seed))

    # ── 4. landmark / PageRank ──
    _show("top_by_influence — landmark horror games (concept=Horror)",
          top_by_influence({"vertical": "game", "concept": "Horror"}))

    # ── 5. community browse ──
    _show("community_browse — neighborhood of '7 Days to Die'",
          community_browse(entity_id=seed))

    # ── 7. CROSS-VERTICAL (graph-only win) ──
    qseed = resolve("Quake II", "game")
    _show("cross_vertical — game 'Quake II' -> MOVIES via shared concepts (graph-only, explainable)",
          cross_vertical(qseed, "movie"))
    sseed = resolve("Resident Evil Re:Verse", "game") or resolve("Resident Evil", "game")
    if sseed:
        _show("cross_vertical — a Resident Evil game -> MOVIES (franchise/concept path)",
              cross_vertical(sseed, "movie"))

    # ── podcast blind spot (honest no_graph_signal) ──
    pseed = resolve("Crime Junkie", "podcast")
    _show("similar_by_attributes — podcast 'Crime Junkie' (expect no_graph_signal)",
          similar_by_attributes(pseed))
    _show("cross_vertical — podcast 'Crime Junkie' -> movies (expect no_graph_signal)",
          cross_vertical(pseed, "movie"))
    _show("fulltext_search — 'Crime Junkie'-style: 'serial killer investigation' podcasts "
          "(the graph path that DOES work for podcasts)",
          fulltext_search("serial killer investigation", vertical="podcast"))

    if _DRIVER is not None:
        _DRIVER.close()


if __name__ == "__main__":
    main()
