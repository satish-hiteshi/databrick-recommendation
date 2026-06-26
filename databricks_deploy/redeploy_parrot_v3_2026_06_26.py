# Databricks notebook source
# MAGIC %md
# MAGIC # Redeploy Endpoint 1 — Agent-Recs (optimized router · Qwen 44k) — 2026-06-26
# MAGIC **What changed in this redeploy**
# MAGIC - **Optimized router code** (`engines/router_src/`): negation recovery (G37/G38), deterministic
# MAGIC   **recency** (`recency.py` — new/newest/latest + epoch date window), graceful **overconstrain
# MAGIC   relaxation** (`MIN_RESULTS=3`), LLM **no-signal/gibberish** fallback (`no_signal.py` — new),
# MAGIC   PROMPT2 fixes (raw-query embedding, `RERANK=auto`, verbatim Capital-prefixed ids).
# MAGIC - **New corpus parquet**: `embeddings_qwen_44k_prefixed.parquet` (Qwen 1024-dim, Capital-prefixed
# MAGIC   ids, carries `release_date_ts`). **Freshly-restored graph** (Aura, from dump) — done out of band.
# MAGIC
# MAGIC **Self-configuring · job-runnable.** Derives repo path + workspace host, registers the collapsed
# MAGIC model (engines + parquet), **creates OR updates** the endpoint, waits READY, runs the acceptance
# MAGIC smoke battery. Override any value via job `base_parameters` / widgets.
# MAGIC
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated; reinstalling it breaks registration.
# MAGIC
# MAGIC > ✅ **Recency:** `vector_search/vs_store.py` now range-filters `release_date_ts` (epoch). Recency
# MAGIC > works **iff the `entities` table + `entities_vs` index are rebuilt from the new parquet carrying
# MAGIC > `release_date_ts`** — verify H5. Date bounds reach `vs_store` via the vector NLU
# MAGIC > (`date_filter_start/end` → `retrieval` → `vector_search`). Gates: `VS_DATE_FILTER=0` disables it;
# MAGIC > `VS_RELEASE_DATE_COL` overrides the column. (The router's own `recency.py` window — new/newest/
# MAGIC > latest — is currently re-derived by the vector NLU; routing its `date_from_ts/to_ts` straight
# MAGIC > through `_vec_query`→`process_query` is a further optional step.)

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host (no hardcoding) =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (parrot bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — a Job can override via base_parameters) =====================
_defaults = {
    "catalog":       "stg_feeds_silver",
    "schema":        "ml",
    "endpoint":      "parrot-api-staging",            # client copy defaults to parrot-api-staging-v2
    "scope":         "feedsai_staging",               # Databricks secret scope (neo4j_password, databricks_token)
    "parquet":       "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet",  # NEW corpus
    "vs_endpoint":   "feedsai-staging-vs",
    "vs_index":      "stg_feeds_silver.ml.entities_vs",
    "neo4j_uri":     "neo4j+s://17aa0e8d.databases.neo4j.io",
    "llm_endpoint":  "llama_v3_3_70b_instruct",       # LLM serving-endpoint NAME (URL built from HOST)
    "qwen_embed":    "databricks-qwen3-embedding-0-6b",
    "workload_size": "Medium",
    "enable_timing": "1",                             # "1" → TIMING_BREAKDOWN (source for per-stage latency)
    # ── observability (OTLP → Grafana Cloud, H1.6) ──
    "otel_service":  "agent-recs",                    # OTEL_SERVICE_NAME
    "enable_otel":   "0",                             # "1" → push telemetry (needs the grafana_otlp_token secret)
    "otel_endpoint": "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":   "grafana_otlp_token",            # secret key in <scope> holding the base64 OTLP token
    "otel_sampler":  "0.15",                          # fraction of requests traced (metrics stay 100%)
    # ── data sync (Step 1.5) ──
    "rebuild_index": "0",                             # "1" → rebuild ml.entities + entities_vs from `parquet` (carries release_date_ts)
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"], "| parquet:", C["parquet"])

# COMMAND ----------
# ===================== 1.5 (OPTIONAL) REBUILD entities table + entities_vs from the parquet =====================
# MAGIC %md
# MAGIC Gated by the **`rebuild_index`** widget. parquet → `<catalog>.<schema>.entities` Delta table
# MAGIC (carrying `release_date_ts`) → **recreate** the `entities_vs` Delta-Sync index (delete + create, so it
# MAGIC picks up `release_date_ts` and the Qwen vectors). Required whenever the corpus/parquet changed — this
# MAGIC is what makes `vs_store`'s recency filter (and correct Qwen retrieval) actually work.

# COMMAND ----------
if C["rebuild_index"] != "1":
    print("rebuild_index=0 → skipping entities/entities_vs rebuild (set the widget to 1 to run it).")
else:
    TABLE = f"{C['catalog']}.{C['schema']}.entities"
    # (1) verify the parquet schema (must include release_date_ts + the Qwen embedding)
    df = spark.read.parquet(C["parquet"])
    print("parquet rows:", df.count()); df.printSchema()
    _missing = {"entity_id", "name", "vertical", "embedding", "release_date_ts"} - set(df.columns)
    assert not _missing, f"parquet missing required columns: {_missing}"
    # (2) parquet → Delta table (+ Change Data Feed, required for a Delta-Sync index)
    (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE))
    spark.sql(f"ALTER TABLE {TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    print("entities table rows:", spark.table(TABLE).count())
    display(spark.sql(f"SELECT vertical, count(*) n, "
                      f"sum(CASE WHEN release_date_ts IS NULL THEN 1 ELSE 0 END) null_dates "
                      f"FROM {TABLE} GROUP BY vertical"))
    # (3) recreate the VS index (delete + create → picks up release_date_ts + the Qwen vectors).
    #     A plain .sync() would NOT add a new column or swap the embedding source — recreate is required.
    from databricks.vector_search.client import VectorSearchClient
    vsc = VectorSearchClient(disable_notice=True)
    _existing = [i["name"] for i in (vsc.list_indexes(C["vs_endpoint"]).get("vector_indexes") or [])]
    if C["vs_index"] in _existing:
        print("deleting stale index…"); vsc.delete_index(C["vs_endpoint"], C["vs_index"])
    vsc.create_delta_sync_index_and_wait(
        endpoint_name=C["vs_endpoint"], index_name=C["vs_index"], source_table_name=TABLE,
        pipeline_type="TRIGGERED", primary_key="entity_id",
        embedding_dimension=1024, embedding_vector_column="embedding",   # self-managed (precomputed) Qwen vectors
        # if your workspace requires explicit column selection, add:
        # columns_to_sync=["entity_id", "name", "vertical", "release_date_ts"],
    )
    # (4) verify the date filter actually works on the index
    idx = vsc.get_index(C["vs_endpoint"], C["vs_index"])
    _sample = spark.table(TABLE).select("embedding").limit(1).collect()[0]["embedding"]
    _chk = idx.similarity_search(query_vector=list(_sample), columns=["entity_id", "name", "vertical"],
            filters={"release_date_ts >=": 1704067200}, num_results=3)   # >= 2024-01-01 UTC
    print("date-filtered sample:", (_chk.get("result", {}).get("data_array") or [])[:3])
    print("entities + entities_vs rebuilt and date filter verified ✓")

# COMMAND ----------
# ===================== 2. REGISTER (bundle optimized engines + new Qwen parquet → UC model) =====================
import mlflow, sys, importlib
mlflow.set_registry_uri("databricks-uc")             # runtime mlflow; do NOT pip-install it
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = C["parquet"]  # the in-memory store rebuilds from THIS parquet at register
sys.modules.pop("register", None)                    # ensure THIS bundle's register is loaded
sys.path.insert(0, SERVING)
import register; importlib.reload(register)
register.main()
from mlflow.tracking import MlflowClient
ver = str(max(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))
print("registered version:", ver)

# COMMAND ----------
# ===================== 3. CREATE-OR-UPDATE the endpoint (full env) + WAIT FOR READY =====================
from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (EndpointCoreConfigInput, ServedEntityInput, TrafficConfig, Route)
wc = WorkspaceClient()

def sec(k): return "{{" + f"secrets/{C['scope']}/{k}" + "}}"
ENV = {
    "ROUTER_ENGINE_MODE": "inprocess",                # collapse: blocks._post/_get dispatch in-process
    "LLM_PROVIDER": "databricks",
    "DATABRICKS_LLM_ENDPOINT": f"{HOST}/serving-endpoints/{C['llm_endpoint']}/invocations",
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "QUERY_EMBED_ENDPOINT": C["qwen_embed"],           # queries embed via Qwen (instruction-prefixed; matches corpus)
    "VECTOR_BACKEND": "databricks",
    "VS_ENDPOINT_NAME": C["vs_endpoint"], "VS_INDEX_NAME": C["vs_index"],
    "NEO4J_URI": C["neo4j_uri"], "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": sec("neo4j_password"), "NEO4J_DATABASE": "neo4j",
}
if C["enable_timing"] == "1":
    ENV["TIMING_BREAKDOWN"] = "1"

# ── observability (H1.6): OTEL_SERVICE_NAME is always safe; the OTLP push is gated on enable_otel
# (the secret must exist in the scope, else the endpoint create fails on an unresolvable secret ref). ──
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["OTEL_EXPORTER_OTLP_HEADERS"]  = "Authorization=Basic%20" + sec(C["otel_secret"])  # %20 = space (literal space 401s)
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="router", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="router", traffic_percentage=100)])
exists = any(e.name == C["endpoint"] for e in wc.serving_endpoints.list())
print(("updating" if exists else "creating") + f" {C['endpoint']} → v{ver} … waiting for READY (~15 min warm-up)")
if exists:
    wc.serving_endpoints.update_config_and_wait(name=C["endpoint"], served_entities=entities,
        traffic_config=traffic, timeout=timedelta(minutes=50))
