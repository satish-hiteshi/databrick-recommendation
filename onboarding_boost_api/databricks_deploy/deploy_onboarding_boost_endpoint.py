# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy — UC8 Onboarding Boost — boost engine
# MAGIC **Self-configuring · job-runnable.** Registers the boost model (engine `src/{data,gaps,vector_store}.py`
# MAGIC + Qwen parquet), **creates OR updates** the endpoint, waits for READY, smoke-tests a boost.
# MAGIC
# MAGIC SELF-CONTAINED at serve time — **no graph, no Qwen endpoint at request time**:
# MAGIC   • embeddings ← the staged Qwen parquet (`data.py` memory backend; no local Postgres),
# MAGIC   • signals    ← Silver via the SQL warehouse (`BOOST_DATA_SOURCE=live`): popularity/centrality/
# MAGIC     proximity reuse UC6 `adaptive_property_*`; the moment gate reads `boost_property_moments`
# MAGIC     (built by `precompute/precompute_moments.py` in this bundle),
# MAGIC   • follows    ← stateless (the app writes; /confirm just validates + echoes accepted ids).
# MAGIC
# MAGIC Prereqs: run `precompute/precompute_moments.py` FIRST (builds `boost_property_moments`); UC6's
# MAGIC `adaptive_property_*` present; the Qwen parquet on a Volume; a SQL warehouse; the secret scope holds
# MAGIC `databricks_token`. **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated.

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (onboarding_boost bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — staging-hardcoded; a Job can override via base_parameters) =====================
_defaults = {
    "catalog":        "stg_feeds_silver",
    "schema":         "ml",
    "endpoint":       "onboarding-boost-staging",
    "scope":          "feeds-default-scope",
    "emb_parquet":    "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet",
    "warehouse_http": "/sql/1.0/warehouses/321252e45d03563e",   # SQL warehouse HTTP path (Silver signal reads)
    "silver_catalog": "stg_feeds_silver",  # BOOST_SILVER_CATALOG (adaptive_property_* + boost_property_moments)
    "workload_size":  "Small",
    "test_followed":  "",                  # comma-sep EXTERNAL property_ids (in the parquet) for the smoke test
    # ── observability (OTLP → Grafana Cloud) ──
    "otel_service":   "onboarding-boost-v1",
    "enable_otel":    "1",
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
# ===================== 2. REGISTER (boost engine + Qwen parquet → UC model) =====================
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
    "BOOST_DATA_SOURCE": "live",                      # signals: Silver via the SQL warehouse (loaded at warm-up)
    "BOOST_SILVER_CATALOG": C["silver_catalog"], "BOOST_SILVER_SCHEMA": C["schema"],
    "BOOST_VECTOR_BACKEND": "memory",                 # in-RAM embeddings from the parquet (no Qdrant)
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": C["warehouse_http"],
    # embeddings: BOOST_PARQUET is auto-set by model._bootstrap to the staged parquet (no env needed)
}
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["GRAFANA_OTLP_TOKEN"]  = sec(C["otel_secret"])
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="onboarding_boost", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="onboarding_boost", traffic_percentage=100)])
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
# ===================== 4. SMOKE TEST — an onboarding boost from a seed set =====================
import requests
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"
followed = [int(x) for x in C["test_followed"].replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()]
rec = {"op": "boost", "session_id": "smoke", "user_id": 1,
       "followed_property_ids": followed, "id_space": "external", "debug": True}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json={"dataframe_records": [rec]}, timeout=300)
r.raise_for_status()
pred = r.json()["predictions"][0]
ctx = pred.get("context", {}) or {}
groups = pred.get("boost_payload", []) or []
n_props = sum(len(g.get("properties", [])) for g in groups)
print("followed:", followed, "| error:", pred.get("error") or pred.get("detail"))
print("context:", ctx)
print(f"boost_payload: {len(groups)} vertical group(s), {n_props} propert(y/ies)")
for g in groups[:4]:
    ps = g.get("properties", [])
    print(f"  [{g.get('vertical')}] {len(ps)} — " + ", ".join(str(p.get('name')) for p in ps[:4]))
assert not pred.get("error"), f"smoke test failed: {pred}"
print("SMOKE OK ✓  (for a real boost, set test_followed to EXTERNAL property_ids present in the parquet, "
      "spanning 1–2 verticals so gaps exist to fill)")
