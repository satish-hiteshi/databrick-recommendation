# Databricks notebook source
# MAGIC %md
# MAGIC # E4 Search — precompute `search_property_popularity` + `search_entity_centrality`  (part of the E4 bundle)
# MAGIC Builds the two tables `store.py` reads when `SEARCH_DATA_SOURCE=live`, **reproducing the developer's
# MAGIC reference method** (`endpoint_4_search/DEPLOYMENT.md` §3.1) so Databricks scores match the eval report:
# MAGIC   • **`popularity_pct`** = `CUME_DIST` (= `count(≤x)/N`, method=max) within **`(vertical, pop_source)`**
# MAGIC     over NON-NULL `raw_popularity`; NULL raw → 0.0. Sources = igdb `game_hypes` / watchmode
# MAGIC     `popularity_percentile` / podchaser `powerScore` (the developer's extraction SQL) ⋈ `public_properties`.
# MAGIC   • **`dedup_key`** = `"{media_source_guid}:{media_source_id|NA}:{media_type_id|NA}"` (NULL if guid NULL).
# MAGIC   • **`centrality_pct`** = `CUME_DIST` of the Aura `:Entity.pagerank` within **vertical** (method=max).
# MAGIC
# MAGIC `store.py` reads `property_id, name, vertical, popularity_pct, recency_date, dedup_key` + `property_id,
# MAGIC centrality_pct`. Run BEFORE/with `deploy_search_endpoint.py`.

# COMMAND ----------
# MAGIC %pip install neo4j
# MAGIC # (%pip install auto-restarts Python; neo4j is importable below)

# COMMAND ----------
dbutils.widgets.text("catalog", "stg_feeds_silver")     # where to WRITE the tables
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("pop_table", "search_property_popularity")
dbutils.widgets.text("cent_table", "search_entity_centrality")
dbutils.widgets.text("silver_catalog", "stg_feeds_silver")   # SOURCE Silver (public_properties + igdb/watchmode/podchaser)
dbutils.widgets.text("neo4j_uri", "neo4j+s://17aa0e8d.databases.neo4j.io")   # the 44k :Entity graph (pagerank)
dbutils.widgets.text("scope", "feedsai_staging")        # secret scope holding neo4j_password
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "pop_table", "cent_table", "silver_catalog", "neo4j_uri", "scope")}
POP = f"{C['catalog']}.{C['schema']}.{C['pop_table']}"
CENT = f"{C['catalog']}.{C['schema']}.{C['cent_table']}"
S = C["silver_catalog"]
print("popularity :", POP, "| centrality :", CENT, "| silver:", S, "| graph:", C["neo4j_uri"])

# COMMAND ----------
# ===================== 1. search_property_popularity =====================
# base = the developer's extraction SQL VERBATIM (game_hypes / popularity_percentile / powerScore).
spark.sql(f"""
CREATE OR REPLACE TABLE {POP} AS
WITH base AS (
  -- GAMES  (media_source_id=1=IGDB ; popularity=game_hypes ; recency=game_first_release_date)
  SELECT p.id AS property_id, 'game' AS vertical, CAST(p.media_source_guid AS STRING) AS media_source_guid,
         p.media_source_id, p.media_type_id, p.name,
         CAST(g.game_hypes AS DOUBLE) AS raw_popularity,
         CASE WHEN g.igdb_game_id IS NOT NULL THEN 'hype_count' ELSE 'null_source' END AS pop_source,
         CAST(g.game_first_release_date AS DATE) AS recency_date,
         CAST(g.game_combined_rating_count AS BIGINT) AS game_rating_count
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.igdb.core_games_extended g
    ON CAST(g.igdb_game_id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 1 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 1
  UNION ALL
  -- MOVIES  (2=Watchmode ; popularity_percentile ; release_date)
  SELECT p.id, 'movie', CAST(p.media_source_guid AS STRING), p.media_source_id, p.media_type_id, p.name,
         CAST(w.popularity_percentile AS DOUBLE),
         CASE WHEN w.id IS NOT NULL THEN 'popularity_percentile' ELSE 'null_source' END,
         CAST(w.release_date AS DATE), CAST(NULL AS BIGINT)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 2 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 3
  UNION ALL
  -- TV  (3=Watchmode ; popularity_percentile ; release_date)
  SELECT p.id, 'tv', CAST(p.media_source_guid AS STRING), p.media_source_id, p.media_type_id, p.name,
         CAST(w.popularity_percentile AS DOUBLE),
         CASE WHEN w.id IS NOT NULL THEN 'popularity_percentile' ELSE 'null_source' END,
         CAST(w.release_date AS DATE), CAST(NULL AS BIGINT)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 3 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 4
  UNION ALL
  -- PODCASTS  (4=Podchaser ; powerScore ; latestEpisodeDate)
  SELECT p.id, 'podcast', CAST(p.media_source_guid AS STRING), p.media_source_id, p.media_type_id, p.name,
         CAST(pc.powerScore AS DOUBLE),
         CASE WHEN pc.id IS NOT NULL THEN 'power_score' ELSE 'null_source' END,
         CAST(pc.latestEpisodeDate AS DATE), CAST(NULL AS BIGINT)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.podchaser.core_podcasts_extended pc
    ON CAST(pc.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 4 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 5
),
nn AS (
  -- percentile over NON-NULL raw only, within (vertical, pop_source). CUME_DIST = count(≤x)/N (method=max):
  -- group max -> 1.0, ties share the top rank. NULL raw rows are excluded here and default to 0.0 below.
  SELECT property_id,
         CUME_DIST() OVER (PARTITION BY vertical, pop_source ORDER BY raw_popularity) AS pct
  FROM base
  WHERE raw_popularity IS NOT NULL
)
SELECT b.property_id, b.name, b.vertical, b.media_source_guid, b.media_source_id, b.media_type_id,
       b.raw_popularity, b.pop_source, b.recency_date, b.game_rating_count,
       ROUND(COALESCE(nn.pct, 0.0), 6) AS popularity_pct,   -- the value ranking uses (0..1)
       -- dedup_key: composite identity "{guid}:{media_source_id|NA}:{media_type_id|NA}"; NULL if guid NULL
       CASE WHEN b.media_source_guid IS NULL THEN NULL
            ELSE concat_ws(':', b.media_source_guid,
                           coalesce(cast(b.media_source_id AS string), 'NA'),
                           coalesce(cast(b.media_type_id AS string), 'NA')) END AS dedup_key
FROM base b
LEFT JOIN nn ON b.property_id = nn.property_id
""")
print("built", POP)

