# Databricks notebook source
# MAGIC %md
# MAGIC # UC8 Onboarding Boost — popularity signal precompute  (`boost_property_popularity`)
# MAGIC Builds the **S5 popularity** signal (the DOMINANT boost weight, 35%). The client ships popularity as
# MAGIC WHOLE NUMBERS on a DIFFERENT scale per vertical (game=hype_count, movie/tv=popularity_percentile,
# MAGIC podcast=power_score); fed RAW they'd swamp the other [0,1] signals, so each vertical is normalized to
# MAGIC [0,1] with the WITHIN-VERTICAL **tie-aware average-rank percentile** over rows with raw>0 (SPEC §5b —
# MAGIC equal raw ⇒ equal pct; NOT percent_rank, which puts big tie-clusters at the min rank); raw NULL/≤0 rows
# MAGIC are KEPT at 0.0. Keyed by `entity_id` ("<Vertical>:<media_source_guid>", twin-safe) with `property_id`
# MAGIC (bare guid) + `profile_key` + `media_source_guid` + `vertical` for back-compat.
# MAGIC Game raw = `combined_rating_count`, fallback `game_hypes` (`pop_source` labels which).
# MAGIC
# MAGIC Same Silver sources UC6's `adaptive_property_popularity` uses (igdb `game_hypes` · watchmode
# MAGIC `popularity_percentile` · podchaser `powerScore` via `public_properties`) — this table stores BOTH the
# MAGIC raw value and the normalized value, so the exact client number stays auditable. Idempotent
# MAGIC (CREATE OR REPLACE). Run BEFORE `deploy_onboarding_boost_endpoint.py` (daily-refresh cadence).

# COMMAND ----------
# MAGIC %run ../../../graph/utils/workspace_catalog

# COMMAND ----------
# MAGIC %run ../../../foundation/_endpoint_env

# COMMAND ----------
# env auto-resolved (catalog · schema · silver) from the workspace; a Job can override the widgets.
dbutils.widgets.text("catalog", CATALOG)          # WHERE to write boost_property_popularity
dbutils.widgets.text("schema", SCHEMA)
dbutils.widgets.text("silver_catalog", CATALOG)   # SOURCE Silver (public_properties + igdb/watchmode/podchaser)
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
  -- game: igdb combined_rating_count, fallback game_hypes (SPEC §5b)
  SELECT concat('Game:', CAST(p.media_source_guid AS STRING)) AS entity_id,
         'igdb_property_game' AS profile_key, CAST(p.media_source_guid AS STRING) AS media_source_guid,
         CAST(p.media_source_guid AS BIGINT) AS property_id, 'game' AS vertical,
         CASE WHEN NULLIF(CAST(g.game_combined_rating_count AS DOUBLE), 0.0) IS NOT NULL
              THEN 'combined_rating_count'
              WHEN g.game_hypes IS NOT NULL THEN 'game_hypes' ELSE 'null_source' END AS pop_source,
         COALESCE(NULLIF(CAST(g.game_combined_rating_count AS DOUBLE), 0.0),
                  CAST(g.game_hypes AS DOUBLE)) AS raw_popularity
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.igdb.core_games_extended g
    ON CAST(g.igdb_game_id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 1
  WHERE p.media_type_id = 1
  UNION ALL
  -- movie: watchmode popularity_percentile
  SELECT concat('Movie:', CAST(p.media_source_guid AS STRING)), 'watchmode_property_movie',
         CAST(p.media_source_guid AS STRING), CAST(p.media_source_guid AS BIGINT), 'movie',
         CASE WHEN w.id IS NOT NULL THEN 'popularity_percentile' ELSE 'null_source' END,
         CAST(w.popularity_percentile AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 2
  WHERE p.media_type_id = 3
  UNION ALL
  -- tv: watchmode popularity_percentile
  SELECT concat('TV:', CAST(p.media_source_guid AS STRING)), 'watchmode_property_tv',
         CAST(p.media_source_guid AS STRING), CAST(p.media_source_guid AS BIGINT), 'tv',
         CASE WHEN w.id IS NOT NULL THEN 'popularity_percentile' ELSE 'null_source' END,
         CAST(w.popularity_percentile AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.watchmode.titles_titles_extended w
    ON CAST(w.id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 3
  WHERE p.media_type_id = 4
  UNION ALL
  -- podcast: podchaser powerScore
  SELECT concat('Podcast:', CAST(p.media_source_guid AS STRING)), 'podchaser_property_podcast',
         CAST(p.media_source_guid AS STRING), CAST(p.media_source_guid AS BIGINT), 'podcast',
         CASE WHEN pc.id IS NOT NULL THEN 'power_score' ELSE 'null_source' END,
         CAST(pc.powerScore AS DOUBLE)
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.podchaser.core_podcasts_extended pc
    ON CAST(pc.id AS STRING) = CAST(p.media_source_guid AS STRING) AND p.media_source_id = 4
  WHERE p.media_type_id = 5
),
dedup AS (   -- media_source_guid can repeat across legacy rows -> one row per entity_id
  SELECT entity_id,
         MAX(profile_key) AS profile_key, MAX(media_source_guid) AS media_source_guid,
         MAX(property_id) AS property_id, MAX(vertical) AS vertical,
         MAX(pop_source) AS pop_source, MAX(raw_popularity) AS raw_popularity
  FROM base WHERE media_source_guid IS NOT NULL
  GROUP BY entity_id
),
avgd AS (    -- tie-aware AVERAGE-rank percentile over raw>0 within vertical (SPEC §5b)
  SELECT t.entity_id,
         ROUND(CASE WHEN t.n_pos > 1 THEN (AVG(t.rn) OVER (PARTITION BY t.vertical, t.raw_popularity) - 1.0)
                                          / (t.n_pos - 1.0) ELSE 1.0 END, 6) AS popularity
  FROM (SELECT entity_id, vertical, raw_popularity,
               ROW_NUMBER() OVER (PARTITION BY vertical ORDER BY raw_popularity) AS rn,
               COUNT(*)    OVER (PARTITION BY vertical) AS n_pos
        FROM dedup WHERE raw_popularity > 0) t
)
SELECT d.entity_id, d.property_id, d.profile_key, d.media_source_guid, d.vertical,
       d.pop_source, d.raw_popularity,
       COALESCE(a.popularity, 0.0) AS popularity     -- raw NULL/≤0 -> 0.0 (row KEPT)
FROM dedup d LEFT JOIN avgd a ON d.entity_id = a.entity_id
""")
print(f"wrote {TARGET}: {spark.table(TARGET).count():,} rows")

# COMMAND ----------
# per-vertical distribution sanity (min~0, max~1, plausible median)
display(spark.sql(f"""
  SELECT vertical, count(*) AS n, round(min(popularity),3) AS mn,
         round(percentile_approx(popularity,0.5),3) AS med, round(max(popularity),3) AS mx
  FROM {TARGET} GROUP BY vertical ORDER BY vertical"""))
# twin check (SPEC section 8): guid 119163 must be 2 distinct rows (Game + Movie)
display(spark.sql(f"""
  SELECT entity_id, vertical, pop_source, popularity FROM {TARGET}
  WHERE media_source_guid = '119163' ORDER BY entity_id"""))
