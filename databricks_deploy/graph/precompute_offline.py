"""GDS-FREE precompute for Neo4j AuraDB (no Graph Data Science library).

AuraDB (unlike AuraDS) has no GDS, so the project's src/precompute.py can't run there. This reproduces
the parts the COLLAPSED ROUTER actually reads, computed in Python and written straight into AuraDB:

  1. Unified Concept layer + vertical labels   — plain Cypher (same as src/precompute.py; no GDS)
  2. Entity.influence   = PageRank              — networkx, over the primary graph
  3. Entity.community   = Louvain communities   — networkx
  4. (:Entity)-[:SIMILAR_TO {score}]->(:Entity) = Node Similarity (Jaccard, topK=10, Entity→Entity)
  5. (:Entity)-[:KNN_SIMILAR {score}]->(:Entity)= cosine-KNN over the multi-hot concept vector, per
                                                  vertical, topK=10

Router criticality: #1 (concepts), #2 (influence — score_within ranking) and #4 (SIMILAR_TO —
graph_similar establisher) are REQUIRED by the unified router. #3/#5 are produced for fidelity with the
graph engine but the router's blocks don't call them. Serve-time queries are plain Cypher either way.

The "primary graph" matches src/precompute.py: nodes Entity+Concept+Keyword+Franchise, relationships
HAS_CONCEPT/HAS_KEYWORD/IN_FRANCHISE, UNDIRECTED. Run ONCE, AFTER schema.py + load.py, against AuraDB:

  pip install neo4j networkx numpy
  NEO4J_URI=neo4j+s://<id>.databases.neo4j.io NEO4J_USER=neo4j NEO4J_PASSWORD=*** \
      python databricks_deploy/graph/precompute_offline.py

Connects from env (NEO4J_URI / NEO4J_USER or NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DATABASE). It is a
one-time data-prep job — it does NOT run inside the serving endpoint.
"""

import os
import time
from collections import defaultdict

import numpy as np
from neo4j import GraphDatabase

URI = os.environ["NEO4J_URI"]
USER = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
PWD = os.environ["NEO4J_PASSWORD"]
DB = os.getenv("NEO4J_DATABASE", "neo4j")

TOP_K = 10
VERTICAL_LABELS = {"game": "Game", "movie": "Movie", "tv": "Tv", "podcast": "Podcast"}
PRIMARY_RELS = ["HAS_CONCEPT", "HAS_KEYWORD", "IN_FRANCHISE"]


# ───────────────────────── 1. Concept layer + labels (plain Cypher, no GDS) ─────────────────────────
def build_concept_layer(s):
    """Materialize (:Concept {key,name}) from genres∪themes (case-insensitive) + vertical labels.
    Identical Cypher to src/precompute.py::build_concepts_vectors_labels (sans the GDS-only attrVec)."""
    s.run("CREATE CONSTRAINT concept_key_unique IF NOT EXISTS "
          "FOR (c:Concept) REQUIRE c.key IS UNIQUE").consume()
    # Genres first so genre casing wins as the Concept display name.
    s.run("MATCH (e:Entity)-[:HAS_GENRE]->(g:Genre) "
          "MERGE (c:Concept {key: toLower(g.name)}) ON CREATE SET c.name = g.name "
          "MERGE (e)-[:HAS_CONCEPT]->(c)").consume()
    s.run("MATCH (e:Entity)-[:HAS_THEME]->(t:Theme) "
          "MERGE (c:Concept {key: toLower(t.name)}) ON CREATE SET c.name = t.name "
          "MERGE (e)-[:HAS_CONCEPT]->(c)").consume()
    for vert, lbl in VERTICAL_LABELS.items():
        s.run(f"MATCH (e:Entity {{vertical: $v}}) SET e:{lbl}", v=vert).consume()
    n_c = s.run("MATCH (c:Concept) RETURN count(*) AS c").single()["c"]
    n_h = s.run("MATCH ()-[r:HAS_CONCEPT]->() RETURN count(*) AS c").single()["c"]
    print(f"  Concept layer: {n_c} concepts, {n_h} HAS_CONCEPT edges")


# ───────────────────────── read the primary graph into memory ─────────────────────────
def read_graph(s):
    """Return: entities (ordered ids), vertical{eid}, attr_neighbors{eid:set(attr_key)},
    concept_keys{eid:set(concept_key)} — all from the loaded graph."""
    ent = [r["eid"] for r in s.run("MATCH (e:Entity) RETURN e.entity_id AS eid")]
    vertical = {r["eid"]: r["v"] for r in
                s.run("MATCH (e:Entity) RETURN e.entity_id AS eid, e.vertical AS v")}

    attr_neighbors = defaultdict(set)
    rel_union = "|".join(PRIMARY_RELS)
    for r in s.run(f"MATCH (e:Entity)-[:{rel_union}]->(a) "
                   f"RETURN e.entity_id AS eid, elementId(a) AS aid"):
        attr_neighbors[r["eid"]].add(r["aid"])

    concept_keys = defaultdict(set)
    for r in s.run("MATCH (e:Entity)-[:HAS_CONCEPT]->(c:Concept) "
                   "RETURN e.entity_id AS eid, c.key AS k"):
        concept_keys[r["eid"]].add(r["k"])

    print(f"  read {len(ent)} entities; "
          f"{sum(len(v) for v in attr_neighbors.values())} primary-graph edges")
    return ent, vertical, dict(attr_neighbors), dict(concept_keys)