# COMMAND ----------
# ===================== 2. search_entity_centrality (CUME_DIST of :Entity.pagerank within vertical) =====================
from neo4j import GraphDatabase
PWD = dbutils.secrets.get(C["scope"], "neo4j_password")
CYPHER = """
MATCH (e:Entity)
WHERE e.property_id IS NOT NULL AND e.pagerank IS NOT NULL
RETURN toInteger(e.property_id) AS property_id, toString(e.vertical) AS vertical, toFloat(e.pagerank) AS pagerank
"""
drv = GraphDatabase.driver(C["neo4j_uri"], auth=("neo4j", PWD))
with drv.session() as s:
    crows = [(r["property_id"], r["vertical"], r["pagerank"]) for r in s.run(CYPHER)]
drv.close()
print("centrality nodes read:", len(crows))

from pyspark.sql.types import StructType, StructField, LongType, StringType, DoubleType
_CS = StructType([StructField("property_id", LongType()), StructField("vertical", StringType()),
                  StructField("pagerank", DoubleType())])
cdf = (spark.createDataFrame(crows, _CS)
       .dropna(subset=["property_id", "pagerank"]).dropDuplicates(["property_id"]))
cdf.createOrReplaceTempView("_search_cent_src")
spark.sql(f"""
CREATE OR REPLACE TABLE {CENT} AS
SELECT property_id, vertical, pagerank,
       -- centrality_pct: CUME_DIST of pagerank within vertical (method=max) — the value ranking uses (0..1).
       -- (Podcasts sit at the pagerank floor -> ~degenerate; ranking.py zeroes podcast centrality anyway.)
       ROUND(CUME_DIST() OVER (PARTITION BY vertical ORDER BY pagerank), 6) AS centrality_pct
FROM _search_cent_src
""")
print("built", CENT)

# COMMAND ----------
# ===================== verify =====================
display(spark.sql(f"""
  SELECT vertical, count(*) AS n, round(avg(popularity_pct), 3) AS avg_pop,
         sum(CASE WHEN pop_source = 'null_source' THEN 1 ELSE 0 END) AS null_src,
         sum(CASE WHEN dedup_key IS NULL THEN 1 ELSE 0 END) AS null_dedup
  FROM {POP} GROUP BY vertical ORDER BY vertical
"""))
display(spark.sql(f"""
  SELECT vertical, count(*) AS n, round(avg(centrality_pct), 3) AS avg_cent,
         round(min(centrality_pct), 3) AS mn, round(max(centrality_pct), 3) AS mx
  FROM {CENT} GROUP BY vertical ORDER BY vertical
"""))
display(spark.sql(f"""
  SELECT property_id, name, vertical, round(popularity_pct,4) AS pop, dedup_key
  FROM {POP} WHERE vertical = 'game' ORDER BY popularity_pct DESC LIMIT 10
"""))
