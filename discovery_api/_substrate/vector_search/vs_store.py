import os
from datetime import datetime, timezone

import numpy as np

try:                                   # latency-attribution seam (serving only; no-op locally)
    from timing import span as _tspan
except Exception:                      # pragma: no cover — `timing` is bundled only in the serving image
    from contextlib import contextmanager as _cm

    @_cm
    def _tspan(_category):
        yield

_INDEX = None

# Recency (router contract, see engines/router_src/recency.py): range-filter the vector record's
# `release_date_ts` (Unix epoch seconds, UTC) so `from_ts <= release_date_ts <= to_ts`. The new corpus
# parquet (embeddings.parquet) carries this column; the entities / entities_vs index
# MUST be rebuilt from it for this to work. Gates:
#   VS_DATE_FILTER=0          → skip the date filter (use against an older index without the column)
#   VS_RELEASE_DATE_COL=...   → override the column name (default release_date_ts)
_DATE_FILTER = os.getenv("VS_DATE_FILTER", "1") == "1"
_DATE_COL = os.getenv("VS_RELEASE_DATE_COL", "release_date_ts")


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


def _to_epoch(v, end_of_day=False):
    """Normalize a date bound to UTC epoch seconds. Accepts an int/float epoch (router form, passed
    through) or a 'YYYY-MM-DD' string (vector-NLU form). Returns None on absent/unparseable input.
    end_of_day pads the upper bound to 23:59:59 so a same-day release is inclusive."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    hms = (23, 59, 59) if end_of_day else (0, 0, 0)
    return int(datetime(d.year, d.month, d.day, *hms, tzinfo=timezone.utc).timestamp())


def vector_search(query_embedding, target_verticals=None, top_k=20,
                  date_start=None, date_end=None):
    vec = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else list(query_embedding)

    # Vector Search filter syntax: {"col": [in-list]} and {"col >=": n} / {"col <=": n}.
    filters = {}
    if target_verticals:
        filters["vertical"] = list(target_verticals)
    # Recency: epoch range-filter on `release_date_ts`. Bounds arrive as 'YYYY-MM-DD' (vector NLU via
    # retrieval.py) or epoch ints (router) — both normalized to epoch seconds. A NULL release_date_ts
    # row fails the >=/<= predicate, so it is correctly excluded when any bound is set (a date-bounded
    # query requires a known date — matches recency.in_window).
    if _DATE_FILTER and (date_start is not None or date_end is not None):
        fr = _to_epoch(date_start, end_of_day=False)
        to = _to_epoch(date_end, end_of_day=True)
        if fr is not None:
            filters[f"{_DATE_COL} >="] = fr
        if to is not None:
            filters[f"{_DATE_COL} <="] = to

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
