import os
from pathlib import Path

from dotenv import load_dotenv

# Pin to vector/.env explicitly so DATABRICKS_TOKEN / DATABRICKS_EMBEDDING_ENDPOINT load regardless of cwd
# (07a finding: a bare load_dotenv() only found it when started from vector/).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()  # also honor a cwd .env if present (no-op override)

# --- API Keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")               # legacy / unused (NLU moved to Databricks)

# --- Databricks Foundation Model (the ONLY LLM; same endpoint the router uses) ---
# Secrets live in the gitignored vector/.env (copied from router/.env, never echoed/committed).
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
DATABRICKS_LLM_ENDPOINT = os.getenv(
    "DATABRICKS_LLM_ENDPOINT",
    "https://dbc-f79d5cae-0d05.cloud.databricks.com/serving-endpoints/"
    "llama_v3_3_70b_instruct_Ishaan/invocations",
)
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "120"))

# --- PostgreSQL ---
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "feedsai_poc")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# --- Embeddings (Databricks Qwen, OpenAI-compatible llm/v1/embeddings interface) ---
# Replaces Voyage. Same 1024-dim space → the Vector Search index / parquet must be REBUILT with this
# model (vectors from two different models are not comparable). Auth reuses DATABRICKS_TOKEN above.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding-0-6b")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
DATABRICKS_EMBEDDING_ENDPOINT = os.getenv(
    "DATABRICKS_EMBEDDING_ENDPOINT",
    "https://dbc-f79d5cae-0d05.cloud.databricks.com/serving-endpoints/"
    "qwen3-embedding-0-6b/invocations",                # ← set to your real Qwen endpoint
)
EMBEDDING_TIMEOUT_S = float(os.getenv("EMBEDDING_TIMEOUT_S", "120"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))
# Qwen3-Embedding improves retrieval when the QUERY (not the document) carries a task instruction.
# Leave empty if the served endpoint already applies it; otherwise set e.g.
# "Given a web search query, retrieve relevant entertainment titles". Documents are never prefixed.
EMBEDDING_QUERY_INSTRUCTION = os.getenv("EMBEDDING_QUERY_INSTRUCTION", "")

# --- Groq / LLM ---
GROQ_MODEL = "llama-3.3-70b-versatile"

# --- Qdrant ---
QDRANT_COLLECTION = "feedsai_entities"

# --- Data Paths ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_v2")
COMPOSITIONS_PATH = os.path.join(DATA_DIR, "all_compositions_v2.json")
PROFILES_PATH = os.path.join(DATA_DIR, "entity_profiles_v2.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")

# --- Hybrid Scoring Weights ---
VECTOR_WEIGHT = 0.7
BM25_WEIGHT = 0.3
BOTH_SET_BONUS = 0.1
FRANCHISE_BOOST = 0.15
TOP_K_RETRIEVAL = 20
TOP_K_RESULTS = 10

# --- Verticals ---
VALID_VERTICALS = {"game", "movie", "tv", "podcast"}
