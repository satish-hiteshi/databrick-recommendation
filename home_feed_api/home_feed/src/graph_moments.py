"""Graph traversal for moments — followed property → its :Moment nodes, on the re-keyed graph.

REUSE NOTE: E2's SubstrateClient (:8010) cannot serve this — that service knows nothing about :Moment.
So E3 traverses the graph DIRECTLY with the neo4j driver (the E1 pattern), read-only.

POST composite-key migration: the old PUBLIC `Entity.property_id` is GONE. The follow anchor is now the
stable `entity_id` ("Prefix:media_source_guid"), so the join is
(:Entity {entity_id})-[:HAS_MOMENT]->(:Moment). The re-keyed :Moment node carries moment_id +
media_source_guid + profile_key + event_starts_at + published_at, but NOT title/description/url — those
come back null (E3 surfaces property_name + event date; moment titles are null by design here). The RETURN
carries the composite (profile_key + media_source_guid) so callers can emit it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Optional

from neo4j import GraphDatabase

from . import config
from .candidate import CandidateMoment

# central identity (namespace import from repo root). src → home_feed → local_code → endpoint_3_home_feed → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
try:
    from shared import identity as _ident                # dev repo layout (repo-root shared/)  # noqa: E402
except ImportError:
    from . import _identity as _ident                    # vendored entity-identity at src/_identity.py

# One row per moment of any of the given followed properties, anchored on entity_id. Filter-free on
# status: the loaded set IS the published set (no status property on the node).
_TRAVERSAL = """
UNWIND $eids AS eid
MATCH (e:Entity {entity_id: eid})-[:HAS_MOMENT]->(m:Moment)
RETURN e.entity_id        AS entity_id,
       e.profile_key      AS profile_key,
       e.media_source_guid AS media_source_guid,
       e.vertical         AS vertical,
       e.name             AS property_name,
       m.moment_id        AS moment_id,
       m.title            AS title,
       m.description      AS description,
       m.url              AS url,
       m.event_starts_at  AS event_starts_at,
       m.profile_key      AS moment_kind,
       m.media_source_guid AS moment_media_source_guid,
       m.media_type_id    AS media_type_id,
       m.moment_type_id   AS moment_type_id,
       m.media_platform_id AS media_platform_id,
       m.published_at     AS published_at,
       m.created_at       AS created_at
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


def _guid_to_int(guid) -> int:
    """media_source_guid → int for the legacy CandidateMoment.property_id link (0 if non-numeric)."""
    try:
        return int(str(guid).strip())
    except (TypeError, ValueError):
        return 0


