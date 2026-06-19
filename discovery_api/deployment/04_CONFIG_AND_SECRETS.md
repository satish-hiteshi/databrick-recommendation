# 04 — Configuration & Secrets

All configuration lives in **one file**, [`config.py`](../src/config.py): every value is read via
`os.getenv("<NAME>", "<default>")`, so **any knob can be set with an environment variable at deploy time, with
no code change** (`config.summary()` returns a non-secret view, surfaced in `/discovery/health`). The config
module loads no `.env` itself — set env vars directly in the deployment. (The only `.env` loading is the
**optional** LLM composer, §3.)

---

## 1. MUST-SET for a deployment (these change behaviour materially)

| Env var | Default (code) | Set to (deploy) | Why |
|---|---|---|---|
| `DISCOVERY_DATA_SOURCE` | `csv` | `csv` **until `LiveDataSource` is implemented**, then `live` | Selects CSV vs live data. `live` today → `NotImplementedError` (doc 02). |
| `VECTOR_API_URL` | `http://localhost:8000` | the deployed **vector service URL** | Where Endpoint 2 reads vector retrieval. |
| `GRAPH_API_URL` | `http://localhost:8010` | the deployed **graph service URL** | Where Endpoint 2 reads graph signals. |
| `DISCOVERY_DEFAULT_ENGINE` | `v1` | **`v2`** (to serve the taste-learning engine by default) | Unselected requests use this engine. |
| `DISCOVERY_NOW_ISO` | `2026-06-18T00:00:00Z` | **`""` (empty)** | The dev default pins "now" to the June-2026 dev snapshot for reproducibility. **In production set it empty so the engine uses the real wall clock** — otherwise recency/trending are computed against a frozen date. |

> ⚠️ **`DISCOVERY_NOW_ISO` is the easiest production foot-gun.** Leaving it at the dev default makes every
> feed think "today" is 2026-06-18. Set it empty in any real deployment.

---

## 2. Tuning knobs (sensible defaults; tune against the eval, not blindly)

These are the **V2-P7-tuned** values (validated by the persona eval — see `eval/PERSONA_EVAL_REPORT_V2P7.md`).
They are good production starting points.

**Three-signal blend** (per-moment score in [`moment_select.py`](../src/feed/moment_select.py)):
| Knob | Default | Role |
|---|---|---|
| `DISCOVERY_V2_W_TASTE` | `1.0` | weight of taste-match |
| `DISCOVERY_V2_W_TRENDING` | `1.0` | weight of trending-velocity |
| `DISCOVERY_V2_W_RECENCY` | `1.0` | weight of recency (V2-P7: raised 0.6→1.0 for freshness) |
| `DISCOVERY_V2_W_COLLABORATIVE` | `0.0` | **collaborative term — wired but DORMANT** (Source 4 not built) |
| `DISCOVERY_V2_SEEN_SUPPRESSION` | `1.0` | demotion for already-seen moments |
| `DISCOVERY_V2_TASTE_CLUSTER_WEIGHTING` | `0.5` | folds recency-weighted cluster share into ranking (the "drift" fix) |
| `DISCOVERY_V2_RECENCY_STALE_DAYS` / `_STALE_FACTOR` | `540` / `0.6` | soft floor: demote (not drop) moments older than N days |
| `DISCOVERY_V2_MOMENT_CAP` | `1` | max moments per property in the feed (V2-P7: 3→1, no duplicates) |

**Trending** (calibrate to real engagement volume in production):
| Knob | Default | Role |
|---|---|---|
| `DISCOVERY_V2_TRENDING_REFRESH_SECONDS` | `900` (15 min) | precompute/cache cadence — **match your data-sync cadence** |
| `DISCOVERY_V2_TRENDING_CONFIDENCE_FULL` | `200` | decayed events ≈ full confidence — **calibrate to real volume** (lower = trending engages sooner) |
| `DISCOVERY_V2_TRENDING_HALFLIFE_DAYS` / `_WINDOW_DAYS` | `3` / `21` | velocity decay half-life / event window |

**Caches & HTTP:**
| Knob | Default | Role |
|---|---|---|
| `DISCOVERY_V2_PROFILE_CACHE_TTL_SECONDS` | `600` | taste-profile cache TTL (profiles change slowly) |
| `DISCOVERY_V2_BUNDLE_CACHE_TTL_SECONDS` | `300` | retrieval-bundle cache TTL (sub-second warm feeds) |
| `DISCOVERY_HTTP_TIMEOUT_S` / `DISCOVERY_HTTP_RETRIES` | `15` / `3` | per-substrate-call timeout / retries |
| `DISCOVERY_SUBSTRATE_MAX_WORKERS` | `4` | bounded concurrency for substrate calls |

**Composer & retrieval depth** (rarely changed): `DISCOVERY_V2_STRING_COMPOSER` (`deterministic`|`llm`,
default `deterministic`), `DISCOVERY_V2_RETRIEVE_TOP_K` (30), `DISCOVERY_V2_CANDIDATE_BUDGET` (240),
`DISCOVERY_V2_EXPLORE_FRAC_MIN/MAX` (0.10/0.50). Full list + comments in [`config.py`](../src/config.py).

---

## 3. Secrets & credentials (named, never printed)

**Endpoint 2 itself needs NO secrets in its default configuration.** It reads CSVs locally and calls the
substrate services over plain HTTP. The secrets that matter belong to the **substrate** (which must already be
running) and to one **optional** Endpoint-2 feature:

| Secret | Needed by | Where it lives (gitignored) | Required for Endpoint 2? |
|---|---|---|---|
| `VOYAGE_API_KEY` | the **vector service** (live phrase embedding in `/api/retrieve`) | `shared/vector/.env` | Indirectly yes — the vector service needs it; Endpoint 2 does not hold it. |
| **Neo4j credentials** (`NEO4J_URI/USER/PASSWORD`) | the **graph service** | `shared/graph/.env` | Indirectly yes — the graph service needs them; Endpoint 2 does not hold them. |
| Postgres password | the vector service | `shared/vector/.env` | Indirectly yes. |
| `DATABRICKS_TOKEN` (+ `DATABRICKS_LLM_ENDPOINT`) | the **optional** v2 `llm` composer | loaded from `shared/vector/.env` + `agent_recs/.env` by [`llm_seam.py`](../src/retrieval/llm_seam.py) | **Only if `DISCOVERY_V2_STRING_COMPOSER=llm`.** Default is `deterministic` → **not needed.** |
| live DB credentials | a future `LiveDataSource` | TBD (deployment secret store) | **Yes, once live data is implemented** (doc 02) — does not exist yet. |

Rules:
- **Never commit secrets.** All `.env` files are gitignored; the repo contains none. Verified: no token/secret
  is present in any committed file.
- At deploy, **inject secret values as environment variables** from a secret store (Databricks Secrets / cloud
  secret manager / K8s secrets). Every value is read via `os.getenv`, so env vars work identically.
- Prefer a **service-principal token** over a personal PAT for `DATABRICKS_TOKEN`; scope it to the serving
  endpoint; rotate on a schedule (this mirrors the Endpoint-1 guidance in `docs/03_DATABRICKS_DEPLOYMENT.md` §4).
- **The actual secret values are not in the repo or these docs** — obtain them from the secret store / the
  team. This doc names *what* is needed and *where it lives*, never the values.
