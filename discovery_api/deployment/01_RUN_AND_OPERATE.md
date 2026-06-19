# 01 — Run & Operate Endpoint 2

How to bring up the discovery-api locally, the request/response contract, the engine selector, the health
check, and degradation behaviour. Grounded in [`run_app.sh`](../../run_app.sh) and [`api.py`](../src/api.py).

---

## 1. Prerequisites

- **Python 3.10** (the repo venv is `.venv`, Python 3.10.12). Runtime deps are light: `fastapi`, `uvicorn`,
  `httpx`, `pydantic`, `python-dotenv`, `numpy` (used by parts of the engine). No discovery-api-specific
  `requirements.txt` — it shares the repo venv that already serves the substrate services.
- **The shared substrate must be reachable** (see doc 03): Neo4j + Postgres containers, the graph service
  (:8010), and the vector service (:8000). Endpoint 2 itself loads nothing into those — it only reads them.

---

## 2. Startup order & dependencies

Endpoint 2 depends on the substrate but **degrades gracefully** if it is down (§7). Recommended order:

1. **Docker DBs** — Neo4j (`feedsai-neo4j`, :7687/:7474) and the vector Postgres (`feedsai-vector-pg`, :5432).
2. **Graph service** `:8010` (`shared/graph/api.py`) — reads Neo4j; fast to start.
3. **Vector service** `:8000` (`shared/vector/pipeline/api.py`) — **loads 57,443 Voyage embeddings + builds
   the in-memory Qdrant + BM25 index on startup (~1 minute)**. Wait for `/api/stats` to answer before load.
4. **Discovery service** `:8030` (this endpoint) — starts immediately; **loads the dev CSVs lazily on the
   first request** (`CsvDataSource.load()` via `_state()` in `api.py`).

*(The Unified Router `:8020` is **Endpoint 1** and is **not** required for Endpoint 2.)*

---

## 3. Exact commands (local, full stack)

The whole stack is scripted in [`run_app.sh`](../../run_app.sh). To run **just what Endpoint 2 needs**, from the
**repo root** (`feedsai-graphdb/`):

```bash
ROOT=$(pwd); VENV="$ROOT/.venv/bin"

# 1) databases (Docker)
docker start feedsai-neo4j feedsai-vector-pg

# 2) graph service :8010
( cd "$ROOT" && nohup "$VENV/uvicorn" api:app --app-dir shared/graph --host 0.0.0.0 --port 8010 >/tmp/graph_api.log 2>&1 & )

# 3) vector service :8000  (≈1 min to load 57,443 embeddings)
( cd "$ROOT/shared/vector" && nohup "$VENV/uvicorn" pipeline.api:app --host 0.0.0.0 --port 8000 >/tmp/vector_api.log 2>&1 & )
curl -s --retry 60 --retry-delay 1 --retry-connrefused -o /dev/null http://127.0.0.1:8000/api/stats   # wait for vector

# 4) discovery-api :8030  — default engine v2 for deploy (code default is v1; see §5)
( cd "$ROOT" && DISCOVERY_DEFAULT_ENGINE=v2 nohup "$VENV/uvicorn" discovery_api.src.api:app --host 0.0.0.0 --port 8030 >/tmp/discovery_api.log 2>&1 & )
curl -s --retry 60 --retry-delay 1 --retry-connrefused http://127.0.0.1:8030/discovery/health
```

> **CRITICAL run requirement:** the discovery package uses **relative imports**, so it MUST run as a
> **package module from the repo root** — `uvicorn discovery_api.src.api:app` (NOT `--app-dir`,
> NOT from inside `discovery_api/`). This is documented in `run_app.sh` step [6/7].

**Frontend (optional, for manual testing):** `cd frontend && npm run dev` → http://localhost:3000 (login
`feeds.ai@hiteshi.com` / `Feeds@Discover2026`). The UI's **Discovery** tab is a read-only feed viewer; the
**Build** tab exercises the interactive session endpoints. The frontend talks to `:8030`.

