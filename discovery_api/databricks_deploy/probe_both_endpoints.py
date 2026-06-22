# Databricks notebook source
# MAGIC %md
# MAGIC # Probe both endpoints — Smoke + Latency report
# MAGIC Runs a **smoke test** (1 representative call → shape/verdict) and a **latency probe**
# MAGIC (N calls per scenario → p50/p90/p95, cold vs warm) against **both** staging endpoints:
# MAGIC `parrot-api-staging` (E1) and `discovery-api-staging` (E2).
# MAGIC
# MAGIC Per-stage breakdown (llm/vector/neo4j/embed) appears **only if `TIMING_BREAKDOWN=1`** is set on the
# MAGIC endpoint env (E1 supports it today; E2 surfaces it once the adapter is re-registered with timing).

# COMMAND ----------
# ===================== CONFIG =====================
REPO = "/Workspace/Users/satish.deshmukh@hiteshi.com/databrick-recommendation"
HOST = "https://<staging-host>"          # e.g. https://dbc-xxxx.cloud.databricks.com
import sys, importlib
sys.path.insert(0, f"{REPO}/databricks_deploy/serving")                 # E1 probe (latency_probe)
sys.path.insert(0, f"{REPO}/discovery_api/databricks_deploy/serving")   # E2 probe (discovery_latency_probe)
TOKEN  = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
E1_URL = f"{HOST}/serving-endpoints/parrot-api-staging/invocations"
E2_URL = f"{HOST}/serving-endpoints/discovery-api-staging/invocations"
print("E1:", E1_URL, "\nE2:", E2_URL)

# COMMAND ----------
# ===================== ENDPOINT 1 — parrot-api-staging (agent-recs) =====================
import latency_probe as lp; importlib.reload(lp)
print("########## ENDPOINT 1: parrot-api-staging ##########\n")
print("=== smoke (1 representative query) ===")
s = lp._call(E1_URL, TOKEN, "cozy farming games like Stardew Valley")
print(f"  status   : {'UP ✓' if not s['error'] else 'FAIL ✗'}")
print(f"  wall_ms  : {s['wall_ms']:.0f}  | path: {s['path']}  | count: {s['count']}  | error: {s['error']}\n")
print("=== latency (6 router paths × 5 calls, serial) ===")
lp.run(token=TOKEN, url=E1_URL, n=5)        # wall p50/p90/p95 (+ per-stage if TIMING_BREAKDOWN=1)

# COMMAND ----------
# ===================== ENDPOINT 2 — discovery-api-staging (discovery) =====================
import discovery_latency_probe as dp; importlib.reload(dp)
print("########## ENDPOINT 2: discovery-api-staging ##########\n")
dp.smoke(token=TOKEN, url=E2_URL)
print()
print("=== latency (5 scenarios × 5 calls, serial) ===")
dp.run(token=TOKEN, url=E2_URL, n=5)

# COMMAND ----------
# MAGIC %md
# MAGIC ## How to read this
# MAGIC - **wall p50/p90/p95** = round-trip latency the caller experiences (excludes the warmup/cold-start call).
# MAGIC - **breakdown** lines (E1) = where the ms went per stage — needs `TIMING_BREAKDOWN=1` on the endpoint
# MAGIC   (set it via *Serving → Edit → environment vars*, no re-register needed; remove it after to avoid overhead).
# MAGIC - For a **cold-start** number, look at the `warmup:` line (first call after the endpoint has been idle).
# MAGIC - **Do not load-test** (Greg asked us to hold) — `n=5` per scenario is a confirmation probe, not load.
# MAGIC
# MAGIC Paste this notebook's full output back and it gets formatted into the Smoke + Latency report.
