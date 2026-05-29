# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # 01 — Setup Catalog, Schema & Delta Tables
# MAGIC
# MAGIC **Run this once** before anything else.
# MAGIC
# MAGIC Prerequisites:
# MAGIC - An existing Unity Catalog **catalog** (use an existing one or ask your admin to create one).
# MAGIC - `CREATE SCHEMA` privilege on that catalog.
# MAGIC
# MAGIC What this notebook creates:
# MAGIC - Schema `{CATALOG}.feedsai`
# MAGIC - Delta table `{CATALOG}.feedsai.entities`  — with Change Data Feed enabled (required for Vector Search Delta Sync)
# MAGIC - Delta table `{CATALOG}.feedsai.query_history`

# COMMAND ----------

# ── CONFIGURE YOUR SANDBOX HERE ──────────────────────────────────────
CATALOG = "dev_feeds_silver_infotech"
SCHEMA  = "feedsai"       # Schema that will be created inside the catalog
# ─────────────────────────────────────────────────────────────────────

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
print(f"Schema ready: {CATALOG}.{SCHEMA}")

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
    embedding        ARRAY<FLOAT>
)
USING DELTA
TBLPROPERTIES (
    delta.enableChangeDataFeed = true,
    delta.columnMapping.mode   = 'name'
)
""")
print(f"Table ready: {CATALOG}.{SCHEMA}.entities")

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
print(f"Table ready: {CATALOG}.{SCHEMA}.query_history")

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}"))
