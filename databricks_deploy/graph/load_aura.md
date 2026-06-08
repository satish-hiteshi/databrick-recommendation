# Load the graph into Neo4j AuraDB (no GDS)

Your instance is **AuraDB** (`3bbae19b`, "Instance01"), which has **no GDS library**. So `schema.py` +
`load.py` run normally, but the GDS `precompute.py` is replaced by `precompute_offline.py` (PageRank /
communities / similarity computed in Python and written back). Serve-time queries are plain Cypher
either way. Run this ONCE, from anywhere that can reach Aura (a laptop or a Databricks notebook).

## 0. Connect — env (note the variable name!)
The code reads **`NEO4J_USER`**, but Aura's download uses `NEO4J_USERNAME`. Set `NEO4J_USER`:
```ini
NEO4J_URI=neo4j+s://3bbae19b.databases.neo4j.io
NEO4J_USER=neo4j                 # NOT NEO4J_USERNAME
NEO4J_PASSWORD=<your-RESET-password>
NEO4J_DATABASE=neo4j
```
(For the running endpoint these go in env vars, password via `{{secrets/feedsai/neo4j_password}}`.)

## 1. Schema + load (no GDS needed)
```bash
./.venv/bin/python src/schema.py        # constraints + entityText full-text index
./.venv/bin/python src/load.py          # 6,945 entities + edges (HAS_GENRE/HAS_THEME/HAS_KEYWORD/…)
```

## 2. GDS-free precompute (replaces src/precompute.py on AuraDB)
```bash
pip install neo4j networkx numpy        # the offline job's only deps
./.venv/bin/python databricks_deploy/graph/precompute_offline.py
```
Writes, in Python: the unified **Concept** layer + vertical labels (plain Cypher), **`Entity.influence`**
(PageRank), **`Entity.community`** (Louvain), **`:SIMILAR_TO`** (Jaccard, topK 10), **`:KNN_SIMILAR`**
(cosine-KNN over the multi-hot concept vector, per vertical). Router-critical outputs are `influence`
(score_within ranking) and `SIMILAR_TO` (graph_similar); the rest are for fidelity.

## 3. Verify
```bash
./.venv/bin/python - <<'PY'
import os
from neo4j import GraphDatabase
d = GraphDatabase.driver(os.environ["NEO4J_URI"],
                         auth=(os.getenv("NEO4J_USER","neo4j"), os.environ["NEO4J_PASSWORD"]))
with d.session() as s:
    print(s.run("MATCH (e:Entity) RETURN e.vertical AS v, count(*) AS n ORDER BY n DESC").data())
    print("with influence:", s.run("MATCH (e:Entity) WHERE e.influence IS NOT NULL RETURN count(*) AS n").single()["n"])
    print("SIMILAR_TO:", s.run("MATCH ()-[r:SIMILAR_TO]->() RETURN count(r) AS n").single()["n"])
    print("Concepts:", s.run("MATCH (c:Concept) RETURN count(c) AS n").single()["n"])
d.close()
PY
```
Expect per-vertical counts ≈ game 1997 / movie 1653 / tv 1297 / podcast 1998, influence on all entities,
and a populated SIMILAR_TO + Concept layer.

## Notes
- `precompute_offline.py` is a ONE-TIME data-prep job — it does **not** run inside the serving endpoint.
- If you later move to **AuraDS**, you can instead run the original `src/precompute.py` (GDS) — but
  with AuraDB this Python path is the way.
