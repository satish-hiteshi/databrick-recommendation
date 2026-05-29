# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # 04 — Package & Deploy MLflow Model to Databricks Model Serving
# MAGIC
# MAGIC **Run order:**
# MAGIC 1. Cell 1: `%pip install` + `restartPython()` — installs deps and restarts kernel
# MAGIC 2. Cell 2: Config — defines all variables (must run after restart)
# MAGIC 3. Cell 3: Secrets — run **once** to store API keys (then skip on future runs)
# MAGIC 4. Cell 4 onwards: Log model → Deploy endpoint → Test

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 1 — Install dependencies & restart kernel

# COMMAND ----------

%pip install voyageai rank-bm25 databricks-vectorsearch databricks-sql-connector --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 2 — Configuration (runs after restart, all variables defined here)

# COMMAND ----------

import sys, os, json, time, requests
import mlflow

# ── CONFIGURE ────────────────────────────────────────────────────────
CATALOG       = "dev_feeds_silver_infotech"
SCHEMA        = "feedsai"
VS_ENDPOINT   = "feedsai-vs-endpoint"
ENDPOINT_NAME = "feedsai-discovery"
SECRET_SCOPE  = "feedsai-secrets"
# ─────────────────────────────────────────────────────────────────────

REGISTERED_MODEL   = f"{CATALOG}.{SCHEMA}.feedsai_model"
ENTITIES_TABLE     = f"{CATALOG}.{SCHEMA}.entities"
VS_INDEX           = f"{ENTITIES_TABLE}_vs_index"
ENTITIES_META_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/artifacts/entities_meta.pkl"

# notebookPath() returns workspace-relative path WITHOUT /Workspace prefix.
# Prepend /Workspace so it resolves on the Databricks filesystem.
_nb_path = (
    dbutils.notebook.entry_point
    .getDbutils().notebook().getContext()
    .notebookPath().get()
)
DATABRICKS_PKG = "/Workspace" + os.path.dirname(os.path.dirname(_nb_path))

# Evict any stale 'pipeline' module cached from the root pipeline/ dir
for _mod in list(sys.modules.keys()):
    if _mod == "pipeline" or _mod.startswith("pipeline."):
        del sys.modules[_mod]

if DATABRICKS_PKG not in sys.path:
    sys.path.insert(0, DATABRICKS_PKG)

print(f"DATABRICKS_PKG     = {DATABRICKS_PKG}")
print(f"REGISTERED_MODEL   = {REGISTERED_MODEL}")
print(f"ENTITIES_META_PATH = {ENTITIES_META_PATH}")

# Verify correct pipeline package is importable
from pipeline.config import CATALOG as _check
print(f"pipeline.config OK  (CATALOG={_check})")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 3 — Store secrets (run **once**, then skip)
# MAGIC
# MAGIC Fill in your values below and run this cell a single time.
# MAGIC `DATABRICKS_TOKEN` must be a **long-lived PAT** from:
# MAGIC Settings → Developer → Access tokens → Generate new token (365 days).

# COMMAND ----------

from databricks.sdk import WorkspaceClient as _WC
_w = _WC()

try:
    _w.secrets.create_scope(scope=SECRET_SCOPE)
    print(f"Scope '{SECRET_SCOPE}' created.")
except Exception as _e:
    print(f"Scope note: {_e}")

_host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()

_secrets = {
    "VOYAGE_API_KEY":        "vk-...",                                   # ← fill in
    "DATABRICKS_HOST":       _host,
    "DATABRICKS_TOKEN":      "<YOUR_LONG_LIVED_PAT>",                    # ← fill in
    "FEEDSAI_CATALOG":       CATALOG,
    "FEEDSAI_SCHEMA":        SCHEMA,
    "FEEDSAI_VS_ENDPOINT":   VS_ENDPOINT,
    "FEEDSAI_SQL_HTTP_PATH": "/sql/1.0/warehouses/<YOUR_WAREHOUSE_ID>",  # ← fill in
}

for _k, _v in _secrets.items():
    _w.secrets.put_secret(scope=SECRET_SCOPE, key=_k, string_value=_v)
    print(f"  Stored: {_k}")
print("All secrets stored.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Log model to MLflow & register in Unity Catalog

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Shared/feedsai-experiments")

from mlflow_model import log_model

run_id = log_model(
    entities_meta_path=ENTITIES_META_PATH,
    pipeline_src_dir=DATABRICKS_PKG,
    run_name="feedsai-v1",
    registered_model_name=REGISTERED_MODEL,
)
print(f"Run ID: {run_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Deploy to Model Serving

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedModelInput,
    ServedModelInputWorkloadSize,
)

w = WorkspaceClient()

# Get latest registered model version
client = mlflow.MlflowClient()
versions = client.search_model_versions(f"name='{REGISTERED_MODEL}'")
latest_version = max(int(v.version) for v in versions)
print(f"Deploying version {latest_version} of {REGISTERED_MODEL}")

# Read secrets to inject as env vars into the serving container
secret_keys = [
    "VOYAGE_API_KEY",
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "FEEDSAI_CATALOG",
    "FEEDSAI_SCHEMA",
    "FEEDSAI_VS_ENDPOINT",
    "FEEDSAI_SQL_HTTP_PATH",
]
env_vars = {k: dbutils.secrets.get(scope=SECRET_SCOPE, key=k) for k in secret_keys}

served_model = ServedModelInput(
    model_name=REGISTERED_MODEL,
    model_version=str(latest_version),
    workload_size=ServedModelInputWorkloadSize.SMALL,
    scale_to_zero_enabled=True,
    environment_vars=env_vars,
)

existing = [e.name for e in w.serving_endpoints.list()]
if ENDPOINT_NAME in existing:
    print(f"Updating endpoint '{ENDPOINT_NAME}' ...")
    w.serving_endpoints.update_config(name=ENDPOINT_NAME, served_models=[served_model])
else:
    print(f"Creating endpoint '{ENDPOINT_NAME}' ...")
    w.serving_endpoints.create(name=ENDPOINT_NAME, config=EndpointCoreConfigInput(served_models=[served_model]))

print(f"Endpoint '{ENDPOINT_NAME}' deploying — check Serving UI for status.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Test the live endpoint

# COMMAND ----------

print("Waiting for endpoint to become ready ...")
for _ in range(60):
    ep    = w.serving_endpoints.get(ENDPOINT_NAME)
    state = ep.state.config_update.value if ep.state else "UNKNOWN"
    print(f"  State: {state}")
    if state == "NOT_UPDATING":
        break
    time.sleep(10)

# COMMAND ----------

host  = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

url      = f"{host}/serving-endpoints/{ENDPOINT_NAME}/invocations"
headers  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
payload  = {"dataframe_records": [{"query": "Games like Elden Ring"}]}

response = requests.post(url, headers=headers, json=payload)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    result = json.loads(response.json()["predictions"][0]["result"])
    print(f"\nQuery:  {result['query']}")
    print(f"Mode:   {result['query_mode']}")
    print(f"Status: {result['status']}")
    for r in result.get("results", [])[:5]:
        print(f"  {r['rank']:>2}. {r['name']:<40} [{r['vertical']}]  score={r['final_score']}")
    for vert, items in result.get("results_by_vertical", {}).items():
        print(f"\n  [{vert.upper()}]")
        for r in items[:3]:
            print(f"    {r['rank']:>2}. {r['name']:<40}  score={r['final_score']}")
else:
    print(f"Error: {response.text}")
