# Endpoint 2 — Discovery API — Deployment Documentation

> **Audience:** whoever deploys and operates Endpoint 2 (primarily Satish, deploying to Databricks).
> **Scope:** how to understand, deploy, run, and test the discovery-api end to end.
> Every claim here is grounded in the actual code; files/functions are cited so you can verify.

---

## What Endpoint 2 is (two paragraphs)

Endpoint 2 is the **discovery-api**: an HTTP service (FastAPI on **port 8030**, [`discovery_api/src/api.py`](../src/api.py)) that returns a **personalised discovery feed** — a vertical "main feed" of content *moments* plus horizontal *carousels* of properties — for a given user. There is **no natural-language query**; the caller passes a structured request (`user_id`, paging, filters, flags) to `POST /discovery/feed` and gets back a **v1.0 JSON envelope** (main feed + carousels, each item with a `why_string`). It serves ~7K→**57,443** entertainment entities across games / movies / TV / podcasts.

Internally it offers **two selectable engines**. **v1** is the global-popularity + similarity-pools baseline. **v2** is the **taste-learning engine** described in [`../V2_STRATEGY.md`](../V2_STRATEGY.md): it builds a recency-decayed, clustered **taste profile** from the user's follows/reactions, retrieves candidates via the **shared vector + graph substrate**, blends a **three-signal score** (taste-match + trending-velocity + recency), adds an exploration layer, and assembles the same v1.0 envelope. Endpoint 2 is a **pure client of the SAME vector (:8000) and graph (:8010) services that Endpoint 1 uses** — it adds **nothing** to Neo4j or the vector index (confirmed read-only against the code; see doc 03).

---

## ⚠️ Current state (read this before planning a deployment)

| Aspect | State |
|---|---|
| Engine (v1 + v2) | **Implemented & tested locally** (unit tests + persona/synthetic eval). |
| Data source | **Reads dev CSVs only** (`CsvDataSource`). **`LiveDataSource` is a complete STUB** — every method raises `NotImplementedError` ([`live_source.py`](../src/data_access/live_source.py)). **Reading live production data is NOT implemented.** |
| Substrate (vector/graph) | **Reuses the existing, already-built substrate read-only.** No new Neo4j load, no vector re-index (doc 03). |
| Trending signal | Mechanically correct; **quiet on dev data** (~31 reactions). Needs near-real-time engagement data to be meaningful (doc 02). |
| Validation | Validated on **dev CSVs + a synthetic engagement population**. **No real-user testing yet.** |
| Interactive endpoints (`/follow`, `/react`, `/me`, …) | Implemented but **in-memory, single-instance demo** (the "Build Your Taste" UI). Not a persistence layer. |

**Bottom line:** the engine is production-quality *code* validated on dev/synthetic data, deployable today **against the dev CSVs**. Before it is a **real production endpoint** the live-data source must be implemented and a few other gaps closed — see **[06_GO_LIVE_CHECKLIST_AND_GAPS.md](06_GO_LIVE_CHECKLIST_AND_GAPS.md)**.

---

## High-level architecture (confirmed against code)

```
                       ┌──────────────────────────────────────────────┐
   caller  ──POST──►   │  discovery-api  (:8030)  discovery_api/src/api │
  (feed request)       │   • v1 engine  (engine.py)                     │
                       │   • v2 engine  (feed/blend.py V2FeedBuilder)   │
                       │   • reads tabular data via DataSource          │
                       └───────┬───────────────────────┬──────────────┘
       reads CSVs (dev)        │                        │  HTTP (READ-ONLY)
   discovery_api/data/dev/ ◄───┘                        ▼
                                      ┌─────────────────────────────────────┐
                                      │ shared VECTOR svc :8000 (Voyage+Qdrant)│  POST /api/retrieve, /api/neighbors
                                      │ shared GRAPH  svc :8010 (Neo4j+GDS)    │  POST /graph/similar,/structured,/score_within
                                      └─────────────────────────────────────┘
```

- Endpoint 2 **reads** tabular data (entities, moments, follows, reactions, gds signals, …) — **currently from CSVs** in `discovery_api/data/dev/`.
- For similarity/retrieval it makes **HTTP calls to the shared services** — all **read** operations ([`substrate_client.py`](../src/data_access/substrate_client.py)). It never writes to Neo4j, the vector index, or any DB (verified: no write ops in `discovery_api/src`).
- `/api/retrieve` (vector) **embeds the composed phrase via Voyage at request time**, so the deployed endpoint needs the vector service's Voyage access available (doc 03).

---

## The documents in this set

| Doc | What it covers |
|---|---|
| **[00_DEPLOYMENT_INDEX.md](00_DEPLOYMENT_INDEX.md)** | This entry point: what E2 is, current state, architecture, the doc map. |
| **[01_RUN_AND_OPERATE.md](01_RUN_AND_OPERATE.md)** | Exact commands to bring up the stack; startup order; the `POST /discovery/feed` request/response contract with curl examples; the v1/v2 engine selector; `/discovery/health`; graceful degradation. |
| **[02_DATA_AND_LIVE_INTEGRATION.md](02_DATA_AND_LIVE_INTEGRATION.md)** | Every data input and what it maps to upstream; **the live-data gap (CSV → live `LiveDataSource` stub)**; the trending data-refresh requirement; the integer-`user_id` note. **The most important doc for go-live.** |
| **[03_NEO4J_AND_VECTOR.md](03_NEO4J_AND_VECTOR.md)** | The substrate: **Neo4j needs NO new load** and the **vector index needs NO change** for Endpoint 2 (both read-only) — stated plainly and confirmed against code. What must already be running. |
| **[04_CONFIG_AND_SECRETS.md](04_CONFIG_AND_SECRETS.md)** | The deployment-relevant config knobs (must-set vs tuning) and the secrets/credentials needed (named, never printed) and where they live. |
| **[05_DATABRICKS_DEPLOYMENT.md](05_DATABRICKS_DEPLOYMENT.md)** | How E2 maps onto the Databricks deployment pattern used for Endpoint 1; packaging/run specifics; connectivity; items marked "to confirm with the platform team". |
| **[06_GO_LIVE_CHECKLIST_AND_GAPS.md](06_GO_LIVE_CHECKLIST_AND_GAPS.md)** | The honest readiness list: deploy + smoke-test checklist, the explicit gaps that block real production, and the test/eval commands as the smoke check. |

**Reading order:** 00 → 01 (run it) → 02 + 03 (data & substrate truth) → 04 (config/secrets) → 05 (Databricks) → 06 (go-live).
