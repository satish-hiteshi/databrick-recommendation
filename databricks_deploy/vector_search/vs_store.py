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

# Composite-key derivation from entity_id (vendored copy of shared/identity.py — see identity.py header).
# Used to backfill profile_key/media_source_guid when the VS index doesn't carry those columns yet.
try:
    from identity import composite_of as _composite_of
except Exception:                      # pragma: no cover — vendored copy is bundled
    _composite_of = None

_INDEX = None

# Recency (router contract, see engines/router_src/recency.py): range-filter the vector record's
# `release_date_ts` (Unix epoch seconds, UTC) so `from_ts <= release_date_ts <= to_ts`. The new corpus
# parquet (embeddings.parquet) carries this column; the entities / entities_vs index
# MUST be rebuilt from it for this to work. Gates:
#   VS_DATE_FILTER=0          → skip the date filter (use against an older index without the column)
#   VS_RELEASE_DATE_COL=...   → override the column name (default release_date_ts)
_DATE_FILTER = os.getenv("VS_DATE_FILTER", "1") == "1"
_DATE_COL = os.getenv("VS_RELEASE_DATE_COL", "release_date_ts")

# Composite columns requested from the Vector Search index. Present ONLY after the index/parquet is
# re-indexed to carry them (see COMPOSITE-READY note below); until then similarity_search silently
# omits unknown columns and we derive the composite from entity_id instead.
_COMPOSITE_COLS = ["profile_key", "media_source_guid"]


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
                  date_start=None, date_end=None, date_from_ts=None, date_to_ts=None):
    vec = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else list(query_embedding)

    # Vector Search filter syntax: {"col": [in-list]} and {"col >=": n} / {"col <=": n}.
    filters = {}
    if target_verticals:
        filters["vertical"] = list(target_verticals)
    # Recency range-filter on `release_date_ts` (LIVE: the corpus parquet + entities_vs carry the column).
    # Epoch bounds (router: date_from_ts/date_to_ts) take precedence; 'YYYY-MM-DD' strings (vector NLU:
    # date_start/date_end) are normalized via _to_epoch. NULL release_date_ts rows fail the predicate, so
    # they are excluded whenever any bound is set (matches recency.in_window). Gate: VS_DATE_FILTER=0 only
    # for an older index without the column.
    if _DATE_FILTER and (date_from_ts is not None or date_to_ts is not None):
        if date_from_ts is not None:
            filters[f"{_DATE_COL} >="] = int(date_from_ts)
        if date_to_ts is not None:
            filters[f"{_DATE_COL} <="] = int(date_to_ts)
    elif _DATE_FILTER and (date_start is not None or date_end is not None):
        fr = _to_epoch(date_start, end_of_day=False)
        to = _to_epoch(date_end, end_of_day=True)
        if fr is not None:
            filters[f"{_DATE_COL} >="] = fr
        if to is not None:
            filters[f"{_DATE_COL} <="] = to

    # COMPOSITE-READY (PK migration): request profile_key + media_source_guid alongside the existing
    # columns so the vector side CARRIES the composite once the index/parquet is regenerated with them.
    # The current deployed Databricks VS index (columns=[entity_id,name,vertical], built from the 57k
    # embeddings parquet) does NOT have these columns yet — MUST be regenerated:
    #   1. add `profile_key` + `media_source_guid` columns to the source Delta table / parquet
    #      (derivable from entity_id via identity.composite_of, or joined from entity_profiles), then
    #   2. re-sync / re-create the VS index so similarity_search can return them.
    # Until then we ask for them but the index omits unknown columns, so we DERIVE the composite from
    # entity_id (identity.composite_of) — the vector path is composite-carrying either way.
    base_cols = ["entity_id", "name", "vertical"]
    want_cols = base_cols + _COMPOSITE_COLS
    with _tspan("vs"):                 # Databricks Vector Search ANN round-trip
        try:
            res = _index().similarity_search(
                query_vector=vec, columns=want_cols, num_results=top_k, filters=filters or None,
            )
            cols = want_cols
        except Exception:              # index predates the composite columns → fall back to base cols
            res = _index().similarity_search(
                query_vector=vec, columns=base_cols, num_results=top_k, filters=filters or None,
            )
            cols = base_cols

    # data_array rows are [<requested columns in order>, <score>]. We keep the 4-tuple return contract
    # (eid, name, vertical, score) that every caller unpacks; the composite is carried separately below
    # via _row_composite and, for the response, re-derived from entity_id by parrot_adapter.
    idx = {c: i for i, c in enumerate(cols)}
    rows = ((res or {}).get("result") or {}).get("data_array") or []
    out = []
    for row in rows:
        entity_id, name, vertical = row[idx["entity_id"]], row[idx["name"]], row[idx["vertical"]]
        score = row[-1]
        _row_composite(row, idx, entity_id)   # resolves index-carried or entity_id-derived composite
        out.append((entity_id, name, vertical, float(score)))
    return out


def _row_composite(row, idx, entity_id):
    """The composite for one VS row: prefer the index-carried profile_key/media_source_guid columns
    (present only after the index is re-synced with them); otherwise derive from entity_id. Pure,
    never raises — returns {} if nothing is derivable. (Exposed so a future caller that widens the
    return contract can attach it; the response itself gets the composite from parrot_adapter.)"""
    pk = row[idx["profile_key"]] if "profile_key" in idx else None
    guid = row[idx["media_source_guid"]] if "media_source_guid" in idx else None
    if pk and guid:
        return {"profile_key": pk, "media_source_guid": guid}
    if entity_id and _composite_of is not None:
        try:
            return _composite_of(entity_id)
        except Exception:
            return {}
    return {}
