"""One-time build: load the EXISTING Voyage vectors + entity metadata into a Unity Catalog Delta table,
then create a Databricks Vector Search Delta-Sync index over it (self-managed embeddings).

Run on a Databricks cluster/notebook with Vector Search enabled. NO re-embedding — we reuse
vector/data_v2/embeddings_v2.npy exactly, so dense-retrieval parity with local Qdrant is preserved.

STEP 0 — upload these four files to a UC Volume (default: /Volumes/<catalog>/<schema>/feedsai_src):
  embeddings_v2.npy        (6945, 1024) float32   — cached voyage-4-large document vectors
  embeddings_ids_v2.json   row-order → entity_id  — aligns npy rows to ids
  all_compositions_v2.json name / vertical / bm25_keywords per entity
  entity_profiles_v2.json  franchise / release_date / … per entity

OUTPUTS:
  <catalog>.<schema>.entities      Delta table (payload + `embedding ARRAY<FLOAT>`, CDF enabled)
  <catalog>.<schema>.entities_vs   Vector Search index (Delta-Sync, self-managed embeddings)

    python databricks_deploy/vector_search/build_index.py     # (inside Databricks)
"""

import json
import os

import numpy as np

CATALOG = os.getenv("UC_CATALOG", "dev_feeds_silver")
SCHEMA = os.getenv("UC_SCHEMA", "ml")
TABLE = f"{CATALOG}.{SCHEMA}.entities"
INDEX = f"{CATALOG}.{SCHEMA}.entities_vs"
VS_ENDPOINT = os.getenv("VS_ENDPOINT_NAME", "feedsai-vs")
SRC = os.getenv("SRC_VOLUME", f"/Volumes/{CATALOG}/{SCHEMA}/feedsai_src")
EMBEDDING_DIM = 1024


def _merge_records():
    """Replicate the pipeline's data_loader merge (compositions ⨝ profiles) + attach the npy vector."""
    with open(f"{SRC}/all_compositions_v2.json") as f:
        comps = json.load(f)
    with open(f"{SRC}/entity_profiles_v2.json") as f:
        profiles = {p["entity_id"]: p for p in json.load(f)}
    vecs = np.load(f"{SRC}/embeddings_v2.npy")
    with open(f"{SRC}/embeddings_ids_v2.json") as f:
        row_of = {eid: i for i, eid in enumerate(json.load(f))}

    records, skipped = [], 0
    for c in comps:
        eid = c["entity_id"]
        i = row_of.get(eid)
        if i is None:
            skipped += 1
            continue                                   # no vector → skip (keeps table aligned to npy)
        p = profiles.get(eid, {})
        rd = p.get("release_date")
        records.append({
            "entity_id": eid,
            "name": c["name"],
            "vertical": c["vertical"],
            "franchise": p.get("franchise"),
            "release_date": rd,
            "release_date_int": int(rd.replace("-", "")) if rd else None,
            "bm25_keywords": c.get("bm25_keywords") or [],
            "embedding": [float(x) for x in vecs[i]],
        })
    if skipped:
        print(f"WARNING: {skipped} compositions had no embedding row and were skipped.")
    return records


def main():
    from databricks.vector_search.client import VectorSearchClient
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    records = _merge_records()
    print(f"Merged {len(records)} entity records, each with a {EMBEDDING_DIM}-dim embedding.")

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
    df = spark.createDataFrame(records)
    (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE))
    spark.sql(f"ALTER TABLE {TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    print(f"Wrote Delta table {TABLE} ({df.count()} rows); Change Data Feed enabled.")

    vsc = VectorSearchClient(disable_notice=True)
    try:
        vsc.get_endpoint(VS_ENDPOINT)
        print(f"Vector Search endpoint {VS_ENDPOINT} exists.")
    except Exception:
        print(f"Creating Vector Search endpoint {VS_ENDPOINT} …")
        vsc.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")

    print(f"Creating Delta-Sync index {INDEX} (self-managed embeddings) …")
    vsc.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        index_name=INDEX,
        source_table_name=TABLE,
        pipeline_type="TRIGGERED",
        primary_key="entity_id",
        embedding_dimension=EMBEDDING_DIM,
        embedding_vector_column="embedding",
    )
    print("Done. Index is syncing from the table.")
    print(f"\nSet on the Vector App:  VS_ENDPOINT_NAME={VS_ENDPOINT}  VS_INDEX_NAME={INDEX}")


if __name__ == "__main__":
    main()
