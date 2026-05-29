"""
PostgreSQL database setup for Feeds.ai pipeline.
Creates the feedsai_poc database, entities table, indexes, and the
find_entity() resolution function.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import numpy as np
from tqdm import tqdm

from pipeline.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    EMBEDDING_DIMENSION,
)
from pipeline.data_loader import get_all_entities
from pipeline.embedding_generator import load_embeddings


def _connect_default():
    """Connect to the default 'postgres' database (for DB creation)."""
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname="postgres",
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def _connect_feedsai():
    """Connect to the feedsai_poc database."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def create_database():
    """Create the feedsai_poc database if it doesn't exist."""
    conn = _connect_default()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (POSTGRES_DB,))
    if cur.fetchone():
        print(f"Database '{POSTGRES_DB}' already exists.")
    else:
        cur.execute(f'CREATE DATABASE "{POSTGRES_DB}";')
        print(f"Database '{POSTGRES_DB}' created.")
    cur.close()
    conn.close()


def create_table():
    """Create the entities table."""
    conn = _connect_feedsai()
    cur = conn.cursor()
    cur.execute("""
        DROP TABLE IF EXISTS entities CASCADE;
        CREATE TABLE entities (
            entity_id       VARCHAR PRIMARY KEY,
            name            VARCHAR NOT NULL,
            vertical        VARCHAR NOT NULL,
            description     TEXT,
            composed_text   TEXT NOT NULL,
            embedding       FLOAT8[],
            bm25_keywords   TEXT[],
            franchise       VARCHAR,
            developer       VARCHAR,
            publisher       VARCHAR,
            canonical_genres TEXT[],
            themes          TEXT[],
            keywords        TEXT[]
        );
    """)
    conn.commit()
    print("Table 'entities' created.")
    cur.close()
    conn.close()


def create_indexes():
    """Create indexes for fast lookups."""
    conn = _connect_feedsai()
    cur = conn.cursor()
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_name_lower ON entities (LOWER(name));
        CREATE INDEX IF NOT EXISTS idx_entities_vertical ON entities (vertical);
        CREATE INDEX IF NOT EXISTS idx_entities_franchise ON entities (franchise);
    """)
    conn.commit()
    print("Indexes created (name_lower, vertical, franchise).")
    cur.close()
    conn.close()


def create_find_entity_function():
    """Create the find_entity() SQL function with resolution cascade."""
    conn = _connect_feedsai()
    cur = conn.cursor()
    cur.execute("""
        CREATE OR REPLACE FUNCTION find_entity(search_name TEXT)
        RETURNS TABLE(
            entity_id       VARCHAR,
            name            VARCHAR,
            vertical        VARCHAR,
            embedding       FLOAT8[],
            bm25_keywords   TEXT[],
            franchise       VARCHAR,
            match_type      TEXT
        ) AS $$
        BEGIN
            -- 1. Exact match (case-insensitive)
            RETURN QUERY
                SELECT e.entity_id, e.name, e.vertical,
                       e.embedding, e.bm25_keywords, e.franchise,
                       'exact'::TEXT AS match_type
                FROM entities e
                WHERE LOWER(e.name) = LOWER(search_name)
                LIMIT 1;
            IF FOUND THEN RETURN; END IF;

            -- 2. Prefix match
            RETURN QUERY
                SELECT e.entity_id, e.name, e.vertical,
                       e.embedding, e.bm25_keywords, e.franchise,
                       'prefix'::TEXT AS match_type
                FROM entities e
                WHERE LOWER(e.name) LIKE LOWER(search_name) || '%'
                ORDER BY LENGTH(e.name)
                LIMIT 1;
            IF FOUND THEN RETURN; END IF;

            -- 3. Contains match
            RETURN QUERY
                SELECT e.entity_id, e.name, e.vertical,
                       e.embedding, e.bm25_keywords, e.franchise,
                       'contains'::TEXT AS match_type
                FROM entities e
                WHERE LOWER(e.name) LIKE '%' || LOWER(search_name) || '%'
                ORDER BY LENGTH(e.name)
                LIMIT 1;
            IF FOUND THEN RETURN; END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)
    conn.commit()
    print("Function 'find_entity()' created.")
    cur.close()
    conn.close()


def insert_entities():
    """Load all entities + embeddings and insert into PostgreSQL."""
    entities = get_all_entities()
    embeddings = load_embeddings()
    if not embeddings:
        raise RuntimeError("No embeddings found. Run embedding_generator.py first.")

    conn = _connect_feedsai()
    cur = conn.cursor()

    print(f"Inserting {len(entities)} entities into PostgreSQL...")
    for e in tqdm(entities, desc="Inserting"):
        eid = e["entity_id"]
        emb = embeddings.get(eid)
        if emb is not None:
            emb_list = emb.tolist() if isinstance(emb, np.ndarray) else emb
        else:
            emb_list = None

        cur.execute("""
            INSERT INTO entities
                (entity_id, name, vertical, description, composed_text,
                 embedding, bm25_keywords, franchise, developer, publisher,
                 canonical_genres, themes, keywords)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_id) DO UPDATE SET
                name = EXCLUDED.name,
                embedding = EXCLUDED.embedding;
        """, (
            eid,
            e["name"],
            e["vertical"],
            e.get("description"),
            e["composed_text"],
            emb_list,
            e["bm25_keywords"],
            e.get("franchise"),
            e.get("developer"),
            e.get("publisher"),
            e.get("canonical_genres", []),
            e.get("themes", []),
            e.get("keywords") if e.get("keywords") else [],
        ))

    conn.commit()
    cur.close()

    # Verify count
    cur2 = conn.cursor()
    cur2.execute("SELECT COUNT(*) FROM entities;")
    count = cur2.fetchone()[0]
    cur2.close()
    conn.close()

    print(f"Inserted {count} entities into PostgreSQL.")
    return count


def setup_postgres():
    """Run full PostgreSQL setup sequence."""
    create_database()
    create_table()
    insert_entities()
    create_indexes()
    create_find_entity_function()
    print("\nPostgreSQL setup complete.")


if __name__ == "__main__":
    setup_postgres()
