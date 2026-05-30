import numpy as np
from rank_bm25 import BM25Okapi
from databricks.vector_search.client import VectorSearchClient

from pipeline.config import VS_ENDPOINT, VS_INDEX, TOP_K_RETRIEVAL
from pipeline import entity_store

_vs_index      = None
_bm25_index    = None
_bm25_entities = []


def _get_vs_index():
    global _vs_index
    if _vs_index is None:
        client    = VectorSearchClient(disable_notice=True)
        _vs_index = client.get_index(endpoint_name=VS_ENDPOINT, index_name=VS_INDEX)
    return _vs_index


def vector_search(query_embedding, target_verticals=None, top_k=TOP_K_RETRIEVAL,
                  date_start=None, date_end=None):
    index   = _get_vs_index()
    vec     = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding
    filters = {"vertical": tuple(target_verticals)} if target_verticals else None

    # Fetch extra results to compensate for date post-filtering
    fetch_k = top_k * 3 if (date_start or date_end) else top_k

    response  = index.similarity_search(
        query_vector=vec,
        columns=["entity_id", "name", "vertical"],
        filters=filters,
        num_results=fetch_k,
    )
    col_names = [col["name"] for col in response.get("manifest", {}).get("columns", [])]
    rows      = response.get("result", {}).get("data_array", [])

    try:
        eid_idx  = col_names.index("entity_id")
        name_idx = col_names.index("name")
        vert_idx = col_names.index("vertical")
    except ValueError:
        eid_idx, name_idx, vert_idx = 0, 1, 2

    results = []
    for row in rows:
        if date_start or date_end:
            # release_date comes from entity_store (in-memory) — not from VS index
            e = entity_store.get_by_id(row[eid_idx])
            rd = e.get("release_date") if e else None
            if not rd:
                continue
            if date_start and rd < date_start:
                continue
            if date_end and rd > date_end:
                continue
        results.append((row[eid_idx], row[name_idx], row[vert_idx], float(row[-1])))
        if len(results) == top_k:
            break

    return results


def _build_bm25_index():
    global _bm25_index, _bm25_entities
    entities       = entity_store.get_all()
    corpus         = [[kw.lower() for kw in e["bm25_keywords"]] for e in entities]
    _bm25_index    = BM25Okapi(corpus)
    _bm25_entities = entities


def keyword_search(anchor_keywords, target_verticals=None, top_k=TOP_K_RETRIEVAL,
                   date_start=None, date_end=None):
    if _bm25_index is None:
        _build_bm25_index()

    scores = _bm25_index.get_scores([kw.lower() for kw in anchor_keywords])
    scored = []
    for e, s in zip(_bm25_entities, scores):
        if target_verticals and e["vertical"] not in target_verticals:
            continue
        if date_start or date_end:
            rd = e.get("release_date")
            if not rd:
                continue
            if date_start and rd < date_start:
                continue
            if date_end and rd > date_end:
                continue
        scored.append((e["entity_id"], e["name"], e["vertical"], float(s)))

    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_k]


def setup():
    _build_bm25_index()
    _get_vs_index()
    print(f"Vector store ready: {len(_bm25_entities)} entities")
