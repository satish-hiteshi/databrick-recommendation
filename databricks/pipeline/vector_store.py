"""
Databricks Vector Search + in-memory BM25 for Feeds.ai.

vector_search()  → Databricks Vector Search (Delta Sync Index, cosine similarity)
keyword_search() → rank-bm25 index built in memory from entity_store data
setup()          → called once at model startup after entity_store is initialised
"""

import numpy as np
from rank_bm25 import BM25Okapi
from databricks.vector_search.client import VectorSearchClient

from pipeline.config import (
    DATABRICKS_HOST,
    DATABRICKS_TOKEN,
    VS_ENDPOINT,
    VS_INDEX,
    TOP_K_RETRIEVAL,
)
from pipeline import entity_store


# ── Module-level singletons ───────────────────────────────────────────

_vs_index   = None
_bm25_index = None
_bm25_entities: list = []


# ── Databricks Vector Search ──────────────────────────────────────────

def _get_vs_index():
    global _vs_index
    if _vs_index is None:
        client = VectorSearchClient(
            workspace_url=DATABRICKS_HOST,
            personal_access_token=DATABRICKS_TOKEN,
            disable_notice=True,
        )
        _vs_index = client.get_index(
            endpoint_name=VS_ENDPOINT,
            index_name=VS_INDEX,
        )
    return _vs_index


def vector_search(
    query_embedding,
    target_verticals=None,
    top_k: int = TOP_K_RETRIEVAL,
) -> list[tuple]:
    """
    ANN search in Databricks Vector Search.
    Returns list of (entity_id, name, vertical, score) sorted by score desc.

    Filter syntax: a tuple passed as the filter value means "IN" condition.
    e.g. {"vertical": ("game", "movie", "tv")}
    """
    index = _get_vs_index()

    vec = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

    filters = {"vertical": tuple(target_verticals)} if target_verticals else None

    response = index.similarity_search(
        query_vector=vec,
        columns=["entity_id", "name", "vertical"],
        filters=filters,
        num_results=top_k,
    )

    # Response shape: {"result": {"column_names": [...], "data_array": [[...], ...]}}
    result_block = response.get("result", {})
    col_names    = result_block.get("column_names", [])
    rows         = result_block.get("data_array", [])

    # The VS SDK appends score as the final column
    try:
        eid_idx  = col_names.index("entity_id")
        name_idx = col_names.index("name")
        vert_idx = col_names.index("vertical")
    except ValueError:
        # Fallback: assume order [entity_id, name, vertical, ..., score]
        eid_idx, name_idx, vert_idx = 0, 1, 2

    results = []
    for row in rows:
        score = float(row[-1])  # score is always last
        results.append((row[eid_idx], row[name_idx], row[vert_idx], score))

    return results


# ── BM25 keyword search ───────────────────────────────────────────────

def _build_bm25_index() -> None:
    global _bm25_index, _bm25_entities
    entities = entity_store.get_all()
    corpus = [[kw.lower() for kw in e["bm25_keywords"]] for e in entities]
    _bm25_index   = BM25Okapi(corpus)
    _bm25_entities = entities
    print(f"BM25 index built over {len(entities)} entities.")


def keyword_search(
    anchor_keywords: list[str],
    target_verticals=None,
    top_k: int = TOP_K_RETRIEVAL,
) -> list[tuple]:
    """
    BM25 keyword search across all entities.
    Returns list of (entity_id, name, vertical, bm25_score) sorted by score desc.
    """
    if _bm25_index is None:
        _build_bm25_index()

    query_tokens = [kw.lower() for kw in anchor_keywords]
    scores = _bm25_index.get_scores(query_tokens)

    scored = []
    for idx, score in enumerate(scores):
        e = _bm25_entities[idx]
        if target_verticals and e["vertical"] not in target_verticals:
            continue
        scored.append((e["entity_id"], e["name"], e["vertical"], float(score)))

    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_k]


# ── One-time setup ────────────────────────────────────────────────────

def setup() -> None:
    """
    Must be called after entity_store.init_from_list().
    Builds the BM25 index and pre-connects to the VS index.
    """
    _build_bm25_index()
    _get_vs_index()
    print("Vector store ready (Databricks VS + BM25).")
