# databricks_deploy — feeds.ai unified router on Databricks (self-contained)

This folder is a **self-contained** bundle that deploys the feeds.ai unified router as a **new version
(v3) of the existing serving model `dev_feeds_silver.ml.parrot-api-hitashi-dev`** — the endpoint URL and
its Parrot/M2M wire contract do not change. It vendors all engine sources under `engines/`, so it does
**not** depend on the rest of this repo.

> Snapshot note: `engines/` is a point-in-time copy of the router + vector pipeline + graph engine from
> the source project. The serving model is the **collapsed** router: one Model Serving container that
> talks directly to Databricks Vector Search, Neo4j AuraDB, the Databricks FM endpoint, and Voyage —
> no separate engine servers.

## Layout
```
databricks_deploy/
  serving/         model.py (the pyfunc) + parrot_adapter + inprocess_engines + inmemory_store
                   + register.py (bundles everything → registers v3) + requirements.txt + tests
  vector_search/   build_index.py (Delta table + Vector Search index) + vs_store.py (queries it)
  graph/           precompute_offline.py (GDS-free PageRank/similarity for AuraDB) + load_aura.md
  probe/           egress_probe.py (checks Model Serving can reach Voyage + Aura)
  config.example.env
  engines/         VENDORED sources (self-contained):
    router_src/    the unified router (route/blocks/assembler/extract …)
    vector/pipeline/ + vector/data_v2/   the vector pipeline + the 4 data artifacts (Voyage vectors)
    graph_src/     the Neo4j graph engine (query/connection …)
    data/entities.jsonl                  graph load input
```

## Deploy (no Databricks CLI needed)

**1. Secrets** (notebook, SDK): create scope `feedsai` with `neo4j_password`, `voyage_api_key`,
`databricks_token`.

**2. Vector Search index** (notebook): run `vector_search/build_index.py` with
`SRC_VOLUME=<repo>/databricks_deploy/engines/vector/data_v2`, `UC_CATALOG=dev_feeds_silver`,
`UC_SCHEMA=ml`, `VS_ENDPOINT_NAME=feedsai-vs`.

**3. Load AuraDB** (laptop or notebook — only talks to Neo4j): from `engines/graph_src`, run
`schema.py` → `load.py`, then `graph/precompute_offline.py` (GDS-free — AuraDB has no GDS). See
`graph/load_aura.md`. Set `NEO4J_USER` (not `NEO4J_USERNAME`).

**4. Register v3** (notebook):
```python
import sys; sys.path.insert(0, "databricks_deploy/serving"); import register; register.main()
```

**5. Repoint + env** (Serving UI): set the endpoint's served entity to **v3** and add the env vars from
`config.example.env` (Neo4j password etc. via `{{secrets/feedsai/...}}`). `ROUTER_ENGINE_MODE=inprocess`,
`VECTOR_BACKEND=databricks`, `ENTITY_BACKEND=memory` are set automatically by the pyfunc.

**6. Egress + smoke test**: deploy `probe/egress_probe.py` once to confirm Voyage + Aura bolt 7687 are
reachable; then query the endpoint.

## Verify the contract offline (no Databricks)
```bash
python databricks_deploy/serving/test_parrot_adapter.py
python databricks_deploy/serving/test_inmemory_store.py
```
