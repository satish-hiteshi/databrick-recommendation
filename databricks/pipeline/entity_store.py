"""
In-memory entity data store for Databricks Model Serving.

Loaded once from a pickled artifact at model startup; replaces all JSON file
reads and bulk SQL lookups used by the BM25 index, reranker, and negative filter.
"""

import numpy as np

# Module-level singletons
_entities_by_id: dict = {}
_entities_list: list  = []


def init_from_list(entities: list) -> None:
    """
    Populate the store from a list of entity dicts.
    Each dict must have: entity_id, name, vertical, bm25_keywords,
    franchise, composed_text, and optionally embedding (list[float]).
    Call this once inside MLflow load_context().
    """
    global _entities_by_id, _entities_list
    _entities_list = entities
    _entities_by_id = {e["entity_id"]: e for e in entities}


def get_all() -> list:
    """Return all entities (used to build BM25 index and reranker lookups)."""
    return _entities_list


def get_by_id(entity_id: str) -> dict | None:
    """Return a single entity dict by entity_id, or None if not found."""
    return _entities_by_id.get(entity_id)


def batch_get(entity_ids: list[str]) -> dict:
    """
    Return a dict mapping entity_id → entity dict for every id in the list.
    Missing ids are silently skipped.
    """
    return {eid: _entities_by_id[eid] for eid in entity_ids if eid in _entities_by_id}


def get_embedding(entity_id: str) -> np.ndarray | None:
    """Return the embedding for an entity as a numpy array, or None."""
    entity = _entities_by_id.get(entity_id)
    if entity is None or entity.get("embedding") is None:
        return None
    emb = entity["embedding"]
    return np.array(emb, dtype=np.float32) if not isinstance(emb, np.ndarray) else emb
