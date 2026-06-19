# 03 — Neo4j & Vector: what does (and does NOT) need loading

The headline for deployment planning: **Endpoint 2 adds NOTHING to Neo4j and changes NOTHING in the vector
index. It is a read-only client of the existing, already-built substrate.** Both claims are confirmed against
the code below.

---

## 1. Neo4j — NO new load (read-only)

**Does Neo4j need any new data load for Endpoint 2? → NO.** Endpoint 2 **only reads** the existing graph.

**What's already in the graph** (built for the substrate / Endpoint 1; see `SPLIT_REPORT.md`, `shared/README.md`):
- **57,443 `Entity` nodes** with GDS node properties: `influence` (PageRank), `community` (Louvain).
- Relationships: `:SIMILAR_TO`, `:KNN_SIMILAR` (~384,120), `:Concept` (46) + `:HAS_CONCEPT`, plus
  `HAS_GENRE/HAS_THEME/HAS_KEYWORD/IN_FRANCHISE/DEVELOPED_BY/PUBLISHED_BY`.
- The graph is stood up from the dump **`shared/data/deploy/feedsai_neo4j_57k.dump`** (~281 MB) — **a
  substrate/Endpoint-1 task, not an Endpoint-2 task.**

**The graph endpoints Endpoint 2 calls** (via [`substrate_client.py`](../src/data_access/substrate_client.py)),
all **READ** operations against the `:8010` graph service:

| Method (substrate_client) | Endpoint hit | Used by | Operation |
|---|---|---|---|
| `graph_similar` | `POST /graph/similar` | v2 retrieval/exploration, v1 popular-with-fans-of | READ — precomputed `:SIMILAR_TO` |
| `graph_structured` | `POST /graph/structured` | v2 content + exploration | READ — relational MATCH (genre/keyword/…) |
| `graph_score_within` | `POST /graph/score_within` | v2 exploration | READ — per-id GDS signals for a fixed set |
| (health) | `GET /graph/health` | reachability check | READ |

Verified: those `:8010` handlers (`graph_similar`, `graph_structured`, `score_within` in `shared/graph/api.py`)
are **MATCH/RETURN** Cypher — **no `CREATE/MERGE/SET/DELETE`**. And `discovery_api/src` contains **no graph
write of any kind** (no Cypher writes, no Neo4j driver writes — it never imports the driver; it only calls the
HTTP service). The local `gds_signals_dev.csv` is used for **bulk popularity prep** (read of a CSV), distinct
from the per-id `graph_score_within` live read.

> **Bottom line for deployment:** Neo4j must simply **be up and already loaded** (the existing 57,443-node
> graph). Endpoint 2 writes nothing to it and requires no migration, no new edges, no re-precompute.

---

## 2. Vector index — NO change / NO re-index (read-only)

**Does the vector index need any change or re-indexing for Endpoint 2? → NO.** Endpoint 2 **reuses the same
57,443 Voyage embeddings, read-only.**

**What's already in the vector service** (`shared/vector`, `:8000`):
- **57,443 entities** embedded with **Voyage `voyage-4-large` (1024-d)**, served from an **in-memory Qdrant**
  ANN index + a **BM25** keyword index, over **Postgres**. `/api/stats` → `total_entities: 57443`
  (game 6537, movie 25855, podcast 19029, tv 6022).

**The vector endpoints Endpoint 2 calls**, all **READ**:

| Method | Endpoint | Used by | Operation |
|---|---|---|---|
| `vector_retrieve` | `POST /api/retrieve` | **v2** composed-string retrieval | READ — **embeds the composed phrase live via Voyage at request time**, then ANN search |
| `vector_neighbors` | `POST /api/neighbors` | **v1** similar/popular pools | READ — nearest neighbours of an entity's **STORED** vector (**no re-embed**) |
| (health) | `GET /api/stats` | reachability check | READ |

- Endpoint 2 **never** writes vectors, never re-embeds the corpus, never rebuilds the index. There is **no
  `/api/embed`-with-store** or any upsert call in `discovery_api/src`.
- **Important runtime dependency:** v2's `/api/retrieve` path means the **vector service embeds a fresh phrase
  via Voyage on each retrieval call**. So the **deployed vector service must have working Voyage access**
  (its `VOYAGE_API_KEY`). Endpoint 2 itself does not call Voyage directly — it relies on the vector service.

> **Bottom line for deployment:** the vector index needs **no change** for Endpoint 2. It must simply be **up
> and serving** the existing embeddings, **with Voyage available** for the live phrase embedding in
> `/api/retrieve`.

---

## 3. Substrate-readiness summary

Endpoint 2 **deploys on top of the existing substrate** that Endpoint 1 already uses. For Endpoint 2 to
function, the following must already be **running and reachable** from the discovery-api host:

| Substrate piece | Must be | Endpoint 2's relationship |
|---|---|---|
| **Neo4j** (graph DB, 57,443-node graph + GDS) | up + loaded | read-only (via the graph service) |
| **Graph service** `:8010` | up | Endpoint 2 calls `/graph/similar`, `/graph/structured`, `/graph/score_within` |
| **Postgres** (vector relational store) | up + loaded | indirect (the vector service uses it) |
| **Vector service** `:8000` (Voyage + Qdrant + BM25, **Voyage key live**) | up + loaded (~1 min) | Endpoint 2 calls `/api/retrieve`, `/api/neighbors` |
| **Voyage access** | available to the vector service | needed for `/api/retrieve` live phrase embedding |

Endpoint 2 reaches the substrate purely via the two URLs `VECTOR_API_URL` / `GRAPH_API_URL` (doc 04) — change
those to point at wherever the substrate is deployed; no other coupling. If the substrate is **down**, Endpoint
2 **degrades to a global feed** rather than failing (doc 01 §7).

> If the production target moves the substrate to **managed services** (Databricks Vector Search instead of
> Qdrant, Neo4j AuraDS instead of self-hosted) — the Endpoint-1 deployment doc `docs/03_DATABRICKS_DEPLOYMENT.md`
> §2–3 describes that "Stage B". **Endpoint 2 is unaffected by that swap** as long as the `:8000`/`:8010`
> read contracts (the request/response shapes in `substrate_client.py`) are preserved behind the same URLs.
