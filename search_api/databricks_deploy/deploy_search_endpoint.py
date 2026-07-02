# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 4 — Search (UC4 in-app + UC7 onboarding thematic) — E4 engine
# MAGIC **Self-configuring · job-runnable.** Registers the E4 model (search_api engine + vendored E3/E2 +
# MAGIC Qwen parquet), **creates OR updates** the endpoint, waits for READY, smoke-tests.
# MAGIC
# MAGIC E4 is SELF-CONTAINED at serve time — no E1/E2/E3 HTTP substrate:
# MAGIC   • **bridge**   ← the Aura **`:Entity`** graph (property_id<->entity_id, neo4j+s bolt) — READ-ONLY,
# MAGIC   • **store**    ← Silver `search_property_popularity` (+ optional `search_entity_centrality`) via the
# MAGIC     SQL warehouse (`SEARCH_DATA_SOURCE=live`) — built by `precompute_search_tables.py` (this bundle),
# MAGIC   • **thematic** ← the Qwen doc-vector parquet (auto-staged; `SEARCH_VECTOR_PARQUET` set by the pyfunc),
# MAGIC   • **embed**    ← the Qwen query-embed serving endpoint (`QWEN_EMBED_ENDPOINT`),
# MAGIC   • **follows**  ← Silver `public_property_followers` (`exclude_followed`; degrades to no-exclusion).
# MAGIC
# MAGIC Prereqs: run `precompute_search_tables.py` FIRST (builds `search_property_popularity`); the Qwen parquet
# MAGIC on a Volume; a SQL warehouse; an **Aura graph with `:Entity {property_id, entity_id}`** (the 44k bridge —
# MAGIC the E1/E2 graph); a **Qwen embed serving endpoint**; the secret scope holds `databricks_token`,
# MAGIC `neo4j_password` (+ `grafana_otlp_headers` if OTLP). **Do NOT `%pip install mlflow`** — runtime MLflow is integrated.

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (search bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — a Job can override via base_parameters) =====================
_defaults = {
    "catalog":        "stg_feeds_silver",
    "schema":         "ml",
    "endpoint":       "search-staging",               # client copy defaults to search-staging-v2
    "scope":          "feedsai_staging",              # secret scope (databricks_token, neo4j_password, grafana_otlp_headers)
    "emb_parquet":    "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet",
    "warehouse_http": "/sql/1.0/warehouses/321252e45d03563e",   # SQL warehouse HTTP path (Silver store + follows)
    "silver_catalog": "stg_feeds_silver",             # SEARCH_SILVER_CATALOG (precompute tables + public_property_followers)
    "neo4j_uri":      "neo4j+s://17aa0e8d.databases.neo4j.io",   # MUST be the 44k :Entity bridge graph (property_id/entity_id)
    "qwen_endpoint":  "databricks-qwen3-embedding-0-6b",  # Qwen query-embed serving endpoint NAME (same one parrot uses; URL built below)
    "workload_size":  "Small",
    "test_query":     "elden ring",                   # a name-mode smoke query (should hit the name index)
    # ── observability (OTLP → Grafana Cloud) ──
    "otel_service":   "search",
    "enable_otel":    "1",                            # "1" → push telemetry (needs grafana_otlp_headers secret)
    "otel_endpoint":  "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":    "grafana_otlp_headers",         # secret holds the FULL header: Authorization=Basic%20<base64>
    "otel_sampler":   "0.15",
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"])

# COMMAND ----------
# ===================== 2. REGISTER (E4 engine + vendored E3/E2 + Qwen parquet → UC model) =====================
import mlflow, sys, importlib
mlflow.set_registry_uri("databricks-uc")
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = C["emb_parquet"]
sys.modules.pop("register", None)
sys.path.insert(0, SERVING)
import register; importlib.reload(register)
register.main()
from mlflow.tracking import MlflowClient
ver = str(max(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))
print("registered version:", ver)

# COMMAND ----------
# ===================== 3. CREATE-OR-UPDATE the endpoint (env) + WAIT FOR READY =====================
from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (EndpointCoreConfigInput, ServedEntityInput, TrafficConfig, Route)
wc = WorkspaceClient()

def sec(k): return "{{" + f"secrets/{C['scope']}/{k}" + "}}"
QWEN_URL = f"{HOST}/serving-endpoints/{C['qwen_endpoint']}/invocations"
ENV = {
    # store + follows: Silver via the SQL warehouse (databricks-sql-connector)
    "SEARCH_DATA_SOURCE": "live",
    "SEARCH_SILVER_CATALOG": C["silver_catalog"], "SEARCH_SILVER_SCHEMA": C["schema"],
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": C["warehouse_http"],
    # bridge: the Aura :Entity graph (bolt) — property_id<->entity_id
    "NEO4J_URI": C["neo4j_uri"], "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": sec("neo4j_password"), "NEO4J_DATABASE": "neo4j",
    # embed: the Qwen query-embed serving endpoint (reuses DATABRICKS_TOKEN for auth)
    "QWEN_EMBED_ENDPOINT": QWEN_URL,
    # thematic: SEARCH_VECTOR_PARQUET is auto-set by model._bootstrap to the staged parquet (no env needed)
}
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["OTEL_EXPORTER_OTLP_HEADERS"]  = sec(C["otel_secret"])   # whole-value ref; secret holds the full header
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="search", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="search", traffic_percentage=100)])
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
# ===================== 4. SMOKE TEST — a name-mode search =====================
import requests, json
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"
body = {"dataframe_records": [{"query": C["test_query"], "limit": 8, "debug": True}]}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json=body, timeout=300)
r.raise_for_status()
pred = r.json()["predictions"][0]
dbg = pred.get("debug", {}) or {}
results = pred.get("results", []) or []
print("query:", pred.get("query_echo"), "| mode_taken:", dbg.get("mode_taken"),
      "| result_count:", pred.get("result_count"), "| error:", pred.get("error"))
for it in results[:6]:
    print(f"  - {str(it.get('vertical')):7} {str(it.get('name'))[:42]:42} score={it.get('score')} "
          f"match={it.get('match_type')}")
if pred.get("error"):
    print("NOTE error:", pred)
assert pred.get("error") is None, f"smoke test failed: {pred}"
print("SMOKE OK ✓  (if result_count==0: confirm search_property_popularity is built, the Aura has :Entity "
      "nodes with property_id/entity_id, and the Qwen embed endpoint is reachable)")
