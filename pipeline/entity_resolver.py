"""
Entity resolution via PostgreSQL find_entity() cascade.
Exact match -> prefix match -> contains match.
"""

import numpy as np
import psycopg2

from pipeline.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
)


def _connect():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def resolve_entity(entity_name: str):
    """
    Resolve an entity name using the PostgreSQL find_entity() cascade.
    Returns dict with: entity_id, name, vertical, embedding (np.array),
    bm25_keywords, franchise, match_type.
    Returns None if not found.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM find_entity(%s);", (entity_name,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row is None:
        print(f"Entity not found: '{entity_name}'")
        return None

    entity_id, name, vertical, embedding, bm25_keywords, franchise, match_type = row

    return {
        "entity_id": entity_id,
        "name": name,
        "vertical": vertical,
        "embedding": np.array(embedding, dtype=np.float32) if embedding else None,
        "bm25_keywords": bm25_keywords or [],
        "franchise": franchise,
        "match_type": match_type,
    }


def batch_fetch_entities(entity_ids: list):
    """
    Batch-fetch entity data (embedding, keywords, franchise, composed_text) by entity_id list.
    Returns dict mapping entity_id -> {embedding, bm25_keywords, franchise, composed_text}.
    """
    if not entity_ids:
        return {}

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """SELECT entity_id, embedding, bm25_keywords, franchise, composed_text
           FROM entities WHERE entity_id = ANY(%s);""",
        (entity_ids,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = {}
    for eid, embedding, keywords, franchise, composed_text in rows:
        result[eid] = {
            "entity_id": eid,
            "embedding": np.array(embedding, dtype=np.float32) if embedding else None,
            "bm25_keywords": keywords or [],
            "franchise": franchise,
            "composed_text": composed_text or "",
        }
    return result


if __name__ == "__main__":
    test_names = [
        "Elden Ring Nightreign",
        "elden ring nightreign",
        "Silent Hill",
        "doom",
        "Paw Patrol",
    ]
    for name in test_names:
        result = resolve_entity(name)
        if result:
            print(f"  '{name}' -> {result['name']} ({result['vertical']}) "
                  f"[{result['match_type']}] emb_dim={len(result['embedding']) if result['embedding'] is not None else 0}")
        else:
            print(f"  '{name}' -> NOT FOUND")
