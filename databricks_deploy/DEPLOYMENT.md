# DEPLOYMENT.md — what we did, file by file (Databricks)

This is the **map of the Databricks deployment**. Open it cold and you should understand *what every
file is, what we built or changed in it, and why* — without having been in any of the build sessions.

For the step-by-step deploy runbook see [`README.md`](README.md). This file is the **annotated
inventory + change history**; the README is the **how-to-run**.

---

## 1. What this deployment is (in five lines)

- We took the feeds.ai **unified router** (LLM intent router → Vector engine + Neo4j Graph engine) and
  registered it as a **new version of the existing serving model** `dev_feeds_silver.ml.parrot-api-hitashi-dev`.
- The **endpoint URL and its Parrot/M2M wire contract do not change** — only the brain behind it does.
- It is the **collapsed** router: **one** Model Serving container that calls the engines **in-process**
  (no separate FastAPI servers). The HTTP calls the router used to make are dispatched to in-process
  Python functions.
- Retrieval uses **Databricks Vector Search** (dense ANN), **Neo4j AuraDB** (graph refine), the
  **Databricks FM endpoint** (LLM intent extraction), and **Voyage** (query embedding).
- The 57,443-entity corpus ships as a **parquet on a Volume** (embeddings + BM25 keywords); no Postgres,
  no Qdrant server, no GDS at runtime.

**Routing model:** *establish-then-refine.* The LLM extracts a structured intent → a deterministic
assembler picks an **establisher** (vector or graph builds the candidate universe) → **refiners** (graph
rerank / negation / semantic rerank) reorder *within* that universe → result. Paths are named after what
ran, e.g. `VECTOR_CONSTRAIN__GRAPH_RERANK`, `MULTIVERTICAL[game,movie,tv,podcast]`, `SEED_VECTOR__VECTOR_RERANK`.

---

## 2. Legend

| Tag | Meaning |
|---|---|
| 🆕 **NEW** | Written specifically for this Databricks deployment |
| ✏️ **EDITED** | Vendored engine source we modified — changes are **env-gated** so local behavior is unchanged |
| 📦 **VENDORED** | Point-in-time copy of the source project, used as-is |

The guiding rule for ✏️ files: **every change is behind an environment flag** (`ROUTER_ENGINE_MODE`,
`VECTOR_BACKEND`, `DATA_BACKEND`). With the flags unset the code behaves exactly as in the original
two-engine microservice project; with them set it runs collapsed inside the serving container.

---

## 3. Folder map

```
databricks_deploy/
  README.md                     deploy runbook (how to run)
  DEPLOYMENT.md                 this file (what we did, per file)
  config.example.env            env-var template for the endpoint

  serving/                      THE SERVING MODEL (all 🆕)
    model.py                    the MLflow pyfunc (RouterModel)
    parrot_adapter.py           Parrot/M2M wire-contract mapping (the only contract choke point)
    inprocess_engines.py        in-process dispatch of the engines' HTTP calls + Neo4j driver mgmt
    inmemory_store.py           parquet-backed 57k entity store (resolve / fetch / embeddings)
    register.py                 bundles everything → registers the new model version
    requirements.txt            serving-container dependencies
    test_parrot_adapter.py      offline contract test (no Databricks needed)
    test_inmemory_store.py      offline store test

  vector_search/                DATABRICKS VECTOR SEARCH (all 🆕)
    build_index.py              builds the Delta table + Delta-Sync index from the embeddings
    vs_store.py                 dense-ANN query against the Vector Search index

  graph/                        NEO4J AURADB (all 🆕)
    precompute_offline.py       GDS-free PageRank / Louvain / Jaccard (AuraDB has no GDS)
    load_aura.md                how to load + precompute on AuraDB

  probe/
    egress_probe.py             🆕 confirms the serving container can reach Voyage + Aura

  engines/                      VENDORED ENGINE SOURCES (self-contained)
    router_src/                 the unified router  (blocks.py ✏️, assembler.py ✏️, rest 📦)
    vector/pipeline/            the vector pipeline (data_loader.py ✏️, vector_store.py ✏️, rest 📦)
    vector/data_v2/             original Voyage vectors + profiles (📦, index-build parity)
    graph_src/                  the Neo4j graph engine (📦)
    data/entities.jsonl         graph load input (📦)
```

