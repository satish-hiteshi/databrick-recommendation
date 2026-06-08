"""Create the Neo4j schema for the Feeds.ai graph PoC (CONTEXT.md §5).

  * Uniqueness constraints on Entity.entity_id and on name for each attribute
    label (Genre, Theme, Keyword, Franchise, Developer, Publisher). Constraints
    also create backing indexes for fast MERGE.
  * A full-text index `entityText` (Lucene/BM25) over Entity.description and
    Entity.name — the embedding-free keyword-retrieval path.

Idempotent (IF NOT EXISTS). Run:  ./.venv/bin/python src/schema.py
"""

from connection import get_driver, NEO4J_DATABASE

# (constraint_name, label, property)
CONSTRAINTS = [
    ("entity_id_unique", "Entity", "entity_id"),
    ("genre_name_unique", "Genre", "name"),
    ("theme_name_unique", "Theme", "name"),
    ("keyword_name_unique", "Keyword", "name"),
    ("franchise_name_unique", "Franchise", "name"),
    ("developer_name_unique", "Developer", "name"),
    ("publisher_name_unique", "Publisher", "name"),
]

FULLTEXT_INDEX = (
    "CREATE FULLTEXT INDEX entityText IF NOT EXISTS "
    "FOR (e:Entity) ON EACH [e.description, e.name]"
)


def main():
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            for name, label, prop in CONSTRAINTS:
                s.run(
                    f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                ).consume()
            s.run(FULLTEXT_INDEX).consume()
            s.run("CALL db.awaitIndexes(300)").consume()

            print("=== CONSTRAINTS ===")
            cons = s.run(
                "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
                "RETURN name, type, labelsOrTypes, properties ORDER BY name"
            ).data()
            for c in cons:
                print(f"  {c['name']:24} {c['type']:18} "
                      f"{c['labelsOrTypes']}.{c['properties']}")

            print("=== INDEXES ===")
            idx = s.run(
                "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state "
                "RETURN name, type, labelsOrTypes, properties, state ORDER BY name"
            ).data()
            for i in idx:
                print(f"  {i['name']:24} {i['type']:12} {i['state']:8} "
                      f"{i['labelsOrTypes']} {i['properties']}")

            ft = s.run(
                "SHOW INDEXES YIELD name, type, options "
                "WHERE name = 'entityText' "
                "RETURN options"
            ).single()
            if ft:
                analyzer = ft["options"].get("indexConfig", {}).get("fulltext.analyzer")
                print(f"  entityText analyzer: {analyzer}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
