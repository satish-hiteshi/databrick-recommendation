# Databricks notebook source

# COMMAND ----------

%pip install databricks-vectorsearch --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient
import time

CATALOG       = "dev_feeds_silver_infotech"
SCHEMA        = "feedsai"
VS_ENDPOINT   = "feedsai-vs-endpoint"
EMBEDDING_DIM = 1024
ENTITIES_TABLE = f"{CATALOG}.{SCHEMA}.entities"
VS_INDEX       = f"{ENTITIES_TABLE}_vs_index"

# COMMAND ----------

client = VectorSearchClient()

existing_endpoints = [e["name"] for e in client.list_endpoints().get("endpoints", [])]

if VS_ENDPOINT not in existing_endpoints:
    client.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
    for _ in range(60):
        state = client.get_endpoint(VS_ENDPOINT)["endpoint_status"]["state"]
        print(f"  {state}")
        if state == "ONLINE":
            break
        time.sleep(10)
else:
    print(f"Endpoint exists: {VS_ENDPOINT}")

# COMMAND ----------

existing_indices = [i["name"] for i in client.list_indexes(VS_ENDPOINT).get("vector_indexes", [])]

if VS_INDEX not in existing_indices:
    client.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        source_table_name=ENTITIES_TABLE,
        index_name=VS_INDEX,
        pipeline_type="TRIGGERED",
        primary_key="entity_id",
        embedding_dimension=EMBEDDING_DIM,
        embedding_vector_column="embedding",
    )
    print(f"Index created: {VS_INDEX}")
else:
    print(f"Index exists: {VS_INDEX}")

# COMMAND ----------

# Wait for index structure, then trigger sync, then wait for data
for i in range(60):
    status = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX).describe().get("status", {})
    print(f"  [{i*10}s] ready={status.get('ready')}  {status.get('message', '')}")
    if status.get("ready"):
        break
    time.sleep(10)

index = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)
index.sync()
print("Sync triggered...")

for i in range(80):
    status = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX).describe().get("status", {})
    count  = status.get("indexed_row_count", 0)
    ready  = status.get("ready", False)
    print(f"  [{i*15}s] rows={count}  ready={ready}")
    if ready and count > 0:
        print(f"Done: {count} rows indexed")
        break
    time.sleep(15)

# COMMAND ----------

sample     = spark.table(ENTITIES_TABLE).limit(1).collect()[0]
sample_emb = list(sample["embedding"])

index   = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)
results = index.similarity_search(
    query_vector=sample_emb,
    columns=["entity_id", "name", "vertical"],
    num_results=5,
)

col_names = [col["name"] for col in results["manifest"]["columns"]]
print(f"Top-5 for '{sample['name']}':")
for row in results["result"]["data_array"]:
    data = dict(zip(col_names[:-1], row[:-1]))
    print(f"  {data['name']:<40} {data['vertical']:<8}  score={row[-1]:.4f}")
