# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # 04 — Package & Deploy MLflow Model to Databricks Model Serving
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Notebooks 01–03 complete (Delta table populated, VS index online).
# MAGIC - Databricks Secrets configured (see "Secrets setup" cell below).
# MAGIC - `entities_meta.pkl` exists at the Volume path output by notebook 02.
# MAGIC
# MAGIC What this notebook does:
# MAGIC 1. Stores all required API keys / connection params in Databricks Secrets.
# MAGIC 2. Logs the FeedsAI pyfunc model to MLflow with `entities_meta.pkl` as an artifact.
# MAGIC 3. Registers the model in Unity Catalog.
# MAGIC 4. Creates a Model Serving endpoint backed by the registered model.
# MAGIC 5. Tests the live endpoint with a sample query.

# COMMAND ----------

# ── CONFIGURE ────────────────────────────────────────────────────────
CATALOG       = "dev_feeds_silver_infotech"
SCHEMA        = "feedsai"
VS_ENDPOINT   = "feedsai-vs-endpoint"

# MLflow / Unity Catalog model registration
REGISTERED_MODEL = f"{CATALOG}.{SCHEMA}.feedsai_model"
ENDPOINT_NAME    = "feedsai-discovery"

# Path to the pickle artifact built by notebook 02
ENTITIES_META_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/artifacts/entities_meta.pkl"

# Databricks Secret scope for API keys
SECRET_SCOPE = "feedsai-secrets"   # create via: databricks secrets create-scope <scope>
# ─────────────────────────────────────────────────────────────────────

ENTITIES_TABLE = f"{CATALOG}.{SCHEMA}.entities"
VS_INDEX       = f"{ENTITIES_TABLE}_vs_index"

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Create secret scope & store secrets
# MAGIC
# MAGIC **IMPORTANT:** `dbutils.secrets` is read-only — you cannot write secrets from a notebook.
# MAGIC Use the Databricks SDK cell below (run once), or the CLI:
# MAGIC ```
# MAGIC databricks secrets create-scope feedsai-secrets
# MAGIC databricks secrets put-secret feedsai-secrets VOYAGE_API_KEY
# MAGIC ```
# MAGIC
# MAGIC For `DATABRICKS_TOKEN`: use a **long-lived Personal Access Token** (PAT) from
# MAGIC your Databricks profile → Settings → Developer → Access tokens → Generate new token.
# MAGIC Do NOT use the notebook context token — it is short-lived and will expire.

# COMMAND ----------

# ── Run this cell once to create the scope and store all secrets ──────
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create scope (skip if it already exists)
try:
    w.secrets.create_scope(scope=SECRET_SCOPE)
    print(f"Scope '{SECRET_SCOPE}' created.")
except Exception as e:
    print(f"Scope note: {e}")

# ── Fill in your values before running ───────────────────────────────
host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()

secrets_to_store = {
    "VOYAGE_API_KEY":        "vk-...",                                   # ← fill in
    "DATABRICKS_HOST":       host,
    "DATABRICKS_TOKEN":      "<YOUR_LONG_LIVED_PAT>",                    # ← fill in (NOT notebook token)
    "FEEDSAI_CATALOG":       CATALOG,
    "FEEDSAI_SCHEMA":        SCHEMA,
    "FEEDSAI_VS_ENDPOINT":   VS_ENDPOINT,
    "FEEDSAI_SQL_HTTP_PATH": "/sql/1.0/warehouses/<YOUR_WAREHOUSE_ID>",  # ← fill in
}

for key, value in secrets_to_store.items():
    w.secrets.put_secret(scope=SECRET_SCOPE, key=key, string_value=value)
    print(f"  Stored: {key}")

print("All secrets stored.")

# COMMAND ----------

%pip install voyageai rank-bm25 databricks-vectorsearch databricks-sql-connector --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import sys, os
import mlflow

# notebookPath() returns the workspace-relative path WITHOUT the /Workspace prefix.
# e.g.  /Users/you@company.com/repo/databricks/notebooks/04_deploy_model
# Filesystem path on Databricks always starts with /Workspace, so we prepend it.
_nb_path = (
    dbutils.notebook.entry_point
    .getDbutils().notebook().getContext()
    .notebookPath().get()
)
DATABRICKS_PKG = "/Workspace" + os.path.dirname(os.path.dirname(_nb_path))
# e.g. /Workspace/Users/you@company.com/repo/databricks

# Remove any stale 'pipeline' cached from the root pipeline/ directory,
# then insert our databricks/pipeline/ at the front of sys.path.
for mod in list(sys.modules.keys()):
    if mod == "pipeline" or mod.startswith("pipeline."):
        del sys.modules[mod]

if DATABRICKS_PKG not in sys.path:
    sys.path.insert(0, DATABRICKS_PKG)

