import os

# ── External API keys (injected as env vars via Databricks Secrets) ───
VOYAGE_API_KEY  = os.getenv("VOYAGE_API_KEY")
VOYAGE_MODEL    = "voyage-4-large"
EMBEDDING_DIMENSION = 1024

# ── LLM (Databricks Foundation Model API — no external key needed) ────
# Llama 3.3 70B is available in every Premium/Enterprise workspace via FMAPI.
LLM_ENDPOINT = os.getenv("FEEDSAI_LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")

# ── Databricks workspace (used by VS client and SQL connector) ─────────
DATABRICKS_HOST  = os.getenv("DATABRICKS_HOST", "")   # e.g. https://adb-xxxx.azuredatabricks.net
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

# ── Unity Catalog sandbox ─────────────────────────────────────────────
CATALOG = os.getenv("FEEDSAI_CATALOG", "dev_feeds_silver_infotech")
SCHEMA  = os.getenv("FEEDSAI_SCHEMA",  "feedsai")
ENTITIES_TABLE = f"{CATALOG}.{SCHEMA}.entities"
HISTORY_TABLE  = f"{CATALOG}.{SCHEMA}.query_history"

# ── Databricks Vector Search ──────────────────────────────────────────
VS_ENDPOINT = os.getenv("FEEDSAI_VS_ENDPOINT", "feedsai-vs-endpoint")
VS_INDEX    = f"{ENTITIES_TABLE}_vs_index"

# ── SQL Warehouse (for entity resolution queries in Model Serving) ─────
# HTTP path looks like: /sql/1.0/warehouses/<id>
SQL_WAREHOUSE_HTTP_PATH = os.getenv("FEEDSAI_SQL_HTTP_PATH", "")

# ── Retrieval / ranking hyper-params ──────────────────────────────────
TOP_K_RETRIEVAL = 20
TOP_K_RESULTS   = 10
VALID_VERTICALS = {"game", "movie", "tv"}
