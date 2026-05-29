# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # 03 — Create Databricks Vector Search Endpoint & Delta Sync Index
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Notebook 02 done (entities Delta table is populated).
# MAGIC - Your workspace has the Vector Search service enabled (Premium/Enterprise).
# MAGIC - Works on both Serverless and traditional clusters — `%pip install` below handles dependencies.
# MAGIC
# MAGIC What this notebook does:
# MAGIC 1. Creates a Vector Search endpoint named `feedsai-vs-endpoint` (if it doesn't exist).
# MAGIC 2. Creates a Delta Sync Index on the `embedding` column of the entities table.
# MAGIC 3. Triggers the initial sync and waits for it to finish.
# MAGIC 4. Runs a test similarity search to confirm the index is working.

# COMMAND ----------

%pip install databricks-vectorsearch --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient
import time

# ── CONFIGURE ────────────────────────────────────────────────────────
CATALOG      = "dev_feeds_silver_infotech"
SCHEMA       = "feedsai"
VS_ENDPOINT  = "feedsai-vs-endpoint"
EMBEDDING_DIM = 1024
# ─────────────────────────────────────────────────────────────────────

ENTITIES_TABLE = f"{CATALOG}.{SCHEMA}.entities"
VS_INDEX       = f"{ENTITIES_TABLE}_vs_index"

# COMMAND ----------

# ── 1. Create Vector Search endpoint ─────────────────────────────────
client = VectorSearchClient()

existing_endpoints = [e["name"] for e in client.list_endpoints().get("endpoints", [])]

if VS_ENDPOINT not in existing_endpoints:
    print(f"Creating endpoint '{VS_ENDPOINT}' ...")
    client.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
    # Wait for endpoint to become ONLINE
    for _ in range(60):
        status = client.get_endpoint(VS_ENDPOINT)["endpoint_status"]["state"]
        print(f"  Endpoint state: {status}")
        if status == "ONLINE":
            break
        time.sleep(10)
    print("Endpoint is ONLINE.")
else:
    print(f"Endpoint '{VS_ENDPOINT}' already exists.")

# COMMAND ----------

# ── 2. Create Delta Sync Index ────────────────────────────────────────
existing_indices = [
    i["name"]
    for i in client.list_indexes(VS_ENDPOINT).get("vector_indexes", [])
]

if VS_INDEX not in existing_indices:
    print(f"Creating index '{VS_INDEX}' ...")
    index = client.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        source_table_name=ENTITIES_TABLE,
        index_name=VS_INDEX,
        pipeline_type="TRIGGERED",       # use CONTINUOUS for real-time sync
        primary_key="entity_id",
        embedding_dimension=EMBEDDING_DIM,
        embedding_vector_column="embedding",
    )
    print(f"Index created: {index}")
else:
    print(f"Index '{VS_INDEX}' already exists.")

# COMMAND ----------

# ── 3. Wait for index structure, trigger sync, wait for data ──────────
#
# TRIGGERED pipeline lifecycle:
#   create_delta_sync_index() → index structure provisioned (no data yet)
#   index.sync()              → starts loading data from Delta
#   poll indexed_row_count    → wait until all 1,757 rows are indexed
#
# Expected time: 5–15 minutes for 1,757 entities.

# Step A: wait for index structure to be provisioned (usually < 2 min)
print("Step A — Waiting for index structure to be provisioned ...")
for i in range(60):  # up to 10 minutes
    desc   = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX).describe()
    status = desc.get("status", {})
    msg    = status.get("message", "provisioning...")
    ready  = status.get("ready", False)
    print(f"  [{i*10}s]  ready={ready}  message={msg}")
    if ready:
        break
    time.sleep(10)

# Step B: trigger the initial data sync
print("\nStep B — Triggering initial data sync ...")
index = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)
index.sync()
print("Sync started. This takes 5–15 minutes for 1,757 entities.\n")

# Step C: poll until all rows are indexed
print("Step C — Waiting for data to be indexed ...")
for i in range(80):  # up to ~20 minutes
    desc   = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX).describe()
    status = desc.get("status", {})
    count  = status.get("indexed_row_count", 0)
    ready  = status.get("ready", False)
    msg    = status.get("message", "")
    print(f"  [{i*15}s]  rows_indexed={count}/1757  ready={ready}  {msg}")
    if ready and count > 0:
        print(f"\nSync complete — {count} rows indexed and ready.")
        break
    time.sleep(15)
else:
    print("Timed out waiting. Check Compute → Vector Search in Databricks UI for live status.")

# COMMAND ----------

# ── 4. Smoke test ─────────────────────────────────────────────────────
# Retrieve the first entity's embedding from Delta and run a similarity search.
sample = spark.table(ENTITIES_TABLE).limit(1).collect()[0]
sample_id  = sample["entity_id"]
sample_emb = list(sample["embedding"])

print(f"Testing with entity: {sample['name']}  ({sample['vertical']})")

index   = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)
results = index.similarity_search(
    query_vector=sample_emb,
    columns=["entity_id", "name", "vertical"],
    num_results=5,
)

col_names = [col["name"] for col in results["manifest"]["columns"]]
print(f"\nTop-5 results for '{sample['name']}':")
for row in results["result"]["data_array"]:
    score = row[-1]
    data  = dict(zip(col_names[:-1], row[:-1]))
    print(f"  {data['name']:<40} {data['vertical']:<8}  score={score:.4f}")
