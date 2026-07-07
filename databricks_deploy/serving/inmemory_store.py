import os

import numpy as np

_PARQUET_NAME = "embeddings.parquet"
_INDEX = None


def _parquet_path():
    p = os.getenv("EMBEDDINGS_PARQUET")
    if p and os.path.isfile(p):
        return p
    try:
        from pipeline.config import DATA_DIR
        cand = os.path.join(DATA_DIR, _PARQUET_NAME)
        if os.path.isfile(cand):
            return cand
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        for root, _dirs, files in os.walk(base):
            if _PARQUET_NAME in files:
                return os.path.join(root, _PARQUET_NAME)
    raise FileNotFoundError(f"{_PARQUET_NAME} not found (set EMBEDDINGS_PARQUET)")


def _ts_to_ymd(ts):
    """release_date_ts (epoch seconds) -> 'YYYY-MM-DD' (UTC) for the vector date filter. None-safe."""
    if ts is None:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def _load():
    global _INDEX
    if _INDEX is None:
        import pyarrow.parquet as pq
        path = _parquet_path()
        # carry release_date_ts if the parquet has it → so the (Qdrant) vector backend can date-filter;
        # without it, recency vector-establishes return empty and the router falls back to a bare-vertical dump.
        has_date = "release_date_ts" in set(pq.read_schema(path).names)
        t = pq.read_table(path, columns=["entity_id", "name", "vertical", "embedding", "bm25_keywords"]
                          + (["release_date_ts"] if has_date else []))
        eids = t.column("entity_id").to_pylist()
        names = t.column("name").to_pylist()
        verts = t.column("vertical").to_pylist()
        kws = t.column("bm25_keywords").to_pylist()
        dts = t.column("release_date_ts").to_pylist() if has_date else [None] * len(eids)
        mat = (t.column("embedding").combine_chunks().flatten()
               .to_numpy(zero_copy_only=False).reshape(len(eids), -1).astype(np.float32))
        by_id, name_list, exact_names, emb = {}, [], {}, {}
        for i, eid in enumerate(eids):
            v = mat[i]
            by_id[eid] = {"entity_id": eid, "name": names[i], "vertical": verts[i],
                          "embedding": v, "bm25_keywords": kws[i] or [],
                          "release_date": _ts_to_ymd(dts[i])}     # 'YYYY-MM-DD' for the date filter
            emb[eid] = v
            nm = (names[i] or "").lower()
            name_list.append((nm, eid))
            exact_names.setdefault(nm, eid)
        _INDEX = {"by_id": by_id, "names": name_list, "exact_names": exact_names,
                  "emb": emb, "dim": int(mat.shape[1])}
    return _INDEX


def embeddings():
    return _load()["emb"]


def resolve_entity(entity_name):
    if not entity_name or not entity_name.strip():
        return None
    q = entity_name.strip().lower()
    idx = _load()
    by_id, names = idx["by_id"], idx["names"]
    eid = idx["exact_names"].get(q)
    if eid:
        match = "exact"
    else:
        prefix = [eid for (nm, eid) in names if nm.startswith(q)]
        if prefix:
            eid, match = min(prefix, key=lambda i: len(by_id[i]["name"])), "prefix"
        else:
            contains = [eid for (nm, eid) in names if q in nm]
            if not contains:
                return None
            eid, match = min(contains, key=lambda i: len(by_id[i]["name"])), "contains"
    rec = dict(by_id[eid])
    rec["embedding"] = np.asarray(rec["embedding"], dtype=np.float32)
    rec["match_type"] = match
    return rec


def batch_fetch_entities(entity_ids):
    if not entity_ids:
        return {}
    by_id = _load()["by_id"]
    out = {}
    for eid in entity_ids:
        e = by_id.get(eid)
        if not e:
            continue
        out[eid] = {"entity_id": eid, "embedding": np.asarray(e["embedding"], dtype=np.float32),
                    "bm25_keywords": e.get("bm25_keywords") or [], "franchise": None, "composed_text": ""}
    return out


def all_records():
    return [{"entity_id": e["entity_id"], "name": e["name"], "vertical": e["vertical"],
             "composed_text": "", "bm25_keywords": e.get("bm25_keywords") or [], "word_count": None,
             "description": None, "canonical_genres": [], "themes": [], "franchise": None,
             "developer": None, "publisher": None, "directors": [], "cast": [],
             "release_date": e.get("release_date")}                # carried from release_date_ts (date filter)
            for e in _load()["by_id"].values()]
