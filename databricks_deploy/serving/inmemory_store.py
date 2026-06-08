"""In-memory, Postgres-FREE entity resolution — drop-in for pipeline.entity_resolver.

The collapsed router runs inside ONE Model Serving container with no Postgres. The vector pipeline's
only hard Postgres dependency on the retrieval path is entity_resolver (resolve_entity /
batch_fetch_entities), which the Postgres `find_entity()` cascade backed. We replicate that cascade
(exact → prefix → contains, case-insensitive) purely from the data the pipeline already loads:

  get_all_entities()  → name / vertical / bm25_keywords / franchise / composed_text
  load_embeddings()   → entity_id → stored Voyage vector

so resolution returns the IDENTICAL record shape with the SAME stored vector — no Postgres, no
re-embedding. Activated by ENTITY_BACKEND=memory (see the env-gate at the bottom of
pipeline/entity_resolver.py). Other Postgres endpoints (login/history/entities/stats) are UI-only and
are simply not exercised by the router.
"""

import numpy as np

from pipeline.data_loader import get_all_entities
from pipeline.embedding_generator import load_embeddings

_INDEX = None


def _index():
    """Build the lookup once: {by_id, names} where names is an ordered [(lowercased_name, id)] list."""
    global _INDEX
    if _INDEX is None:
        ents = get_all_entities()
        emb = load_embeddings() or {}
        by_id = {
            e["entity_id"]: {
                "entity_id": e["entity_id"],
                "name": e["name"],
                "vertical": e["vertical"],
                "embedding": emb.get(e["entity_id"]),
                "bm25_keywords": e.get("bm25_keywords") or [],
                "franchise": e.get("franchise"),
                "composed_text": e.get("composed_text") or "",
            }
            for e in ents
        }
        names = [(e["name"].lower(), e["entity_id"]) for e in ents]
        _INDEX = {"by_id": by_id, "names": names}
    return _INDEX


def resolve_entity(entity_name: str):
    """Resolve a name via exact → prefix → contains (case-insensitive). Returns the same dict shape as
    the Postgres resolver: entity_id, name, vertical, embedding(np.float32|None), bm25_keywords,
    franchise, match_type. Among prefix/contains ties, prefer the SHORTEST name (most specific)."""
    if not entity_name or not entity_name.strip():
        return None
    q = entity_name.strip().lower()
    idx = _index()
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
    emb = rec.get("embedding")
    rec["embedding"] = np.asarray(emb, dtype=np.float32) if emb is not None else None
    rec["match_type"] = match
    rec.pop("composed_text", None)            # resolve_entity's contract omits composed_text
    return rec


def batch_fetch_entities(entity_ids):
    """Batch-fetch by id → {id: {entity_id, embedding, bm25_keywords, franchise, composed_text}}."""
    if not entity_ids:
        return {}
    by_id = _index()["by_id"]
    out = {}
    for eid in entity_ids:
        e = by_id.get(eid)
        if not e:
            continue
        emb = e.get("embedding")
        out[eid] = {
            "entity_id": eid,
            "embedding": np.asarray(emb, dtype=np.float32) if emb is not None else None,
            "bm25_keywords": e.get("bm25_keywords") or [],
            "franchise": e.get("franchise"),
            "composed_text": e.get("composed_text") or "",
        }
    return out
