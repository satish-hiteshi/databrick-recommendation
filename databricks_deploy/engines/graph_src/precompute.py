"""GDS precompute layer for the Feeds.ai graph PoC (CONTEXT.md §5).

Runs the four algorithms via the graphdatascience client, writing results back so
reads are fast, and reports stats / samples / coverage.

CRITICAL — genre/theme unification (PROMPT 02 finding):
  The SAME concept is modeled differently per vertical: "horror" is a *Genre* for
  movies/TV but a *Theme* for games. With separate Genre/Theme nodes, a horror game
  (Theme:Horror) and a horror movie (Genre:Horror) share NO node and look unrelated —
  silently breaking the cross-vertical matching this project exists to do. We:
    1. Report genre<->theme name overlap (names that are BOTH a Genre and a Theme),
       flagging non-identical near-synonyms (e.g. War vs Warfare) without merging them.
    2. Materialize a unified `(:Concept {key,name})` layer: every genre and theme name
       maps (case-insensitively) to one Concept, with (:Entity)-[:HAS_CONCEPT]->(:Concept).
       So Genre:Horror and Theme:Horror collapse to Concept:horror.
    3. Run Node Similarity BOTH ways and compare cross-vertical recall:
         (i) genre-only shared neighbors,  (ii) genre+theme unified (Concept) shared neighbors.
       The combined (unified) version is the PRIMARY :SIMILAR_TO / :KNN_SIMILAR going
       forward; genre-only numbers are reported for comparison.

Algorithms / writes:
  1. PageRank      -> Entity.influence
  2. Louvain       -> Entity.community
  3. Node Sim.     -> (:Entity)-[:SIMILAR_TO {score}]->(:Entity)   (unified concepts + kw + franchise)
  4. Filtered-KNN  -> (:Entity)-[:KNN_SIMILAR {score}]->(:Entity)  (cosine on unified concept vector)

Run:  ./.venv/bin/python src/precompute.py
"""

import json
import time
from pathlib import Path

import pandas as pd

from connection import get_driver, get_gds, NEO4J_DATABASE

_ROOT = Path(__file__).resolve().parent.parent
ENTITIES = _ROOT / "data" / "entities.jsonl"
OUT = _ROOT / "results" / "precompute_stats.json"

PRIMARY_GRAPH = "feedsai_primary"   # Entity + Concept + Keyword + Franchise (UNDIRECTED)
CMP_GENRE = "cmp_genre"             # Entity + Genre (genre-only comparison)
CMP_CONCEPT = "cmp_concept"         # Entity + Concept (genre+theme unified comparison)
KNN_GRAPH = "feedsai_knn"           # node-only + unified attrVec
VERTICAL_LABELS = {"game": "Game", "movie": "Movie", "tv": "Tv", "podcast": "Podcast"}
TOP_K = 10


# ───────────────────────── genre/theme overlap report ─────────────────────────

def report_overlap(driver):
    with driver.session(database=NEO4J_DATABASE) as s:
        genres = sorted(r["n"] for r in s.run("MATCH (g:Genre) RETURN g.name AS n"))
        themes = sorted(r["n"] for r in s.run("MATCH (t:Theme) RETURN t.name AS n"))
    gl = {g.lower(): g for g in genres}
    tl = {t.lower(): t for t in themes}
    exact = sorted(set(gl) & set(tl))
    overlap = [{"concept": k, "genre": gl[k], "theme": tl[k],
                "case_differs": gl[k] != tl[k]} for k in exact]
    # Near-synonyms across genre/theme (NOT exact) — flag, do NOT merge.
    near = []
    for g in genres:
        for t in themes:
            if g.lower() == t.lower():
                continue
            gl_, tl_ = g.lower(), t.lower()
            if gl_[:4] == tl_[:4] or gl_ in tl_ or tl_ in gl_:
                near.append({"genre": g, "theme": t})
    return {"n_genres": len(genres), "n_themes": len(themes),
            "genres": genres, "themes": themes,
            "unifiable_exact_caseinsensitive": overlap,
            "flagged_near_synonyms_not_merged": near}


