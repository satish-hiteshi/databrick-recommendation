# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 3 — Home Feed (follow-gated, UC3)
# MAGIC **Self-configuring · job-runnable.** Derives the repo path + workspace host at runtime, registers the
# MAGIC model (local home-feed engine + discovery engine + 57k embeddings npy), **creates OR updates** the
# MAGIC endpoint with the env, **waits for READY**, then smoke-tests a real follower's feed. No cell edits needed.
# MAGIC
# MAGIC The home feed is SELF-CONTAINED: it ranks over PRECOMPUTED embeddings (no query-time embed) and reads the
# MAGIC Silver lakehouse via a SQL warehouse (`HOME_DATA_SOURCE=live`). So — unlike E2 — it needs **no** Vector
# MAGIC Search / Neo4j / Qwen endpoint. Prereqs: E1's `embeddings_qwen_44k_prefixed.parquet` on a Volume
# MAGIC (REUSED — guid-keyed, bridged to property_id); a SQL warehouse; the scope holds `databricks_token`
# MAGIC (+ `grafana_otlp_token` if OTLP).
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated; reinstalling it breaks registration.

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host (no hardcoding) =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (home_feed bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — a Job can override via base_parameters) =====================
_defaults = {
    "catalog":        "stg_feeds_silver",
    "schema":         "ml",
    "endpoint":       "home-feed-staging",            # client copy defaults to home-feed-staging-v2
    "scope":          "feedsai_staging",              # secret scope (databricks_token, grafana_otlp_token)
    "emb_parquet":    "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet",
    "warehouse_http": "/sql/1.0/warehouses/321252e45d03563e",   # SQL warehouse HTTP path (live Silver reads)
    "silver_catalog": "stg_feeds_silver",             # HOME_SILVER_CATALOG (public_properties/moments/followers)
    "workload_size":  "Small",
    "test_user":      "13",                           # a user who FOLLOWS properties (else feed is empty)
    # ── observability (OTLP → Grafana Cloud, H1.6) ──
    "otel_service":   "home-feed",                    # OTEL_SERVICE_NAME
    "enable_otel":    "1",                            # "1" → push telemetry (needs the grafana_otlp_token secret)
    "otel_endpoint":  "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":    "grafana_otlp_token",
    "otel_sampler":   "0.15",
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"])

# COMMAND ----------
# ===================== 2. REGISTER (local home-feed + discovery engine + 57k npy → UC model) =====================
import mlflow, sys, importlib
mlflow.set_registry_uri("databricks-uc")             # runtime mlflow; do NOT pip-install it
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = C["emb_parquet"]
sys.modules.pop("register", None)                    # ensure THIS bundle's register is loaded
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
ENV = {
    # live data source: discovery/src/{data,store}.py read Silver via the SQL warehouse (no SparkSession)
    "HOME_DATA_SOURCE": "live",
    "HOME_SILVER_CATALOG": C["silver_catalog"],
    "DISCOVERY_PG": "0",                              # no Postgres in serving (follows from Silver)
    # auth + SQL warehouse for the live reads
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": C["warehouse_http"],
}
# ── observability (H1.6): OTEL_SERVICE_NAME is always safe; the OTLP push is gated on enable_otel. ──
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["OTEL_EXPORTER_OTLP_HEADERS"]  = "Authorization=Basic%20" + sec(C["otel_secret"])  # %20 = space
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="home_feed", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="home_feed", traffic_percentage=100)])
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
# ===================== 4. SMOKE TEST — a real follower's home feed =====================
import requests, json
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"
body = {"dataframe_records": [{"user_id": int(C["test_user"]), "limit": 8, "debug": True}]}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json=body, timeout=300)
r.raise_for_status()
feed = r.json()["predictions"][0]
ctx = feed.get("context", {}) or {}
main = feed.get("main_feed", {}) or {}
items = main.get("items", []) or []
print("mode:", ctx.get("mode"), "| signal:", ctx.get("signal_strength"), "| follows:", ctx.get("follow_count"),
      "| error:", feed.get("error"))
print("main_feed items:", len(items), "| carousels:", len(feed.get("carousels", []) or []))
for it in items[:6]:
    print(f"  - {str(it.get('vertical')):7} {it.get('property_name')}: {str(it.get('title'))[:46]}")
if feed.get("error"):
    print("NOTE error envelope:", feed)
assert feed.get("error") is None, f"smoke test failed: {feed}"
print("SMOKE OK ✓  (if items==0, pick a test_user who follows properties)")