print(f"DATABRICKS_PKG = {DATABRICKS_PKG}")
print(f"sys.path[0]    = {sys.path[0]}")

# COMMAND ----------

# Verify the pipeline package is importable before logging the model
try:
    from pipeline.config import CATALOG as _CAT
    print(f"pipeline.config imported OK  (CATALOG={_CAT})")
except ImportError as e:
    raise RuntimeError(
        f"Cannot import pipeline package from {DATABRICKS_PKG}. "
        f"Make sure the notebook is running from within a Databricks Repo. Error: {e}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Log model to MLflow

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Shared/feedsai-experiments")

# Import log_model from the databricks/ directory
from mlflow_model import log_model   # databricks/mlflow_model.py

run_id = log_model(
    entities_meta_path=ENTITIES_META_PATH,
    pipeline_src_dir=DATABRICKS_PKG,   # bundles databricks/ into the model
    run_name="feedsai-v1",
    registered_model_name=REGISTERED_MODEL,
)
print(f"Run ID: {run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Deploy to Model Serving

# COMMAND ----------

import requests

# Get the latest model version
client = mlflow.MlflowClient()
versions = client.search_model_versions(f"name='{REGISTERED_MODEL}'")
latest_version = max(int(v.version) for v in versions)
print(f"Deploying version {latest_version} of {REGISTERED_MODEL}")

# COMMAND ----------

# Read secrets and inject them as env vars into the serving endpoint container.
secret_keys = [
    "VOYAGE_API_KEY",        # Voyage AI — only external dependency
    "DATABRICKS_HOST",       # workspace URL (e.g. https://adb-xxx.azuredatabricks.net)
    "DATABRICKS_TOKEN",      # must be a long-lived PAT — NOT the notebook session token
    "FEEDSAI_CATALOG",
    "FEEDSAI_SCHEMA",
    "FEEDSAI_VS_ENDPOINT",
    "FEEDSAI_SQL_HTTP_PATH",
    # Llama 3.3 70B (NLU) runs on Databricks FMAPI — no external key needed
]

env_vars_for_endpoint = [
    {
        "name":  key,
        "value": dbutils.secrets.get(scope=SECRET_SCOPE, key=key),
    }
    for key in secret_keys
]

# COMMAND ----------

# Use Databricks SDK to create / update the serving endpoint
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedModelInput,
    ServedModelInputWorkloadSize,
)

w = WorkspaceClient()

served_model = ServedModelInput(
    model_name=REGISTERED_MODEL,
    model_version=str(latest_version),
    workload_size=ServedModelInputWorkloadSize.SMALL,
    scale_to_zero_enabled=True,
    environment_vars={kv["name"]: kv["value"] for kv in env_vars_for_endpoint},
)

config = EndpointCoreConfigInput(served_models=[served_model])

existing = [e.name for e in w.serving_endpoints.list()]
if ENDPOINT_NAME in existing:
    print(f"Updating endpoint '{ENDPOINT_NAME}' ...")
    w.serving_endpoints.update_config(name=ENDPOINT_NAME, served_models=[served_model])
else:
    print(f"Creating endpoint '{ENDPOINT_NAME}' ...")
    w.serving_endpoints.create(name=ENDPOINT_NAME, config=config)

print(f"Endpoint '{ENDPOINT_NAME}' deploying — check the Serving UI for status.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Test the live endpoint

# COMMAND ----------

import time, json

# Wait for endpoint to be ready (up to 10 min)
print("Waiting for endpoint to become READY ...")
for _ in range(60):
    ep = w.serving_endpoints.get(ENDPOINT_NAME)
    state = ep.state.config_update.value if ep.state else "UNKNOWN"
    print(f"  State: {state}")
    if state in ("NOT_UPDATING", "IN_PROGRESS"):
        if state == "NOT_UPDATING":
            break
    time.sleep(10)

# COMMAND ----------

# Send a test request
host  = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

url     = f"{host}/serving-endpoints/{ENDPOINT_NAME}/invocations"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
payload = {"dataframe_records": [{"query": "Games like Elden Ring"}]}

response = requests.post(url, headers=headers, json=payload)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    # The result column contains a JSON string; parse it
    result_json = data["predictions"][0]["result"]
    result      = json.loads(result_json)
    print(f"\nQuery:  {result['query']}")
    print(f"Mode:   {result['query_mode']}")
    print(f"Status: {result['status']}")
    print(f"\nTop results:")
    for r in result.get("results", [])[:5]:
        print(f"  {r['rank']:>2}. {r['name']:<40} [{r['vertical']}]  score={r['final_score']}")
    for vert, items in result.get("results_by_vertical", {}).items():
        print(f"\n  [{vert.upper()}]")
        for r in items[:3]:
            print(f"    {r['rank']:>2}. {r['name']:<40}  score={r['final_score']}")
else:
    print(f"Error: {response.text}")