# ───────────────────────── 2+3. PageRank + Louvain (networkx) ─────────────────────────
def pagerank_louvain(ent, attr_neighbors):
    import networkx as nx
    G = nx.Graph()
    G.add_nodes_from(("E", e) for e in ent)
    for e in ent:
        for a in attr_neighbors.get(e, ()):  # UNDIRECTED Entity—attr edges
            G.add_edge(("E", e), ("A", a))

    t0 = time.time()
    pr = nx.pagerank(G, alpha=0.85, max_iter=100, tol=1e-6)
    influence = {e: float(pr.get(("E", e), 0.0)) for e in ent}
    print(f"  PageRank: {len(influence)} entities ({time.time() - t0:.1f}s)")

    t0 = time.time()
    parts = nx.community.louvain_communities(G, seed=42)
    community = {}
    for cid, members in enumerate(parts):
        for n in members:
            if isinstance(n, tuple) and n[0] == "E":
                community[n[1]] = cid
    n_comm = len({c for e, c in community.items()})
    print(f"  Louvain: {n_comm} communities over {len(community)} entities ({time.time() - t0:.1f}s)")
    return influence, community


# ───────────────────────── 4. Node Similarity (Jaccard, topK) ─────────────────────────
def node_similarity(ent, attr_neighbors, top_k=TOP_K):
    """Jaccard of attr-neighbor sets, Entity→Entity, topK per source — matches GDS nodeSimilarity.
    Uses an inverted index (attr → entities) so only entities that SHARE a neighbor are compared."""
    inv = defaultdict(list)
    for e in ent:
        for a in attr_neighbors.get(e, ()):
            inv[a].append(e)

    edges = []
    t0 = time.time()
    for i, a in enumerate(ent):
        na = attr_neighbors.get(a)
        if not na:
            continue
        # candidate co-neighbors and the count of shared attrs
        shared = defaultdict(int)
        for attr in na:
            for b in inv[attr]:
                if b != a:
                    shared[b] += 1
        scored = []
        la = len(na)
        for b, inter in shared.items():
            union = la + len(attr_neighbors[b]) - inter
            if union:
                scored.append((b, inter / union))
        scored.sort(key=lambda x: x[1], reverse=True)
        for b, sc in scored[:top_k]:
            edges.append((a, b, round(float(sc), 6)))
        if (i + 1) % 2000 == 0:
            print(f"    node-sim {i + 1}/{len(ent)} …")
    print(f"  Node Similarity: {len(edges)} SIMILAR_TO edges ({time.time() - t0:.1f}s)")
    return edges


# ───────────────────────── 5. KNN over multi-hot concept vectors (per vertical) ─────────────────────────
def knn_similar(ent, vertical, concept_keys, top_k=TOP_K, cutoff=0.1):
    all_keys = sorted({k for ks in concept_keys.values() for k in ks})
    idx = {k: i for i, k in enumerate(all_keys)}
    edges = []
    t0 = time.time()
    for vert in VERTICAL_LABELS:
        members = [e for e in ent if vertical.get(e) == vert and concept_keys.get(e)]
        if len(members) < 2:
            continue
        M = np.zeros((len(members), len(all_keys)), dtype=np.float32)
        for row, e in enumerate(members):
            for k in concept_keys[e]:
                M[row, idx[k]] = 1.0
        norms = np.linalg.norm(M, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        Mn = M / norms
        sim = Mn @ Mn.T
        np.fill_diagonal(sim, -1.0)
        for row, e in enumerate(members):
            order = np.argsort(-sim[row])[:top_k]
            for j in order:
                sc = float(sim[row, j])
                if sc >= cutoff:
                    edges.append((e, members[j], round(sc, 6)))
    print(f"  KNN: {len(edges)} KNN_SIMILAR edges ({time.time() - t0:.1f}s)")
    return edges


# ───────────────────────── writes (batched UNWIND) ─────────────────────────
def write_props(s, influence, community):
    rows = [{"eid": e, "infl": influence.get(e, 0.0), "comm": community.get(e)} for e in influence]
    for i in range(0, len(rows), 1000):
        s.run("UNWIND $rows AS r MATCH (e:Entity {entity_id: r.eid}) "
              "SET e.influence = r.infl, e.community = r.comm", rows=rows[i:i + 1000]).consume()
    print(f"  wrote influence + community for {len(rows)} entities")


def write_edges(s, edges, reltype):
    s.run(f"MATCH ()-[r:{reltype}]->() CALL {{ WITH r DELETE r }} IN TRANSACTIONS OF 10000 ROWS").consume()
    rows = [{"a": a, "b": b, "score": sc} for (a, b, sc) in edges]
    for i in range(0, len(rows), 1000):
        s.run(f"UNWIND $rows AS r MATCH (a:Entity {{entity_id: r.a}}), (b:Entity {{entity_id: r.b}}) "
              f"MERGE (a)-[x:{reltype}]->(b) SET x.score = r.score", rows=rows[i:i + 1000]).consume()
    print(f"  wrote {len(rows)} {reltype} edges")


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    driver.verify_connectivity()
    print(f"Connected to {URI} (db={DB}) — GDS-free precompute")
    try:
        with driver.session(database=DB) as s:
            print("1. Concept layer + vertical labels …")
            build_concept_layer(s)
            print("   reading primary graph …")
            ent, vertical, attr_neighbors, concept_keys = read_graph(s)

        influence, community = pagerank_louvain(ent, attr_neighbors)
        sim_edges = node_similarity(ent, attr_neighbors)
        knn_edges = knn_similar(ent, vertical, concept_keys)

        with driver.session(database=DB) as s:
            print("writing back …")
            write_props(s, influence, community)
            write_edges(s, sim_edges, "SIMILAR_TO")
            write_edges(s, knn_edges, "KNN_SIMILAR")
        print("Done. AuraDB now has influence / community / SIMILAR_TO / KNN_SIMILAR (no GDS used).")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
