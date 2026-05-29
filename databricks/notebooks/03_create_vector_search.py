# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # 03 — Create Databricks Vector Search Endpoint & Delta Sync Index
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Notebook 02 done (entities Delta table is populated).
# MAGIC - Your workspace has the Vector Search service enabled (Premium/Enterprise).
# MAGIC - The cluster running this notebook must have the `databricks-vectorsearch` library installed.
# MAGIC   Install via: Cluster → Libraries → PyPI → `databricks-vectorsearch`.
# MAGIC
# MAGIC What this notebook does:
# MAGIC 1. Creates a Vector Search endpoint named `feedsai-vs-endpoint` (if it doesn't exist).
# MAGIC 2. Creates a Delta Sync Index on the `embedding` column of the entities table.
# MAGIC 3. Triggers the initial sync and waits for it to finish.
# MAGIC 4. Runs a test similarity search to confirm the index is working.

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

# ── 3. Wait for initial sync to complete ─────────────────────────────
index = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)

print("Waiting for index to become ONLINE ...")
for _ in range(120):
    status = client.get_index(
        endpoint_name=VS_ENDPOINT, index_name=VS_INDEX
    ).describe().get("status", {}).get("ready")
    print(f"  Index ready: {status}")
    if status:
        break
    time.sleep(10)

# Trigger the initial data sync
index.sync()
print("Sync triggered. Waiting for completion ...")
time.sleep(30)  # Allow first sync to run
print("Initial sync complete.")

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

col_names = results["result"]["column_names"]
print(f"\nTop-5 results for '{sample['name']}':")
for row in results["result"]["data_array"]:
    score = row[-1]
    data  = dict(zip(col_names[:-1], row[:-1]))
    print(f"  {data['name']:<40} {data['vertical']:<8}  score={score:.4f}")
