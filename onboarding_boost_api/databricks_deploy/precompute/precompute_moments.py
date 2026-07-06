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
# MAGIC **Writes** `{catalog}.{schema}.boost_property_moments(property_id, vertical, moment_count, recent_count,
# MAGIC last_event_at, velocity, richness, trending)` — richness/trending are WITHIN-VERTICAL percentiles.
# MAGIC Run BEFORE `deploy_onboarding_boost_endpoint.py`. Idempotent (CREATE OR REPLACE).

# COMMAND ----------
# env (widgets — staging-hardcoded; a Job can override). Deploy repo has no workspace_catalog helper.
dbutils.widgets.text("catalog", "stg_feeds_silver")          # WHERE to write boost_property_moments
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("silver_catalog", "stg_feeds_silver")   # SOURCE Silver (public_moments + public_properties)
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

# bridge: public id -> external id (media_source_guid) + vertical
bridge = (spark.table(f"{S}.{C['props_table']}")
          .select(F.col("id").cast("long").alias("public_id"),
                  F.col("media_source_guid").cast("long").alias("property_id"),   # EXTERNAL id
                  _MT2VERT[F.col("media_type_id").cast("int")].alias("vertical"))
          .where(F.col("property_id").isNotNull() & F.col("vertical").isNotNull())
          .dropDuplicates(["public_id"]))

# moments joined to the bridge -> per (external, vertical) aggregates
moments = (spark.table(f"{S}.{C['moments_table']}")
           .select(F.col("property_id").cast("long").alias("public_id"),
                   F.to_timestamp("event_starts_at").alias("event_ts"))
           .join(bridge, "public_id", "inner"))

_cutoff = F.date_sub(F.current_timestamp(), RECENT_DAYS)
agg = (moments.groupBy("property_id", "vertical")
       .agg(F.count(F.lit(1)).alias("moment_count"),
            F.sum(F.when(F.col("event_ts") >= _cutoff, 1).otherwise(0)).alias("recent_count"),
            F.max("event_ts").alias("last_event_at"))
       .where(F.col("moment_count") > 0)
       .withColumn("velocity", F.lit(0.6) * F.log1p("moment_count") + F.lit(1.0) * F.log1p("recent_count")))

# within-vertical rank-percentile (matches the runtime's centrality/richness convention)
_wv_rich  = Window.partitionBy("vertical").orderBy(F.col("velocity").asc())
_wv_trend = Window.partitionBy("vertical").orderBy(F.col("recent_count").asc())
out = (agg
       .withColumn("richness", F.round(F.percent_rank().over(_wv_rich), 6))
       .withColumn("trending", F.round(F.percent_rank().over(_wv_trend), 6))
       .select("property_id", "vertical", "moment_count", "recent_count",
               "last_event_at", F.round("velocity", 6).alias("velocity"), "richness", "trending"))

out.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET)
print(f"wrote {TARGET}: {spark.table(TARGET).count():,} active properties")

# COMMAND ----------
# coverage report — confirm every vertical can fill a gap with active content (richness > 0.5)
display(spark.sql(f"""
  SELECT vertical, count(*) AS active,
         sum(CASE WHEN richness > 0.5 THEN 1 ELSE 0 END) AS rich_gt_half,
         max(moment_count) AS max_cnt, max(recent_count) AS max_recent
  FROM {TARGET} GROUP BY vertical ORDER BY vertical"""))