else:
    wc.serving_endpoints.create_and_wait(name=C["endpoint"],
        config=EndpointCoreConfigInput(served_entities=entities, traffic_config=traffic),
        timeout=timedelta(minutes=50))
print("endpoint state:", wc.serving_endpoints.get(C["endpoint"]).state)

# COMMAND ----------
# ===================== 4. ACCEPTANCE SMOKE BATTERY (REVIEW_CHECKLIST H-battery) =====================
import requests, json
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"

def ask(query, agent="morgan", uid="13", top_k=10):
    body = {"dataframe_records": [{"user_id": uid, "query": query, "requesting_agent": agent, "top_k": top_k}]}
    r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                      json=body, timeout=120)
    r.raise_for_status()
    inner = r.json()["predictions"][0]
    resp = inner.get("response"); resp = resp if isinstance(resp, dict) else json.loads(resp)
    return resp, (resp.get("router", {}) or {})

def show(tag, query, resp, rt):
    res = resp.get("results") or []
    print(f"\n[{tag}] {query!r}")
    print(f"   error={resp.get('error')} count={resp.get('count')} path={rt.get('path_taken') or rt.get('universe_establisher')} "
          f"timing_ms={rt.get('timing_ms')}")
    for it in res[:6]:
        print(f"     - {str(it.get('vertical')):7} {it.get('entity_id'):>14}  {str(it.get('name'))[:42]}")
    return res

