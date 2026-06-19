# 06 — Go-Live Checklist & Honest Gaps

The deploy-and-smoke-test checklist, the explicit gaps that must be closed before this is a **real production
endpoint**, and the test/eval commands that serve as the deployment smoke check.

---

## 1. Deploy + smoke-test checklist

**Pre-flight**
- [ ] Host has Python 3.10, outbound HTTP to the substrate (and to Databricks LLM **only if** `V2_STRING_COMPOSER=llm`).
- [ ] The **substrate is deployed and reachable**: vector `:8000` (loaded, Voyage live) and graph `:8010`
      (Neo4j loaded). Endpoint 2 adds nothing to them (doc 03).
- [ ] Data available: dev CSVs present (CSV mode) **or** `LiveDataSource` implemented (live mode) — doc 02.
- [ ] Production env vars set (doc 04 MUST-SET): `VECTOR_API_URL`, `GRAPH_API_URL`,
      `DISCOVERY_DEFAULT_ENGINE=v2`, **`DISCOVERY_NOW_ISO=""`**, `DISCOVERY_DATA_SOURCE`.

**Bring-up**
- [ ] Start the substrate; confirm `:8000/api/stats` → **57,443** and `:8010/graph/health` → ok.
- [ ] Start the discovery-api: `uvicorn discovery_api.src.api:app --host 0.0.0.0 --port 8030` **from repo root**.

**Verify (smoke test)**
- [ ] `GET /discovery/health` → `status:ok`, `entities:57443`, `substrate_reachable:true`,
      `default_engine:v2`, `data_source_mode:` (csv|live as configured).
- [ ] **Cold-start request** — a user with no follows → `context.mode:"cold_start"`, a **non-empty global**
      main feed:
      ```bash
      curl -s -X POST :8030/discovery/feed -d '{"user_id":7064,"limit":5}' | jq '.context.mode, .main_feed.count'
      ```
- [ ] **Personalized request** — fixture `12305` (28 follows) → `context.mode:"personalized"`, "Because you
      follow …" why_strings, `cluster_/trending/exploration` carousels:
      ```bash
      curl -s -X POST ':8030/discovery/feed?engine=v2' -d '{"user_id":12305,"limit":8,"debug":true}' \
        | jq '.context, [.main_feed.items[].why_string]'
      ```
- [ ] **Engine default** — confirm `?engine=v1` vs `?engine=v2` produce **different** feeds (selector works).
- [ ] **Exclusions** — pass `property_ids` (a followed/excluded id) and confirm it never appears.
- [ ] **Degradation** — stop the substrate, repeat the personalized request → still returns a global feed,
      `substrate_reachable:false`, no 500.

---

## 2. Run the tests & eval (the deployment smoke check)

All run with the repo venv from the **repo root** (substrate up for the live-substrate ones):

```bash
# Engine unit/integration tests (each prints "RESULT: ALL PASS")
.venv/bin/python discovery_api/test_taste_profile_v2.py     # V2-P2  taste profile + clustering
.venv/bin/python discovery_api/test_v2p3_retrieval.py       # V2-P3  vector+graph retrieval + exclusions (needs substrate)
.venv/bin/python discovery_api/test_v2p4_feed.py            # V2-P4  trending + blend + assembly (needs substrate)
.venv/bin/python discovery_api/test_v2p6_wiring.py          # V2-P6  engine selector + bundle cache (needs substrate)

# Earlier P-series suites (engine core / API)
.venv/bin/python -m pytest discovery_api/tests/ -q          # test_core / test_p4 / test_p51 / test_p5_api

# Trending-goes-live validation (synthetic population; proves velocity-not-volume)
cd discovery_api/eval && /<repo>/.venv/bin/python synthetic_population.py

# Persona evaluation — quality, before/after (writes the PERSONA_EVAL_REPORT_V2P7.md)
cd discovery_api/eval && /<repo>/.venv/bin/python persona_eval_v2p7.py    # tuned engine, synthetic population
cd discovery_api/eval && /<repo>/.venv/bin/python persona_eval.py         # v2-vs-v1, dev data
```

