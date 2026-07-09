# Databricks notebook source
# MAGIC %md
# MAGIC # E4 Search — precompute `search_property_popularity` + `search_entity_centrality`  (part of the E4 bundle)
# MAGIC Builds the two tables `store.py` reads when `SEARCH_DATA_SOURCE=live`, per **PRECOMPUTE_SPEC §5b/§5c**
# MAGIC (one popularity computation shared with E6/E8 — bit-identical values, E4 just adds recency/dedup extras):
# MAGIC   • **`popularity_pct`** = WITHIN-VERTICAL **tie-aware average-rank percentile** over rows with raw>0
# MAGIC     (equal raw ⇒ equal pct); raw NULL/≤0 → 0.0. Sources: game = igdb `combined_rating_count`, fallback
# MAGIC     `game_hypes` (`pop_source` labels which); movie/tv = watchmode `popularity_percentile`; podcast =
# MAGIC     podchaser `powerScore` — ⋈ `public_properties`.
# MAGIC   • **`dedup_key`** = `"{media_source_guid}:{media_source_id|NA}:{media_type_id|NA}"` (NULL if guid NULL).
# MAGIC   • **`centrality_pct`** = tie-aware average-rank percentile of the re-keyed Aura `:Entity.pagerank`
# MAGIC     within vertical, + raw `pagerank`/`degree`/`community` columns (SPEC §5c).
# MAGIC Both tables carry `entity_id` ("<Vertical>:<media_source_guid>", twin-safe) + `profile_key`; store.py
# MAGIC already keys rows by entity_id (`_row_entity_id`). Run BEFORE/with `deploy_search_endpoint.py`.

# COMMAND ----------
# MAGIC %pip install neo4j
# MAGIC # (%pip install auto-restarts Python; neo4j is importable below)

# COMMAND ----------
# MAGIC %run ../../graph/utils/workspace_catalog

# COMMAND ----------
# MAGIC %run ../../foundation/_endpoint_env

# COMMAND ----------
# env (catalog · silver · neo4j · scope) auto-resolved from the workspace via workspace_catalog + _endpoint_env.
dbutils.widgets.text("catalog", CATALOG)                # where to WRITE the tables
dbutils.widgets.text("schema", SCHEMA)
dbutils.widgets.text("pop_table", "search_property_popularity")
dbutils.widgets.text("cent_table", "search_entity_centrality")
dbutils.widgets.text("silver_catalog", CATALOG)   # SOURCE Silver (public_properties + igdb/watchmode/podchaser)
dbutils.widgets.text("neo4j_uri", NEO4J_URI)   # the 44k :Entity graph (pagerank)
dbutils.widgets.text("scope", SCOPE)        # secret scope holding neo4j_password
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
  -- GAMES  (media_source_id=1=IGDB ; popularity=combined_rating_count, fallback game_hypes ; recency=first_release)
  SELECT concat('Game:', CAST(p.media_source_guid AS STRING)) AS entity_id,
         'igdb_property_game' AS profile_key,
         p.id AS property_id, 'game' AS vertical, CAST(p.media_source_guid AS STRING) AS media_source_guid,
         p.media_source_id, p.media_type_id, p.name,
         COALESCE(NULLIF(CAST(g.game_combined_rating_count AS DOUBLE), 0.0),
                  CAST(g.game_hypes AS DOUBLE)) AS raw_popularity,
         CASE WHEN NULLIF(CAST(g.game_combined_rating_count AS DOUBLE), 0.0) IS NOT NULL
              THEN 'combined_rating_count'
              WHEN g.game_hypes IS NOT NULL THEN 'game_hypes' ELSE 'null_source' END AS pop_source,
         CAST(g.game_first_release_date AS DATE) AS recency_date,
         CAST(g.game_combined_rating_count AS BIGINT) AS game_rating_count
  FROM {S}.feedspostgres.public_properties p
  LEFT JOIN {S}.igdb.core_games_extended g
    ON CAST(g.igdb_game_id AS STRING) = CAST(p.media_source_guid AS STRING)
   AND p.media_source_id = 1 AND p.media_source_id IS NOT NULL
  WHERE p.media_type_id = 1
  UNION ALL
  -- MOVIES  (2=Watchmode ; popularity_percentile ; release_date)
  SELECT concat('Movie:', CAST(p.media_source_guid AS STRING)), 'watchmode_property_movie',
         p.id, 'movie', CAST(p.media_source_guid AS STRING), p.media_source_id, p.media_type_id, p.name,
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
  SELECT concat('TV:', CAST(p.media_source_guid AS STRING)), 'watchmode_property_tv',
         p.id, 'tv', CAST(p.media_source_guid AS STRING), p.media_source_id, p.media_type_id, p.name,
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
  SELECT concat('Podcast:', CAST(p.media_source_guid AS STRING)), 'podchaser_property_podcast',
         p.id, 'podcast', CAST(p.media_source_guid AS STRING), p.media_source_id, p.media_type_id, p.name,
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
  -- tie-aware AVERAGE-rank percentile over raw>0, within vertical (SPEC §5b — same computation as the
  -- E6/E8 popularity tables, so values are bit-identical). Equal raw ⇒ equal pct; raw NULL/≤0 → 0.0 below.
  SELECT entity_id,
         ROUND(CASE WHEN n_pos > 1 THEN (avg_rn - 1.0) / (n_pos - 1.0) ELSE 1.0 END, 6) AS pct
  FROM (SELECT entity_id,
               AVG(rn)  OVER (PARTITION BY vertical, raw_popularity) AS avg_rn,
               COUNT(*) OVER (PARTITION BY vertical) AS n_pos
        FROM (SELECT entity_id, vertical, raw_popularity,
                     ROW_NUMBER() OVER (PARTITION BY vertical ORDER BY raw_popularity) AS rn
              FROM base WHERE raw_popularity > 0) t0) t
)
SELECT b.entity_id, b.profile_key, b.property_id, b.name, b.vertical, b.media_source_guid,
       b.media_source_id, b.media_type_id,
       b.raw_popularity, b.pop_source, b.recency_date, b.game_rating_count,
       ROUND(COALESCE(nn.pct, 0.0), 6) AS popularity_pct,   -- the value ranking uses (0..1)
       -- dedup_key: composite identity  guid : media_source_id(or NA) : media_type_id(or NA) ; NULL when guid is NULL
       CASE WHEN b.media_source_guid IS NULL THEN NULL
            ELSE concat_ws(':', b.media_source_guid,
                           coalesce(cast(b.media_source_id AS string), 'NA'),
                           coalesce(cast(b.media_type_id AS string), 'NA')) END AS dedup_key