---

## 4. The request contract — `POST /discovery/feed`

Request body (pydantic `FeedRequest` in [`api.py`](../src/api.py)) — all fields optional:

| Field | Type | Meaning |
|---|---|---|
| `user_id` | int \| null | **Internal integer DB id** (NOT a Frontegg UUID — see doc 02). `null` → cold-start anon. |
| `sort_order` | `"trending"`(default) \| `"recent"` \| `"popular"` | Re-weights the **v1** blend. **v2 currently honours only its config blend** (echoed, not re-weighted — flagged in code). |
| `time_window` | `"last_7d"` \| `"last_30d"` \| null | Filters main-feed moments by event date. |
| `date_range` | `{start,end}` ISO \| null | Explicit event-date filter on the main feed. |
| `limit` | int (default 20) | Main-feed page size. |
| `offset` | int (default 0) | Main-feed page offset → `next_offset`. |
| `property_ids` | int[] \| null | **EXCLUSION** list (properties to never return). |
| `seen_ids` | int[] \| null | Moment ids already shown → suppressed/demoted. |
| `debug` | bool (default false) | Adds a per-item signal breakdown + a top-level debug block. |
| `now` | ISO string \| null | Reference "now". null → `config.DEFAULT_NOW_ISO` (dev: `2026-06-18`) or wall clock if that is empty. |
| `engine` | `"v1"` \| `"v2"` \| null | Engine selector (§5). null → `config.V2_DEFAULT_ENGINE`. |
| `session_id` | string \| null | Interactive "build your taste" session (forces v2 over an in-memory overlay — demo only, doc 02). |

**Response — the v1.0 envelope** (same shape for v1 and v2 so the contract/UI is unchanged):

```jsonc
{
  "version": "1.0", "endpoint": "discovery-api",
  "user_id": 12305, "generated_at": "2026-06-18T00:00:00+00:00",
  "context": { "mode": "personalized|cold_start", "followed_count": 24,
               "signal_strength": 1.0, "substrate_reachable": true, "engine": "v2" /* v2 only */ },
  "request_echo": { "sort_order": "trending", "limit": 20, "offset": 0, ... },
  "main_feed": {
    "items": [ { "type":"moment", "moment_id":…, "entity_id":"Movie:…", "property_name":…,
                 "vertical":"movie", "title":…, "description":…, "event_starts_at":…,
                 "media_platform_id":…, "score":…, "why_string":"Because you follow …",
                 "debug": { … } /* when debug=true */ } ],
    "count": 20, "next_offset": 20
  },
  "carousels": [ { "carousel_id":"cluster_1|trending|exploration|new_in_genre_…|new_on_platform_…",
                   "reason_type":"…", "reason_string":"Because you follow …", "item_type":"property",
                   "items":[ { "type":"property", "entity_id":…, "name":…, "vertical":…,
                               "genres":[…], "score":…, "why_string":…, "latest_moment":{…} } ] } ],
  "debug": { … } /* when debug=true: pools_built, timing_ms, substrate_calls, bundle_cache, etc. */
}
```

On an internal error the service returns **HTTP 500 with a structured body** `{"version":"1.0","endpoint":
"discovery-api","error":"<Type>: <msg>"}` (it never crashes the response).

### Example requests

```bash
# Cold-start user (no follows) → global feed (works on both engines)
curl -s -X POST http://localhost:8030/discovery/feed \
  -H 'Content-Type: application/json' \
  -d '{"user_id":7064,"limit":5,"now":"2026-06-18T00:00:00Z"}' | jq '.context, .main_feed.count'
#  expect: mode "cold_start", a non-empty global main feed.

# Personalized user (fixture 12305 = 28 follows) on v2, with debug
curl -s -X POST 'http://localhost:8030/discovery/feed?engine=v2' \
  -H 'Content-Type: application/json' \
  -d '{"user_id":12305,"limit":8,"now":"2026-06-18T00:00:00Z","debug":true}' \
  | jq '.context, [.main_feed.items[].why_string], [.carousels[].carousel_id]'
#  expect: mode "personalized", "Because you follow …" why_strings, cluster_/trending/exploration carousels.
#  NOTE: first personalized build ≈ 5 s (6 vector calls); the per-(user,now) bundle cache makes repeats sub-second.
```

