# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 1 — Agent-Recs (collapsed parrot/router)
# MAGIC **Self-configuring · job-runnable.** Derives the repo path + workspace host at runtime, registers the
# MAGIC collapsed model (engines + Qwen parquet), **creates OR updates** the endpoint with the full env,
# MAGIC **waits for READY**, then smoke-tests. No cell edits needed — run by hand or as a Databricks Job
# MAGIC (override any value via job `base_parameters` / widgets).
# MAGIC
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated; reinstalling it breaks registration.

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
    "scope":         "feeds-default-scope",               # Databricks secret scope (neo4j_password, databricks_token)
    "parquet":       "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet",
    "vs_endpoint":   "feedsai-staging-vs",
    "vs_index":      "stg_feeds_silver.ml.entities_vs",
    "vector_backend": "qdrant",   # "qdrant" (in-memory from parquet) | "databricks" (Vector Search)
    "neo4j_uri":     "neo4j+s://17aa0e8d.databases.neo4j.io",
    "enable_graph": "1",         # "1" = graph refine via Aura | "0" = vector-only
    "llm_endpoint":  "llama_v3_3_70b_instruct",       # LLM serving-endpoint NAME (URL built from HOST)
    "qwen_embed":    "databricks-qwen3-embedding-0-6b",
    "workload_size": "Medium",
    "enable_timing": "1",                             # "1" → TIMING_BREAKDOWN (source for per-stage latency)
    # ── observability (OTLP → Grafana Cloud, H1.6) ──
    "otel_service":  "agent-recs",                    # OTEL_SERVICE_NAME (discovery sets discovery-api)
    "enable_otel":   "1",                             # "1" → push telemetry (needs the grafana_otlp_token secret)
    "otel_endpoint": "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":   "grafana_otlp_token",            # secret holds ONLY the base64 credential; otel_setup builds the Authorization: Basic <token> header
    "otel_sampler":  "0.15",                          # fraction of requests traced (metrics stay 100%)
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"])

# COMMAND ----------
# ===================== 2. REGISTER (bundle engines + Qwen parquet → UC model) =====================
import mlflow, sys, importlib
mlflow.set_registry_uri("databricks-uc")             # runtime mlflow; do NOT pip-install it
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = C["parquet"]
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
    "LLM_PROVIDER": "databricks",
    "DATABRICKS_LLM_ENDPOINT": f"{HOST}/serving-endpoints/{C['llm_endpoint']}/invocations",
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "QUERY_EMBED_ENDPOINT": C["qwen_embed"],          # queries embed via Qwen (matches the corpus)
    "VECTOR_BACKEND": C["vector_backend"],            # switch: qdrant (default) | databricks
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

# ── reranker OFF (match local): local runs with no cross-encoder installed, so its "auto" no-ops.
# Env var (not a re-register): overrides the config.py default "auto". Set to "auto"/"learned"/"cross_encoder" to enable.
ENV["RERANK"] = "none"

# ── observability (H1.6): OTEL_SERVICE_NAME is always safe; the OTLP push is gated on enable_otel
# (the secret must exist in the scope, else the endpoint create fails on an unresolvable secret ref). ──
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["GRAFANA_OTLP_TOKEN"]  = sec(C["otel_secret"])   # whole-value secret ref (credential only); otel_setup builds Authorization: Basic <token>
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
# ===================== 4. SMOKE TEST (against the now-READY endpoint) =====================
import requests, json
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"
body = {"dataframe_records": [{"user_id": "13", "query": "cozy farming games like Stardew Valley",
                              "requesting_agent": "morgan"}]}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json=body, timeout=120)
r.raise_for_status()
inner = r.json()["predictions"][0]
resp = inner.get("response"); resp = resp if isinstance(resp, dict) else json.loads(resp)
rt = resp.get("router", {}) or {}
print("routed_to :", inner.get("routed_to"), "| count:", resp.get("count"), "| error:", resp.get("error"))
print("timing_ms :", rt.get("timing_ms"), "| breakdown:", rt.get("timing_breakdown"))
assert resp.get("error") is None and (resp.get("count") or 0) > 0, "smoke test failed"
print("SMOKE OK ✓")
