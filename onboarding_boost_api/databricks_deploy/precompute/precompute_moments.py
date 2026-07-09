# Databricks notebook source
# MAGIC %md
# MAGIC # UC8 Onboarding Boost — moment signal precompute  (`boost_property_moments`)
# MAGIC Builds the **S7 moment-richness** signal the boost engine hard-gates on (`moment_count > 0`) and
# MAGIC weights 16%. None of UC6's `adaptive_property_*` tables carry moment activity, so this owns it.
# MAGIC
# MAGIC **Id-space bridge (do not simplify):** moments are keyed by the PUBLIC id; the corpus + all other
# MAGIC signals are keyed by the EXTERNAL id (`media_source_guid`). The valid join is
# MAGIC `public_moments.property_id → public_properties.id → public_properties.media_source_guid (= external)`.
# MAGIC The output is keyed by the EXTERNAL id so it joins 1:1 to the corpus / `adaptive_property_*`.
# MAGIC
# MAGIC **Writes** `{catalog}.{schema}.boost_property_moments(entity_id, property_id, profile_key,
# MAGIC media_source_guid, vertical, moment_count, recent_count, last_event_at, velocity, richness, trending)` —
# MAGIC keyed by `entity_id` (twin-safe; `property_id` = bare guid kept for back-compat). richness/trending are
# MAGIC WITHIN-VERTICAL **tie-aware average-rank** percentiles (SPEC §5d — NOT percent_rank: 7,169 of 8,170
# MAGIC podcasts tie on velocity, and min-rank ties would crater the whole cluster to ~0 instead of ~0.5,
# MAGIC emptying the podcast gap-fill gate at the 0.5 floor).
# MAGIC Run BEFORE `deploy_onboarding_boost_endpoint.py`. Idempotent (CREATE OR REPLACE).

# COMMAND ----------
# MAGIC %run ../../../graph/utils/workspace_catalog

# COMMAND ----------
# MAGIC %run ../../../foundation/_endpoint_env

# COMMAND ----------
# env auto-resolved (catalog · schema · silver) from the workspace; a Job can override the widgets.
dbutils.widgets.text("catalog", CATALOG)          # WHERE to write boost_property_moments
dbutils.widgets.text("schema", SCHEMA)
dbutils.widgets.text("silver_catalog", CATALOG)   # SOURCE Silver (public_moments + public_properties)
dbutils.widgets.text("moments_table", "feedspostgres.public_moments")       # property_id(public), event_starts_at
dbutils.widgets.text("props_table",   "feedspostgres.public_properties")    # id(public), media_source_guid, media_type_id
dbutils.widgets.text("recent_days", "90")
C = {k: dbutils.widgets.get(k) for k in ("catalog", "schema", "silver_catalog", "moments_table", "props_table", "recent_days")}
NS = f"{C['catalog']}.{C['schema']}"
S = C["silver_catalog"]
TARGET = f"{NS}.boost_property_moments"
RECENT_DAYS = int(C["recent_days"])
print("writing:", TARGET, "| silver:", S, "| recent_days:", RECENT_DAYS)

# COMMAND ----------
from pyspark.sql import functions as F, Window

# media_type_id -> vertical (verified from public_properties)
_MT2VERT = F.create_map(*sum(([F.lit(int(k)), F.lit(v)] for k, v in
                              {1: "game", 3: "movie", 4: "tv", 5: "podcast"}.items()), []))

# bridge: public id -> external id (media_source_guid) + vertical + entity_id/profile_key (SPEC §5 keying)
_V2PREFIX = F.create_map(F.lit("game"), F.lit("Game"), F.lit("movie"), F.lit("Movie"),
                         F.lit("tv"), F.lit("TV"), F.lit("podcast"), F.lit("Podcast"))
_V2PK = F.create_map(F.lit("game"), F.lit("igdb_property_game"), F.lit("movie"), F.lit("watchmode_property_movie"),
                     F.lit("tv"), F.lit("watchmode_property_tv"), F.lit("podcast"), F.lit("podchaser_property_podcast"))
