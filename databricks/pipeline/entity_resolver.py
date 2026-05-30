import numpy as np
from databricks import sql as dbsql

from pipeline.config import DATABRICKS_HOST, DATABRICKS_TOKEN, SQL_WAREHOUSE_HTTP_PATH, ENTITIES_TABLE
from pipeline import entity_store

_SELECT = f"SELECT entity_id, name, vertical, bm25_keywords, franchise FROM {ENTITIES_TABLE}"


def _get_cursor():
    host = DATABRICKS_HOST.replace("https://", "").replace("http://", "")
    conn = dbsql.connect(server_hostname=host, http_path=SQL_WAREHOUSE_HTTP_PATH, access_token=DATABRICKS_TOKEN)
    return conn, conn.cursor()


def _close(conn, cur):
    try: cur.close()
    except Exception: pass
    try: conn.close()
    except Exception: pass


def _esc(s: str) -> str:
    """Escape single quotes for safe SQL string literals."""
    return s.replace("'", "''")


def resolve_entity(entity_name: str) -> dict | None:
    conn, cur = _get_cursor()
    row, match_type = None, None
    n = _esc(entity_name.lower())

    try:
        cur.execute(f"{_SELECT} WHERE LOWER(name) = '{n}' LIMIT 1")
        row = cur.fetchone()
        if row: match_type = "exact"

        if row is None:
            cur.execute(f"{_SELECT} WHERE LOWER(name) LIKE '{n}%' LIMIT 1")
            row = cur.fetchone()
            if row: match_type = "prefix"

        if row is None:
            cur.execute(f"{_SELECT} WHERE LOWER(name) LIKE '%{n}%' ORDER BY LENGTH(name) LIMIT 1")
            row = cur.fetchone()
            if row: match_type = "contains"
    finally:
        _close(conn, cur)

    if row is None:
        print(f"Entity not found: '{entity_name}'")
        return None

    entity_id, name, vertical, bm25_keywords, franchise = row
    return {
        "entity_id":     entity_id,
        "name":          name,
        "vertical":      vertical,
        "embedding":     entity_store.get_embedding(entity_id),
        "bm25_keywords": bm25_keywords or [],
        "franchise":     franchise,
        "match_type":    match_type,
    }