# ───────────────────────── unified Concept layer + attrVec + labels ─────────────────────────

def build_concepts_vectors_labels(driver):
    """Materialize the unified Concept layer (genre∪theme by case-insensitive name),
    write a multi-hot `attrVec` over concepts to each Entity, and add vertical labels."""
    with driver.session(database=NEO4J_DATABASE) as s:
        s.run("CREATE CONSTRAINT concept_key_unique IF NOT EXISTS "
              "FOR (c:Concept) REQUIRE c.key IS UNIQUE").consume()
        # Genres first so the genre casing wins as the Concept display name.
        s.run("MATCH (e:Entity)-[:HAS_GENRE]->(g:Genre) "
              "MERGE (c:Concept {key: toLower(g.name)}) ON CREATE SET c.name = g.name "
              "MERGE (e)-[:HAS_CONCEPT]->(c)").consume()
        s.run("MATCH (e:Entity)-[:HAS_THEME]->(t:Theme) "
              "MERGE (c:Concept {key: toLower(t.name)}) ON CREATE SET c.name = t.name "
              "MERGE (e)-[:HAS_CONCEPT]->(c)").consume()
        n_concepts = s.run("MATCH (c:Concept) RETURN count(*) AS c").single()["c"]
        n_has = s.run("MATCH ()-[r:HAS_CONCEPT]->() RETURN count(*) AS c").single()["c"]

    # Unified multi-hot vector over concept keys (genres+themes collapsed by name).
    rows = [json.loads(l) for l in ENTITIES.read_text().splitlines() if l.strip()]
    keys = sorted({v.lower() for r in rows for v in (r["genres"] + r["themes"])})
    idx = {k: i for i, k in enumerate(keys)}
    dim = len(keys)
    payload = []
    for r in rows:
        vec = [0.0] * dim
        for v in r["genres"] + r["themes"]:
            vec[idx[v.lower()]] = 1.0
        payload.append({"entity_id": r["entity_id"], "vec": vec})

    with driver.session(database=NEO4J_DATABASE) as s:
        for i in range(0, len(payload), 1000):
            s.run("UNWIND $rows AS row MATCH (e:Entity {entity_id: row.entity_id}) "
                  "SET e.attrVec = row.vec", rows=payload[i:i + 1000]).consume()
        for vert, lbl in VERTICAL_LABELS.items():
            s.run(f"MATCH (e:Entity {{vertical: $v}}) SET e:{lbl}", v=vert).consume()
    return {"concepts": n_concepts, "has_concept_edges": n_has,
            "attrvec_dim": dim, "note": "concept = genres∪themes unified case-insensitively"}


# ───────────────────────── projections ─────────────────────────

def _drop(gds, name):
    if gds.graph.exists(name)["exists"]:
        gds.graph.drop(name)


def project_primary(gds):
    _drop(gds, PRIMARY_GRAPH)
    rel = {t: {"orientation": "UNDIRECTED"} for t in
           ["HAS_CONCEPT", "HAS_KEYWORD", "IN_FRANCHISE"]}
    G, _ = gds.graph.project(PRIMARY_GRAPH,
                             ["Entity", "Concept", "Keyword", "Franchise"], rel)
    return G


def project_natural(gds, name, attr_label, rel_type):
    _drop(gds, name)
    G, _ = gds.graph.project(name, ["Entity", attr_label], rel_type)  # NATURAL: only Entity has outgoing
    return G


def project_knn(gds):
    _drop(gds, KNN_GRAPH)
    G, _ = gds.graph.project(KNN_GRAPH, list(VERTICAL_LABELS.values()), "*",
                             nodeProperties=["attrVec"])
    return G


# ───────────────────────── helpers ─────────────────────────