def _moment_id_int(mid) -> int:
    """m.moment_id is a numeric STRING on the re-keyed node → int (CandidateMoment.moment_id is int; the
    serializer/why templates do arithmetic on it). 0 if somehow non-numeric."""
    try:
        return int(str(mid).strip())
    except (TypeError, ValueError):
        return 0


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

    def resolve_follow_keys(self, keys: Iterable) -> "set":
        """Normalise raw follow keys → SERVED entity_ids. An entity_id/composite is coerced (no I/O) and
        kept iff it exists in the graph; a bare source_id is resolved against the graph via
        candidate_entity_ids — if it matches MORE THAN ONE vertical it is AMBIGUOUS (warn + drop), and a
        legacy PUBLIC property_id simply won't match (dropped). Returns a set of entity_id strings."""
        import logging
        log = logging.getLogger("home_feed.follow_source")
        keys = list(keys or [])
        if not keys:
            return set()
        # 1) split into direct entity_ids/composites (no I/O) vs bare guids needing a graph lookup
        direct, bare = [], []
        for k in keys:
            eid = _ident.coerce_to_entity_id(k)
            (direct if eid is not None else bare).append(eid if eid is not None else k)
        # 2) verify direct entity_ids exist; build candidate set for bare guids
        want_direct = {e for e in direct if e}
        cand_map = {}   # entity_id → source bare key (for the ambiguity warning)
        for k in bare:
            for c in _ident.candidate_entity_ids(k):
                cand_map[c] = k
        all_check = want_direct | set(cand_map.keys())
        if not all_check:
            return set()
        q = "MATCH (e:Entity) WHERE e.entity_id IN $eids RETURN e.entity_id AS eid"
        with self._driver.session(database=self._database) as s:
            present = s.execute_read(lambda tx: {r["eid"] for r in tx.run(q, eids=list(all_check))})
        resolved = {e for e in want_direct if e in present}
        # 3) resolve bare guids: exactly-one present vertical wins; >1 ⇒ ambiguous (warn+drop)
        by_bare = {}
        for c in cand_map:
            if c in present:
                by_bare.setdefault(cand_map[c], []).append(c)
        for k, cands in by_bare.items():
            if len(cands) == 1:
                resolved.add(cands[0])
            else:
                log.warning("ambiguous follow key %r resolves to %s across verticals; re-supply the "
                            "followers export with entity_id — dropped", k, cands)
        dropped = [k for k in bare if k not in by_bare]
        if dropped:
            log.warning("%d follow key(s) did not resolve on the re-keyed graph (likely legacy PUBLIC "
                        "property_id); the followers CSV must be re-supplied with entity_id: e.g. %r",
                        len(dropped), dropped[:5])
        return resolved

    def property_attributes(self, entity_ids: Iterable[str]) -> dict:
        """For the taste model: {entity_id: {entity_id, profile_key, media_source_guid, vertical, name,
        genres[], themes[], keywords[], categories[]}}, keyed and anchored on entity_id. Powers the taste
        vector (entity_id → parquet vector) AND the secondary attribute-overlap signal.

        PODCASTS carry NO HAS_GENRE/HAS_THEME/HAS_KEYWORD — they carry HAS_CATEGORY (their only attribute
        edge). We read it so podcast candidates get a non-null attribute-overlap signal, consistent with how
        game/movie/tv resolve via genres. `categories` is empty for game/movie/tv (they have no HAS_CATEGORY),
        so those verticals are unchanged."""
        eids = [str(e) for e in entity_ids if e]
        if not eids:
            return {}
        q = """
        UNWIND $eids AS eid
        MATCH (e:Entity {entity_id: eid})
        RETURN eid AS entity_id, e.profile_key AS profile_key, e.media_source_guid AS media_source_guid,
               e.vertical AS vertical, e.name AS name,
               [(e)-[:HAS_GENRE]->(g)|g.name]      AS genres,
               [(e)-[:HAS_THEME]->(x)|x.name]      AS themes,
               [(e)-[:HAS_KEYWORD]->(k)|k.name]    AS keywords,
               [(e)-[:HAS_CATEGORY]->(cat)|cat.name] AS categories
        """
        with self._driver.session(database=self._database) as s:
            return {r["entity_id"]: {"entity_id": r["entity_id"], "profile_key": r["profile_key"],
                                     "media_source_guid": r["media_source_guid"], "vertical": r["vertical"],
                                     "name": r["name"], "genres": r["genres"], "themes": r["themes"],
                                     "keywords": r["keywords"], "categories": r["categories"]}
                    for r in s.execute_read(lambda tx: tx.run(q, eids=eids).data())}

    def moments_for_properties(self, entity_ids: Iterable[str]) -> List[CandidateMoment]:
        """Traverse to every moment of the given followed properties (anchored on entity_id). Returns the
        RAW pool (no suppression, no cap). Properties with no moments contribute nothing (never error)."""
        eids = [str(e) for e in entity_ids if e]
        if not eids:
            return []
        with self._driver.session(database=self._database) as s:
            rows = s.execute_read(lambda tx: tx.run(_TRAVERSAL, eids=eids).data())
        return [CandidateMoment(
            moment_id=_moment_id_int(r["moment_id"]), property_id=_guid_to_int(r["media_source_guid"]),
            entity_id=r["entity_id"], profile_key=r["profile_key"] or "",
            media_source_guid=str(r["media_source_guid"]) if r["media_source_guid"] is not None else "",
            vertical=r["vertical"], property_name=r["property_name"], title=r["title"] or "",
            description=r["description"], url=r["url"], event_starts_at=_native(r["event_starts_at"]),
            moment_kind=r.get("moment_kind") or "",
            moment_media_source_guid=(str(r["moment_media_source_guid"])
                                      if r.get("moment_media_source_guid") is not None else ""),
            media_type_id=r["media_type_id"], moment_type_id=r["moment_type_id"],
            media_platform_id=r["media_platform_id"], published_at=_native(r["published_at"]),
            created_at=_native(r["created_at"]),
        ) for r in rows]
