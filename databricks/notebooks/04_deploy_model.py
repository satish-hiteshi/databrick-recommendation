# Databricks notebook source

# COMMAND ----------

%pip install voyageai rank-bm25 databricks-vectorsearch databricks-sql-connector mlflow --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import sys, os, json, time, requests
import mlflow

CATALOG       = "dev_feeds_silver_infotech"
SCHEMA        = "feedsai"
VS_ENDPOINT   = "feedsai-vs-endpoint"
ENDPOINT_NAME = "feedsai-discovery"
SECRET_SCOPE  = "feedsai-secrets"

REGISTERED_MODEL   = f"{CATALOG}.{SCHEMA}.feedsai_model"
ENTITIES_TABLE     = f"{CATALOG}.{SCHEMA}.entities"
VS_INDEX           = f"{ENTITIES_TABLE}_vs_index"
ENTITIES_META_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/artifacts/entities_meta.pkl"

_nb_path = (
    dbutils.notebook.entry_point
    .getDbutils().notebook().getContext()
    .notebookPath().get()
)
DATABRICKS_PKG = "/Workspace" + os.path.dirname(os.path.dirname(_nb_path))

for _mod in list(sys.modules.keys()):
    if _mod == "pipeline" or _mod.startswith("pipeline."):
        del sys.modules[_mod]

if DATABRICKS_PKG not in sys.path:
    sys.path.insert(0, DATABRICKS_PKG)

from pipeline.config import CATALOG as _check
print(f"CATALOG={_check}  |  DATABRICKS_PKG={DATABRICKS_PKG}")

# COMMAND ----------

# Store secrets — run this cell once, then skip on future runs
from databricks.sdk import WorkspaceClient as _WC
_w = _WC()

try:
    _w.secrets.create_scope(scope=SECRET_SCOPE)
except Exception:
    pass

_host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()

for _k, _v in {
    "VOYAGE_API_KEY":        "vk-...",                                   # fill in
    "DATABRICKS_HOST":       _host,
    "DATABRICKS_TOKEN":      "<LONG_LIVED_PAT>",                         # fill in
    "FEEDSAI_CATALOG":       CATALOG,
    "FEEDSAI_SCHEMA":        SCHEMA,
    "FEEDSAI_VS_ENDPOINT":   VS_ENDPOINT,
    "FEEDSAI_SQL_HTTP_PATH": "/sql/1.0/warehouses/<WAREHOUSE_ID>",       # fill in
}.items():
    _w.secrets.put_secret(scope=SECRET_SCOPE, key=_k, string_value=_v)
    print(f"  {_k}")

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Shared/feedsai-experiments")

import importlib, mlflow_model as _mm
importlib.reload(_mm)
from mlflow_model import FeedsAIModel
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import Schema, ColSpec

pipeline_pkg    = os.path.join(DATABRICKS_PKG, "pipeline")
mlflow_model_py = os.path.join(DATABRICKS_PKG, "mlflow_model.py")

signature = ModelSignature(
    inputs=Schema([ColSpec("string", "query")]),
    outputs=Schema([ColSpec("string", "result")]),
)

pip_deps = [
    "voyageai>=0.3", "rank-bm25>=0.2.2", "numpy>=1.24",
    "databricks-vectorsearch>=0.40", "databricks-sql-connector>=3.0",
    "pandas>=2.0",
]

with mlflow.start_run(run_name="feedsai-v1") as run:
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=FeedsAIModel(),
        artifacts={"entities_meta": ENTITIES_META_PATH},
        code_paths=[pipeline_pkg, mlflow_model_py],
        signature=signature,
        pip_requirements=pip_deps,
        registered_model_name=REGISTERED_MODEL,
    )
    run_id = run.info.run_id

print(f"run_id={run_id}  |  code_paths=[{pipeline_pkg}]")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedModelInput,
    ServedModelInputWorkloadSize,
)

w = WorkspaceClient()

versions = mlflow.MlflowClient().search_model_versions(f"name='{REGISTERED_MODEL}'")
latest_version = max(int(v.version) for v in versions)
print(f"Deploying {REGISTERED_MODEL} v{latest_version}")

env_vars = {
    k: dbutils.secrets.get(scope=SECRET_SCOPE, key=k)
    for k in [
        "VOYAGE_API_KEY", "DATABRICKS_HOST", "DATABRICKS_TOKEN",
        "FEEDSAI_CATALOG", "FEEDSAI_SCHEMA", "FEEDSAI_VS_ENDPOINT", "FEEDSAI_SQL_HTTP_PATH",
    ]
}

served_model = ServedModelInput(
    model_name=REGISTERED_MODEL,
    model_version=str(latest_version),
    workload_size=ServedModelInputWorkloadSize.SMALL,
    scale_to_zero_enabled=True,
    environment_vars=env_vars,
)

existing = [e.name for e in w.serving_endpoints.list()]
if ENDPOINT_NAME in existing:
    w.serving_endpoints.update_config(name=ENDPOINT_NAME, served_models=[served_model])
else:
    w.serving_endpoints.create(
        name=ENDPOINT_NAME,
        config=EndpointCoreConfigInput(served_models=[served_model])
    )
print(f"Endpoint '{ENDPOINT_NAME}' deploying...")

# COMMAND ----------

print("Waiting for endpoint...")
for _ in range(60):
    ep    = w.serving_endpoints.get(ENDPOINT_NAME)
    state = ep.state.config_update.value if ep.state else "UNKNOWN"
    print(f"  {state}")
    if state == "NOT_UPDATING":
        break
    time.sleep(10)

# COMMAND ----------

host  = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

response = requests.post(
    f"{host}/serving-endpoints/{ENDPOINT_NAME}/invocations",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"dataframe_records": [{"query": "Games like Elden Ring"}]},
)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    raw    = response.json()["predictions"][0]["result"]
    result = json.loads(raw)

    # Print full result first so any error is visible
    if result.get("error"):
        print(f"Pipeline error: {result['error']}")
    else:
        print(f"Query: {result.get('query')}  |  mode={result.get('query_mode')}  |  status={result.get('status')}")
        for r in result.get("results", [])[:5]:
            print(f"  {r.get('rank')}. {r.get('name')} [{r.get('vertical')}]  {r.get('final_score')}")
        for vert, items in result.get("results_by_vertical", {}).items():
            print(f"\n  {vert.upper()}")
            for r in items[:3]:
                print(f"    {r.get('rank')}. {r.get('name')}  {r.get('final_score')}")
else:
    print(f"HTTP {response.status_code}: {response.text}")