def _delete_rels(driver, reltype):
    with driver.session(database=NEO4J_DATABASE) as s:
        s.run("CALL apoc.periodic.iterate("
              f"'MATCH ()-[r:{reltype}]->() RETURN r', 'DELETE r', "
              "{batchSize:10000, parallel:false})").consume()


def _id_to_vertical(driver):
    with driver.session(database=NEO4J_DATABASE) as s:
        return {r["id"]: r["v"] for r in
                s.run("MATCH (e:Entity) RETURN id(e) AS id, e.vertical AS v")}


def _stream_xvert(gds, G, id2v):
    """Run nodeSimilarity.stream and count total + cross-vertical pairs."""
    df = gds.nodeSimilarity.stream(G, topK=TOP_K)
    if df.empty:
        return {"total_pairs": 0, "cross_vertical_pairs": 0}
    v1 = df["node1"].map(id2v)
    v2 = df["node2"].map(id2v)
    xv = int((v1 != v2).sum())
    return {"total_pairs": int(len(df)), "cross_vertical_pairs": xv}


# ───────────────────────── algorithms ─────────────────────────

def run_pagerank(gds, G, driver):
    t0 = time.time()
    res = gds.pageRank.write(G, writeProperty="influence", maxIterations=30, dampingFactor=0.85)
    wall = time.time() - t0
    with driver.session(database=NEO4J_DATABASE) as s:
        s.run("MATCH (n) WHERE n.influence IS NOT NULL AND NOT n:Entity REMOVE n.influence").consume()
        top = [r.data() for r in s.run(
            "MATCH (e:Entity) RETURN e.name AS name, e.vertical AS vertical, "
            "round(e.influence,4) AS influence ORDER BY e.influence DESC LIMIT 15")]
        ent_dist = s.run(
            "MATCH (e:Entity) WITH e.influence AS x "
            "RETURN round(min(x),4) AS min, round(max(x),4) AS max, round(avg(x),4) AS mean, "
            "round(percentileCont(x,0.5),4) AS p50, round(percentileCont(x,0.9),4) AS p90, "
            "round(percentileCont(x,0.99),4) AS p99").single().data()
        per_vert_top = {v: [r.data() for r in s.run(
            "MATCH (e:Entity {vertical:$v}) RETURN e.name AS name, round(e.influence,4) AS influence "
            "ORDER BY e.influence DESC LIMIT 3", v=v)] for v in ["game", "movie", "tv", "podcast"]}
    return {"compute_millis": int(res["computeMillis"]), "wall_s": round(wall, 2),
            "entity_distribution": ent_dist, "top15": top, "top3_per_vertical": per_vert_top,
            "note": "GDS centralityDistribution covers attribute nodes too; entity_distribution is Entity-only."}


def run_louvain(gds, G, driver):
    t0 = time.time()
    res = gds.louvain.write(G, writeProperty="community")
    wall = time.time() - t0
    with driver.session(database=NEO4J_DATABASE) as s:
        s.run("MATCH (n) WHERE n.community IS NOT NULL AND NOT n:Entity REMOVE n.community").consume()
        sizes = [(r["c"], r["n"]) for r in s.run(
            "MATCH (e:Entity) WHERE e.community IS NOT NULL "
            "RETURN e.community AS c, count(*) AS n ORDER BY n DESC")]
        top5 = []
        for cid, n in sizes[:5]:
            members = [r.data() for r in s.run(
                "MATCH (e:Entity {community:$c}) RETURN e.name AS name, e.vertical AS v "
                "ORDER BY e.influence DESC LIMIT 5", c=cid)]
            genres = [r.data() for r in s.run(
                "MATCH (e:Entity {community:$c})-[:HAS_GENRE]->(g:Genre) "
                "RETURN g.name AS name, count(*) AS n ORDER BY n DESC LIMIT 3", c=cid)]
            verts = {r["v"]: r["n"] for r in s.run(
                "MATCH (e:Entity {community:$c}) RETURN e.vertical AS v, count(*) AS n ORDER BY n DESC", c=cid)}
            top5.append({"community": cid, "size": n, "vertical_mix": verts,
                         "dominant_genres": genres, "sample_members": members})
        singletons = sum(1 for _, n in sizes if n == 1)
    return {"compute_millis": int(res["computeMillis"]), "wall_s": round(wall, 2),
            "community_count": int(res["communityCount"]), "modularity": round(float(res["modularity"]), 4),
            "entity_communities": len(sizes), "singleton_communities": singletons,
            "largest_sizes": [n for _, n in sizes[:10]], "top5_communities": top5}


