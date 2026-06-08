"""Neo4j connection helpers for the Feeds.ai graph PoC.

Single source of connection truth for all `src/` modules. Opens the official
`neo4j` driver and a `graphdatascience` (GDS) client from config (env / .env at
the project root). Keep credentials in `.env`, not in code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from graphdatascience import GraphDataScience

# Load .env from the project root (the parent of this src/ dir).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "feedsaiGraphPoC2026")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

_AUTH = (NEO4J_USER, NEO4J_PASSWORD)


def get_driver():
    """Return a connectivity-verified neo4j driver. Caller is responsible for .close()."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=_AUTH)
    driver.verify_connectivity()
    return driver


def get_gds():
    """Return a graphdatascience (GDS) client bound to the configured database.
    Caller is responsible for .close()."""
    return GraphDataScience(NEO4J_URI, auth=_AUTH, database=NEO4J_DATABASE)


if __name__ == "__main__":
    drv = get_driver()
    print(f"Connected to {NEO4J_URI} as {NEO4J_USER} (database={NEO4J_DATABASE}).")
    drv.close()
