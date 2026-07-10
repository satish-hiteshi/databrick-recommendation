# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 3 — Home Feed (follow-gated, UC3) — NEW E3 engine
# MAGIC **Self-configuring · job-runnable.** Registers the E3 model (home_feed engine + minimal vendored E2
# MAGIC config/timeutil + Qwen parquet), **creates OR updates** the endpoint, waits for READY, smoke-tests.
# MAGIC
# MAGIC E3's main feed is SELF-CONTAINED: follows ← Silver `public_property_followers` (via SQL warehouse),
# MAGIC moments ← the **Aura moments graph** (`:Moment` / `HAS_MOMENT`, neo4j+s bolt), vectors ← the Qwen parquet.
# MAGIC No Vector Search, no E1/E2 HTTP substrate. Carousels are `[]` until `home_assembler` is implemented.
# MAGIC
# MAGIC Prereqs: the `embeddings.parquet` on a Volume; a SQL warehouse; an **Aura graph that
# MAGIC contains `:Moment` nodes + `HAS_MOMENT`** (E1/E2's graph is moment-less — point `neo4j_uri` at the moments
# MAGIC graph); the secret scope holds `databricks_token`, `neo4j_password` (+ `grafana_otlp_token` if OTLP).
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated.

# COMMAND ----------

# Cluster deps for REGISTRATION-TIME validation: after logging, MLflow loads the model IN-PROCESS on this
# job cluster, importing the engine (neo4j / databricks-sql / pyarrow / fastapi ...). The SERVING container
# installs from serving/requirements.txt — this cell only covers the job cluster (clean clusters lack these,
# so running this notebook failed with a missing-dependency error without it). mlflow deliberately NOT
# installed (runtime-integrated); anyio pinned <4 to avoid the jupyter-server resolver conflict.
# MAGIC %pip install -q "anyio<4" numpy pandas pyarrow neo4j databricks-sql-connector fastapi "pydantic>=2" opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

# COMMAND ----------
# GUARDED restart: in notebook JOBS a restart re-executes the whole notebook, so restart ONLY when a dep is
# actually missing (post-restart everything imports -> no-op; avoids double registration).
import importlib.util
if any(importlib.util.find_spec(m) is None for m in ("neo4j", "databricks.sql", "pyarrow", "fastapi")):
    dbutils.library.restartPython()

# COMMAND ----------

# ===================== 0. AUTO-DERIVE repo location + workspace host =====================
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
    "scope":          "feeds-default-scope",              # secret scope (databricks_token, neo4j_password, grafana_otlp_token)
    "emb_parquet":    "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet",
    "warehouse_http": "/sql/1.0/warehouses/321252e45d03563e",   # SQL warehouse HTTP path (Silver follows)
    "silver_catalog": "stg_feeds_silver",             # HOME_SILVER_CATALOG (public_property_followers)
    "neo4j_uri":      "neo4j+s://17aa0e8d.databases.neo4j.io",   # MUST be the MOMENTS graph (:Moment/HAS_MOMENT)
    "workload_size":  "Small",
    "test_user":      "13",                           # a user who FOLLOWS properties (else feed is empty)
    # ── observability (OTLP → Grafana Cloud) ──
    "otel_service":   "home-feed",
    "enable_otel":    "1",                            # "1" → push telemetry (needs grafana_otlp_token secret)
    "otel_endpoint":  "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":    "grafana_otlp_token",         # secret holds ONLY the base64 credential; header built in otel_setup
    "otel_sampler":   "0.15",
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"])

# COMMAND ----------
# ===================== 2. REGISTER (E3 engine + vendored E2 + Qwen parquet → UC model) =====================
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
    # follows: Silver via the SQL warehouse
    "HOME_SILVER_CATALOG": C["silver_catalog"],
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": C["warehouse_http"],
    # moments: the Aura moments graph (bolt)
    "NEO4J_URI": C["neo4j_uri"], "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": sec("neo4j_password"), "NEO4J_DATABASE": "neo4j",
    # vectors: HOME_VECTOR_PARQUET is auto-set by model._bootstrap to the staged parquet (no env needed)
}
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["GRAFANA_OTLP_TOKEN"]  = sec(C["otel_secret"])   # whole-value ref (credential only); header built in otel_setup
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
pred = r.json()["predictions"][0]
ctx = pred.get("context", {}) or {}
main = pred.get("main_feed", {}) or {}
items = main.get("items", []) or []
print("mode:", ctx.get("mode"), "| signal:", ctx.get("signal_strength"), "| follows:", ctx.get("follow_count"),
      "| error:", pred.get("error"))
print("main_feed items:", len(items), "| carousels:", len(pred.get("carousels", []) or []), "(carousels stubbed → 0)")
for it in items[:6]:
    print(f"  - {str(it.get('vertical')):7} {it.get('property_name')}: {str(it.get('title'))[:46]}")
if pred.get("error"):
    print("NOTE error:", pred)
assert pred.get("error") is None, f"smoke test failed: {pred}"
print("SMOKE OK ✓  (if items==0: pick a test_user who follows properties, and confirm the Aura graph has :Moment nodes)")