FROM base b
LEFT JOIN nn ON b.entity_id = nn.entity_id
""")
print("built", POP)

# COMMAND ----------
# ===================== 2. search_entity_centrality (tie-avg pct of :Entity.pagerank within vertical) =====================
# RE-KEYED graph: nodes carry entity_id/profile_key/media_source_guid + GDS pagerank/degree/community —
# there is NO e.property_id (the old `WHERE e.property_id IS NOT NULL` returned 0 rows -> empty table ->
# store fell back to neutral centrality). property_id below = the bare guid (back-compat only).
from neo4j import GraphDatabase
PWD = dbutils.secrets.get(scope="feeds-default-scope", key="neo4j_password")
CYPHER = """
MATCH (e:Entity)
WHERE e.pagerank IS NOT NULL
RETURN e.entity_id AS entity_id, e.profile_key AS profile_key,
       toString(e.media_source_guid) AS media_source_guid, toString(e.vertical) AS vertical,
       toFloat(e.pagerank) AS pagerank, toFloat(e.degree) AS degree, toInteger(e.community) AS community
"""
drv = GraphDatabase.driver(C["neo4j_uri"], auth=("neo4j", PWD), max_connection_lifetime=300, liveness_check_timeout=30, connection_acquisition_timeout=30, keep_alive=True)
with drv.session() as s:
    crows = [(r["entity_id"], r["profile_key"], r["media_source_guid"], r["vertical"],
              r["pagerank"], r["degree"], r["community"]) for r in s.run(CYPHER)]
drv.close()
print("centrality nodes read:", len(crows))

from pyspark.sql.types import StructType, StructField, LongType, StringType, DoubleType
_CS = StructType([StructField("entity_id", StringType()), StructField("profile_key", StringType()),
                  StructField("media_source_guid", StringType()), StructField("vertical", StringType()),
                  StructField("pagerank", DoubleType()), StructField("degree", DoubleType()),
                  StructField("community", LongType())])
cdf = (spark.createDataFrame(crows, _CS)
       .dropna(subset=["entity_id", "pagerank"]).dropDuplicates(["entity_id"]))
cdf.createOrReplaceTempView("_search_cent_src")
spark.sql(f"""
CREATE OR REPLACE TABLE {CENT} AS
SELECT entity_id, profile_key, media_source_guid, CAST(media_source_guid AS BIGINT) AS property_id,
       vertical, pagerank, degree, community,
       -- centrality_pct: tie-aware AVERAGE-rank percentile of pagerank within vertical (SPEC §5c).
       -- (Podcasts sit at the pagerank floor -> ~degenerate; ranking.py zeroes podcast centrality anyway.)
       ROUND(CASE WHEN n_pos > 1 THEN (avg_rn - 1.0) / (n_pos - 1.0) ELSE 1.0 END, 6) AS centrality_pct
FROM (SELECT *,
             AVG(rn)  OVER (PARTITION BY vertical, pagerank) AS avg_rn,
             COUNT(*) OVER (PARTITION BY vertical) AS n_pos
      FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY vertical ORDER BY pagerank) AS rn
            FROM _search_cent_src) t0) t
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
  SELECT entity_id, name, vertical, round(popularity_pct,4) AS pop, dedup_key
  FROM {POP} WHERE vertical = 'game' ORDER BY popularity_pct DESC LIMIT 10
"""))
# twin check: guid 119163 must be 2 distinct rows (Game + Movie) in both tables
display(spark.sql(f"SELECT entity_id, vertical, popularity_pct FROM {POP} WHERE media_source_guid='119163' ORDER BY entity_id"))
display(spark.sql(f"SELECT entity_id, vertical, centrality_pct FROM {CENT} WHERE media_source_guid='119163' ORDER BY entity_id"))
