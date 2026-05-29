# Feeds.ai Entertainment Discovery Pipeline — System Documentation

> A complete technical guide to understanding the Feeds.ai PoC pipeline, from raw data to recommendation results. Written for someone exploring the system for the first time.

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Architecture Overview](#2-architecture-overview)
3. [Data Foundation](#3-data-foundation)
4. [Embedding Generation](#4-embedding-generation)
5. [Storage Layer](#5-storage-layer)
6. [Query Processing Pipeline](#6-query-processing-pipeline)
   - 6.1 Natural Language Understanding (NLU)
   - 6.2 Entity Resolution
   - 6.3 Dual Retrieval
   - 6.4 Reciprocal Rank Fusion (RRF)
   - 6.5 Negative Filtering
   - 6.6 Reranking
   - 6.7 Similarity Percentage
7. [Handling Different Query Types](#7-handling-different-query-types)
8. [API Layer](#8-api-layer)
9. [Frontend](#9-frontend)
10. [File Reference](#10-file-reference)
11. [Setup & Running](#11-setup--running)

---

## 1. What This System Does

A user types a natural language query like:

> "I love Elden Ring and Nioh 3, recommend me movies"

The system:
1. Understands that the user named two games and wants movie recommendations
2. Looks up both games in PostgreSQL, retrieves their pre-computed embedding vectors and keywords
3. Searches a vector database (Qdrant) for movies with similar experiential "feel"
4. Simultaneously runs keyword-based search (BM25) for movies sharing genre/theme terms
5. Fuses all search results using Reciprocal Rank Fusion (RRF)
6. Applies reranking bonuses (franchise matching, keyword boosting, diversity enforcement)
7. Returns the top 10 movies ranked by similarity, each with a human-readable percentage score

The system covers **1,757 entertainment entities** across three verticals: 956 games, 547 movies, and 254 TV shows. It supports within-vertical recommendations (games like a game) and cross-vertical discovery (movies for someone who liked a game).

---

## 2. Architecture Overview

```
User Query
    |
    v
[NLU — Groq/Llama 3.3 70B]
    |  Extracts: query_mode, entities, keywords, verticals
    v
[Entity Resolution — PostgreSQL]
    |  Resolves entity names to database records via SQL cascade
    v
[Dual Retrieval]
    |--- Vector Search (Qdrant) --- cosine similarity on embeddings
    |--- BM25 Search (rank-bm25) -- keyword overlap scoring
    v
[Reciprocal Rank Fusion]
    |  Merges ranked lists: RRF_score = sum of 1/(60 + rank) across all lists
    v
[Negative Filtering]
    |  Penalizes/removes results similar to things user dislikes
    v
[Reranking]
    |  Franchise boost, keyword boost, vertical weighting, diversity
    v
[Similarity Percentage]
    |  Top result = 100%, others scaled proportionally
    v
[JSON Response → React Frontend]
```

**Technology Stack:**
- **Python 3.11+** — all pipeline code
- **PostgreSQL** — entity storage, SQL-based entity resolution, query history
- **Qdrant** (in-memory) — vector similarity search (ANN)
- **Voyage AI** (`voyage-4-large`) — 1024-dimensional embedding generation
- **Groq API** (`llama-3.3-70b-versatile`) — LLM function calling for query understanding
- **rank-bm25** — BM25 Okapi keyword scoring
- **FastAPI** — REST API backend
- **React + TypeScript + Vite** — frontend application

---

## 3. Data Foundation

### Source Files

The system is built on two JSON files containing pre-composed entity data:

**`data/all_compositions.json`** — 1,757 entries, each with:
```json
{
  "entity_id": "Game:385645",
  "name": "Elden Ring Nightreign",
  "vertical": "game",
  "composed_text": "Elden Ring Nightreign extends the hauntingly vast universe of FromSoftware's landmark action role-playing creation into a standalone cooperative experience... (180 words describing the experiential essence)",
  "bm25_keywords": ["Action", "Role-Playing", "FromSoftware", "Bandai Namco", "Elden Ring", "fantasy", "open world", "survival", "roguelike", "cooperative", "dark fantasy", "procedural", "challenging"],
  "word_count": 151
}
```

**`data/entity_profiles_final.json`** — 1,757 entries with structured metadata:
```json
{
  "entity_id": "Game:385645",
  "name": "Elden Ring Nightreign",
  "vertical": "game",
  "description": "Elden Ring: Nightreign is a standalone adventure...",
  "canonical_genres": ["Action", "Role-Playing"],
  "themes": ["Action", "Fantasy", "Open world", "Survival"],
  "keywords": [],
  "franchise": null,
  "developer": "FromSoftware",
  "publisher": "Bandai Namco Entertainment",
  "directors": [],
  "cast": []
}
```

### Data Merging

`pipeline/data_loader.py` merges both files on `entity_id` into a unified dataset. Each entity ends up with both the rich 180-word composition (for embedding) and the structured metadata (for keyword search, filtering, and display).

### Entity Distribution

| Vertical | Count |
|----------|-------|
| Games    | 956   |
| Movies   | 547   |
| TV Shows | 254   |
| **Total** | **1,757** |

### What Makes the Compositions Special

The `composed_text` is not a plot summary — it describes the **experiential essence** of each entity. For a game, it captures how it *feels* to play. For a movie, it captures the emotional tone and thematic resonance. This is critical because the embeddings are generated from these compositions, so the vector search finds entities that feel similar, not just entities that share metadata tags.

---

## 4. Embedding Generation

**Module:** `pipeline/embedding_generator.py`

### How Embeddings Are Created

1. Load all 1,757 entities via `data_loader.get_all_entities()`
2. For each entity's `composed_text`, call the Voyage AI API:
   - Model: `voyage-4-large`
   - Dimensions: 1024
   - Input type: `document` (for indexing; queries use `query` type)
3. Process in batches of 50 to respect rate limits
4. Save results in three formats:
   - `data/embeddings_cache.json` — JSON array of `{entity_id, embedding}` (39 MB)
   - `data/embeddings.npy` — NumPy array for fast loading (7.2 MB)
   - `data/embeddings_ids.json` — ID ordering index to map numpy rows back to entity IDs

### Embedding Details

- **Model:** Voyage AI `voyage-4-large` — a state-of-the-art embedding model optimized for semantic similarity
- **Dimensions:** 1024 floats per entity
- **Total tokens processed:** ~405,000
- **Generation time:** ~30 seconds for all 1,757 entities

### Query Embeddings

When the system needs to embed a user's query (for theme-based and descriptive queries), it uses the same model but with `input_type='query'`:

```python
def embed_query_text(text: str) -> list:
    # Uses voyage-4-large with input_type='query'
    # Results cached in memory for the session
```

Voyage AI recommends using different `input_type` values for documents vs queries — this is a design choice that improves retrieval quality.

---

## 5. Storage Layer

### PostgreSQL — Entity Storage & Resolution

**Module:** `pipeline/database_setup.py`

**Database:** `feedsai_poc`

**Table: `entities`**
| Column | Type | Purpose |
|--------|------|---------|
| entity_id | VARCHAR PK | Unique identifier (e.g., "Game:385645") |
| name | VARCHAR | Display name |
| vertical | VARCHAR | "game", "movie", or "tv" |
| description | TEXT | Original short description |
| composed_text | TEXT | 180-word experiential composition |
| embedding | FLOAT8[] | 1024-dimensional vector |
| bm25_keywords | TEXT[] | 12-15 keyword strings |
| franchise | VARCHAR | Franchise name (if any) |
| developer | VARCHAR | Developer/studio name |
| publisher | VARCHAR | Publisher name |
| canonical_genres | TEXT[] | Genre tags |
| themes | TEXT[] | Theme tags |
| keywords | TEXT[] | Additional keywords |

**Indexes:**
- `idx_entities_name_lower` — on `LOWER(name)` for fast case-insensitive lookups
- `idx_entities_vertical` — for vertical filtering
- `idx_entities_franchise` — for franchise matching

**SQL Function: `find_entity(search_name)`**

This is the entity resolution cascade — given a user-typed name, it finds the matching entity:

```sql
-- 1. Exact match (case-insensitive)
WHERE LOWER(name) = LOWER(search_name) LIMIT 1
-- If not found:
-- 2. Prefix match
WHERE LOWER(name) LIKE LOWER(search_name) || '%' ORDER BY LENGTH(name) LIMIT 1
-- If not found:
-- 3. Contains match
WHERE LOWER(name) LIKE '%' || LOWER(search_name) || '%' ORDER BY LENGTH(name) LIMIT 1
```

This means "Elden Ring" resolves to "Elden Ring Nightreign" via prefix match, "Resident Evil" resolves to "Resident Evil Requiem" via prefix, and "Paw Patrol" resolves to "A Paw Patrol Christmas" via contains.

**Table: `query_history`**
Stores every query processed through the API:
| Column | Type |
|--------|------|
| id | SERIAL PK |
| query_text | TEXT |
| parsed_intent | JSONB |
| results | JSONB |
| latency_ms | FLOAT |
| created_at | TIMESTAMP |

### Qdrant — Vector Similarity Search

**Module:** `pipeline/vector_store.py`

Qdrant runs in **in-memory mode** (no server needed). On startup:
1. Creates collection `feedsai_entities` with vector_size=1024 and cosine distance
2. Uploads all 1,757 vectors in batches of 500
3. Each vector's payload includes: entity_id, name, vertical, bm25_keywords, franchise, composed_text preview

**Vector search:**
```python
def vector_search(query_embedding, target_verticals=None, top_k=20):
    # Returns: [(entity_id, name, vertical, cosine_score), ...]
    # Applies metadata filter on vertical if specified
```

### BM25 Index

**Also in:** `pipeline/vector_store.py`

Built from all entity BM25 keywords using `rank-bm25`'s `BM25Okapi` implementation:
```python
corpus = [[kw.lower() for kw in entity["bm25_keywords"]] for entity in all_entities]
_bm25_index = BM25Okapi(corpus)
```

**Keyword search:**
```python
def keyword_search(anchor_keywords, target_verticals=None, top_k=20):
    # Scores all entities against the anchor's keywords
    # Filters by vertical, returns top_k sorted by BM25 score
```

---

## 6. Query Processing Pipeline

When a user submits a query, it flows through six stages:

### 6.1 Natural Language Understanding (NLU)

**Module:** `pipeline/nlu.py`

Uses **Groq API** with **Llama 3.3 70B** and function calling to parse the query into structured intent.

**Input:** `"I love Elden Ring and Nioh 3, recommend me movies"`

**Output:**
```json
{
  "query_mode": "entity_multi",
  "positive_entities": ["Elden Ring", "Nioh 3"],
  "negative_entities": [],
  "additional_keywords": [],
  "description_derived_keywords": [],
  "target_verticals": ["movie"],
  "query_type": "cross_vertical"
}
```

**The 5 Query Modes:**

| Mode | Description | Example |
|------|-------------|---------|
| `entity_single` | User names exactly one entity | "Games like Elden Ring" |
| `entity_multi` | User names 2+ entities | "I love Elden Ring and Nioh 3, recommend movies" |
| `theme_based` | User describes genres/themes without naming entities | "Horror content across all categories" |
| `descriptive` | User describes what they want in natural language | "I like content with country wars and gun fighting" |
| `mixed` | User combines named entities with themes or dislikes | "Love Elden Ring but hate Star Wars, want dark fantasy movies" |

**Key NLU Behaviors:**
- **Negative entities:** Detected from "hate", "don't like", "but not", "except" phrases
- **Description translation:** Vague descriptions are translated to standard terms. "country wars and gun fighting" becomes `["military warfare", "combat", "war drama", "tactical shooter"]`
- **Vertical detection:** "movies" → `["movie"]`, "shows" → `["tv"]`, "content" or no specification → `["game", "movie", "tv"]`

### 6.2 Entity Resolution

**Module:** `pipeline/entity_resolver.py`

For each entity name extracted by the NLU:
1. Call PostgreSQL's `find_entity()` function (exact → prefix → contains cascade)
2. Retrieve the entity's pre-computed embedding vector and BM25 keywords
3. If resolution fails (entity not in the 1,757-item database), it's skipped for retrieval
4. Negative entities that don't resolve (e.g., "comedy") are passed as keyword-only negatives

**Example resolutions:**
- "Elden Ring" → "Elden Ring Nightreign" [prefix match]
- "Silent Hill" → "Silent Hill f" [prefix match]
- "Resident Evil" → "Resident Evil Requiem" [prefix match]
- "comedy" → NOT FOUND → treated as keyword negative

### 6.3 Dual Retrieval

**Module:** `pipeline/retrieval.py`

For each resolved positive entity, the system runs **two parallel searches**:

**A. Vector Search (Qdrant)**
- Uses the entity's 1024-dimensional embedding
- Finds entities whose compositions feel experientially similar
- Filtered by target_verticals
- Returns top 15-20 results ranked by cosine similarity

**B. BM25 Keyword Search**
- Uses the entity's BM25 keywords (e.g., ["Action", "Role-Playing", "dark fantasy", "cooperative"])
- Finds entities sharing genre/theme keywords
- Filtered by target_verticals
- Returns top 15-20 results ranked by BM25 overlap score

**Why two signals?** Vector search captures subjective "feel" similarity (two entities can feel alike despite different genres), while BM25 captures objective genre/keyword overlap. Together they find recommendations that are both experientially similar AND genre-appropriate.

### 6.4 Reciprocal Rank Fusion (RRF)

**Module:** `pipeline/retrieval.py` — `_rrf_fuse()`

This is the core ranking algorithm. Instead of combining raw scores (which have different scales and distributions), RRF works purely on **rank positions**.

**The Formula:**

```
RRF_score(entity) = sum of 1/(k + rank_i) for each ranked list i where entity appears
```

Where `k = 60` (standard smoothing constant) and `rank_i` is the entity's 1-indexed position in list `i`.

**Example:** If an entity appears at:
- Vector list 1: rank 3 → contribution = 1/(60+3) = 0.0159
- BM25 list 1: rank 7 → contribution = 1/(60+7) = 0.0149
- Vector list 2: rank 12 → contribution = 1/(60+12) = 0.0139
- BM25 list 2: not present → contribution = 0

**Total RRF = 0.0159 + 0.0149 + 0.0139 = 0.0447**

**How Many Lists?** It depends on the query mode:

| Mode | Lists |
|------|-------|
| entity_single | 2 lists (1 vector + 1 BM25) |
| entity_multi (2 entities) | 4 lists (2 vector + 2 BM25) |
| entity_multi (N entities) | 2N lists |
| theme_based | 2 lists (1 vector + 1 BM25 from query embedding) |
| mixed (2 entities + theme) | 6 lists (2 vector + 2 BM25 + 1 theme vector + 1 theme BM25) |

**Bonuses Applied After RRF:**
- **Dual signal bonus (+0.005):** If an entity appears in at least one vector list AND at least one BM25 list — it was found by both semantic similarity and keyword matching, making it a stronger recommendation
- **Multi-entity overlap bonus (+0.003 per additional entity):** If an entity appears in results from multiple positive entities, it's relevant to more of the user's stated preferences

**Why RRF Instead of Weighted Scoring?**
- Raw scores from vector search (cosine similarity: 0.3-0.8) and BM25 (arbitrary scale: 0-50+) are not comparable
- Weighted combination (0.7 × vector + 0.3 × BM25) requires careful normalization and the weights are arbitrary
- RRF uses only rank positions, which are naturally comparable across any scoring system
- RRF is a proven technique used by Elasticsearch, major search engines, and information retrieval research

### 6.5 Negative Filtering

**Module:** `pipeline/negative_filter.py`

Applied when the user expresses dislikes. There are two types of negatives:

**Type 1: Resolved Entities** (e.g., user says "hate Star Wars" → resolves to "Star Wars: Galactic Racer")
- **Franchise exclusion:** If candidate shares franchise with negative entity → REMOVED entirely
- **Embedding similarity penalty:** If cosine_similarity(candidate, negative) > 0.6 → penalty = 0.3 × similarity
- **Keyword overlap penalty:** If >40% of candidate's keywords overlap with negative entity → penalty = 0.1

**Type 2: Unresolved Keywords** (e.g., "comedy" doesn't resolve as an entity)
- If "comedy" appears in candidate's BM25 keywords → penalty = 0.15
- If "comedy" appears in candidate's composed_text → penalty = 0.08

**Score floor:** If any candidate's score drops to ≤ 0 after penalties, it's removed entirely.

### 6.6 Reranking

**Module:** `pipeline/reranker.py`

Post-retrieval score adjustments:

1. **Self-exclusion:** Remove the user's stated entities from results (you wouldn't recommend Elden Ring to someone who just said they like Elden Ring)

2. **Franchise boost (+0.10):** If candidate shares franchise with a positive entity

3. **Keyword boosting:** For each keyword from `additional_keywords` + `description_derived_keywords`:
   - +0.05 if keyword appears in candidate's BM25 keywords
   - +0.03 if keyword appears in candidate's composed_text
   - Capped at +0.20 per candidate

4. **Vertical-aware weighting:** In multi-entity queries, if a candidate's vertical matches a positive entity's vertical AND is in the target verticals → 1.1× multiplier

5. **Per-vertical splitting:** For multi-vertical queries, results are split by vertical and each vertical gets its own top 10

6. **Franchise diversity:** Maximum 3 results per franchise within each vertical's top 10

### 6.7 Similarity Percentage

**Module:** `pipeline/query_engine.py`

After all scoring, each result gets a human-readable `similarity_percentage`:
- The highest-scoring result in each list gets **100%**
- All others are scaled proportionally: `round((result_rrf / max_rrf) * 100)`

This means the #1 result always shows "100% Match", #2 might show "85% Match", etc. The percentage tells users "this is 85% as good a match as the top result."

**Color coding on the frontend:**
- 80-100%: bright green
- 60-79%: teal
- 40-59%: amber
- 20-39%: orange
- Below 20%: red

---

## 7. Handling Different Query Types

### entity_single: "Games like Elden Ring Nightreign"

```
NLU → positive_entities: ["Elden Ring Nightreign"], target: ["game"]
  ↓
Resolve "Elden Ring Nightreign" → entity found [exact match]
  ↓
Vector search with Elden Ring's embedding → top 20 games by cosine similarity
BM25 search with Elden Ring's keywords → top 20 games by keyword overlap
  ↓
RRF fuse 2 lists → ranked candidates
  ↓
Self-exclude "Elden Ring Nightreign" → final top 10
```

**Result:** Nioh 3 (100%), Jotunnslayer (95%), Darkest Days (92%)...

### entity_multi: "I love Elden Ring and Nioh 3, recommend me movies"

```
NLU → positive_entities: ["Elden Ring", "Nioh 3"], target: ["movie"]
  ↓
Resolve both → Elden Ring Nightreign [prefix], Nioh 3 [exact]
  ↓
For Elden Ring: vector search (top 15 movies) + BM25 search (top 15 movies)
For Nioh 3:     vector search (top 15 movies) + BM25 search (top 15 movies)
  ↓
RRF fuse 4 lists → entities appearing in multiple lists get higher scores
  + overlap bonus for entities found via both Elden Ring AND Nioh 3
  + dual signal bonus for entities found via both vector AND BM25
  ↓
Self-exclude both anchors → final top 10 movies
```

**Result:** Movies relevant to BOTH games rank highest due to overlap bonus.

### theme_based: "Horror content across all categories"

```
NLU → query_mode: "theme_based", additional_keywords: ["horror"], target: all
  ↓
No entity resolution (no named entities)
  ↓
Embed "horror" via Voyage AI → query embedding
Vector search with query embedding → top 20 across all verticals
BM25 search with ["horror"] as keywords → top 20 across all verticals
  ↓
RRF fuse 2 lists → ranked candidates
  ↓
Split by vertical → top 10 per vertical (games, movies, TV)
```

### descriptive: "I like content with country wars and gun fighting"

```
NLU → query_mode: "descriptive"
       description_derived_keywords: ["military warfare", "combat", "war drama", "tactical shooter"]
  ↓
Embed "military warfare combat war drama tactical shooter" → query embedding
Vector search + BM25 search → fuse via RRF
  ↓
Result: Warfare (movie), Shadows of Soldiers (game), Forefront (game)...
```

The LLM translates the user's casual description into standard entertainment terminology before embedding.

### mixed: "Love Elden Ring but hate Star Wars, want dark fantasy movies"

```
NLU → positive: ["Elden Ring"], negative: ["Star Wars"]
       additional_keywords: ["dark fantasy"], target: ["movie"]
  ↓
Resolve "Elden Ring" → Elden Ring Nightreign
Resolve "Star Wars" → Star Wars: Galactic Racer (for negative filtering)
  ↓
Entity retrieval: vector + BM25 from Elden Ring's embedding/keywords
Theme retrieval: embed "dark fantasy" → vector + BM25
  ↓
RRF fuse 4 lists (entity gets weight 1.0, theme gets weight 0.8)
  ↓
Negative filter: penalize anything similar to Star Wars
  ↓
Keyword boost: +0.05 for results containing "dark fantasy" in keywords
  ↓
Result: In the Lost Lands, Tales from Black Manor, The Witcher films...
```

---

## 8. API Layer

**Module:** `pipeline/api.py`

FastAPI server running on port 8000. Initializes Qdrant + BM25 index on startup (~1.4 seconds).

### Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/query` | Process a query, return recommendations |
| GET | `/api/history` | List all past queries |
| GET | `/api/history/{id}` | Full details of a past query |
| DELETE | `/api/history` | Clear query history |
| GET | `/api/entities` | Browse entities (paginated, filterable) |
| GET | `/api/entities/{id}` | Single entity details |
| GET | `/api/stats` | Dashboard statistics |

### Query Response Format

```json
{
  "query": "Games like Elden Ring Nightreign",
  "parsed_intent": { "query_mode": "entity_single", ... },
  "query_mode": "entity_single",
  "anchor_entities_resolved": ["Elden Ring Nightreign (game) [prefix]"],
  "negative_entities_resolved": [],
  "status": "success",
  "timings": {
    "nlu_ms": 450,
    "retrieval_ms": 65,
    "filter_ms": 0,
    "rerank_ms": 4,
    "total_ms": 519
  },
  "results": [
    {
      "rank": 1,
      "name": "Nioh 3",
      "vertical": "game",
      "final_score": 0.0367,
      "rrf_score": 0.0367,
      "similarity_percentage": 100,
      "vector_rank": 3,
      "bm25_rank": 3,
      "appeared_in_vector": true,
      "appeared_in_bm25": true,
      "in_both_sets": true,
      "shared_keywords": ["action", "challenging", "cooperative"],
      "negative_penalty": 0
    }
  ]
}
```

For multi-vertical queries, results are split:
```json
{
  "results": [],
  "results_by_vertical": {
    "game": [ ... top 10 games ... ],
    "movie": [ ... top 10 movies ... ],
    "tv": [ ... top 10 TV shows ... ]
  }
}
```

---

## 9. Frontend

**Stack:** React 18 + TypeScript + Vite + React Router

### Layout
- **Sidebar** (200px, collapsible to 60px) — dark gradient, route-based navigation
- **Main content** — fills remaining width, switches based on route
- **Detail panel** — slides in from right as fixed overlay when an entity is clicked

### Routes
| Route | Component | Purpose |
|-------|-----------|---------|
| `/chat` | ChatTab | Query interface with chat-style results |
| `/history` | HistoryList | Table of past queries |
| `/history/:id` | HistoryDetail | Full results of a specific past query |
| `/dataset` | DatasetTab | Browse/search/filter all 1,757 entities |

### Result Cards Display
Each recommendation card shows:
- **Rank number** — colored by vertical (green=game, blue=movie, amber=TV)
- **Entity name** and vertical badge
- **Similarity percentage** — e.g., "85% Match" with color-coded bar
- **Signal indicators** — "Vector #3 ✓" in blue, "BM25 #7 ✓" in purple, or "✗" in gray
- **Raw RRF score** — small monospace text
- **Shared keywords** — pills showing genre/theme overlap
- **Dual Signal badge** — if found by both vector AND BM25 search

### Key Design Decisions
- **Satoshi font** — loaded locally via @font-face (woff2 files in `src/fonts/`)
- **API base URL** — dynamically set to `window.location.hostname:8000` so the app works on any network
- **History patching** — older history entries (saved before `similarity_percentage` existed) are patched on the fly when displayed

---

## 10. File Reference

### Pipeline (Python Backend)

| File | Purpose |
|------|---------|
| `pipeline/config.py` | Environment variables, constants, paths |
| `pipeline/data_loader.py` | Loads and merges entity JSON files |
| `pipeline/embedding_generator.py` | Voyage AI embedding generation + caching |
| `pipeline/database_setup.py` | PostgreSQL schema, indexes, SQL functions |
| `pipeline/entity_resolver.py` | SQL entity resolution + batch fetching |
| `pipeline/vector_store.py` | Qdrant collection + BM25 index |
| `pipeline/nlu.py` | Groq/Llama NLU with function calling |
| `pipeline/retrieval.py` | Dual retrieval + RRF fusion (core algorithm) |
| `pipeline/negative_filter.py` | Penalize/remove disliked content |
| `pipeline/reranker.py` | Score adjustments, diversity, vertical splitting |
| `pipeline/query_engine.py` | End-to-end orchestration + similarity percentage |
| `pipeline/api.py` | FastAPI REST endpoints |
| `pipeline/run_api.py` | Server launcher |
| `pipeline/setup_all.py` | One-command database + index setup |

### Data

| File | Size | Purpose |
|------|------|---------|
| `data/all_compositions.json` | 3.1 MB | Entity compositions + BM25 keywords |
| `data/entity_profiles_final.json` | 2.2 MB | Full entity metadata |
| `data/embeddings.npy` | 6.9 MB | Pre-computed embedding vectors (numpy) |
| `data/embeddings_cache.json` | 39 MB | Embedding vectors (JSON format) |
| `data/embeddings_ids.json` | 28 KB | Entity ID ordering for numpy array |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/App.tsx` | Root layout + React Router routes |
| `frontend/src/api/client.ts` | Axios API client for all endpoints |
| `frontend/src/api/patchResults.ts` | Backfill similarity_percentage for old data |
| `frontend/src/types/index.ts` | TypeScript interfaces for all API models |
| `frontend/src/components/ChatTab.tsx` | Query input + chat-style results |
| `frontend/src/components/ResultCard.tsx` | Individual recommendation card |
| `frontend/src/components/DetailPanel.tsx` | Entity detail slide-in panel |
| `frontend/src/components/HistoryList.tsx` | Past queries table |
| `frontend/src/components/HistoryDetail.tsx` | Full past query view |
| `frontend/src/components/DatasetTab.tsx` | Entity browser with search/filter |
| `frontend/src/components/Sidebar.tsx` | Navigation sidebar |

### Reports (in `results/`)

| File | Purpose |
|------|---------|
| `EMBEDDING_REPORT.md` | Embedding generation stats and sanity checks |
| `STORAGE_REPORT.md` | Database and vector index validation |
| `PIPELINE_REPORT.md` | Phase 1 pipeline test results |
| `FINAL_TEST_REPORT.md` | Phase 1 comprehensive test (15 queries) |
| `NLU_V2_TEST.md` | NLU v2 query mode classification accuracy |
| `RETRIEVAL_V2_TEST.md` | Retrieval v2 test across all 5 modes |
| `RERANKER_V2_TEST.md` | Full chain test (NLU → retrieval → filter → rerank) |
| `FINAL_TEST_REPORT_V2.md` | Phase 2 comprehensive test (20 queries) |
| `COMPLEX_TEST_RESULTS.md` | 20 complex query results |
| `QUALITY_EVALUATION.md` | Ground truth metadata-based evaluation |
| `HUMAN_QUALITY_EVALUATION.md` | Human-perspective quality evaluation |
| `API_TEST.md` | REST API endpoint test results |

---

## 11. Setup & Running

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Node.js 18+

### First-Time Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Create .env from example
cp .env.example .env
# Edit .env with your API keys (VOYAGE_API_KEY, GROQ_API_KEY, POSTGRES_PASSWORD)

# 3. Start PostgreSQL, then set up database + indexes
python -m pipeline.setup_all

# 4. Install frontend dependencies
cd frontend && npm install && cd ..
```

### Running

```bash
# Terminal 1: Start the API server
python -m pipeline.run_api
# Runs on http://0.0.0.0:8000

# Terminal 2: Start the frontend
cd frontend && npx vite --host 0.0.0.0 --port 3000
# Runs on http://0.0.0.0:3000
```

### Network Access

Both servers bind to `0.0.0.0`, so anyone on the same network can access:
- Frontend: `http://<your-ip>:3000`
- API: `http://<your-ip>:8000`
- API Docs: `http://<your-ip>:8000/docs`

---

## Key Design Decisions & Tradeoffs

1. **Experiential embeddings over metadata matching:** Compositions describe how content *feels*, not just what it is. This means the system can recommend a thriller movie to a horror game fan even if they share zero metadata tags — because the "feel" is similar.

2. **RRF over weighted scoring:** Eliminates the need to normalize incompatible score distributions. A rank-based approach is more robust and well-studied in information retrieval.

3. **Qdrant in-memory:** Simplifies deployment (no external service) at the cost of needing to rebuild the index on every server restart (~1.4 seconds). For production, switch to persistent Qdrant.

4. **LLM for query parsing:** Using Llama 3.3 70B via Groq gives excellent natural language understanding at ~500ms latency. The NLU is the main latency bottleneck (85% of total query time).

5. **Dual-signal bonus:** Entities found by BOTH vector search and keyword search are likely the best recommendations — they match on both subjective feel and objective metadata. The +0.005 bonus rewards this.

6. **Negative filtering as a separate stage:** Rather than trying to subtract negative signals during retrieval (which is mathematically complex), the pipeline retrieves first, then penalizes. This is cleaner and more debuggable.
