import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- PostgreSQL ---
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "feedsai_poc")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# --- Voyage AI ---
VOYAGE_MODEL = "voyage-4-large"
EMBEDDING_DIMENSION = 1024

# --- Groq / LLM ---
GROQ_MODEL = "llama-3.3-70b-versatile"

# --- Qdrant ---
QDRANT_COLLECTION = "feedsai_entities"

# --- Data Paths ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
COMPOSITIONS_PATH = os.path.join(DATA_DIR, "all_compositions.json")
PROFILES_PATH = os.path.join(DATA_DIR, "entity_profiles_final.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")

# --- Hybrid Scoring Weights ---
VECTOR_WEIGHT = 0.7
BM25_WEIGHT = 0.3
BOTH_SET_BONUS = 0.1
FRANCHISE_BOOST = 0.15
TOP_K_RETRIEVAL = 20
TOP_K_RESULTS = 10

# --- Verticals ---
VALID_VERTICALS = {"game", "movie", "tv_show"}
