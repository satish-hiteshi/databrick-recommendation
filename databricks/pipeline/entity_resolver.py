"""
Entity resolution via Databricks SQL (Delta table).
Replicates the exact → prefix → contains cascade from the original PostgreSQL
find_entity() stored function, then enriches the result with the in-memory
embedding from entity_store.
"""

import numpy as np
from databricks import sql as dbsql

from pipeline.config import (
    DATABRICKS_HOST,
    DATABRICKS_TOKEN,
    SQL_WAREHOUSE_HTTP_PATH,
    ENTITIES_TABLE,
)
from pipeline import entity_store


# ── Connection factory ────────────────────────────────────────────────

def _get_cursor():
    """Open a short-lived Databricks SQL connection and return (conn, cursor)."""
    host = DATABRICKS_HOST.replace("https://", "").replace("http://", "")
    conn = dbsql.connect(
        server_hostname=host,
        http_path=SQL_WAREHOUSE_HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
    )
    return conn, conn.cursor()


def _close(conn, cur):
    try:
        cur.close()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


# ── Core resolver ─────────────────────────────────────────────────────

_SELECT = f"""
    SELECT entity_id, name, vertical, bm25_keywords, franchise
    FROM   {ENTITIES_TABLE}
"""


def resolve_entity(entity_name: str) -> dict | None:
    """
    Find an entity by name using a three-tier fallback:
      1. Exact match   (case-insensitive)
      2. Prefix match  (name starts with query)
      3. Contains match (name contains query)

    Returns a dict with keys: entity_id, name, vertical, embedding (np.array),
    bm25_keywords, franchise, match_type. Returns None if nothing found.
    """
    conn, cur = _get_cursor()
    row = None
    match_type = None

    try:
        # 1. Exact
        cur.execute(
            f"{_SELECT} WHERE LOWER(name) = %s LIMIT 1",
            (entity_name.lower(),),
        )
        row = cur.fetchone()
        if row:
            match_type = "exact"

        # 2. Prefix
        if row is None:
            cur.execute(
                f"{_SELECT} WHERE LOWER(name) LIKE %s LIMIT 1",
                (entity_name.lower() + "%",),
            )
            row = cur.fetchone()
            if row:
                match_type = "prefix"

        # 3. Contains
        if row is None:
            cur.execute(
                f"{_SELECT} WHERE LOWER(name) LIKE %s ORDER BY LENGTH(name) LIMIT 1",
                ("%" + entity_name.lower() + "%",),
            )
            row = cur.fetchone()
            if row:
                match_type = "contains"

    finally:
        _close(conn, cur)

    if row is None:
        print(f"Entity not found: '{entity_name}'")
        return None

    entity_id, name, vertical, bm25_keywords, franchise = row

    # Pull embedding from in-memory store (avoids fetching 4 KB per request via SQL)
    embedding = entity_store.get_embedding(entity_id)

    return {
        "entity_id":     entity_id,
        "name":          name,
        "vertical":      vertical,
        "embedding":     embedding,
        "bm25_keywords": bm25_keywords or [],
        "franchise":     franchise,
        "match_type":    match_type,
    }