bridge = (spark.table(f"{S}.{C['props_table']}")
          .select(F.col("id").cast("long").alias("public_id"),
                  F.col("media_source_guid").cast("string").alias("media_source_guid"),
                  F.col("media_source_guid").cast("long").alias("property_id"),   # EXTERNAL id (back-compat)
                  _MT2VERT[F.col("media_type_id").cast("int")].alias("vertical"))
          .where(F.col("media_source_guid").isNotNull() & F.col("vertical").isNotNull())
          .withColumn("entity_id", F.concat(_V2PREFIX[F.col("vertical")], F.lit(":"), F.col("media_source_guid")))
          .withColumn("profile_key", _V2PK[F.col("vertical")])
          .dropDuplicates(["public_id"]))

# moments joined to the bridge -> per (external, vertical) aggregates
moments = (spark.table(f"{S}.{C['moments_table']}")
           .select(F.col("property_id").cast("long").alias("public_id"),
                   F.to_timestamp("event_starts_at").alias("event_ts"))
           .join(bridge, "public_id", "inner"))

_cutoff = F.date_sub(F.current_timestamp(), RECENT_DAYS)
agg = (moments.groupBy("entity_id", "profile_key", "media_source_guid", "property_id", "vertical")
       .agg(F.count(F.lit(1)).alias("moment_count"),
            F.sum(F.when(F.col("event_ts") >= _cutoff, 1).otherwise(0)).alias("recent_count"),
            F.max("event_ts").alias("last_event_at"))
       .where(F.col("moment_count") > 0)
       .withColumn("velocity", F.lit(0.6) * F.log1p("moment_count") + F.lit(1.0) * F.log1p("recent_count")))

# within-vertical TIE-AWARE AVERAGE-rank percentile (SPEC §5d): equal value => equal (average) pct.
def _tie_avg_pct(value_col, out_col, df):
    w_rn  = Window.partitionBy("vertical").orderBy(F.col(value_col).asc(), F.col("entity_id").asc())
    w_tie = Window.partitionBy("vertical", value_col)
    w_all = Window.partitionBy("vertical")
    return (df.withColumn("_rn", F.row_number().over(w_rn))
              .withColumn("_avg_rn", F.avg("_rn").over(w_tie))
              .withColumn("_n", F.count(F.lit(1)).over(w_all))
              .withColumn(out_col, F.round(F.when(F.col("_n") > 1,
                                                  (F.col("_avg_rn") - 1.0) / (F.col("_n") - 1.0))
                                            .otherwise(F.lit(1.0)), 6))
              .drop("_rn", "_avg_rn", "_n"))

out = _tie_avg_pct("velocity", "richness", agg)
out = _tie_avg_pct("recent_count", "trending", out)
out = out.select("entity_id", "property_id", "profile_key", "media_source_guid", "vertical",
                 "moment_count", "recent_count", "last_event_at",
                 F.round("velocity", 6).alias("velocity"), "richness", "trending")

out.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET)
print(f"wrote {TARGET}: {spark.table(TARGET).count():,} active properties")

# COMMAND ----------
# coverage report — confirm every vertical can fill a gap with active content (richness > 0.5)
display(spark.sql(f"""
  SELECT vertical, count(*) AS active,
         sum(CASE WHEN richness > 0.5 THEN 1 ELSE 0 END) AS rich_gt_half,
         max(moment_count) AS max_cnt, max(recent_count) AS max_recent
  FROM {TARGET} GROUP BY vertical ORDER BY vertical"""))
# podcast tie-cluster sanity: the dominant velocity tie must sit NEAR 0.5 (avg-rank), not near 0 (min-rank)
display(spark.sql(f"""
  SELECT velocity, count(*) AS n, round(min(richness),4) AS richness
  FROM {TARGET} WHERE vertical = 'podcast' GROUP BY velocity ORDER BY n DESC LIMIT 3"""))
