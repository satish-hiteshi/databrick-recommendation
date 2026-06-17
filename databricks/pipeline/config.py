import os

# Qwen embeddings via a Databricks serving endpoint (OpenAI-compatible llm/v1/embeddings).
# Called by name through the mlflow deploy client (same pattern as LLM_ENDPOINT), so no API key.
EMBEDDING_ENDPOINT  = os.getenv("FEEDSAI_EMBEDDING_ENDPOINT", "qwen3-embedding-0-6b")
EMBEDDING_DIMENSION = 1024

LLM_ENDPOINT = os.getenv("FEEDSAI_LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")

DATABRICKS_HOST  = os.getenv("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

CATALOG        = os.getenv("FEEDSAI_CATALOG", "dev_feeds_silver_infotech")
SCHEMA         = os.getenv("FEEDSAI_SCHEMA",  "feedsai")
ENTITIES_TABLE = f"{CATALOG}.{SCHEMA}.entities"
HISTORY_TABLE  = f"{CATALOG}.{SCHEMA}.query_history"

VS_ENDPOINT = os.getenv("FEEDSAI_VS_ENDPOINT", "feedsai-vs-endpoint")
VS_INDEX    = f"{ENTITIES_TABLE}_vs_index"

SQL_WAREHOUSE_HTTP_PATH = os.getenv("FEEDSAI_SQL_HTTP_PATH", "")

TOP_K_RETRIEVAL = 20
TOP_K_RESULTS   = 10
VALID_VERTICALS = {"game", "movie", "tv", "podcast"}
