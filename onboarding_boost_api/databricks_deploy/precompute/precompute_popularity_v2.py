# Databricks notebook source
# MAGIC %md
# MAGIC # UC8 Onboarding Boost — popularity signal precompute  (`boost_property_popularity`)
# MAGIC Builds the **S5 popularity** signal (the DOMINANT boost weight, 35%). The client ships popularity as
# MAGIC WHOLE NUMBERS on a DIFFERENT scale per vertical (game=hype_count, movie/tv=popularity_percentile,
# MAGIC podcast=power_score); fed RAW they'd swamp the other [0,1] signals, so each vertical is normalized to
# MAGIC [0,1] with a **WITHIN-VERTICAL rank-percentile** (`PERCENT_RANK`), keyed by the EXTERNAL id
# MAGIC (`media_source_guid`) so it joins 1:1 to the corpus / `adaptive_property_*` / `boost_property_moments`.
# MAGIC
# MAGIC Same Silver sources UC6's `adaptive_property_popularity` uses (igdb `game_hypes` · watchmode
# MAGIC `popularity_percentile` · podchaser `powerScore` via `public_properties`) — this table stores BOTH the
# MAGIC raw value and the normalized value, so the exact client number stays auditable. Idempotent
# MAGIC (CREATE OR REPLACE). Run BEFORE `deploy_onboarding_boost_endpoint.py` (daily-refresh cadence).

# COMMAND ----------
# env (widgets — staging-hardcoded; a Job can override). Deploy repo has no workspace_catalog helper.
dbutils.widgets.text("catalog", "stg_feeds_silver")          # WHERE to write boost_property_popularity
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("silver_catalog", "stg_feeds_silver")   # SOURCE Silver (public_properties + igdb/watchmode/podchaser)
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "silver_catalog")}
NS = f"{C['catalog']}.{C['schema']}"
S = C["silver_catalog"]
TARGET = f"{NS}.boost_property_popularity"
print("writing:", TARGET, "| silver:", S)

# COMMAND ----------
# Per-vertical PERCENT_RANK of the source popularity → [0,1], keyed by media_source_guid (the external id).
spark.sql(f"""
CREATE OR REPLACE TABLE {TARGET} AS
WITH base AS (
  -- game: igdb hype_count
  SELECT CAST(p.media_source_guid AS BIGINT) AS property_id, 'game' AS vertical, 'hype_count' AS pop_source,
         CAST(g.game_hypes AS DOUBLE) AS raw_popularity
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.igdb.core_games_extended g
    ON CAST(g.igdb_game_id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 1
  WHERE p.media_type_id = 1
  UNION ALL
  -- movie: watchmode popularity_percentile
  SELECT CAST(p.media_source_guid AS BIGINT), 'movie', 'popularity_percentile',
         CAST(w.popularity_percentile AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 2
  WHERE p.media_type_id = 3
  UNION ALL
  -- tv: watchmode popularity_percentile
  SELECT CAST(p.media_source_guid AS BIGINT), 'tv', 'popularity_percentile',
         CAST(w.popularity_percentile AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 3
  WHERE p.media_type_id = 4
  UNION ALL
  -- podcast: podchaser powerScore
  SELECT CAST(p.media_source_guid AS BIGINT), 'podcast', 'power_score',
         CAST(pc.powerScore AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.podchaser.core_podcasts_extended pc
    ON CAST(pc.id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 4
  WHERE p.media_type_id = 5
),
dedup AS (   -- media_source_guid can repeat across legacy rows -> one row per (id, vertical)
  SELECT property_id, vertical, pop_source, MAX(raw_popularity) AS raw_popularity
  FROM base WHERE property_id IS NOT NULL AND raw_popularity IS NOT NULL
  GROUP BY property_id, vertical, pop_source
)
SELECT property_id, vertical, pop_source, raw_popularity,
       -- within-vertical rank-percentile 0..1 (highest raw -> ~1). data.py reads `popularity`.
       ROUND(PERCENT_RANK() OVER (PARTITION BY vertical ORDER BY raw_popularity ASC), 6) AS popularity
FROM dedup
""")
print(f"wrote {TARGET}: {spark.table(TARGET).count():,} rows")

# COMMAND ----------
# per-vertical distribution sanity (min~0, max~1, plausible median)
display(spark.sql(f"""
  SELECT vertical, count(*) AS n, round(min(popularity),3) AS mn,
         round(percentile_approx(popularity,0.5),3) AS med, round(max(popularity),3) AS mx
  FROM {TARGET} GROUP BY vertical ORDER BY vertical"""))
