# Databricks notebook source
# MAGIC %md
# MAGIC # Adaptive-Rec (UC6) precompute — signal tables  (part of the adaptive_rec bundle)
# MAGIC Reads the Aura **`:Entity`** graph ONCE and writes the three signal tables the engine's `data.py`
# MAGIC loads when `ADAPTIVE_DATA_SOURCE=live` (mirrors the dev branch's `precompute/*.py`, which target a
# MAGIC local Postgres/Neo4j):
# MAGIC   • **`adaptive_property_centrality`** (`property_id, wdegree, pagerank_pct`) — data.py reads `wdegree`
# MAGIC     and ranks it WITHIN-vertical at load (S4 centrality).
# MAGIC   • **`adaptive_property_popularity`** (`property_id, popularity, user_rating, critic_rating`) —
# MAGIC     `popularity = clamp(coalesce(user_rating, critic_rating)/100, 0, 1)` (S5, the DOMINANT signal).
# MAGIC   • **`adaptive_property_proximity`** (`property_id, franchises[], genres[]`) — S6 overlap.
# MAGIC
# MAGIC Null-safe: an :Entity missing a property yields NULL/[] → that signal stays neutral (data.py degrades
# MAGIC gracefully to taste-only, no crash). property_id = `coalesce(e.property_id, e.node_key)` so this works
# MAGIC whether the graph keys on `property_id` (E1/E2 graph) or `node_key` (the dev PoC graph).
# MAGIC
# MAGIC Run this (once, and on a refresh cadence) BEFORE/with `deploy_adaptive_endpoint.py`.

# COMMAND ----------
# MAGIC %pip install neo4j
# MAGIC # (%pip install auto-restarts the Python interpreter; neo4j is importable in the next cell)

# COMMAND ----------
dbutils.widgets.text("catalog", "stg_feeds_silver")   # where to WRITE the signal tables
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("neo4j_uri", "neo4j+s://17aa0e8d.databases.neo4j.io")   # the :Entity graph (with rating/degree props)
dbutils.widgets.text("scope", "feedsai_staging")      # secret scope holding neo4j_password
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "neo4j_uri", "scope")}
NS = f"{C['catalog']}.{C['schema']}"
print("writing to :", NS, "| graph:", C["neo4j_uri"])

# COMMAND ----------
# ── one streamed read of every :Entity (id + all signal props) ──
from neo4j import GraphDatabase
PWD = dbutils.secrets.get(C["scope"], "neo4j_password")
CYPHER = """
MATCH (e:Entity)
WHERE coalesce(e.property_id, e.node_key) IS NOT NULL
RETURN toInteger(coalesce(e.property_id, e.node_key)) AS property_id,
       toFloat(e.wdegree)       AS wdegree,
       toFloat(e.pagerank_pct)  AS pagerank_pct,
       toFloat(e.user_rating)   AS user_rating,
       toFloat(e.critic_rating) AS critic_rating,
       [x IN coalesce(e.franchises, []) | toString(x)] AS franchises,
       [x IN coalesce(e.genres, [])     | toString(x)] AS genres
"""
drv = GraphDatabase.driver(C["neo4j_uri"], auth=("neo4j", PWD))
with drv.session() as s:
    rows = [r.data() for r in s.run(CYPHER)]
drv.close()
print("entities read:", len(rows))

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.types import (StructType, StructField, LongType, DoubleType, ArrayType, StringType)

_SCHEMA = StructType([
    StructField("property_id", LongType()),
    StructField("wdegree", DoubleType()),
    StructField("pagerank_pct", DoubleType()),
    StructField("user_rating", DoubleType()),
    StructField("critic_rating", DoubleType()),
    StructField("franchises", ArrayType(StringType())),
    StructField("genres", ArrayType(StringType())),
])
# ORDER-SAFE: build rows as tuples in the SCHEMA's field order. (Row(**dict) reorders fields, so a schema
# applied by position would scramble columns.) Tuples + explicit schema match by position, deterministically.
_data = [(r.get("property_id"), r.get("wdegree"), r.get("pagerank_pct"), r.get("user_rating"),
          r.get("critic_rating"), r.get("franchises"), r.get("genres")) for r in rows]
raw = spark.createDataFrame(_data, _SCHEMA) \
           .dropna(subset=["property_id"]).dropDuplicates(["property_id"])
raw.cache()
print("distinct properties:", raw.count())

# COMMAND ----------
# ── 1. centrality (wdegree) ──
cent = raw.select("property_id", "wdegree", "pagerank_pct").where(F.col("wdegree").isNotNull())
cent.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_centrality")
print("adaptive_property_centrality:", cent.count())

# ── 2. popularity = clamp(coalesce(user_rating, critic_rating)/100, 0, 1) ──
pop = (raw.withColumn("_raw", F.coalesce("user_rating", "critic_rating"))
          .where(F.col("_raw").isNotNull())
          .withColumn("popularity", F.least(F.greatest(F.col("_raw") / F.lit(100.0), F.lit(0.0)), F.lit(1.0)))
          .select("property_id", "popularity", "user_rating", "critic_rating"))
pop.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_popularity")
print("adaptive_property_popularity:", pop.count())

# ── 3. proximity (franchises / genres arrays) ──
prox = raw.select("property_id", "franchises", "genres") \
          .where((F.size("franchises") > 0) | (F.size("genres") > 0))
prox.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_proximity")
print("adaptive_property_proximity:", prox.count())

# COMMAND ----------
# ── verify: coverage of each signal ──
for t in ("adaptive_property_centrality", "adaptive_property_popularity", "adaptive_property_proximity"):
    display(spark.sql(f"SELECT '{t}' AS table, count(*) AS rows FROM {NS}.{t}"))
display(spark.sql(f"SELECT round(min(popularity),3) mn, round(avg(popularity),3) av, round(max(popularity),3) mx "
                  f"FROM {NS}.adaptive_property_popularity"))
