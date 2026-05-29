# Feeds.ai Entertainment Discovery Pipeline

## Project Overview
Proof of Concept for Feeds.ai — an entertainment discovery platform across games, movies, TV shows, and podcasts. The system takes a natural language question like "What movies should I watch if I liked Elden Ring?" and returns the top 10 most relevant cross-vertical recommendations using hybrid retrieval (embedding-based vector similarity + BM25 keyword matching).

## Pipeline Stages

### Stage 1 — Data Loading & Embedding Generation
- 1,757 pre-composed entity descriptions (956 games, 547 movies, 254 TV shows)
- Each entity has a rich text composition (~180 words) describing its experiential essence, plus 12-15 BM25 keywords
- Embeddings generated via Voyage AI `voyage-4-large` model (1024 dimensions)

### Stage 2 — Storage
- PostgreSQL (local): entity_id, name, vertical, description, composed_text, embedding vector, bm25_keywords, franchise, developer, publisher
- Qdrant vector database: embeddings for fast ANN similarity search

### Stage 3 — User Query Processing
- Llama 3.3 70B via Groq API with function calling
- Extracts: anchor_entity, intent, target_verticals, query_type, filters

### Stage 4 — Entity Resolution
- SQL query against PostgreSQL: exact match → prefix match → fuzzy match fallbacks
- Retrieves pre-computed embedding vector and BM25 keywords

### Stage 5 — Dual Retrieval
- (A) Vector search in Qdrant: top 20 by cosine similarity, filtered by target_verticals
- (B) BM25 keyword search: top 20 by keyword overlap score, filtered by verticals

### Stage 6 — Hybrid Merge & Reranking
- Normalize scores, combined scoring: 0.7 × vector_score + 0.3 × bm25_score
- Both-set bonus: +0.1 for entities in both result sets
- Franchise boost: +0.15 for shared franchise
- Self-exclusion, diversity enforcement
- Return top 10

### Stage 7 — Response
- Structured JSON: rank, name, vertical, final_score, vector_score, bm25_score, shared_keywords

## Data Files
- `data/all_compositions.json` — 1,757 entities with: entity_id, name, vertical, composed_text, bm25_keywords, word_count
- `data/entity_profiles_final.json` — 1,757 entities with: entity_id, name, vertical, description, canonical_genres, themes, keywords, franchise, developer, publisher, modes, perspectives, directors, cast

## Technology Stack
- Python 3.11+
- PostgreSQL (local) — entity storage and SQL-based entity resolution
- Qdrant (qdrant-client, in-memory mode) — vector similarity search
- Voyage AI (voyageai SDK) — embedding generation with voyage-4-large
- Groq API (groq SDK) — LLM function calling with llama-3.3-70b-versatile
- rank-bm25 — BM25 keyword scoring

## Project Structure
```
/home/ishaan/Desktop/Feedsai-pipeline/
├── data/                              (source data files)
├── pipeline/                          (all pipeline code)
├── results/                           (test outputs and reports)
├── .env                               (API keys — not committed)
├── requirements.txt
└── CLAUDE.md
```

## Environment Variables
- `VOYAGE_API_KEY` — Voyage AI embedding API
- `GROQ_API_KEY` — Groq LLM API
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
