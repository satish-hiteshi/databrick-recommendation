"""entity_id ⇄ composite bridge — over the vendored GraphMomentsBase neo4j lifecycle (see _vendored.py).

POST composite-key migration: the old PUBLIC `Entity.property_id` is GONE from the graph (this file's
`int(r["property_id"])` was the HARD startup crash — `int(None)` TypeError). The stable identity is now
the composite (profile_key + media_source_guid), whose string form is entity_id "Prefix:media_source_guid".

This bridge is now **entity_id-native**: it pulls the whole :Entity map keyed on entity_id, carrying the
composite (profile_key + media_source_guid) + vertical/name/genres. It also exposes a legacy bare
media_source_guid (=source_id) ↔ entity_id shim (collision-lossy — ~321 guids collide across verticals)
so the PUBLIC-keyed PG tables (property_popularity/entity_centrality) can be joined on source_id ONCE THEY
ARE RE-KEYED (they currently hold the dead PUBLIC id — see store.py / the report).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ._vendored import GraphMomentsBase


class SearchBridge(GraphMomentsBase):
    def full_map(self) -> List[dict]:
        q = """
        MATCH (e:Entity)
        RETURN e.entity_id AS entity_id, e.profile_key AS profile_key,
               e.media_source_guid AS media_source_guid, e.vertical AS vertical,
               e.name AS name, [(e)-[:HAS_GENRE]->(g) | g.name] AS genres
        """
        with self._driver.session(database=self._database) as s:
            return s.run(q).data()


def _guid_to_int(guid) -> Optional[int]:
    """media_source_guid → int for the legacy source_id shim (None if non-numeric; all property guids are numeric)."""
    try:
        return int(str(guid).strip())
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class Bridge:
    # PRIMARY: keyed on the stable entity_id.
    meta: Dict[str, dict] = field(default_factory=dict)   # entity_id -> {profile_key, media_source_guid, vertical, name, genres}
    # ENGINE-FACING view keyed on the numeric source_id (=media_source_guid) — the engine's integer join key
    # POST-migration (the dead PUBLIC property_id is replaced by source_id, which the re-keyed PG tables also
    # carry). Collision-lossy on the ~321 cross-vertical guids (the store's dedup_key disambiguates).
    meta_by_source_id: Dict[int, dict] = field(default_factory=dict)   # source_id(int) -> {entity_id, profile_key, ...}
    # LEGACY source_id shim (collision-lossy, last-write-wins): bare media_source_guid(int) ⇄ entity_id.
    guid2eid: Dict[int, str] = field(default_factory=dict)
    eid2guid: Dict[str, int] = field(default_factory=dict)

    # ── back-compat aliases (old callers used pid2eid/eid2pid; property_id ≡ the surviving source_id now) ──
    @property
    def pid2eid(self) -> Dict[int, str]:
        return self.guid2eid

    @property
    def eid2pid(self) -> Dict[str, int]:
        return self.eid2guid

    @property
    def size(self) -> int:
        return len(self.meta)


def build_bridge(uri: str, user: str, password: str, database: str) -> Bridge:
    """Read-only pull of the whole :Entity map, keyed on entity_id + carrying the composite. Caller-supplied
    creds (E4 config). NO MORE int(None): entity_id is always present; the numeric source_id shim is
    populated only for numeric guids."""
    b = Bridge()
    with SearchBridge(uri=uri, user=user, password=password, database=database) as gm:
        for r in gm.full_map():
            eid = str(r["entity_id"])
            if not eid:
                continue
            guid = r["media_source_guid"]
            b.meta[eid] = {"profile_key": r["profile_key"],
                           "media_source_guid": (str(guid) if guid is not None else ""),
                           "vertical": r["vertical"], "name": r["name"], "genres": r["genres"] or []}
            gi = _guid_to_int(guid)
            if gi is not None:
                b.guid2eid[gi] = eid            # collision-lossy (last-write-wins); display/legacy join only
                b.eid2guid[eid] = gi
                b.meta_by_source_id[gi] = {"entity_id": eid, **b.meta[eid]}   # engine's int-keyed view
    return b
