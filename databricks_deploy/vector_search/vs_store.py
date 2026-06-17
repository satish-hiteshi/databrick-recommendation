import os

import numpy as np

try:                                   # latency-attribution seam (serving only; no-op locally)
    from timing import span as _tspan
except Exception:                      # pragma: no cover — `timing` is bundled only in the serving image
    from contextlib import contextmanager as _cm

    @_cm
    def _tspan(_category):
        yield

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
    vec = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else list(query_embedding)

    # Vector Search filter syntax: {"col": [in-list]} and {"col >=": n} / {"col <=": n}.
    filters = {}
    if target_verticals:
        filters["vertical"] = list(target_verticals)
    # date filters skipped: the 57k entities table (built from the parquet) has no release_date column.
    # (re-add by joining entity_profiles for release_date_int if date-bounded queries become needed.)
    _ = (date_start, date_end)

    with _tspan("vs"):                 # Databricks Vector Search ANN round-trip
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
