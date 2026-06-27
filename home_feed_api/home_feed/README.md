# Feeds.ai Home Feed Endpoint (UC3) — POC

A **follow-gated** home feed: it returns a ranked stream of **moments only from the properties a
user follows**, plus horizontal **carousels** that suggest *unfollowed* properties to discover
("because you follow X, you might like Y"). This is the **inverse** of the discovery feed (which
shows *unfollowed* content).

Spec: `V1.3 Feeds Endpoints and Recommender Use Cases / UC3_Home_Feed_v1.3.md`.

This folder is **self-contained for the endpoint logic** and **reuses the discovery engine**
(`discovery/src/`) as a library — it does **not** modify the discovery package. Nothing here touches
the discovery `/discovery/*` endpoint or the frontend.

---

## What's in here

```
home_feed/src/
  home_api.py        FastAPI app — POST /home-feed  (Databricks-style dataframe_records -> predictions)
  home_schema.py     request model (HomeFeedBody) — UC3 §5
  home_ranking.py    the FOLLOW-GATED ranker (rank_home) — UC3 §2 weights
  home_carousels.py  unfollowed-discovery carousels (layout, insert_after_index, 30-day freshness)
  home_response.py   UC3 response envelope + field mapping (UC3 §6)
```

It reuses these discovery engine modules by import (via a small `sys.path` bootstrap at the top of
each file): `data.py` (asset loader), `ranking.py` (signal primitives), `carousels.py` (carousel
candidate generation), `store.py` (per-user follow/reaction state).

---

## Run locally

From the **project root** (the folder that contains `home_feed/`, `discovery/`, `vector/`, `venv/`):

```bash
PYTHONUTF8=1 venv/Scripts/python.exe -m uvicorn home_api:app --app-dir home_feed/src --port 8040
```

`PYTHONUTF8=1` is **required** (the CSVs contain non-cp1252 characters). Startup loads all assets once
(~70–90 s, dominated by the embedding matrix + first cold Neo4j call). Then:

```
GET http://localhost:8040/home-feed/health   ->  {"status":"ok", "moments":100000, "moment_enrich_loaded":54718, ...}
```

### Data this endpoint reads (all LOCAL in the POC)

| Source | Where | Used for |
|---|---|---|
| `public_properties.csv`, `public_moments.csv` | `discovery/data/raw/` | catalogue + moment pool |
| `enrich_moment_types.csv`, `enrich_media_platforms.csv`, `enrich_moments.csv`, `enrich_properties.csv` | `discovery/data/raw/` | media_platform, is_live, hero image, handle, logo (Databricks Silver exports) |
| `embeddings_qwen_57k.npy` + ids | `vector/data_v2/` | S1 relevance (taste match) |
| Neo4j (HTTP `:7475`) | local graph | S4 centrality, genres |
| Postgres (`:5433`, db `feedsai_discovery`) | `user_follows`, `user_reactions`, `entity_scores` | follow list + trending/popularity |

> **Note for GitHub / Databricks:** the data files above are **git-ignored** (large CSV/`.npy`) and are
> **not** in this repo. The CSVs are exports of Databricks **Silver tables**. To run on Databricks,
> point `discovery/src/data.py` at the Silver tables / Volumes (and Vector Search / AuraDB) instead of
> the local CSV / Postgres / local-Neo4j sources — the endpoint logic in `home_feed/` does not change.

### Prerequisites
- `venv/` with `fastapi`, `uvicorn`, `numpy`, `requests`, `psycopg2` (already present in the project venv).
- Neo4j graph reachable at `http://localhost:7475/db/neo4j/tx/commit` (basic auth `neo4j` / `feedsaiGraphPoC2026`).
  If down, the feed still runs (centrality/genres degrade gracefully).
- Postgres `feedsai_discovery` on `:5433` for the follow list. If down, the store degrades to in-memory.

---

## API

### `POST /home-feed`

Databricks Model-Serving style envelope (a flat single record is also accepted):

```json
{ "dataframe_records": [
  { "user_id": 12305, "limit": 20, "sort_order": "relevance" }
] }
```

Key request fields (full list in `home_schema.py` / UC3 §5): `user_id` (**required** — no anonymous
mode; missing → 422), `limit`, `offset`, `sort_order` (`"relevance"`|`"recent"`), `time_window`,
`date_range` `{start,end}`, `seen_ids[]`, `done_ids[]`, `dismissed_property_ids[]`,
`blocked_property_ids[]`, `user_prefs{excluded_platforms[], excluded_verticals[], weight_today}`,
`carousel_slots`, `carousel_interval`, `debug`, `now`.

Response: `{ "predictions": [ <envelope>, ... ] }`, where each envelope has
`context` (mode/signal_strength/follow_count), `main_feed.items[]` (moments — each `is_followed:true`,
with `why_string`, `score`, `media_platform`, `is_live`, `badge`, …), `carousels[]`
(unfollowed discovery, with `layout` / `insert_after_index`), and `pagination`. See UC3 §6.

### `GET /home-feed/health`
Asset + persistence status.

---

## Quick test

```bash
# (server running on :8040)
curl -s -X POST localhost:8040/home-feed -H 'content-type: application/json' \
  -d '{"dataframe_records":[{"user_id":12305,"limit":10,"debug":true}]}'
```

A scripted 5-scenario check (mapped to the UC3 user stories) and an end-to-end assertion test live at
the project root (`_uc3_scenarios.py`, `_home_int_test.py`) — these are dev-only and not shipped here.

---

## POC limits (data, not code)
- `trending` signal is ~dead locally (engagement table is sparse) and `is_live` is always false (no
  "Live Now" moments in the current pool) — these light up when real engagement / live data arrives.
- Enrichment (media_platform / hero image / handle) covers ~50% of moments in the current export, so
  some cards have honest `null` images/platform.
- Only a handful of users have follows in the local DB, so personalization is real but small-scale.
