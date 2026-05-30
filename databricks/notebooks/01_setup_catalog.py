# Databricks notebook source

# COMMAND ----------

CATALOG = "dev_feeds_silver_infotech"
SCHEMA  = "feedsai"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
print(f"Schema: {CATALOG}.{SCHEMA}")

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.entities (
    entity_id        STRING NOT NULL,
    name             STRING NOT NULL,
    vertical         STRING NOT NULL,
    description      STRING,
    composed_text    STRING,
    bm25_keywords    ARRAY<STRING>,
    canonical_genres ARRAY<STRING>,
    themes           ARRAY<STRING>,
    franchise        STRING,
    developer        STRING,
    publisher        STRING,
    directors        ARRAY<STRING>,
    cast_members     ARRAY<STRING>,
    embedding        ARRAY<FLOAT>,
    release_date     STRING
)
USING DELTA
TBLPROPERTIES (
    delta.enableChangeDataFeed = true,
    delta.columnMapping.mode   = 'name'
)
""")
print(f"Table: {CATALOG}.{SCHEMA}.entities")

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.query_history (
    id            BIGINT GENERATED ALWAYS AS IDENTITY,
    query_text    STRING NOT NULL,
    parsed_intent STRING,
    results       STRING,
    latency_ms    DOUBLE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported'
)
""")
print(f"Table: {CATALOG}.{SCHEMA}.query_history")

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}"))
