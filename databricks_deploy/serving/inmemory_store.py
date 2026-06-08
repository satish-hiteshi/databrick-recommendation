"""In-memory entity store backed by the 57k Voyage embeddings PARQUET (Postgres-free, npy-free).

The collapsed router runs in ONE Model Serving container. At 57k the corpus vectors are ~235 MB and the
old `.npy` is gone — they now live in `embeddings_voyage_57k.parquet`
(entity_id, name, vertical, embedding[1024], bm25_keywords), bundled into the model. This module loads
that parquet ONCE and powers everything the collapsed router needs from the corpus:

  • resolve_entity / batch_fetch_entities  (name → record + stored vector)  [drop-in for entity_resolver]
  • embeddings()                           (entity_id → vector)             [for score_set / neighbors]
  • all_records()                          (full-schema entity dicts)       [for data_loader / BM25]

Vector ANN itself is served by Databricks Vector Search (vs_store), NOT from here. Path resolution:
env `EMBEDDINGS_PARQUET`, else `<pipeline DATA_DIR>/embeddings_voyage_57k.parquet`, else a walk of the
model dir. composed_text is not in the parquet (rerankers only; they're off by default) → returned "".
"""

import os

import numpy as np

_PARQUET_NAME = "embeddings_voyage_57k.parquet"
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


def _load():
    """Read the parquet once → {by_id, names, emb}. Embeddings become one (N,1024) float32 matrix;
    per-id entries are VIEWS into it (no per-row copy), so RAM ≈ the matrix itself (~235 MB at 57k)."""
    global _INDEX
    if _INDEX is None:
        import pyarrow.parquet as pq
        t = pq.read_table(_parquet_path(),
                          columns=["entity_id", "name", "vertical", "embedding", "bm25_keywords"])
        eids = t.column("entity_id").to_pylist()
        names = t.column("name").to_pylist()
        verts = t.column("vertical").to_pylist()
        kws = t.column("bm25_keywords").to_pylist()
        mat = (t.column("embedding").combine_chunks().flatten()
               .to_numpy(zero_copy_only=False).reshape(len(eids), -1).astype(np.float32))
        by_id, name_list, emb = {}, [], {}
        for i, eid in enumerate(eids):
            v = mat[i]
            by_id[eid] = {"entity_id": eid, "name": names[i], "vertical": verts[i],
                          "embedding": v, "bm25_keywords": kws[i] or []}
            emb[eid] = v
            name_list.append(((names[i] or "").lower(), eid))
        _INDEX = {"by_id": by_id, "names": name_list, "emb": emb, "dim": int(mat.shape[1])}
    return _INDEX


def embeddings():
    """{entity_id: np.float32[dim]} — used by score_set / neighbors."""
    return _load()["emb"]


def resolve_entity(entity_name):
    """exact → prefix → contains (case-insensitive); shortest name wins ties. Same dict shape as the
    Postgres resolver: entity_id, name, vertical, embedding(np.float32), bm25_keywords, match_type."""
    if not entity_name or not entity_name.strip():
        return None
    q = entity_name.strip().lower()
    idx = _load()
    by_id, names = idx["by_id"], idx["names"]
    exact = [eid for (nm, eid) in names if nm == q]
    if exact:
        eid, match = exact[0], "exact"
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
    """id → {entity_id, embedding, bm25_keywords, franchise(None), composed_text("")}."""
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
    """Full-schema entity dicts for pipeline.data_loader.get_all_entities (BM25 + downstream). Fields the
    parquet doesn't carry are blanked so no consumer KeyErrors."""
    return [{"entity_id": e["entity_id"], "name": e["name"], "vertical": e["vertical"],
             "composed_text": "", "bm25_keywords": e.get("bm25_keywords") or [], "word_count": None,
             "description": None, "canonical_genres": [], "themes": [], "franchise": None,
             "developer": None, "publisher": None, "directors": [], "cast": [], "release_date": None}
            for e in _load()["by_id"].values()]