---

## 5. The v1 ↔ v2 engine selector

Selection precedence (in `discovery_feed()`): **`?engine=` query param > `engine` body field >
`config.V2_DEFAULT_ENGINE`**.

- **`config.V2_DEFAULT_ENGINE` default in code is `"v1"`** ([`config.py`](../src/config.py)). The demo instance
  is run with the env override `DISCOVERY_DEFAULT_ENGINE=v2`.
- **To serve v2 by default in a deployment: set the env var `DISCOVERY_DEFAULT_ENGINE=v2`.**
- v1's path is byte-identical to before the selector was added (early-return for v2; v1 untouched).
- `/discovery/health` reports the active default under `default_engine` and the available `engines:["v1","v2"]`.

---

## 6. Health check — `GET /discovery/health`

Returns (live example):

```json
{ "status":"ok", "endpoint":"discovery-api", "version":"1.0", "port":8030,
  "data_source_mode":"csv", "entities":57443,
  "vector_api_url":"http://localhost:8000", "graph_api_url":"http://localhost:8010",
  "default_engine":"v2", "engines":["v1","v2"], "substrate_reachable":true,
  "now":"2026-06-18T00:00:00+00:00" }
```

Use it as a **liveness/readiness check**. Key fields for ops:
- `data_source_mode` — **`csv`** today (would be `live` once `LiveDataSource` is implemented, doc 02).
- `entities` — should be **57443** (confirms the CSVs loaded).
- `substrate_reachable` — whether `:8000`+`:8010` answered (cached ~15 s). `false` → the feed still works in a
  degraded global mode (§7).
- `default_engine` — which engine unselected requests use.

---

## 7. Graceful degradation (substrate down)

Confirmed in code:
- **Reachability is cached ~15 s** (`_State.substrate_up()`); each request reads it.
- **v1:** when the substrate is unreachable, the API routes to `engine_global` (a `DiscoveryEngine` built with
  `substrate=None`) → personalised similarity pools are empty → a **global feed** (fresh + trending + new-in-genre
  from the local CSVs) is still returned.
- **v2:** every substrate call goes through `SubstrateClient`, which **raises `SubstrateError` after retries**;
  the retrieval layer catches it per-call (`run_concurrent` turns a failed call into an empty result) and
  degrades. Cold-start / no-cluster users always route to the v1 global feed (`fallback_to_global`).
- **The feed never 500s on a substrate blip** — it returns a thinner, global feed and `substrate_reachable:false`.
- Per-request HTTP timeout `DISCOVERY_HTTP_TIMEOUT_S` (15 s) and `DISCOVERY_HTTP_RETRIES` (3) bound the wait.

---

## 8. Operational notes

- **Caches are in-process, per instance** (profile cache, bundle cache, trending table). They are not shared
  across instances. Safe, but a horizontally-scaled deployment gets per-instance caches (no correctness issue;
  just less cache-hit sharing). TTLs are config (doc 04).
- **Interactive session endpoints** (`/discovery/search|follow|unfollow|react|reset|me`) keep state in an
  **in-memory `SessionStore`** — single-instance, ephemeral, demo-only (the "Build Your Taste" UI). They are
  **not** a production engagement store and do not persist across restarts or share across instances.
- After any code change to `discovery_api/src/`, **restart `:8030`** (uvicorn caches the module; no `--reload`
  in the run script).
- Logs (PoC): `/tmp/discovery_api.log`.
