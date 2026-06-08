"""Load data/entities.jsonl into Neo4j (CONTEXT.md §5 graph model).

Batched UNWIND. Per entity: MERGE the Entity by entity_id and set its scalar
properties (incl. the bm25_keywords list for the full-text layer), then MERGE the
shared attribute nodes by name and MERGE the relationships:
  HAS_GENRE, HAS_THEME, HAS_KEYWORD, IN_FRANCHISE, DEVELOPED_BY, PUBLISHED_BY.

All-MERGE => idempotent (safe to re-run; upserts properties, no duplicate
nodes/rels). Requires the constraints from schema.py first (for dedup + speed).

Run:  ./.venv/bin/python src/load.py
"""

import json
from pathlib import Path

from connection import get_driver, NEO4J_DATABASE

_ROOT = Path(__file__).resolve().parent.parent
ENTITIES = _ROOT / "data" / "entities.jsonl"
BATCH_SIZE = 500

LOAD_CYPHER = """
UNWIND $rows AS row
MERGE (e:Entity {entity_id: row.entity_id})
  SET e.name = row.name,
      e.vertical = row.vertical,
      e.description = row.description,
      e.word_count = row.word_count,
      e.bm25_keywords = row.bm25_keywords
WITH e, row
CALL (e, row) { UNWIND row.genres   AS v MERGE (n:Genre   {name: v}) MERGE (e)-[:HAS_GENRE]->(n) }
CALL (e, row) { UNWIND row.themes   AS v MERGE (n:Theme   {name: v}) MERGE (e)-[:HAS_THEME]->(n) }
CALL (e, row) { UNWIND row.keywords AS v MERGE (n:Keyword {name: v}) MERGE (e)-[:HAS_KEYWORD]->(n) }
FOREACH (_ IN CASE WHEN row.franchise IS NULL THEN [] ELSE [1] END |
  MERGE (n:Franchise {name: row.franchise}) MERGE (e)-[:IN_FRANCHISE]->(n))
FOREACH (_ IN CASE WHEN row.developer IS NULL THEN [] ELSE [1] END |
  MERGE (n:Developer {name: row.developer}) MERGE (e)-[:DEVELOPED_BY]->(n))
FOREACH (_ IN CASE WHEN row.publisher IS NULL THEN [] ELSE [1] END |
  MERGE (n:Publisher {name: row.publisher}) MERGE (e)-[:PUBLISHED_BY]->(n))
"""


def _read_rows():
    with ENTITIES.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    rows = _read_rows()
    total = len(rows)
    print(f"Loading {total} entities from {ENTITIES.relative_to(_ROOT)} "
          f"(batch={BATCH_SIZE}) ...")

    driver = get_driver()
    loaded = 0
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            for start in range(0, total, BATCH_SIZE):
                batch = rows[start:start + BATCH_SIZE]
                s.execute_write(lambda tx, b=batch: tx.run(LOAD_CYPHER, rows=b).consume())
                loaded += len(batch)
                print(f"  ...{loaded}/{total}")
    finally:
        driver.close()
    print(f"Done. Loaded/merged {loaded} entities.")


if __name__ == "__main__":
    main()