def run_node_similarity(gds, G, driver):
    _delete_rels(driver, "SIMILAR_TO")
    t0 = time.time()
    res = gds.nodeSimilarity.filtered.write(
        G, writeRelationshipType="SIMILAR_TO", writeProperty="score",
        topK=TOP_K, sourceNodeFilter="Entity", targetNodeFilter="Entity")
    wall = time.time() - t0
    with driver.session(database=NEO4J_DATABASE) as s:
        top10 = [r.data() for r in s.run(
            "MATCH (a:Entity)-[r:SIMILAR_TO]->(b:Entity) "
            "RETURN a.name AS a, a.vertical AS av, b.name AS b, b.vertical AS bv, "
            "round(r.score,3) AS score ORDER BY r.score DESC, a.name LIMIT 10")]
        cross = [r.data() for r in s.run(
            "MATCH (a:Entity)-[r:SIMILAR_TO]->(b:Entity) WHERE a.vertical <> b.vertical "
            "RETURN a.name AS a, a.vertical AS av, b.name AS b, b.vertical AS bv, "
            "round(r.score,3) AS score ORDER BY r.score DESC LIMIT 6")]
        n_cross = s.run("MATCH (a:Entity)-[:SIMILAR_TO]->(b:Entity) WHERE a.vertical<>b.vertical "
                        "RETURN count(*) AS n").single()["n"]
    return {"compute_millis": int(res["computeMillis"]), "wall_s": round(wall, 2),
            "relationships_written": int(res["relationshipsWritten"]),
            "similarity_distribution": {k: round(float(v), 4) for k, v in
                                        dict(res["similarityDistribution"]).items() if isinstance(v, (int, float))},
            "cross_vertical_edges": n_cross, "top10_pairs": top10, "cross_vertical_samples": cross}


def run_filtered_knn(gds, G, driver):
    _delete_rels(driver, "KNN_SIMILAR")
    per_vertical = {}
    total_ms = 0
    t0 = time.time()
    for vert, lbl in VERTICAL_LABELS.items():
        res = gds.knn.filtered.write(
            G, nodeProperties={"attrVec": "COSINE"}, topK=TOP_K,
            sourceNodeFilter=lbl, targetNodeFilter=lbl,
            writeRelationshipType="KNN_SIMILAR", writeProperty="score",
            randomSeed=42, concurrency=1, sampleRate=0.8, deltaThreshold=0.001, similarityCutoff=0.1)
        total_ms += int(res["computeMillis"])
        per_vertical[vert] = {"relationships_written": int(res["relationshipsWritten"]),
                              "compute_millis": int(res["computeMillis"])}
    wall = time.time() - t0
    with driver.session(database=NEO4J_DATABASE) as s:
        total = s.run("MATCH ()-[r:KNN_SIMILAR]->() RETURN count(r) AS n").single()["n"]
        samples = [r.data() for r in s.run(
            "MATCH (a:Entity)-[r:KNN_SIMILAR]->(b:Entity) "
            "RETURN a.name AS a, a.vertical AS av, b.name AS b, round(r.score,3) AS score "
            "ORDER BY r.score DESC, a.name LIMIT 10")]
    return {"wall_s": round(wall, 2), "total_compute_millis": total_ms,
            "relationships_written_total": total, "per_vertical": per_vertical, "sample_pairs": samples}