> **Run-location note:** the `discovery_api/test_*.py` files put the repo root on `sys.path` and run from
> anywhere. The `discovery_api/eval/*.py` scripts import their siblings (`persona_eval`, `synthetic_population`)
> so run them **from `discovery_api/eval/`** with the **absolute** venv python path.

What "green" proves: the engine is correct on dev/synthetic data — taste profiles cluster correctly, retrieval
excludes followed/seen, the three-signal blend ranks as designed, trending lights up with real volume, drift
is reflected in the feed, no duplicate properties, exclusions never leak. **It does not prove real-user
quality** — see the gaps below.

---

## 3. The honest GAPS (what must be resolved before real production)

| # | Gap | State | Owner / action |
|---|---|---|---|
| 1 | **LIVE-DATA SOURCE** (CSV → live) | **`LiveDataSource` is a full stub** (all methods `NotImplementedError`) | **Blocker.** Implement the 24-method `DataSource` over the live Silver/Lakehouse tables (doc 02 §2). Until then the endpoint serves only dev-snapshot data. |
| 2 | **Near-real-time engagement feed for trending** | trending needs recent follows/reactions; dev data is thin (quiet) | Ensure follows/reactions land in the readable table with low latency; set `V2_TRENDING_REFRESH_SECONDS` to the sync cadence; calibrate `V2_TRENDING_CONFIDENCE_FULL` to real volume (doc 02 §3, doc 04). |
| 3 | **User-id resolution** | endpoint needs the **integer** `user_id`, not the Frontegg UUID | Decide where UUID→int resolution happens (caller vs `LiveDataSource`). Required for live + for the future dwell signal (doc 02 §4). |
| 4 | **Canonical field mapping** | the engine computes its own `influence`/recency; canonical popularity/recency/similarity fields live upstream | Reconcile with the **Feeds.ai data team (Michelle)** — see the "Open questions" in `V2_STRATEGY.md`. Decide which signals are canonical vs engine-computed. |
| 5 | **CICD** | not established for this repo | Set up build/test/deploy with the platform team (doc 05 §4); use the §2 suites as the gate. |
| 6 | **Substrate deployed & reachable** | confirmed locally; production placement TBD | Confirm the vector/graph services are deployed where the discovery-api can reach them, with Voyage live (doc 03, doc 05 §5). |
| 7 | **Real-user validation** | validated on **dev + synthetic** only | Run real users through the feed; watch fresh-account taste build (the engine is designed for this lifecycle). |
| 8 | **Production config** | dev defaults pin "now" to 2026-06-18 and engine to v1 | Set `DISCOVERY_NOW_ISO=""` and `DISCOVERY_DEFAULT_ENGINE=v2` (doc 04 §1). |

**Built-but-DORMANT (not gaps — intentional sockets, do not describe as working):**
- **Collaborative filtering** (Source 4): the blend term is **wired but weight `0.0`** — the "similar users
  also engage with X" computation is **not built**. Activates when engagement data is dense.
- **Dwell-time signal**: a documented **extension point only** — **not built** (and needs the UUID resolution, #3).
- **Interactive session endpoints** (`/follow`, `/react`, `/me`, `/search`, `/reset`): an **in-memory,
  single-instance demo** (the "Build Your Taste" UI), **not** a production engagement store. If product wants
  in-app follow/react driving the live feed, that needs a persistent, shared store — separate work.

---

## 4. Summary readiness statement (for the client / team)

The discovery-api **engine is built, tuned, and validated on dev + synthetic data**, and **deployable today
against the dev CSVs** on top of the existing vector + graph substrate (to which it **adds nothing** —
read-only). The **one hard prerequisite for a real production deployment is implementing the live-data source**
(gap #1); the supporting gaps (#2–#6) are the standard integration work, each named and scoped, with a clean
interface seam (`DataSource`) designed for exactly that swap and **no engine changes required**.
