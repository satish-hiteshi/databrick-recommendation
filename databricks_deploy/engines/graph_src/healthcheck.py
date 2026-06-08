"""End-to-end Python -> Neo4j healthcheck.

Connects via the shared connection helpers and prints the Neo4j server version,
GDS version, and APOC version, then confirms full-text procedures are available.
Run:  ./.venv/bin/python src/healthcheck.py
"""

from connection import (
    get_driver,
    get_gds,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_DATABASE,
)


def main() -> int:
    print(f"Connecting to {NEO4J_URI} as {NEO4J_USER} (database={NEO4J_DATABASE}) ...")
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            comp = s.run(
                "CALL dbms.components() YIELD name, versions, edition "
                "RETURN versions[0] AS version, edition"
            ).single()
            print(f"  Neo4j server : {comp['version']}  ({comp['edition']} edition)")

            gds_v = s.run("RETURN gds.version() AS v").single()["v"]
            print(f"  GDS plugin   : {gds_v}")

            apoc_v = s.run("RETURN apoc.version() AS v").single()["v"]
            print(f"  APOC plugin  : {apoc_v}")

            ft = s.run(
                "SHOW PROCEDURES YIELD name "
                "WHERE name STARTS WITH 'db.index.fulltext' RETURN count(*) AS n"
            ).single()["n"]
            gds_n = s.run(
                "SHOW PROCEDURES YIELD name "
                "WHERE name STARTS WITH 'gds.' RETURN count(*) AS n"
            ).single()["n"]
            apoc_n = s.run(
                "SHOW PROCEDURES YIELD name "
                "WHERE name STARTS WITH 'apoc.' RETURN count(*) AS n"
            ).single()["n"]
            print(f"  Procedures   : {gds_n} gds.*, {apoc_n} apoc.*, "
                  f"{ft} db.index.fulltext.*")
    finally:
        driver.close()

    # Exercise the GDS python client too (separate driver under the hood).
    gds = get_gds()
    try:
        print(f"  GDS client   : round-trip gds.version() = {gds.version()}")
    finally:
        gds.close()

    print("OK: end-to-end Python -> Neo4j connectivity verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