# ───────────────────────── coverage + comparison ─────────────────────────

def coverage_report(driver):
    with driver.session(database=NEO4J_DATABASE) as s:
        cov = [r.data() for r in s.run(
            "MATCH (e:Entity) WITH e, size([(e)-[:SIMILAR_TO]->()|1]) AS sim, "
            "        size([(e)-[:KNN_SIMILAR]->()|1]) AS knn "
            "RETURN e.vertical AS vertical, "
            "  sum(CASE WHEN sim>0 THEN 1 ELSE 0 END) AS with_similar_to, "
            "  sum(CASE WHEN knn>0 THEN 1 ELSE 0 END) AS with_knn_similar, "
            "  sum(CASE WHEN sim=0 AND knn=0 THEN 1 ELSE 0 END) AS with_no_sim_edges, "
            "  count(*) AS total ORDER BY total DESC")]
        comm = [r.data() for r in s.run(
            "MATCH (e:Entity) WHERE e.community IS NOT NULL "
            "RETURN e.vertical AS vertical, count(DISTINCT e.community) AS communities, "
            "count(*) AS entities ORDER BY entities DESC")]
    return {"similarity_coverage_by_vertical": cov, "community_coverage_by_vertical": comm}


def compare_examples(driver, names):
    out = []
    with driver.session(database=NEO4J_DATABASE) as s:
        for nm in names:
            simto = [r.data() for r in s.run(
                "MATCH (a:Entity {name:$n})-[r:SIMILAR_TO]->(b:Entity) "
                "RETURN b.name AS name, b.vertical AS v, round(r.score,3) AS score "
                "ORDER BY r.score DESC LIMIT 5", n=nm)]
            knn = [r.data() for r in s.run(
                "MATCH (a:Entity {name:$n})-[r:KNN_SIMILAR]->(b:Entity) "
                "RETURN b.name AS name, b.vertical AS v, round(r.score,3) AS score "
                "ORDER BY r.score DESC LIMIT 5", n=nm)]
            info = s.run("MATCH (e:Entity {name:$n}) RETURN e.vertical AS v, "
                         "[(e)-[:HAS_GENRE]->(g)|g.name] AS genres, "
                         "[(e)-[:HAS_THEME]->(t)|t.name] AS themes LIMIT 1", n=nm).single()
            out.append({"name": nm, "vertical": info["v"] if info else None,
                        "genres": info["genres"] if info else [], "themes": info["themes"] if info else [],
                        "similar_to_top5": simto, "knn_similar_top5": knn})
    return out


# ───────────────────────── main ─────────────────────────

