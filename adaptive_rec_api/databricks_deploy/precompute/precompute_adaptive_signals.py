# Databricks notebook source
# MAGIC %md
# MAGIC # Adaptive-Rec (UC6) precompute — signal tables  (part of the adaptive_rec bundle)
# MAGIC Builds the three signal tables the engine's `data.py` loads when `ADAPTIVE_DATA_SOURCE=live`:
# MAGIC   • **`adaptive_property_centrality`** (`property_id, wdegree, pagerank`) ← the Aura `:Entity` graph
# MAGIC     (`e.degree` is the weighted-degree hub signal; data.py ranks it WITHIN-vertical at load = S4).
# MAGIC   • **`adaptive_property_proximity`** (`property_id, franchises[], genres[]`) ← the graph's
# MAGIC     `IN_FRANCHISE` / `HAS_GENRE` edges (S6 overlap).
# MAGIC   • **`adaptive_property_popularity`** (`property_id, popularity`) ← **Silver** ratings (igdb/watchmode/
# MAGIC     podchaser via `public_properties`), per-vertical `PERCENT_RANK` → 0..1. The DOMINANT signal (S5).
# MAGIC     The bridge graph carries NO audience/critic ratings, so popularity comes from Silver, not the graph.
# MAGIC
# MAGIC Null-safe: a property with no degree/edges/rating yields NULL/[] → that signal stays neutral (data.py
# MAGIC degrades to taste-only, no crash). Order-safe DataFrame build (tuples in schema order).
# MAGIC
# MAGIC Run this (once, and on a refresh cadence) BEFORE/with `deploy_adaptive_endpoint.py`.

# COMMAND ----------
# MAGIC %pip install neo4j
# MAGIC # (%pip install auto-restarts the Python interpreter; neo4j is importable in the next cell)

# COMMAND ----------
dbutils.widgets.text("catalog", "stg_feeds_silver")   # where to WRITE the signal tables
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("silver_catalog", "stg_feeds_silver")   # SOURCE Silver for popularity (public_properties + igdb/watchmode/podchaser)
dbutils.widgets.text("neo4j_uri", "neo4j+s://17aa0e8d.databases.neo4j.io")   # the :Entity bridge graph (degree + genre/franchise edges)
dbutils.widgets.text("scope", "feedsai_staging")      # secret scope holding neo4j_password
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "silver_catalog", "neo4j_uri", "scope")}
NS = f"{C['catalog']}.{C['schema']}"
S = C["silver_catalog"]
print("writing to :", NS, "| silver:", S, "| graph:", C["neo4j_uri"])

# COMMAND ----------
# ── GRAPH: one streamed read of every :Entity — degree (S4) + franchise/genre edges (S6) ──
# Property names verified against this Aura: node has `degree` + `pagerank`; franchises/genres are EDGES
# (IN_FRANCHISE / HAS_GENRE), NOT node arrays. (No user_rating/critic_rating here → popularity from Silver.)
from neo4j import GraphDatabase
PWD = dbutils.secrets.get(C["scope"], "neo4j_password")
CYPHER = """
MATCH (e:Entity)
WHERE e.property_id IS NOT NULL
RETURN toInteger(e.property_id) AS property_id,
       toFloat(e.degree)   AS wdegree,
       toFloat(e.pagerank) AS pagerank,
       [(e)-[:IN_FRANCHISE]->(f) WHERE coalesce(f.name, f.title) IS NOT NULL | toString(coalesce(f.name, f.title))] AS franchises,
       [(e)-[:HAS_GENRE]->(g)    WHERE g.name IS NOT NULL | toString(g.name)] AS genres
"""
drv = GraphDatabase.driver(C["neo4j_uri"], auth=("neo4j", PWD))
with drv.session() as s:
    rows = [r.data() for r in s.run(CYPHER)]
drv.close()
print("entities read:", len(rows))

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.types import (StructType, StructField, LongType, DoubleType, ArrayType, StringType)

# ORDER-SAFE: tuples in schema field order (Row(**dict) reorders fields → a schema applied by position scrambles).
_CENT_SCHEMA = StructType([StructField("property_id", LongType()), StructField("wdegree", DoubleType()),
                           StructField("pagerank", DoubleType())])
_PROX_SCHEMA = StructType([StructField("property_id", LongType()),
                           StructField("franchises", ArrayType(StringType())),
                           StructField("genres", ArrayType(StringType()))])

cent_rows = [(r.get("property_id"), r.get("wdegree"), r.get("pagerank")) for r in rows]
prox_rows = [(r.get("property_id"), r.get("franchises") or [], r.get("genres") or []) for r in rows]

# ── 1. centrality (wdegree = graph degree) ──
cent = (spark.createDataFrame(cent_rows, _CENT_SCHEMA)
        .dropna(subset=["property_id"]).dropDuplicates(["property_id"])
        .where(F.col("wdegree").isNotNull()))
cent.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_centrality")
print("adaptive_property_centrality:", cent.count())

# ── 2. proximity (franchises / genres from edges) ──
prox = (spark.createDataFrame(prox_rows, _PROX_SCHEMA)
        .dropna(subset=["property_id"]).dropDuplicates(["property_id"])
        .where((F.size("franchises") > 0) | (F.size("genres") > 0)))
prox.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_proximity")
print("adaptive_property_proximity:", prox.count())

# COMMAND ----------
# ── 3. popularity from SILVER (S5, DOMINANT) — per-vertical PERCENT_RANK of the source rating, 0..1.
#      Same sources E4's search_property_popularity uses (games=igdb game_hypes; movies/tv=watchmode
#      popularity_percentile; podcasts=podchaser powerScore), joined to public_properties. ──
spark.sql(f"""
CREATE OR REPLACE TABLE {NS}.adaptive_property_popularity AS
WITH base AS (
  SELECT p.id AS property_id, 'game' AS vertical, CAST(g.game_hypes AS DOUBLE) AS raw_popularity
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.igdb.core_games_extended g
    ON CAST(g.igdb_game_id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 1 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 1
  UNION ALL
  SELECT p.id, 'movie', CAST(w.popularity_percentile AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 2 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 3
  UNION ALL
  SELECT p.id, 'tv', CAST(w.popularity_percentile AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 3 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 4
  UNION ALL
  SELECT p.id, 'podcast', CAST(pc.powerScore AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.podchaser.core_podcasts_extended pc
    ON CAST(pc.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 4 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 5
)
SELECT property_id,
       -- per-vertical PERCENT_RANK in 0..1 (highest raw rating -> ~1; no source -> ~0). data.py reads `popularity`.
       ROUND(PERCENT_RANK() OVER (PARTITION BY vertical ORDER BY raw_popularity ASC), 6) AS popularity
FROM base
WHERE property_id IS NOT NULL
""")
print("adaptive_property_popularity: built")

# COMMAND ----------
# ── verify: row counts + coverage of each signal ──
for t in ("adaptive_property_centrality", "adaptive_property_popularity", "adaptive_property_proximity"):
    display(spark.sql(f"SELECT '{t}' AS table, count(*) AS rows FROM {NS}.{t}"))
display(spark.sql(f"SELECT round(min(popularity),3) mn, round(avg(popularity),3) av, round(max(popularity),3) mx "
                  f"FROM {NS}.adaptive_property_popularity"))
display(spark.sql(f"SELECT round(avg(wdegree),2) avg_deg, max(wdegree) max_deg FROM {NS}.adaptive_property_centrality"))
