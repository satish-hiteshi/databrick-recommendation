# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy — Onboarding Adaptive-Rec (UC6) — adaptive_rec engine
# MAGIC **Self-configuring · job-runnable.** Registers the adaptive-rec model (engine `src/{api,data,store}.py`
# MAGIC + Qwen parquet), **creates OR updates** the endpoint, waits for READY, smoke-tests.
# MAGIC
# MAGIC SELF-CONTAINED at serve time — **no graph, no Qwen endpoint at request time**:
# MAGIC   • embeddings ← the staged Qwen 44k parquet (`data.py` parquet path; no local Postgres),
# MAGIC   • signals    ← Silver `adaptive_property_{centrality,popularity,proximity}` via the SQL warehouse
# MAGIC     (`ADAPTIVE_DATA_SOURCE=live`) — built by `precompute/precompute_adaptive_signals.py` (this bundle),
# MAGIC   • session    ← in-memory (`ADAPTIVE_PG=0`; the client passes `exclude_ids` to dedup across calls).
# MAGIC
# MAGIC Prereqs: run `precompute_adaptive_signals.py` FIRST (builds the 3 Silver signal tables); the Qwen
# MAGIC parquet on a Volume; a SQL warehouse; the secret scope holds `databricks_token` (+ `grafana_otlp_headers`
# MAGIC if OTLP). **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated.

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (adaptive_rec bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — a Job can override via base_parameters) =====================
_defaults = {
    "catalog":        "stg_feeds_silver",
    "schema":         "ml",
    "endpoint":       "onboarding-adaptive-staging",  # client copy defaults to onboarding-adaptive-staging-v2
    "scope":          "feedsai_staging",              # secret scope (databricks_token, grafana_otlp_headers)
    "emb_parquet":    "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet",
    "warehouse_http": "/sql/1.0/warehouses/321252e45d03563e",   # SQL warehouse HTTP path (Silver signal reads)
    "silver_catalog": "stg_feeds_silver",             # ADAPTIVE_SILVER_CATALOG (the 3 precompute tables)
    "workload_size":  "Small",
    "test_followed":  "",                             # comma-sep property_ids (>=2, with embeddings) for the smoke test
    "test_threshold": "0.5",
    # ── observability (OTLP → Grafana Cloud) ──
    "otel_service":   "onboarding-adaptive",
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
# ===================== 2. REGISTER (adaptive-rec engine + Qwen parquet → UC model) =====================
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
ENV = {
    # signals: Silver via the SQL warehouse (databricks-sql-connector) — loaded once at warm-up
    "ADAPTIVE_DATA_SOURCE": "live",
    "ADAPTIVE_SILVER_CATALOG": C["silver_catalog"], "ADAPTIVE_SILVER_SCHEMA": C["schema"],
    "ADAPTIVE_PG": "0",                               # in-memory session (no local Postgres in serving)
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": C["warehouse_http"],
    # embeddings: ADAPTIVE_PARQUET is auto-set by model._bootstrap to the staged parquet (no env needed)
}
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["OTEL_EXPORTER_OTLP_HEADERS"]  = sec(C["otel_secret"])   # whole-value ref; secret holds the full header
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="adaptive_rec", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="adaptive_rec", traffic_percentage=100)])
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
# ===================== 4. SMOKE TEST — an onboarding session (>=2 follows) =====================
import requests
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"
followed = [int(x) for x in C["test_followed"].replace(" ", "").split(",") if x.strip().isdigit()]
rec = {"session_id": "smoke", "followed_property_ids": followed,
       "confidence_threshold": float(C["test_threshold"]), "debug": True}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json={"dataframe_records": [rec]}, timeout=300)
r.raise_for_status()
pred = r.json()["predictions"][0]
ctx = pred.get("context", {}) or {}
sug = pred.get("suggestion")
print("followed:", followed, "| error:", pred.get("error"))
print("context:", ctx)
if sug:
    print(f"  suggestion: {sug.get('name')} [{sug.get('vertical')}]  score={sug.get('score')}  — {sug.get('why_string')}")
else:
    print("  suggestion: null (threshold not met / <2 follows / no embeddings for the followed set)")
if pred.get("error"):
    print("NOTE error:", pred)
assert pred.get("error") is None, f"smoke test failed: {pred}"
print("SMOKE OK ✓  (for a real suggestion, set test_followed to >=2 property_ids that exist in the parquet)")