def main():
    driver = get_driver()
    gds = get_gds()
    report = {}
    try:
        print("Reporting genre<->theme overlap ...")
        report["genre_theme_overlap"] = report_overlap(driver)
        ov = report["genre_theme_overlap"]
        print(f"  {len(ov['unifiable_exact_caseinsensitive'])} unifiable concepts, "
              f"{len(ov['flagged_near_synonyms_not_merged'])} flagged near-synonyms")

        print("Building unified Concept layer + attrVec + vertical labels ...")
        report["concept_layer"] = build_concepts_vectors_labels(driver)
        print(f"  {report['concept_layer']['concepts']} concepts, "
              f"{report['concept_layer']['has_concept_edges']} HAS_CONCEPT, "
              f"attrVec dim={report['concept_layer']['attrvec_dim']}")

        # ── genre-only vs genre+theme(unified) cross-vertical comparison ──
        print("Comparing genre-only vs genre+theme(unified) cross-vertical recall ...")
        id2v = _id_to_vertical(driver)
        Gg = project_natural(gds, CMP_GENRE, "Genre", "HAS_GENRE")
        genre_only = _stream_xvert(gds, Gg, id2v)
        _drop(gds, CMP_GENRE)
        Gc = project_natural(gds, CMP_CONCEPT, "Concept", "HAS_CONCEPT")
        combined = _stream_xvert(gds, Gc, id2v)
        _drop(gds, CMP_CONCEPT)
        report["similarity_comparison"] = {
            "genre_only": genre_only, "genre_plus_theme_unified": combined,
            "cross_vertical_recovered": combined["cross_vertical_pairs"] - genre_only["cross_vertical_pairs"],
            "note": "Same Jaccard top-K=10. Unifying genre+theme by name recovers cross-vertical pairs "
                    "(e.g. horror game <-> horror movie) that the separate genre/theme spaces miss."}
        print(f"  genre-only x-vert pairs: {genre_only['cross_vertical_pairs']}  |  "
              f"genre+theme(unified) x-vert pairs: {combined['cross_vertical_pairs']}  |  "
              f"recovered: {report['similarity_comparison']['cross_vertical_recovered']}")

        # ── primary projection: PageRank, Louvain, Node Similarity (unified) ──
        print("Projecting primary graph (Concept+Keyword+Franchise, UNDIRECTED) ...")
        Gp = project_primary(gds)
        report["projection_primary"] = {"nodes": int(Gp.node_count()), "relationships": int(Gp.relationship_count())}
        print(f"  {PRIMARY_GRAPH}: {Gp.node_count()} nodes, {Gp.relationship_count()} rels")

        print("PageRank -> influence ...")
        report["pagerank"] = run_pagerank(gds, Gp, driver)
        print("Louvain -> community ...")
        report["louvain"] = run_louvain(gds, Gp, driver)
        print("Node Similarity (unified) -> SIMILAR_TO ...")
        report["node_similarity"] = run_node_similarity(gds, Gp, driver)
        _drop(gds, PRIMARY_GRAPH)

        # ── KNN on unified concept vector ──
        print("Projecting KNN graph (node-only + unified attrVec) ...")
        Gk = project_knn(gds)
        print("Filtered-KNN -> KNN_SIMILAR (per vertical) ...")
        report["filtered_knn"] = run_filtered_knn(gds, Gk, driver)
        _drop(gds, KNN_GRAPH)

        print("Coverage report ...")
        report["coverage"] = coverage_report(driver)

        with driver.session(database=NEO4J_DATABASE) as s:
            ex = []
            for v in ("game", "movie"):
                row = s.run("MATCH (e:Entity {vertical:$v}) "
                            "WHERE size([(e)-[:KNN_SIMILAR]->()|1])>0 AND size([(e)-[:SIMILAR_TO]->()|1])>0 "
                            "RETURN e.name AS n ORDER BY e.influence DESC LIMIT 1", v=v).single()
                if row:
                    ex.append(row["n"])
            # a cross-vertical example: an entity whose SIMILAR_TO crosses verticals
            xrow = s.run("MATCH (a:Entity)-[:SIMILAR_TO]->(b:Entity) WHERE a.vertical<>b.vertical "
                         "RETURN a.name AS n ORDER BY a.influence DESC LIMIT 1").single()
            if xrow and xrow["n"] not in ex:
                ex.append(xrow["n"])
        report["comparison"] = compare_examples(driver, ex)

    finally:
        for g in (PRIMARY_GRAPH, CMP_GENRE, CMP_CONCEPT, KNN_GRAPH):
            try:
                _drop(gds, g)
            except Exception as e:  # noqa
                print(f"  (drop {g} failed: {e})")
        gds.close()
        driver.close()

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    _print(report)