---

## 4. File-by-file — what we did and why

### `serving/` — the serving model (all NEW)

#### 🆕 `serving/model.py` — the pyfunc
**Role.** The MLflow `PythonModel` (`RouterModel`) the endpoint actually runs. `predict()` maps a Parrot
request → `route()` → a Parrot response.
**What we did.**
- Sets the engine wiring env (`ROUTER_ENGINE_MODE=inprocess`, `VECTOR_BACKEND=databricks`,
  `ENTITY_BACKEND=memory`, `DATA_BACKEND=parquet`) **before** importing the router (some modules read
  these at import time). Uses `setdefault` so an endpoint env var can still override.
- `_bootstrap_paths()` **discovers** the bundled router / vector / graph / serving dirs by walking the
  model artifact (MLflow's `code_paths` layout varies by version, so we discover instead of hard-coding).
- `load_context()` **pre-warms** the heavy singletons (the 57k embeddings matrix + the BM25 corpus) so
  the first — possibly parallel multivertical — query doesn't race or duplicate-load them.
- `predict()` wraps request parsing and each row's `route()` in try/except → returns a shape-preserving
  **error envelope** (never a 5xx body to M2M callers) and prints `[parrot] …` logs.
**Why.** The endpoint must speak the fixed contract, survive bad input, and be fast on the first call.

#### 🆕 `serving/parrot_adapter.py` — the wire-contract choke point
**Role.** The **only** place the Parrot/M2M contract and the router's native shape meet.
**What we did.**
- Maps router output → `{query, routed_to, response:{routed_to, entity_type, results[], count, router{}}}`.
- `routed_to = "agent-recs"` (preserved from the existing contract).
- **`entity_type = "property"`** at the outer level *and* per result item — see the change history
  (§5.1); this is load-bearing for the client.
- `_interleave_by_vertical()` round-robins multivertical results so the top **alternates**
  game/movie/tv/podcast instead of stacking one vertical first.
- Carries the full router trace (`path_taken`, establisher, refinements, timing) under `response.router`
  for debugging; M2M callers ignore unknown keys.
**Why.** Keep the contract stable while adding feeds.ai fields; make non-game results actually survive on
the client side.

#### 🆕 `serving/inprocess_engines.py` — the collapse shim
**Role.** Replaces the router's HTTP calls to the Vector/Graph engines with **in-process** function calls.
**What we did.**
- Implements the engine endpoints the router uses: `/api/query`, `/api/retrieve`, `/api/score_set`,
  `/api/neighbors`, `/api/texts` (vector) and the `/graph/*` handlers (Neo4j).
- Builds and manages the **Neo4j driver** (`max_connection_lifetime=180`, `connection_acquisition_timeout=5`,
  `connection_timeout=5`, `keep_alive=True`) with a `_reset_driver()` for reconnects.
- `dispatch()` **retries transient errors** (429/5xx/timeout/SessionExpired/defunct…) up to 3 attempts
  with backoff, resetting the driver on Neo4j connection errors.
**Why.** One container, no engine servers; and resilience against transient Aura/VS blips (see §5.3).

#### 🆕 `serving/inmemory_store.py` — parquet-backed entity store
**Role.** Postgres-free entity resolution + the in-memory embeddings matrix.
**What we did.** Reads the 57k embeddings parquet into an `(N, 1024)` float32 matrix; provides
`resolve_entity` (exact → prefix → contains), `batch_fetch_entities`, `embeddings()`, `all_records()`
(the BM25 corpus).
**Why.** The corpus and vectors must be available in-process without any external store.

#### 🆕 `serving/register.py` — registration
**Role.** Bundles the sources via MLflow **models-from-code** and registers the **new model version**.
**What we did.** `code_paths` the serving + engine dirs; **stages the embeddings parquet** from the
Volume (`EMBEDDINGS_PARQUET_SRC`) into the bundle; sets a `ModelSignature` whose `response` is typed
`AnyType` (string fallback for older MLflow) so Unity Catalog's "must have outputs" rule is satisfied
without coercing the nested response object.
**Why.** UC registration with the exact signature + self-contained artifact.

#### 🆕 `serving/requirements.txt`
Serving-container deps: `mlflow`, `httpx`, `neo4j`, `voyageai`, `databricks-vectorsearch`,
`qdrant-client`, `rank-bm25`, `psycopg2-binary`, `graphdatascience`, `pyarrow`.

#### 🆕 `serving/test_parrot_adapter.py`, `serving/test_inmemory_store.py`
Offline tests (no Databricks) that lock the contract mapping and the parquet store behavior.

### `vector_search/` — Databricks Vector Search (all NEW)

#### 🆕 `vector_search/build_index.py`
Builds the Delta source table and the **Delta-Sync** Vector Search index (self-managed Voyage
`voyage-4-large`, 1024-dim) from the embeddings.

#### 🆕 `vector_search/vs_store.py`
Dense-ANN query against the index — `vector_search(query_embedding, target_verticals, top_k)` returning
`[(entity_id, name, vertical, score), …]`, the **same signature** as the local Qdrant call so the
pipeline needs no change. Applies the `vertical` filter; **date filters are skipped** (the 57k table has
no `release_date` column — so temporal queries return results but are not date-bounded; see §5.6).

### `graph/` — Neo4j AuraDB (all NEW)

#### 🆕 `graph/precompute_offline.py`
Computes **PageRank / Louvain / Jaccard similarity** in plain Cypher/Python and writes them back as
node properties / edges — because **AuraDB has no GDS** at runtime. Run once after loading.

#### 🆕 `graph/load_aura.md`
How to load the graph into AuraDB and run the offline precompute (and the `NEO4J_USER` gotcha).

### `probe/`

#### 🆕 `probe/egress_probe.py`
A throwaway model you deploy once to confirm the serving container's network can reach **Voyage** and
**Aura bolt (7687)** before debugging routing.

### `engines/` — vendored sources (what we EDITED)

The whole `engines/` tree is a point-in-time copy of the source project so the bundle is self-contained.
Four files carry **deploy-specific edits** — all **env-gated**:

#### ✏️ `engines/router_src/blocks.py`
The router's engine-call layer + retrieval primitives. Two changes:
1. **Collapse hook.** `_post`/`_get` dispatch **in-process** when `ROUTER_ENGINE_MODE=inprocess`
   (→ `inprocess_engines.dispatch`); default `http` keeps the original microservice behavior.
2. **Establisher recall fallback** (empty-fix, §5.5). In `vector_constrain`, if the NLU `/api/query`
   path yields no rows for the target vertical, fall back to pure embedding recall (`/api/retrieve`) so
   an establisher can never zero a populated universe.

#### ✏️ `engines/router_src/assembler.py`
The establish-then-refine planner. Added **`_parallel_assemble()`** — a `ThreadPoolExecutor`
(order-preserving, single job inline) used by `assemble_multivertical` and `assemble_multi` to run the
per-vertical / per-intent sub-plans **concurrently** (they're I/O-bound on the engines), so wall-clock ≈
the slowest sub-plan, not the sum (§5.4). All other logic in this file (subject/topic safety net,
temporal handling) is upstream source kept in sync (§5.7).

#### ✏️ `engines/vector/pipeline/data_loader.py`
`get_all_entities()` is env-gated: with `DATA_BACKEND=parquet` it returns
`inmemory_store.all_records()` (the 57k parquet corpus that powers BM25) instead of reading bundled JSON.

#### ✏️ `engines/vector/pipeline/vector_store.py`
With `VECTOR_BACKEND=databricks`: `setup_qdrant()` short-circuits (no Qdrant server) and the module
imports `vector_search` **by file path** from `vs_store.py` — overriding the Qdrant dense ANN while
leaving in-process BM25 (`rank-bm25`) intact. Loaded by path (not `import databricks…`) so it never
clashes with the Databricks SDK's own `databricks` namespace.

#### 📦 Everything else under `engines/`
Used as-is: the rest of `router_src/` (`route`, `extract`, `intent`, `llm`, `config`, `backfill`,
`extraction_prompt`, `api`), the rest of `vector/pipeline/` (NLU, retrieval, reranker, reasoning,
embedding_generator, query_engine…), `vector/data_v2/` (original Voyage vectors used for index-build
parity — the **runtime** corpus is the 57k parquet), all of `graph_src/`, and `data/entities.jsonl`.

---

## 5. Change history — the fixes, pinned to their file

Each entry = the symptom that prompted it, the fix, and the file.

### 5.1 Non-game results vanished on the client → `parrot_adapter.py`
**Symptom.** "Only games show up; movies/TV/podcasts return nothing."
**Cause.** Not our endpoint — feeds-api types results by id-prefix and **drops non-`property`
candidates on hydration**; our `Movie:`/`Tv:`/`Podcast:` prefixes weren't recognized and fell back to
the outer type, which was `"entertainment"` → dropped.
**Fix.** `entity_type = "property"` at the **outer level and per item**.

### 5.2 Multivertical results stacked game-first → `parrot_adapter.py`
**Fix.** `_interleave_by_vertical()` round-robins verticals so the top leads with a mix.

### 5.3 "Same query sometimes empty, sometimes fine" → `inprocess_engines.py`
**Cause.** Transient Aura / Vector Search blips (LLM temperature was already 0.0, so not randomness).
**Fix.** Retries on transient markers + Neo4j reconnect + fail-fast connect/acquire timeouts.

### 5.4 Broad queries too slow for the 3s client timeout → `assembler.py` (+ `model.py`)
**Fix.** Parallelized the multivertical/multi-intent fan-out (`_parallel_assemble`) + pre-warmed the 57k
embeddings & BM25 in `load_context`. Result: full 4-vertical queries land ~1.7s instead of timing out.

### 5.5 Structural-mode queries returned EMPTY → `blocks.py`
**Symptom.** "co-op game…", "crafting…", "single-player…" returned 0 results.
**Cause.** Sparse phrases ("co-op, not too competitive") make the NLU **re-target across verticals**; the
`vertical="game"` post-filter then drops every row, so the establisher returned empty and `assemble()`
bailed to `EMPTY` **before** the graph rerank ran.
**Fix.** Establisher recall fallback in `vector_constrain` — pure embedding recall (`/api/retrieve`) when
the NLU path yields nothing for the vertical. Non-regressive (only fires on the empty case).

### 5.6 Known gap — temporal queries are not date-bounded → `vs_store.py`
The 57k Vector Search table has no `release_date` column, so `vs_store.py` skips date filters. Queries
like "thriller from the last 2 years" still return results (no error) but the date window is **not
applied**. To enable: add `release_date` to the index source table and restore the date filter in
`vs_store.vector_search`.

### 5.7 Vendored-engine sync with upstream `feeds-ai-unified-router`
The `engines/` tree is periodically refreshed from the source project. Most recent sync pulled: subject/
topic + occasion-intent capture and temporal-via-raw-query (`assembler.py`, `extraction_prompt.py`) and
the vector-NLU genre/feature fix (`nlu.py`, `retrieval.py`) — the latter complements §5.5 by degrading
misclassified genre/feature phrases ("horror games", "co-op") to keyword search at the NLU layer instead
of treating them as titles. When syncing, copy source → vendored but **preserve the env-gated edits** in
the four ✏️ files above.

---

## 6. Deploy & test (pointer)

Full runbook in [`README.md`](README.md). The recurring cycle after a code change:

1. **Commit + push** the deploy repo → **pull** on Databricks.
2. **Register** a new version:
   ```python
   import os, sys, importlib
   os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/dev_feeds_silver/ml/feedsai_src/embeddings_voyage_57k.parquet"
   sys.path.insert(0, "<repo>/databricks_deploy/serving"); import register; importlib.reload(register)
   register.main()
   ```
3. **Repoint** the endpoint to the new version with the env block (§7), `workload_size="Medium"`,
   `scale_to_zero_enabled=False`. (Legacy `auto_capture_config` is deprecated — use **AI Gateway
   inference tables** for request/response logging.)
4. **Verify**: run the complex-query sweep + the repeat-consistency loop; check `path_taken`,
   per-query `timing_ms`, vertical mix, and that no archetype returns empty.

---

## 7. Infrastructure IDs & env

| Thing | Value |
|---|---|
| Serving endpoint | `parrot-api-hitashi-dev` |
| UC model | `dev_feeds_silver.ml.parrot-api-hitashi-dev` |
| Catalog.schema | `dev_feeds_silver.ml` |
| SQL warehouse | Serverless Starter Warehouse |
| Vector Search endpoint | `feedsai-hiteshi-vs` |
| Vector Search index | `dev_feeds_silver.ml.entities_vs` (source table `dev_feeds_silver.ml.entities`) |
| Embeddings parquet | `/Volumes/dev_feeds_silver/ml/feedsai_src/embeddings_voyage_57k.parquet` |
| Neo4j AuraDB | `neo4j+s://3bbae19b.databases.neo4j.io` (Professional, GCP Mumbai `asia-south1`) |
| Secret scope | `feedsai_hiteshi` → `neo4j_password`, `voyage_api_key`, `databricks_token` |
| FM (LLM) endpoint | `llama_v3_3_70b_instruct_Ishaan` |
| Workspace | `dbc-f79d5cae-0d05.cloud.databricks.com` |
| Corpus | 57,443 entities — game 6,537 / movie 25,855 / tv 6,022 / podcast 19,029 |

**Endpoint env (repoint):** `LLM_PROVIDER=databricks`, `DATABRICKS_LLM_ENDPOINT`, `DATABRICKS_HOST`,
`DATABRICKS_TOKEN`, `VOYAGE_API_KEY`, `VS_ENDPOINT_NAME`, `VS_INDEX_NAME`, `NEO4J_URI`, `NEO4J_USER`
(**not** `NEO4J_USERNAME`), `NEO4J_PASSWORD`, `NEO4J_DATABASE`. The pyfunc sets `ROUTER_ENGINE_MODE`,
`VECTOR_BACKEND`, `ENTITY_BACKEND`, `DATA_BACKEND` itself. Secrets are referenced as
`{{secrets/feedsai_hiteshi/<key>}}`.

---

## 8. Where to change things (choke points)

| To change… | Edit… |
|---|---|
| The Parrot request/response shape, `routed_to`, `entity_type`, id mapping, interleaving | `serving/parrot_adapter.py` |
| Which engine calls run / engine resilience (retries, timeouts, reconnect) | `serving/inprocess_engines.py` |
| Routing logic (establisher choice, refiners, fan-out) | `engines/router_src/assembler.py` + `blocks.py` |
| Vector Search query (filters, top_k, columns, date filter) | `vector_search/vs_store.py` |
| Graph analytics (PageRank/Louvain/Jaccard) | `graph/precompute_offline.py` |
| Startup warm-up, error handling, the pyfunc itself | `serving/model.py` |
| What gets bundled / the model signature | `serving/register.py` |
