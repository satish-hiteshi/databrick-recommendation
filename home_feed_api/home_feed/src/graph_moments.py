"""Graph traversal for moments — followed property → its :Moment nodes, on the 44k graph (:7688).

REUSE NOTE: E2's SubstrateClient (:8010) cannot serve this — that service points at the 57k graph and
knows nothing about :Moment. So E3 traverses the 44k graph DIRECTLY with the neo4j driver (the E1
pattern), read-only. The join is strictly (:Entity {property_id})-[:HAS_MOMENT]->(:Moment), verified
in Step 0: edge direction Entity→Moment, follow key = bare-int Entity.property_id.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from neo4j import GraphDatabase

from . import config
from .candidate import CandidateMoment

# One row per moment of any of the given followed properties. Filter-free on status: the loaded set IS
# the published (status=3) set (Step 0 — no status property exists on the node).
_TRAVERSAL = """
UNWIND $pids AS pid
MATCH (e:Entity {property_id: pid})-[:HAS_MOMENT]->(m:Moment)
RETURN e.property_id   AS property_id,
       e.entity_id     AS entity_id,
       e.vertical      AS vertical,
       e.name          AS property_name,
       m.moment_id     AS moment_id,
       m.title         AS title,
       m.description   AS description,
       m.url           AS url,
       m.event_starts_at  AS event_starts_at,
       m.media_type_id    AS media_type_id,
       m.moment_type_id   AS moment_type_id,
       m.media_platform_id AS media_platform_id,
       m.published_at  AS published_at,
       m.created_at    AS created_at
"""


def _native(v):
    """neo4j temporal -> python datetime (driver returns DateTime). ISO STRINGS (the Aura moments were
    CSV-loaded, so event_starts_at/published_at/created_at can arrive as text) -> datetime via E2's
    parse_ts; unparseable/'null'/'' -> None. Passthrough for everything else. Without this, a string
    date reaches suppression/recency and raises 'datetime <= str'."""
    if hasattr(v, "to_native"):
        return v.to_native()
    if isinstance(v, str):
        from .reuse import timeutil            # lazy import: avoids any import cycle; called only at query time
        return timeutil.parse_ts(v)
    return v


class GraphMoments:
    """Thin read-only wrapper over the 44k graph for moment traversal. Caller owns the lifecycle
    (use as a context manager or call close())."""

    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None,
                 password: Optional[str] = None, database: Optional[str] = None):
        self._driver = GraphDatabase.driver(
            uri or config.NEO4J_URI,
            auth=(user or config.NEO4J_USER, password or config.NEO4J_PASSWORD),
            # Singleton (built once at warm-up). liveness_check_timeout discards a connection Aura has
            # already dropped BEFORE it is handed to a query — kills the intermittent "defunct connection"
            # error; execute_read (below) additionally retries transient failures.
            max_connection_lifetime=300, liveness_check_timeout=30,
            connection_acquisition_timeout=30, keep_alive=True)
        self._database = database or config.NEO4J_DATABASE

    def __enter__(self) -> "GraphMoments":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._driver.close()

    def property_attributes(self, property_ids: Iterable[int]) -> dict:
        """For the taste model: {property_id: {entity_id, vertical, name, genres[], themes[], keywords[]}}.
        Read live from the graph edges (no precomputed table). Powers the taste vector (entity_id → parquet
        vector) AND the secondary attribute-overlap signal."""
        pids = [int(p) for p in property_ids]
        if not pids:
            return {}
        q = """
        UNWIND $pids AS pid
        MATCH (e:Entity {property_id: pid})
        RETURN pid AS property_id, e.entity_id AS entity_id, e.vertical AS vertical, e.name AS name,
               [(e)-[:HAS_GENRE]->(g)|g.name]   AS genres,
               [(e)-[:HAS_THEME]->(x)|x.name]   AS themes,
               [(e)-[:HAS_KEYWORD]->(k)|k.name] AS keywords
        """
        with self._driver.session(database=self._database) as s:
            rows = s.execute_read(lambda tx: tx.run(q, pids=pids).data())
        return {r["property_id"]: {"entity_id": r["entity_id"], "vertical": r["vertical"],
                                   "name": r["name"], "genres": r["genres"], "themes": r["themes"],
                                   "keywords": r["keywords"]} for r in rows}

    def moments_for_properties(self, property_ids: Iterable[int]) -> List[CandidateMoment]:
        """Traverse to every moment of the given followed properties. Returns the RAW pool (no
        suppression, no cap). Properties with no moments simply contribute nothing (never error)."""
        pids = [int(p) for p in property_ids]
        if not pids:
            return []
        with self._driver.session(database=self._database) as s:
            rows = s.execute_read(lambda tx: tx.run(_TRAVERSAL, pids=pids).data())
        return [CandidateMoment(
            moment_id=r["moment_id"], property_id=r["property_id"], entity_id=r["entity_id"],
            vertical=r["vertical"], property_name=r["property_name"], title=r["title"] or "",
            description=r["description"], url=r["url"], event_starts_at=_native(r["event_starts_at"]),
            media_type_id=r["media_type_id"], moment_type_id=r["moment_type_id"],
            media_platform_id=r["media_platform_id"], published_at=_native(r["published_at"]),
            created_at=_native(r["created_at"]),
        ) for r in rows]
