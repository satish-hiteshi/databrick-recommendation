import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from graphdatascience import GraphDataScience

# Load .env from the project root (the parent of this src/ dir).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# Committed defaults name the CORRECT re-keyed substrate explicitly (the local re-keyed graph on :7690 =
# 52,510 :Entity nodes). Prod overrides NEO4J_URI/PASSWORD via env to the AuraDS instance. The old :7687
# (57k) / :7688 (44k) instances are obsolete and must never be picked up silently — substrate_guard.py
# asserts the entity count at startup and FAILS LOUD on a wrong graph.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7690")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "feedsaiRekeyGraph2026")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# ── Schema portability (env-driven; mirrors shared/graph/connection.py) ──
# The re-keyed neo4j 2026.05 graph stores PageRank as `pagerank` (not `influence`) and names the maker
# edges HAS_DEVELOPER/HAS_PUBLISHER (not DEVELOPED_BY/PUBLISHED_BY). These knobs let the SAME Cypher run
# on either graph — nothing is hard-coded to a dataset. (Cypher cannot parameterise a property/rel NAME,
# so these are interpolated into query text; values come only from our own env config, never user input.)
# Defaults now name the re-keyed graph's schema (matches model.py's deploy setdefaults); env can override.
GRAPH_INFLUENCE_PROP = os.getenv("GRAPH_INFLUENCE_PROP", "pagerank")
GRAPH_DEVELOPER_REL = os.getenv("GRAPH_DEVELOPER_REL", "HAS_DEVELOPER")
GRAPH_PUBLISHER_REL = os.getenv("GRAPH_PUBLISHER_REL", "HAS_PUBLISHER")

_AUTH = (NEO4J_USER, NEO4J_PASSWORD)


def get_driver():
    # Client Neo4j spec: liveness_check discards a dropped connection before use; keep_alive + lifetime.
    driver = GraphDatabase.driver(NEO4J_URI, auth=_AUTH,
                                  max_connection_lifetime=300, liveness_check_timeout=30,
                                  connection_acquisition_timeout=30, keep_alive=True)
    driver.verify_connectivity()
    return driver


def get_gds():
    return GraphDataScience(NEO4J_URI, auth=_AUTH, database=NEO4J_DATABASE)


if __name__ == "__main__":
    drv = get_driver()
    print(f"Connected to {NEO4J_URI} as {NEO4J_USER} (database={NEO4J_DATABASE}).")
    drv.close()
