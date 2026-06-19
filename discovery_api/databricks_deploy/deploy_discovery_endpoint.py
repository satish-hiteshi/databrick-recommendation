# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 2 — Discovery API
# MAGIC Registers the **collapsed discovery model** (E2 engine + E1's Qwen substrate + LiveDataSource) and
# MAGIC creates the **`discovery-api-staging`** serving endpoint, then smoke-tests a real user's feed.
# MAGIC
# MAGIC Prereqs: the repo is pulled; the Qwen parquet exists on the Volume; a SQL warehouse exists; the
# MAGIC `feedsai_staging` secret scope has `neo4j_password`, `voyage_api_key`, `databricks_token`.

# COMMAND ----------
# MAGIC %md
# MAGIC **Do NOT `%pip install mlflow`** — the Databricks runtime's MLflow is integrated; reinstalling it
# MAGIC breaks registration (circular-import errors, `log_model` returns None, no version created).
# MAGIC `mlflow` + `databricks-sdk` are already in the ML runtime. If `databricks-sdk` is somehow missing,
# MAGIC install ONLY it (`%pip install databricks-sdk` then `dbutils.library.restartPython()`).

# COMMAND ----------
# ===================== CONFIG — fill these in =====================
REPO        = "/Workspace/Users/satish.deshmukh@hiteshi.com/databrick-recommendation"   # the pulled repo
HOST        = "https://<staging-host>"                          # e.g. https://dbc-xxxx.cloud.databricks.com
CATALOG     = "stg_feeds_silver"
SCHEMA      = "ml"
SCOPE       = "feedsai_staging"
MODEL_NAME  = f"{CATALOG}.{SCHEMA}.discovery-api-staging"
ENDPOINT    = "discovery-api-staging"
PARQUET     = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen.parquet"  # the Qwen parquet (Phase 3)
VS_ENDPOINT = "feedsai-staging-vs"
VS_INDEX    = f"{CATALOG}.{SCHEMA}.entities_vs"
NEO4J_URI   = "neo4j+s://<your-aura>"
QWEN_EMBED  = "databricks-qwen3-embedding-0-6b"
WAREHOUSE_HTTP_PATH = "/sql/1.0/warehouses/<warehouse-id>"      # Warehouses → your WH → Connection details → HTTP path
print("config:", MODEL_NAME, "| endpoint:", ENDPOINT)

# COMMAND ----------
# ===================== 1. REGISTER the model =====================
import mlflow
mlflow.set_registry_uri("databricks-uc")     # init MLflow before register (runtime mlflow; do NOT pip-install it)
import os, sys, importlib
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = PARQUET
sys.path.insert(0, f"{REPO}/discovery_api/databricks_deploy/serving")
import register; importlib.reload(register)
register.main()      # bundles E2 engine + E1 collapsed substrate + Qwen parquet → new UC version

# verify a version was actually created (NOT just the success print)
from mlflow.tracking import MlflowClient
print("versions:", sorted(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))

# COMMAND ----------
# ===================== 2. CREATE the endpoint =====================
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (EndpointCoreConfigInput, ServedEntityInput, TrafficConfig, Route)
import mlflow
from mlflow.tracking import MlflowClient
mlflow.set_registry_uri("databricks-uc")
ver = str(max(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))
print("model version:", ver)

def sec(k): return "{{" + f"secrets/{SCOPE}/{k}" + "}}"
ENV = {
    # ── discovery engine (E2) ──
    "DISCOVERY_DATA_SOURCE": "live", "DISCOVERY_DEFAULT_ENGINE": "v2", "DISCOVERY_NOW_ISO": "",
    "DISCOVERY_CATALOG": CATALOG, "SUBSTRATE_MODE": "inprocess",
    # ── E1 collapsed substrate (the engines E2 reuses) ──
    "ROUTER_ENGINE_MODE": "inprocess", "VECTOR_BACKEND": "databricks",
    "ENTITY_BACKEND": "memory", "DATA_BACKEND": "parquet",
    "VS_ENDPOINT_NAME": VS_ENDPOINT, "VS_INDEX_NAME": VS_INDEX,
    "NEO4J_URI": NEO4J_URI, "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": sec("neo4j_password"), "NEO4J_DATABASE": "neo4j",
    "QUERY_EMBED_ENDPOINT": QWEN_EMBED,                 # query embeds via Qwen (matches the corpus)
    "VOYAGE_API_KEY": sec("voyage_api_key"),            # dormant import — keep so the module loads
    # ── auth + the SQL warehouse for LiveDataSource ──
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "DATABRICKS_HTTP_PATH": WAREHOUSE_HTTP_PATH,
}
WorkspaceClient().serving_endpoints.create(
    name=ENDPOINT,
    config=EndpointCoreConfigInput(
        served_entities=[ServedEntityInput(name="discovery", entity_name=MODEL_NAME, entity_version=ver,
            workload_size="Medium", scale_to_zero_enabled=False, environment_vars=ENV)],
        traffic_config=TrafficConfig(routes=[Route(served_model_name="discovery", traffic_percentage=100)])))
print(f"creating {ENDPOINT} v{ver} — watch Serving for Ready (~15 min: loads the Qwen parquet + Silver tables)")

# COMMAND ----------
# ===================== 3. SMOKE TEST — user 13 (a real game-follower) =====================
import requests
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{ENDPOINT}/invocations"
body = {"dataframe_records": [{"user_id": 13, "sort_order": "trending", "limit": 8, "debug": True}]}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json=body, timeout=300)
r.raise_for_status()
feed = r.json()["predictions"][0]
ctx = feed.get("context", {})
print("mode:", ctx.get("mode"), "| signal:", ctx.get("signal_strength"), "| path:", ctx.get("path"),
      "| error:", feed.get("error"))
print("main_feed count:", feed["main_feed"]["count"])
for it in feed["main_feed"]["items"][:8]:
    print(f"  - {str(it.get('vertical')):7} {it.get('property_name')}: {str(it.get('title'))[:48]}  "
          f"(why: {str(it.get('why_string',''))[:48]})")
print("carousels:", [(c["reason_string"], len(c["items"])) for c in feed.get("carousels", [])])

# COMMAND ----------
# MAGIC %md
# MAGIC **Expected:** `mode: personalized`, a non-empty `main_feed` with "Because you follow …" why-strings,
# MAGIC and cluster/trending/exploration carousels. A cold-start user (no follows) → `mode: cold_start` + a
# MAGIC global feed. If `error` is set, check the endpoint **Logs** (`[discovery] …`) — most likely the
# MAGIC warehouse HTTP path, a secret, or the Qwen/VS/Aura env.
