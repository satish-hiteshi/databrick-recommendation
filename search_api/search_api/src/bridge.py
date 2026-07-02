"""property_id <-> entity_id bridge — REUSE of endpoint_3 graph_moments.GraphMoments.

The parquet (vectors) is entity_id-keyed; popularity/centrality are property_id-keyed. The verified
1:1 mapping lives on the :7688 :Entity nodes (BOTH property_id int + entity_id str). We subclass E3's
GraphMoments (its driver + creds + the exact :Entity pattern) and pull the FULL map once at startup,
read-only — the same bridge E3 taste.py uses, just materialized for all 44,052 instead of per-request.
Genres come along cheaply via the same HAS_GENRE edge pattern E3 already uses (best-effort, else []).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .reuse import GraphMoments


class SearchBridge(GraphMoments):
    def full_map(self) -> List[dict]:
        q = """
        MATCH (e:Entity)
        RETURN e.property_id AS property_id, e.entity_id AS entity_id, e.vertical AS vertical,
               e.name AS name, [(e)-[:HAS_GENRE]->(g) | g.name] AS genres
        """
        with self._driver.session(database=self._database) as s:
            return s.run(q).data()


@dataclass(slots=True)
class Bridge:
    pid2eid: Dict[int, str] = field(default_factory=dict)
    eid2pid: Dict[str, int] = field(default_factory=dict)
    meta: Dict[int, dict] = field(default_factory=dict)   # property_id -> {vertical, name, genres}

    @property
    def size(self) -> int:
        return len(self.pid2eid)


def build_bridge(uri: str, user: str, password: str, database: str) -> Bridge:
    """Read-only pull of the whole :Entity map. Caller-supplied creds (E4 config), not E3's scrubbed ones."""
    b = Bridge()
    with SearchBridge(uri=uri, user=user, password=password, database=database) as gm:
        for r in gm.full_map():
            pid = int(r["property_id"]); eid = str(r["entity_id"])
            b.pid2eid[pid] = eid
            b.eid2pid[eid] = pid
            b.meta[pid] = {"vertical": r["vertical"], "name": r["name"], "genres": r["genres"] or []}
    return b
