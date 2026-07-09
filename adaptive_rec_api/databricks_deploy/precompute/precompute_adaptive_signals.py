# Databricks notebook source
# MAGIC %md
# MAGIC # Adaptive-Rec (UC6) precompute — signal tables  (part of the adaptive_rec bundle)
# MAGIC Builds the three signal tables the engine's `data.py` loads when `ADAPTIVE_DATA_SOURCE=live`. **All three
# MAGIC are keyed by `entity_id` (`"<Vertical>:<media_source_guid>"`) per PRECOMPUTE_SPEC §5** — collision-safe on
# MAGIC the ~320 cross-vertical guid twins — and carry `property_id` (bare guid as BIGINT) + `profile_key` +
# MAGIC `media_source_guid` + `vertical` for back-compat (the loader joins entity_id first, guid fallback):
# MAGIC   • **`adaptive_property_centrality`** (`wdegree` = raw GDS degree, `pagerank`) ← the re-keyed Aura
# MAGIC     `:Entity` graph (data.py ranks wdegree WITHIN-vertical at load = S4).
# MAGIC   • **`adaptive_property_proximity`** (`franchises[], developers[], publishers[], genres[], themes[],
# MAGIC     modes[], community`) ← the graph's edges + GDS Louvain (S6 overlap + why-strings).
# MAGIC   • **`adaptive_property_popularity`** (`raw_popularity, pop_source, popularity`) ← **Silver** ratings via
# MAGIC     `public_properties`. Per SPEC §5b: game = `combined_rating_count`, fallback `game_hypes`; movie/tv =
# MAGIC     `popularity_percentile`; podcast = `powerScore`. Normalized with the WITHIN-VERTICAL **tie-aware
# MAGIC     average-rank percentile** over rows with raw>0 (equal raw ⇒ equal pct); raw NULL/≤0 → 0.0. S5, DOMINANT.
# MAGIC
# MAGIC Null-safe: a property with no degree/edges/rating yields NULL/[]/0 → that signal stays neutral (data.py
# MAGIC degrades to taste-only, no crash). Order-safe DataFrame build (tuples in schema order).
# MAGIC
# MAGIC Run this (once, and on a refresh cadence) BEFORE/with `deploy_adaptive_endpoint.py`.

# COMMAND ----------
# MAGIC %pip install neo4j
# MAGIC # (%pip install auto-restarts the Python interpreter; neo4j is importable in the next cell)

# COMMAND ----------
# MAGIC %run ../../../graph/utils/workspace_catalog

# COMMAND ----------
# MAGIC %run ../../../foundation/_endpoint_env

# COMMAND ----------
# env (catalog · silver · neo4j · scope) auto-resolved from the workspace via workspace_catalog + _endpoint_env.
dbutils.widgets.text("catalog", CATALOG)   # where to WRITE the signal tables
dbutils.widgets.text("schema", SCHEMA)
dbutils.widgets.text("silver_catalog", CATALOG)   # SOURCE Silver for popularity (public_properties + igdb/watchmode/podchaser)
dbutils.widgets.text("neo4j_uri", NEO4J_URI)   # the re-keyed :Entity graph (GDS + proximity edges)
dbutils.widgets.text("scope", SCOPE)      # secret scope holding neo4j_password
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "silver_catalog", "neo4j_uri", "scope")}
NS = f"{C['catalog']}.{C['schema']}"
S = C["silver_catalog"]
print("writing to :", NS, "| silver:", S, "| graph:", C["neo4j_uri"])

# COMMAND ----------
# ── GRAPH: one streamed read of every :Entity — identity + GDS (S4) + proximity edges (S6) ──
# The RE-KEYED graph carries entity_id/profile_key/media_source_guid/vertical + GDS pagerank/degree/community
# ON THE NODE (no `property_id` — the old `WHERE e.property_id IS NOT NULL` filter returned 0 rows here).
from neo4j import GraphDatabase
PWD = dbutils.secrets.get(scope="feeds-default-scope", key="neo4j_password")
CYPHER = """
MATCH (e:Entity)
RETURN e.entity_id           AS entity_id,
       e.profile_key         AS profile_key,
       toString(e.media_source_guid) AS media_source_guid,
       e.vertical            AS vertical,
       toFloat(e.degree)     AS wdegree,
       toFloat(e.pagerank)   AS pagerank,
       toInteger(e.community) AS community,
       [(e)-[:IN_FRANCHISE]->(f)  WHERE coalesce(f.name, f.title) IS NOT NULL | toString(coalesce(f.name, f.title))] AS franchises,
       [(e)-[:HAS_DEVELOPER]->(d) WHERE coalesce(d.name, d.title) IS NOT NULL | toString(coalesce(d.name, d.title))] AS developers,
       [(e)-[:HAS_PUBLISHER]->(p) WHERE coalesce(p.name, p.title) IS NOT NULL | toString(coalesce(p.name, p.title))] AS publishers,
       [(e)-[:HAS_GENRE]->(g)     WHERE g.name IS NOT NULL | toString(g.name)] AS genres,
       [(e)-[:HAS_THEME]->(t)     WHERE t.name IS NOT NULL | toString(t.name)] AS themes,
       [(e)-[:HAS_MODE]->(m)      WHERE m.name IS NOT NULL | toString(m.name)] AS modes
"""
drv = GraphDatabase.driver(C["neo4j_uri"], auth=("neo4j", PWD), max_connection_lifetime=300, liveness_check_timeout=30, connection_acquisition_timeout=30, keep_alive=True)
with drv.session() as s:
    rows = [r.data() for r in s.run(CYPHER)]
