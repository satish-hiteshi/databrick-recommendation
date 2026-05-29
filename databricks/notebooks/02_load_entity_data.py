# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # 02 — Load Entity Data into Delta + Build entities_meta.pkl
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Notebook 01 has been run (tables exist).
# MAGIC - Upload the four data files to a Databricks **Volume** or DBFS path, then set
# MAGIC   `DATA_DIR` below.
# MAGIC   Files needed:
# MAGIC   - `all_compositions.json`
# MAGIC   - `entity_profiles_final.json`
# MAGIC   - `embeddings.npy`
# MAGIC   - `embeddings_ids.json`
# MAGIC
# MAGIC   Quickest upload: Databricks UI → Catalog → `dev_feeds_silver_infotech` → `feedsai`
# MAGIC   → Volumes → Create Volume (name: `raw_data`) → upload files.
# MAGIC
# MAGIC What this notebook does:
# MAGIC 1. Reads the JSON + embedding files.
# MAGIC 2. Writes the merged entity data (including embeddings) to the Delta table.
# MAGIC 3. Saves `entities_meta.pkl` to the Volume — this artifact is bundled into the
# MAGIC    MLflow model in notebook 04 so Model Serving doesn't need to hit Delta for
# MAGIC    bulk lookups (BM25, reranker, negative-filter).

# COMMAND ----------

import json
import os
import pickle
import numpy as np
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, ArrayType, FloatType
)

# ── CONFIGURE ────────────────────────────────────────────────────────
CATALOG  = "dev_feeds_silver_infotech"
SCHEMA   = "feedsai"

# Where you uploaded the data files (DBFS Volume path)
DATA_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Where to write the pickle artifact
ARTIFACT_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/artifacts"
# ─────────────────────────────────────────────────────────────────────

# COMMAND ----------

# Ensure artifact dir exists
dbutils.fs.mkdirs(ARTIFACT_DIR)

# Read JSON data files from the mounted volume
compositions_path = f"{DATA_DIR}/all_compositions.json"
profiles_path     = f"{DATA_DIR}/entity_profiles_final.json"
emb_npy_path      = f"{DATA_DIR}/embeddings.npy"
emb_ids_path      = f"{DATA_DIR}/embeddings_ids.json"

# Read via local path (Volumes are accessible as /Volumes/...)
with open(compositions_path) as f:
    compositions = json.load(f)

with open(profiles_path) as f:
    profiles = json.load(f)

emb_array = np.load(emb_npy_path)          # shape: (N, 1024)

with open(emb_ids_path) as f:
    emb_ids = json.load(f)

print(f"Compositions: {len(compositions)}")
print(f"Profiles:     {len(profiles)}")
print(f"Embeddings:   {emb_array.shape}")

# COMMAND ----------

# Build unified entity list (same merge logic as original data_loader.py)
profile_map    = {p["entity_id"]: p for p in profiles}
embedding_map  = {eid: emb_array[i] for i, eid in enumerate(emb_ids)}

entities = []
for comp in compositions:
    eid     = comp["entity_id"]
    profile = profile_map.get(eid, {})
    emb     = embedding_map.get(eid)

    entities.append({
        "entity_id":        eid,
        "name":             comp["name"],
        "vertical":         comp["vertical"],
        "description":      profile.get("description"),
        "composed_text":    comp["composed_text"],
        "bm25_keywords":    comp["bm25_keywords"],
        "canonical_genres": profile.get("canonical_genres", []),
        "themes":           profile.get("themes", []),
        "franchise":        profile.get("franchise"),
        "developer":        profile.get("developer"),
        "publisher":        profile.get("publisher"),
        "directors":        profile.get("directors", []),
        "cast_members":     profile.get("cast", []),
        "embedding":        emb.tolist() if emb is not None else None,
    })

print(f"Merged entities: {len(entities)}")

# COMMAND ----------

# Write to Delta table via Spark
# Convert to rows Spark can handle (embedding as list[float])
rows = [
    (
        e["entity_id"],
        e["name"],
        e["vertical"],
        e["description"],
        e["composed_text"],
        e["bm25_keywords"],
        e["canonical_genres"],
        e["themes"],
        e["franchise"],
        e["developer"],
        e["publisher"],
        e["directors"],
        e["cast_members"],
        e["embedding"],   # list[float] → ARRAY<FLOAT> in Delta
    )
    for e in entities
]

schema = StructType([
    StructField("entity_id",        StringType(),             False),
    StructField("name",             StringType(),             False),
    StructField("vertical",         StringType(),             False),
    StructField("description",      StringType(),             True),
    StructField("composed_text",    StringType(),             True),
    StructField("bm25_keywords",    ArrayType(StringType()),  True),
    StructField("canonical_genres", ArrayType(StringType()),  True),
    StructField("themes",           ArrayType(StringType()),  True),
    StructField("franchise",        StringType(),             True),
    StructField("developer",        StringType(),             True),
    StructField("publisher",        StringType(),             True),
    StructField("directors",        ArrayType(StringType()),  True),
    StructField("cast_members",     ArrayType(StringType()),  True),
    StructField("embedding",        ArrayType(FloatType()),   True),
])

df = spark.createDataFrame(rows, schema=schema)

(
    df.write
      .format("delta")
      .mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable(f"{CATALOG}.{SCHEMA}.entities")
)

count = spark.table(f"{CATALOG}.{SCHEMA}.entities").count()
print(f"Delta table written: {count} rows in {CATALOG}.{SCHEMA}.entities")

# COMMAND ----------

# Build and save entities_meta.pkl
# This pickle stores all entity data (including embeddings) so that Model Serving
# can load it as an MLflow artifact and skip Delta SQL for bulk in-memory lookups.

pickle_path_local = f"/Volumes/{CATALOG}/{SCHEMA}/artifacts/entities_meta.pkl"

with open(pickle_path_local, "wb") as f:
    pickle.dump(entities, f, protocol=pickle.HIGHEST_PROTOCOL)

size_mb = os.path.getsize(pickle_path_local) / 1e6
print(f"Saved entities_meta.pkl  ({size_mb:.1f} MB)  →  {pickle_path_local}")
print("Use this path as the 'entities_meta' artifact in notebook 04.")
