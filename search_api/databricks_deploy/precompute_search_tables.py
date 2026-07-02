# Databricks notebook source
# MAGIC %md
# MAGIC # E4 Search — precompute `search_property_popularity`  (part of the E4 bundle)
# MAGIC Builds the popularity + recency table that E4's `store.py` reads when `SEARCH_DATA_SOURCE=live`.
# MAGIC Source = the client's per-vertical query over the Silver source tables (igdb / watchmode / podchaser)
# MAGIC joined to `public_properties`, wrapped with:
# MAGIC   • **`popularity_pct`** = per-vertical `PERCENT_RANK` × 100 — normalizes the mixed raw units
# MAGIC     (games=`hype_count`, movies/TV=`popularity_percentile`, podcasts=`power_score`) to a 0–100 scale.
# MAGIC   • **`dedup_key`** = normalized name — lets the search ranker collapse duplicate titles.
# MAGIC
# MAGIC Output columns match `store.py`'s live query: `property_id, name, vertical, popularity_pct, recency_date,
# MAGIC dedup_key` (plus `raw_popularity`/`pop_source`/`media_source_guid` for debugging).
# MAGIC
# MAGIC NOTE: **centrality** (`search_entity_centrality`) is a SEPARATE graph precompute — GDS PageRank over the
# MAGIC `*SimilarTo` edges (IGDBGameSimilarTo / WatchmodeTitleSimilarTo). Not built here (fast-follow); E4 serves
# MAGIC with neutral centrality until it exists. `StreamsCharts_Channel` is not an E4 vertical → excluded.
# MAGIC
# MAGIC Run this (once, and on a refresh cadence) BEFORE/with `deploy_search_endpoint.py`.

# COMMAND ----------
dbutils.widgets.text("catalog", "stg_feeds_silver")     # where to WRITE the precompute table
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("pop_table", "search_property_popularity")
dbutils.widgets.text("silver_catalog", "stg_feeds_silver")   # SOURCE Silver (public_properties + igdb/watchmode/podchaser)
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "pop_table", "silver_catalog")}
OUT = f"{C['catalog']}.{C['schema']}.{C['pop_table']}"
S = C["silver_catalog"]
print("source silver :", S)
print("writing table :", OUT)

# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE TABLE {OUT} AS
WITH base AS (
  -- GAMES  (media_source_id=1=IGDB ; popularity=game_hypes ; recency=game_first_release_date)
  SELECT p.id AS property_id, 'game' AS vertical, CAST(p.media_source_guid AS STRING) AS media_source_guid,
         p.media_source_id, p.media_type_id, p.name,
         CAST(g.game_hypes AS DOUBLE) AS raw_popularity,
         CASE WHEN g.igdb_game_id IS NOT NULL THEN 'hype_count' ELSE 'null_source' END AS pop_source,
         CAST(g.game_first_release_date AS DATE) AS recency_date
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
         CAST(w.release_date AS DATE)
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
         CAST(w.release_date AS DATE)
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
         CAST(pc.latestEpisodeDate AS DATE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.podchaser.core_podcasts_extended pc
    ON CAST(pc.id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 4 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 5
)
SELECT
  property_id, name, vertical, media_source_guid, media_source_id, media_type_id,
  raw_popularity, pop_source, recency_date,
  -- popularity_pct: per-vertical PERCENT_RANK (0..100). Highest raw -> ~100; null_source -> ~0.
  ROUND(100 * PERCENT_RANK() OVER (PARTITION BY vertical ORDER BY raw_popularity ASC), 4) AS popularity_pct,
  -- dedup_key: normalized name so the ranker can collapse duplicate titles across sources
  lower(trim(regexp_replace(coalesce(name, ''), '[^A-Za-z0-9]+', ' '))) AS dedup_key
FROM base
""")
print("built", OUT)

# COMMAND ----------
# ── verify: per-vertical counts + how many rows had no popularity source, and a sample top-N ──
display(spark.sql(f"""
  SELECT vertical, count(*) AS n,
         round(avg(popularity_pct), 1) AS avg_pct,
         sum(CASE WHEN pop_source = 'null_source' THEN 1 ELSE 0 END) AS null_pop
  FROM {OUT} GROUP BY vertical ORDER BY vertical
"""))
display(spark.sql(f"""
  SELECT property_id, name, vertical, popularity_pct, recency_date, dedup_key
  FROM {OUT} WHERE vertical = 'game' ORDER BY popularity_pct DESC LIMIT 10
"""))
