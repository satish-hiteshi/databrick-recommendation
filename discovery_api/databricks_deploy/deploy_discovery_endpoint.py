# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 2 — Discovery API (collapsed discovery feed)
# MAGIC **Self-configuring · job-runnable.** Derives the repo path + workspace host at runtime, registers the
# MAGIC collapsed model (E2 engine + E1 substrate + Qwen parquet), **creates OR updates** the endpoint with the
# MAGIC full env, **waits for READY**, then smoke-tests a real user's feed. No cell edits needed — run by hand
# MAGIC or as a Databricks Job (override any value via job `base_parameters` / widgets).
# MAGIC
# MAGIC Prereqs: the Qwen parquet on the Volume; a SQL warehouse (for LiveDataSource); the secret scope holds
# MAGIC `neo4j_password`, `databricks_token`.
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated; reinstalling it breaks registration.

# COMMAND ----------
# Cluster deps for REGISTRATION-TIME validation: after logging, MLflow loads the model IN-PROCESS on this
# job cluster, importing the engine (router config -> dotenv, neo4j, qdrant, bm25, otel...). The
# SERVING container installs from requirements.txt — this cell only covers the job cluster (dev clusters
# are clean; staging happened to have these preinstalled). mlflow deliberately NOT touched (runtime-
# integrated); torch/sentence-transformers avoided via RERANK=none during registration (see step 2).
# MAGIC %pip install -q "anyio<4" python-dotenv neo4j graphdatascience qdrant-client psycopg2-binary httpx pydantic rank-bm25 tqdm pyarrow opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

# COMMAND ----------
# GUARDED restart: in notebook JOBS a restart re-executes the whole notebook, so an unconditional
# restart runs everything twice (observed: two model versions registered per run). Only restart when a
# dep is actually missing — on the post-restart pass everything imports, so this becomes a no-op.
import importlib.util
if any(importlib.util.find_spec(m) is None
       for m in ("dotenv", "neo4j", "graphdatascience", "qdrant_client", "rank_bm25")):
    dbutils.library.restartPython()

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host (no hardcoding) =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (discovery bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — a Job can override via base_parameters) =====================
_defaults = {
    "catalog":        "stg_feeds_silver",
    "schema":         "ml",
    "endpoint":       "discovery-api-staging",        # client copy defaults to discovery-api-staging-v2
    "scope":          "feeds-default-scope",              # secret scope (neo4j_password, databricks_token)
    "parquet":        "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet",
    "vs_endpoint":    "feedsai-staging-vs",
    "vs_index":       "stg_feeds_silver.ml.entities_vs",
    "vector_backend": "qdrant",   # "qdrant" (in-memory from parquet) | "databricks" (Vector Search)
    "neo4j_uri":      "neo4j+s://17aa0e8d.databases.neo4j.io",
    "enable_graph": "1",         # "1" = graph refine via Aura | "0" = vector-only
    "qwen_embed":     "databricks-qwen3-embedding-0-6b",
    "warehouse_http": "/sql/1.0/warehouses/321252e45d03563e",   # SQL warehouse HTTP path (LiveDataSource reads)
    "workload_size":  "Medium",
    "enable_timing":  "1",                            # "1" → TIMING_BREAKDOWN (source for per-stage latency)
    # ── observability (OTLP → Grafana Cloud, H1.6) ──
    "otel_service":   "discovery-api",                # OTEL_SERVICE_NAME
    "enable_otel":    "1",                            # "1" → push telemetry (needs the grafana_otlp_token secret)
    "otel_endpoint":  "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":    "grafana_otlp_token",           # secret holds ONLY the base64 credential; otel_setup builds the Authorization: Basic <token> header
    "otel_sampler":   "0.15",                         # fraction of requests traced (metrics stay 100%)
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"])

# COMMAND ----------
# ===================== 2. REGISTER (E2 engine + E1 substrate + Qwen parquet → UC model) =====================
import mlflow, sys, importlib
mlflow.set_registry_uri("databricks-uc")             # runtime mlflow; do NOT pip-install it
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = C["parquet"]
os.environ["RERANK"] = "none"    # registration-time: keep the cross-encoder path (torch, 2GB+) out of validation
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
    # discovery engine (E2)
    "DISCOVERY_DATA_SOURCE": "live", "DISCOVERY_DEFAULT_ENGINE": "v2", "DISCOVERY_NOW_ISO": "",
    "DISCOVERY_CATALOG": C["catalog"], "SUBSTRATE_MODE": "inprocess",
    # E1 collapsed substrate (engines E2 reuses)
    "ROUTER_ENGINE_MODE": "inprocess", "VECTOR_BACKEND": C["vector_backend"], "RERANK": "none",
    "ENTITY_BACKEND": "memory", "DATA_BACKEND": "parquet",
    "QUERY_EMBED_ENDPOINT": C["qwen_embed"],
    # auth + SQL warehouse for LiveDataSource
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": C["warehouse_http"],
}
# ── vector switch: Databricks VS needs the endpoint/index; qdrant (default) needs neither ──
if C["vector_backend"] == "databricks":
    ENV["VS_ENDPOINT_NAME"] = C["vs_endpoint"]
    ENV["VS_INDEX_NAME"]    = C["vs_index"]
# ── graph switch: "1" wires this env's Aura; "0" -> router degrades to vector-only ──
if C["enable_graph"] == "1":
    ENV["NEO4J_URI"]      = C["neo4j_uri"]
    ENV["NEO4J_USER"]     = "neo4j"
    ENV["NEO4J_PASSWORD"] = sec("neo4j_password")
    ENV["NEO4J_DATABASE"] = "neo4j"
if C["enable_timing"] == "1":
    ENV["TIMING_BREAKDOWN"] = "1"

# ── observability (H1.6): OTEL_SERVICE_NAME is always safe; the OTLP push is gated on enable_otel
# (the secret must exist in the scope, else the endpoint create fails on an unresolvable secret ref). ──
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["GRAFANA_OTLP_TOKEN"]  = sec(C["otel_secret"])   # whole-value secret ref (credential only); otel_setup builds Authorization: Basic <token>
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="discovery", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="discovery", traffic_percentage=100)])
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
# ===================== 4. SMOKE TEST — user 13 (a real game-follower) =====================
import requests, json
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"
body = {"dataframe_records": [{"user_id": 13, "limit": 8, "debug": True}]}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json=body, timeout=300)
r.raise_for_status()
feed = r.json()["predictions"][0]
ctx = feed.get("context", {}) or {}
print("mode:", ctx.get("mode"), "| signal:", ctx.get("signal_strength"), "| error:", feed.get("error"))
print("main_feed count:", feed["main_feed"]["count"], "| carousels:", len(feed.get("carousels", [])))
for it in feed["main_feed"]["items"][:6]:
    print(f"  - {str(it.get('vertical')):7} {it.get('property_name')}: {str(it.get('title'))[:46]}")
assert feed.get("error") is None and feed["main_feed"]["count"] > 0, "smoke test failed"
print("SMOKE OK ✓")
