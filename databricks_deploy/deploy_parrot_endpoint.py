# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Endpoint 1 — Agent-Recs (parrot-api-staging)
# MAGIC Re-registers the collapsed parrot/router model (engines + Qwen parquet bundled) and points the
# MAGIC **`parrot-api-staging`** endpoint at the new version. **Reuses the endpoint's current env** (so the
# MAGIC LLM/VS/Neo4j/secret wiring carries over untouched) and optionally flips on `TIMING_BREAKDOWN` for the
# MAGIC per-stage latency report.
# MAGIC
# MAGIC Prereqs: repo pulled; the **Qwen** parquet on the Volume; the secret scope holds the keys.
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's is integrated; reinstalling it breaks registration.

# COMMAND ----------
# ===================== CONFIG =====================
REPO        = "/Workspace/Users/satish.deshmukh@hiteshi.com/databrick-recommendation"
HOST        = "https://<staging-host>"
MODEL_NAME  = "stg_feeds_silver.ml.parrot-api-staging"     # E1's staging UC model
ENDPOINT    = "parrot-api-staging"
PARQUET     = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen.parquet"   # Qwen (matches v3)
ENABLE_TIMING = True       # add TIMING_BREAKDOWN=1 so the latency probe gets the per-stage split
print("config:", MODEL_NAME, "| endpoint:", ENDPOINT, "| timing:", ENABLE_TIMING)

# COMMAND ----------
# ===================== 1. REGISTER =====================
import mlflow
mlflow.set_registry_uri("databricks-uc")     # runtime mlflow; do NOT pip-install it
import os, sys, importlib
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = PARQUET            # bundle the Qwen parquet (in-memory matrix)
sys.path.insert(0, f"{REPO}/databricks_deploy/serving")
import register; importlib.reload(register)
register.main()

from mlflow.tracking import MlflowClient
print("versions:", sorted(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))

# COMMAND ----------
# ===================== 2. POINT the endpoint at the new version (reuse live env) =====================
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (EndpointCoreConfigInput, ServedEntityInput, TrafficConfig, Route)
wc = WorkspaceClient()
ver = str(max(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))

existing = next((e for e in wc.serving_endpoints.list() if e.name == ENDPOINT), None)
if existing is None:
    raise RuntimeError(f"{ENDPOINT} doesn't exist — create it first (this notebook updates an existing E1 endpoint).")
se = wc.serving_endpoints.get(ENDPOINT).config.served_entities[0]
env = dict(se.environment_vars or {})                    # carry the live env over verbatim
print("=== carried-over env ===")
for k, v in env.items():
    print(f"  {k:24} = {v}")
assert env.get("QUERY_EMBED_ENDPOINT"), "env didn't carry over — inspect the endpoint before updating"
if ENABLE_TIMING:
    env["TIMING_BREAKDOWN"] = "1"                         # per-stage attribution in response.router.timing_breakdown

wc.serving_endpoints.update_config(
    name=ENDPOINT,
    served_entities=[ServedEntityInput(name=se.name, entity_name=MODEL_NAME, entity_version=ver,
        workload_size=se.workload_size or "Medium",
        scale_to_zero_enabled=bool(se.scale_to_zero_enabled), environment_vars=env)],
    traffic_config=TrafficConfig(routes=[Route(served_model_name=se.name, traffic_percentage=100)]))
print(f"\nupdating {ENDPOINT} → v{ver}  (timing={'on' if ENABLE_TIMING else 'off'}) — watch Serving for Ready")

# COMMAND ----------
# ===================== 3. SMOKE TEST =====================
import requests
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{ENDPOINT}/invocations"
body = {"dataframe_records": [{"user_id": "13", "query": "cozy farming games like Stardew Valley",
                              "requesting_agent": "morgan"}]}
r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                  json=body, timeout=120)
r.raise_for_status()
inner = r.json()["predictions"][0]
resp = inner.get("response"); resp = resp if isinstance(resp, dict) else __import__("json").loads(resp)
rt = resp.get("router", {}) or {}
print("routed_to    :", inner.get("routed_to"))
print("count        :", resp.get("count"), "| error:", resp.get("error"))
print("timing_ms    :", rt.get("timing_ms"))
print("breakdown    :", rt.get("timing_breakdown"))      # per-stage ms (since TIMING_BREAKDOWN=1)

# COMMAND ----------
# MAGIC %md
# MAGIC **After the latency report:** set `ENABLE_TIMING=False` and re-run cell 2 (or remove `TIMING_BREAKDOWN`
# MAGIC from the endpoint env in the UI) so production doesn't carry the instrumentation overhead.