drv.close()
print("entities read:", len(rows))

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.types import (StructType, StructField, LongType, DoubleType, ArrayType, StringType)

# ORDER-SAFE: tuples in schema field order (Row(**dict) reorders fields → a schema applied by position scrambles).
_ID_FIELDS = [StructField("entity_id", StringType()), StructField("profile_key", StringType()),
              StructField("media_source_guid", StringType()), StructField("vertical", StringType())]
_CENT_SCHEMA = StructType(_ID_FIELDS + [StructField("wdegree", DoubleType()), StructField("pagerank", DoubleType())])
_PROX_SCHEMA = StructType(_ID_FIELDS + [StructField("franchises", ArrayType(StringType())),
                                        StructField("developers", ArrayType(StringType())),
                                        StructField("publishers", ArrayType(StringType())),
                                        StructField("genres", ArrayType(StringType())),
                                        StructField("themes", ArrayType(StringType())),
                                        StructField("modes", ArrayType(StringType())),
                                        StructField("community", LongType())])

def _idt(r):
    return (r.get("entity_id"), r.get("profile_key"), r.get("media_source_guid"), r.get("vertical"))

cent_rows = [_idt(r) + (r.get("wdegree"), r.get("pagerank")) for r in rows]
prox_rows = [_idt(r) + (r.get("franchises") or [], r.get("developers") or [], r.get("publishers") or [],
                        r.get("genres") or [], r.get("themes") or [], r.get("modes") or [],
                        r.get("community")) for r in rows]

# back-compat bare-guid column (BIGINT; the loader's guid FALLBACK — entity_id is the join key)
_pid = F.col("media_source_guid").cast("long").alias("property_id")

# ── 1. centrality (wdegree = raw GDS degree; data.py re-percentiles within-vertical at load) ──
cent = (spark.createDataFrame(cent_rows, _CENT_SCHEMA)
        .dropna(subset=["entity_id"]).where(F.col("wdegree").isNotNull())
        .withColumn("property_id", _pid)
        .dropDuplicates(["entity_id"]))
cent.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_centrality")
print("adaptive_property_centrality:", cent.count())

# ── 2. proximity (franchise/developer/publisher/genre/theme/mode arrays + Louvain community) ──
prox = (spark.createDataFrame(prox_rows, _PROX_SCHEMA)
        .dropna(subset=["entity_id"])
        .where((F.size("franchises") > 0) | (F.size("developers") > 0) | (F.size("publishers") > 0) |
               (F.size("genres") > 0) | (F.size("themes") > 0) | (F.size("modes") > 0) |
               F.col("community").isNotNull())
        .withColumn("property_id", _pid)
        .dropDuplicates(["entity_id"]))
prox.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{NS}.adaptive_property_proximity")
print("adaptive_property_proximity:", prox.count())