# H1 — franchise (graph establish): Final Fantasy
resp, rt = ask("Final Fantasy games"); r1 = show("H1 franchise", "Final Fantasy games", resp, rt)
assert resp.get("error") is None and (resp.get("count") or 0) > 0, "H1 failed"

# H3 — negation, RUN TWICE (extraction varies — the G38 lesson): games but not horror → expect 0 horror
for run in (1, 2):
    resp, rt = ask("games but not horror"); show(f"H3 negation run{run}", "games but not horror", resp, rt)
    assert resp.get("error") is None and (resp.get("count") or 0) > 0, f"H3 run{run} failed"
print("   ↳ MANUALLY VERIFY: 0 horror titles in BOTH runs (response carries no genre — eyeball names/ids).")

# H5 — recency: new sci-fi movies (see the recency caveat in the header)
resp, rt = ask("new sci-fi movies"); show("H5 recency", "new sci-fi movies", resp, rt)
assert resp.get("error") is None, "H5 errored"
print("   ↳ VERIFY recency filtered (recent only). If all-eras appear → entities_vs lacks release_date_ts (rebuild index from new parquet).")

# H9 — gibberish → no_signal fallback (low confidence, not junk/empty)
resp, rt = ask("asdfghjkl qwerty zxcvb"); show("H9 gibberish", "asdfghjkl qwerty zxcvb", resp, rt)
print(f"   ↳ expect no_signal_fallback / low-confidence (path={rt.get('path_taken')}).")

# H10 — over-constrained → graceful relaxation (keeps vertical + negation, result_type=relaxed)
resp, rt = ask("cozy non-violent farming roguelike horror games from 2027"); show("H10 overconstrain", "…2027 over-constrained", resp, rt)
assert resp.get("error") is None, "H10 errored"

print("\nSMOKE BATTERY DONE — review H3 (0 horror ×2) and H5 (recency window) manually per REVIEW_CHECKLIST.")
