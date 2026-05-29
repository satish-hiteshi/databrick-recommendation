# Databricks notebook source

# COMMAND ----------

import json, os, pickle
import numpy as np
from pyspark.sql.types import StructType, StructField, StringType, ArrayType, FloatType

CATALOG      = "dev_feeds_silver_infotech"
SCHEMA       = "feedsai"
DATA_DIR     = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"
ARTIFACT_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/artifacts"

# COMMAND ----------

dbutils.fs.mkdirs(ARTIFACT_DIR)

with open(f"{DATA_DIR}/all_compositions.json") as f:
    compositions = json.load(f)

with open(f"{DATA_DIR}/entity_profiles_final.json") as f:
    profiles = json.load(f)

emb_array = np.load(f"{DATA_DIR}/embeddings.npy")

with open(f"{DATA_DIR}/embeddings_ids.json") as f:
    emb_ids = json.load(f)

print(f"compositions={len(compositions)}  profiles={len(profiles)}  embeddings={emb_array.shape}")

# COMMAND ----------

profile_map   = {p["entity_id"]: p for p in profiles}
embedding_map = {eid: emb_array[i] for i, eid in enumerate(emb_ids)}

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

print(f"Merged: {len(entities)} entities")

# COMMAND ----------

rows = [
    (
        e["entity_id"], e["name"], e["vertical"], e["description"],
        e["composed_text"], e["bm25_keywords"], e["canonical_genres"],
        e["themes"], e["franchise"], e["developer"], e["publisher"],
        e["directors"], e["cast_members"], e["embedding"],
    )
    for e in entities
]

schema = StructType([
    StructField("entity_id",        StringType(),            False),
    StructField("name",             StringType(),            False),
    StructField("vertical",         StringType(),            False),
    StructField("description",      StringType(),            True),
    StructField("composed_text",    StringType(),            True),
    StructField("bm25_keywords",    ArrayType(StringType()), True),
    StructField("canonical_genres", ArrayType(StringType()), True),
    StructField("themes",           ArrayType(StringType()), True),
    StructField("franchise",        StringType(),            True),
    StructField("developer",        StringType(),            True),
    StructField("publisher",        StringType(),            True),
    StructField("directors",        ArrayType(StringType()), True),
    StructField("cast_members",     ArrayType(StringType()), True),
    StructField("embedding",        ArrayType(FloatType()),  True),
])

df = spark.createDataFrame(rows, schema=schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.entities")

count = spark.table(f"{CATALOG}.{SCHEMA}.entities").count()
print(f"Loaded: {count} rows → {CATALOG}.{SCHEMA}.entities")

# COMMAND ----------

pickle_path = f"{ARTIFACT_DIR}/entities_meta.pkl"
with open(pickle_path, "wb") as f:
    pickle.dump(entities, f, protocol=pickle.HIGHEST_PROTOCOL)

print(f"Saved: {pickle_path}  ({os.path.getsize(pickle_path)/1e6:.1f} MB)")
