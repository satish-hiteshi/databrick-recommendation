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


# ── Backend switch (deployment) ───────────────────────────────────────────────────────────────────
# Local dev (default) keeps the Postgres `find_entity()` cascade above. The collapsed router on
# Databricks runs with no Postgres and sets ENTITY_BACKEND=memory; the in-memory implementation lives
# in databricks_deploy/serving/inmemory_store.py and is loaded BY FILE PATH (not a package import),
# matching vector_store's Vector Search switch. Same function signatures + record shape.
import os as _os

if _os.getenv("ENTITY_BACKEND", "").lower() == "memory":
    try:                                                # bundle: inmemory_store already on sys.path
        from inmemory_store import resolve_entity, batch_fetch_entities  # noqa: F811
    except ImportError:                                 # local repo: load from databricks_deploy/serving
        import sys as _sys
        _dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            "databricks_deploy", "serving")
        if _dir not in _sys.path:
            _sys.path.insert(0, _dir)
        from inmemory_store import resolve_entity, batch_fetch_entities  # noqa: F811,E402


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
