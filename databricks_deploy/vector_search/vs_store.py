"""Databricks Vector Search implementation of the vector pipeline's dense-ANN call.

Drop-in for pipeline.vector_store.vector_search — SAME signature, SAME return shape
[(entity_id, name, vertical, score), ...] — so retrieval.py needs no change. Activated when the Vector
App runs with VECTOR_BACKEND=databricks (see the env-gated import at the bottom of
pipeline/vector_store.py). BM25 keyword_search stays in-process (rank-bm25) and is NOT overridden here.

Reuses the EXISTING Voyage vectors: build_index.py loaded vector/data_v2/embeddings_v2.npy into the
`embedding` column of the source Delta table, so retrieval parity with local Qdrant holds up to ANN
recall. Query vectors are produced upstream by the same voyage-4-large model (retrieval passes the
embedding in) — nothing re-embeds here.

Env:
  VS_ENDPOINT_NAME   Vector Search endpoint (e.g. feedsai-vs)
  VS_INDEX_NAME      Delta-Sync index (e.g. dev_feeds_silver.ml.entities_vs)
Auth is taken from the standard Databricks env (DATABRICKS_HOST/TOKEN or the App's service principal).
"""

import os

import numpy as np

_INDEX = None


def _index():
    global _INDEX
    if _INDEX is None:
        from databricks.vector_search.client import VectorSearchClient   # the SDK's `databricks` ns
        vsc = VectorSearchClient(disable_notice=True)
        _INDEX = vsc.get_index(
            endpoint_name=os.environ["VS_ENDPOINT_NAME"],
            index_name=os.environ["VS_INDEX_NAME"],
        )
    return _INDEX


def vector_search(query_embedding, target_verticals=None, top_k=20,
                  date_start=None, date_end=None):
    """Dense ANN over Databricks Vector Search. Returns [(entity_id, name, vertical, score), ...]."""
    vec = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else list(query_embedding)

    # Vector Search filter syntax: {"col": [in-list]} and {"col >=": n} / {"col <=": n}.
    filters = {}
    if target_verticals:
        filters["vertical"] = list(target_verticals)
    # date filters skipped: the 57k entities table (built from the parquet) has no release_date column.
    # (re-add by joining entity_profiles for release_date_int if date-bounded queries become needed.)
    _ = (date_start, date_end)

    res = _index().similarity_search(
        query_vector=vec,
        columns=["entity_id", "name", "vertical"],
        num_results=top_k,
        filters=filters or None,
    )

    # data_array rows are [<requested columns in order>, <score>].
    rows = ((res or {}).get("result") or {}).get("data_array") or []
    out = []
    for row in rows:
        entity_id, name, vertical = row[0], row[1], row[2]
        score = row[-1]
        out.append((entity_id, name, vertical, float(score)))
    return out
