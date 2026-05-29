import numpy as np

_entities_by_id: dict = {}
_entities_list: list  = []


def init_from_list(entities: list) -> None:
    global _entities_by_id, _entities_list
    _entities_list = entities
    _entities_by_id = {e["entity_id"]: e for e in entities}


def get_all() -> list:
    return _entities_list


def get_by_id(entity_id: str) -> dict | None:
    return _entities_by_id.get(entity_id)


def batch_get(entity_ids: list[str]) -> dict:
    return {eid: _entities_by_id[eid] for eid in entity_ids if eid in _entities_by_id}


def get_embedding(entity_id: str) -> np.ndarray | None:
    entity = _entities_by_id.get(entity_id)
    if entity is None or entity.get("embedding") is None:
        return None
    emb = entity["embedding"]
    return np.array(emb, dtype=np.float32) if not isinstance(emb, np.ndarray) else emb