def _print(r):
    print("\n" + "=" * 72)
    ov = r["genre_theme_overlap"]
    print("GENRE<->THEME OVERLAP:")
    print(f"  unifiable (case-insensitive): " +
          ", ".join(f"{o['genre']}" + ("*" if o["case_differs"] else "") for o in ov["unifiable_exact_caseinsensitive"]))
    print(f"    (* = case differed, e.g. 'Science Fiction' genre vs 'Science fiction' theme — unified)")
    print(f"  flagged near-synonyms (NOT merged): " +
          ", ".join(f"{n['genre']}~{n['theme']}" for n in ov["flagged_near_synonyms_not_merged"]) or "(none)")
    sc = r["similarity_comparison"]
    print("\nGENRE-ONLY vs GENRE+THEME(UNIFIED) — cross-vertical recall:")
    print(f"  genre-only        : {sc['genre_only']['cross_vertical_pairs']} cross-vert / "
          f"{sc['genre_only']['total_pairs']} total pairs")
    print(f"  genre+theme unified: {sc['genre_plus_theme_unified']['cross_vertical_pairs']} cross-vert / "
          f"{sc['genre_plus_theme_unified']['total_pairs']} total pairs")
    print(f"  >>> cross-vertical pairs RECOVERED by unification: {sc['cross_vertical_recovered']}")
    pr = r["pagerank"]
    print(f"\nPAGERANK (compute {pr['compute_millis']}ms): entity dist {pr['entity_distribution']}")
    for e in pr["top15"]:
        print(f"    {e['influence']:>8}  [{e['vertical']}] {e['name']}")
    lv = r["louvain"]
    print(f"\nLOUVAIN (compute {lv['compute_millis']}ms): {lv['community_count']} communities, "
          f"modularity={lv['modularity']}, singletons={lv['singleton_communities']}, "
          f"largest={lv['largest_sizes']}")
    for c in lv["top5_communities"]:
        gens = ", ".join(f"{g['name']}({g['n']})" for g in c["dominant_genres"])
        print(f"    c{c['community']} size={c['size']} mix={c['vertical_mix']} genres=[{gens or 'none'}]")
        print(f"        members: " + "; ".join(f"{m['name']}[{m['v']}]" for m in c["sample_members"]))
    ns = r["node_similarity"]
    print(f"\nNODE SIMILARITY (compute {ns['compute_millis']}ms): {ns['relationships_written']} SIMILAR_TO, "
          f"{ns['cross_vertical_edges']} cross-vertical; dist {ns['similarity_distribution']}")
    for p in ns["top10_pairs"]:
        print(f"    {p['score']:>6}  {p['a']}[{p['av']}] -> {p['b']}[{p['bv']}]")
    print("  cross-vertical samples:")
    for p in ns["cross_vertical_samples"]:
        print(f"    {p['score']:>6}  {p['a']}[{p['av']}] -> {p['b']}[{p['bv']}]")
    kn = r["filtered_knn"]
    print(f"\nFILTERED-KNN (compute {kn['total_compute_millis']}ms wall {kn['wall_s']}s): "
          f"{kn['relationships_written_total']} KNN_SIMILAR")
    for v, d in kn["per_vertical"].items():
        print(f"    {v:8}: {d['relationships_written']} edges ({d['compute_millis']}ms)")
    print("\nCOVERAGE BY VERTICAL:")
    for c in r["coverage"]["similarity_coverage_by_vertical"]:
        print(f"    {c['vertical']:8}: SIMILAR_TO {c['with_similar_to']}/{c['total']}, "
              f"KNN {c['with_knn_similar']}/{c['total']}, no-sim {c['with_no_sim_edges']}/{c['total']}")
    for c in r["coverage"]["community_coverage_by_vertical"]:
        print(f"    {c['vertical']:8}: {c['communities']} communities / {c['entities']} entities")
    print("\nNODE SIMILARITY vs FILTERED-KNN (examples):")
    for ex in r["comparison"]:
        print(f"  {ex['name']} [{ex['vertical']}] genres={ex['genres']} themes={ex['themes']}")
        print("    SIMILAR_TO : " + " | ".join(f"{p['name']}[{p['v']}] {p['score']}" for p in ex["similar_to_top5"]))
        print("    KNN_SIMILAR: " + " | ".join(f"{p['name']}[{p['v']}] {p['score']}" for p in ex["knn_similar_top5"]))
    print(f"\nStats -> {OUT.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