# COMMAND ----------
# ── 3. popularity from SILVER (S5, DOMINANT) — SPEC §5b raw fields + tie-aware average-rank percentile. ──
#      entity_id = "<Vertical>:<guid>" derived from media_type_id; profile_key = the per-vertical constant.
#      game raw = combined_rating_count, fallback game_hypes (pop_source labels which); movie/tv =
#      popularity_percentile; podcast = powerScore. Percentile over raw>0 within vertical (equal raw ⇒ equal
#      pct, avg-rank method — NOT percent_rank/cume_dist, which put large tie-clusters at the min/max rank);
#      raw NULL/≤0 rows are KEPT with popularity = 0.0 so coverage is the full universe.
spark.sql(f"""
CREATE OR REPLACE TABLE {NS}.adaptive_property_popularity AS
WITH base AS (
  SELECT concat('Game:', CAST(p.media_source_guid AS STRING)) AS entity_id,
         'igdb_property_game' AS profile_key,
         CAST(p.media_source_guid AS STRING) AS media_source_guid,
         CAST(p.media_source_guid AS BIGINT) AS property_id, 'game' AS vertical,
         COALESCE(NULLIF(CAST(g.game_combined_rating_count AS DOUBLE), 0.0),
                  CAST(g.game_hypes AS DOUBLE)) AS raw_popularity,
         CASE WHEN NULLIF(CAST(g.game_combined_rating_count AS DOUBLE), 0.0) IS NOT NULL
              THEN 'combined_rating_count'
              WHEN g.game_hypes IS NOT NULL THEN 'game_hypes' ELSE 'null_source' END AS pop_source
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.igdb.core_games_extended g
    ON CAST(g.igdb_game_id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 1 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 1
  UNION ALL
  SELECT concat('Movie:', CAST(p.media_source_guid AS STRING)), 'watchmode_property_movie',
         CAST(p.media_source_guid AS STRING), CAST(p.media_source_guid AS BIGINT), 'movie',
         CAST(w.popularity_percentile AS DOUBLE),
         CASE WHEN w.id IS NOT NULL THEN 'popularity_percentile' ELSE 'null_source' END
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 2 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 3
  UNION ALL
  SELECT concat('TV:', CAST(p.media_source_guid AS STRING)), 'watchmode_property_tv',
         CAST(p.media_source_guid AS STRING), CAST(p.media_source_guid AS BIGINT), 'tv',
         CAST(w.popularity_percentile AS DOUBLE),
         CASE WHEN w.id IS NOT NULL THEN 'popularity_percentile' ELSE 'null_source' END
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 3 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 4
  UNION ALL
  SELECT concat('Podcast:', CAST(p.media_source_guid AS STRING)), 'podchaser_property_podcast',
         CAST(p.media_source_guid AS STRING), CAST(p.media_source_guid AS BIGINT), 'podcast',
         CAST(pc.powerScore AS DOUBLE),
         CASE WHEN pc.id IS NOT NULL THEN 'power_score' ELSE 'null_source' END
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.podchaser.core_podcasts_extended pc
    ON CAST(pc.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 4 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 5
),
dedup AS (   -- media_source_guid can repeat across legacy public_properties rows -> one row per entity_id
  SELECT entity_id,
         MAX(profile_key) AS profile_key, MAX(media_source_guid) AS media_source_guid,
         MAX(property_id) AS property_id, MAX(vertical) AS vertical,
         MAX(raw_popularity) AS raw_popularity, MAX(pop_source) AS pop_source
  FROM base WHERE media_source_guid IS NOT NULL
  GROUP BY entity_id
),
avgd AS (     -- tie-aware AVERAGE-rank percentile over raw>0 within vertical (SPEC §5b)
  SELECT t.entity_id,
         ROUND(CASE WHEN t.n_pos > 1 THEN (AVG(t.rn) OVER (PARTITION BY t.vertical, t.raw_popularity) - 1.0)
                                          / (t.n_pos - 1.0) ELSE 1.0 END, 6) AS popularity
  FROM (SELECT entity_id, vertical, raw_popularity,
               ROW_NUMBER() OVER (PARTITION BY vertical ORDER BY raw_popularity) AS rn,
               COUNT(*)    OVER (PARTITION BY vertical) AS n_pos
        FROM dedup WHERE raw_popularity > 0) t
)
SELECT d.entity_id, d.property_id, d.profile_key, d.media_source_guid, d.vertical,
       d.raw_popularity, d.pop_source,
       COALESCE(a.popularity, 0.0) AS popularity     -- raw NULL/≤0 -> 0.0 (row KEPT)
FROM dedup d LEFT JOIN avgd a ON d.entity_id = a.entity_id
""")
print("adaptive_property_popularity: built")

# COMMAND ----------
# ── verify: row counts + coverage of each signal + the twin check (SPEC §8) ──
for t in ("adaptive_property_centrality", "adaptive_property_popularity", "adaptive_property_proximity"):
    display(spark.sql(f"SELECT '{t}' AS table, count(*) AS rows, count(DISTINCT entity_id) AS eids FROM {NS}.{t}"))
display(spark.sql(f"SELECT vertical, count(*) n, round(min(popularity),3) mn, round(avg(popularity),3) av, "
                  f"round(max(popularity),3) mx, sum(CASE WHEN pop_source='null_source' THEN 1 ELSE 0 END) null_src "
                  f"FROM {NS}.adaptive_property_popularity GROUP BY vertical ORDER BY vertical"))
display(spark.sql(f"SELECT round(avg(wdegree),2) avg_deg, max(wdegree) max_deg FROM {NS}.adaptive_property_centrality"))
# twin guid 119163 must be TWO distinct rows (Game + Movie) in every table
display(spark.sql(f"SELECT entity_id, vertical, popularity FROM {NS}.adaptive_property_popularity "
                  f"WHERE media_source_guid = '119163' ORDER BY entity_id"))
