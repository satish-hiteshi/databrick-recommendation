"""live_source_dbx.py — LiveDataSource over the Silver lakehouse (Databricks deployment of Endpoint 2).

Implements the SAME `DataSource` interface as CsvDataSource, returning the SAME record dataclasses, so the
discovery engine is byte-unchanged — only the data SOURCE swaps (DISCOVERY_DATA_SOURCE=live). Mirrors
CsvDataSource's in-memory-index structure, but every table is read from Silver via an injected
`query_fn(sql) -> list[dict]`. That keeps this engine-agnostic:
  • in a notebook (testing):  query_fn = lambda sql: [r.asDict() for r in spark.sql(sql).collect()]
  • in the serving pyfunc:     query_fn = a databricks-sql-connector query (no SparkSession in serving)

═══ STAGING ID RECONCILIATION (foundational — read before changing anything) ═══
The engine treats entity_id as an OPAQUE string and converts to property_id ONLY through the bridge
methods (verified: no int(entity_id) anywhere in discovery_api/src). The STAGING vector corpus
(umi_enriched.entity_embeddings_ready -> ml.entities_vs) is keyed by the BARE `media_source_guid`
(measured: 100% join to public_properties.media_source_guid, 2% to .id). So here:

    entity_id == str(media_source_guid)        # NOT the dev "Vertical:property_id" format

…so the engine's substrate calls (vector_neighbors / vector_retrieve / graph_*) match the corpus. The
bridge maps media_source_guid <-> public_properties.id. If the corpus is ever rebuilt with
"Vertical:property_id" ids, change ONLY `_entity_id_of()` + the entity/bridge SELECTs below.

Genres: the enrichment table carries bm25_keywords but NOT canonical_genres -> keywords-primary taste
(the contract's "minimum viable"); canonical_genres stays [] until a genres source is wired (additive).

Two read tiers (scale split): personal reads (a user's follows/reactions) are cheap; global streams
(iter_*, recent moments, entities, gds) are loaded once and refreshed on a cadence (REFRESH_SECONDS).
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

# The engine's record types + the abstract interface (vendored discovery_api/src). Absolute import so
# this works from the repo root (notebook) and from the serving bundle (discovery_api on sys.path).
from discovery_api.src.data_access.base import DataSource
from discovery_api.src.data_access.records import (
    Cta, Entity, FollowEvent, GdsSignal, Lookups, Moment, ReactionEvent, User)

# media_type_id -> vertical (lowercase, the fixed set). Same map the engine uses.
MEDIA_TYPE_TO_VERTICAL = {1: "game", 3: "movie", 4: "tv", 5: "podcast"}
_VALID_MEDIA_TYPES = tuple(MEDIA_TYPE_TO_VERTICAL)


def _utc(dt) -> Optional[datetime]:
    """Coerce any value to a tz-aware UTC datetime (or None). The engine does `now - ts` everywhere and
    raises on naive datetimes, so every created_at/event_starts_at MUST be tz-aware UTC."""
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _kw_list(v) -> List[str]:
    """bm25_keywords -> lowercase str list. Robust to the source: spark.sql returns a Python LIST; the
    databricks-sql-connector returns a numpy ARRAY (arrow fetch) or a JSON-array STRING ('["sim","rpg"]').
    NOTE: never use `if not v` here — numpy arrays raise 'truth value is ambiguous'. Check None explicitly
    and convert any array-like to a plain list first."""
    if v is None:
        return []
    if hasattr(v, "tolist") and not isinstance(v, (str, bytes)):   # numpy/pandas array -> plain list
        v = v.tolist()
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("[") and s.endswith("]"):
            import json as _json
            try:
                v = _json.loads(s)
            except Exception:
                return [s.lower()]
        else:
            return [s.lower()] if s else []
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip().lower() for x in v if x is not None and str(x).strip()]


class LiveDataSource(DataSource):
    def __init__(self, query_fn: Callable[[str], List[dict]],
                 catalog: str = "stg_feeds_silver",
                 pg_schema: str = "feedspostgres",
                 ml_schema: str = "ml",
                 enrich_schema: str = "umi_enriched",
                 enrich_table: str = "entity_embeddings_ready",
                 refresh_seconds: Optional[int] = None):
        self._q = query_fn
        self.cat = catalog
        self.pg = f"{catalog}.{pg_schema}"
        self.ml = f"{catalog}.{ml_schema}"
        self.enrich = f"{catalog}.{enrich_schema}.{enrich_table}"
        self.refresh_seconds = (refresh_seconds if refresh_seconds is not None
                                else int(os.getenv("DISCOVERY_GLOBAL_REFRESH_SECONDS", "900")))
        self._loaded_at = 0.0
        self._loaded = False
        # indexes (mirror CsvDataSource)
        self._entities: Dict[str, Entity] = {}
        self._by_vertical: Dict[str, List[str]] = defaultdict(list)
        self._prop_to_eid: Dict[int, str] = {}          # property_id -> entity_id(guid)  (TOTAL)
        self._eid_to_prop: Dict[str, int] = {}          # entity_id(guid) -> canonical property_id
        self._moments_by_entity: Dict[str, List[Moment]] = defaultdict(list)
        self._moment_by_id: Dict[int, Moment] = {}
        self._all_moments: List[Moment] = []
        self._ctas_by_moment: Dict[int, List[Cta]] = defaultdict(list)
        self._follows_by_user: Dict[int, List[int]] = defaultdict(list)
        self._followers_by_prop: Dict[int, List[int]] = defaultdict(list)
        self._all_follows: List[tuple] = []             # (uid, pid, eid|None, created)
        self._reactions_by_user: Dict[int, List[ReactionEvent]] = defaultdict(list)
        self._all_reactions: List[ReactionEvent] = []
        self._gds: Dict[str, GdsSignal] = {}
        self._podcast_cats: Dict[str, List[str]] = {}
        self._users: Dict[int, User] = {}
        self._lookups = Lookups()
        self._recency_cache: Dict[tuple, List[Moment]] = {}

    # ── identity: the staging entity_id IS the media_source_guid (see module docstring) ──
    @staticmethod
    def _entity_id_of(media_source_guid) -> Optional[str]:
        if media_source_guid is None:
            return None
        s = str(media_source_guid).strip()
        return s or None

    # ── loading (cache-backed; refresh on cadence) ──────────────────────────
    def load(self) -> "LiveDataSource":
        if self._loaded and (time.time() - self._loaded_at) < self.refresh_seconds:
            return self
        self._reset()
        self._load_entities()      # public_properties ⋈ enrichment ; builds bridge too
        self._load_moments()       # public_moments (Published)
        self._load_ctas()          # public_moment_ctas
        self._load_follows()       # public_property_followers
        self._load_reactions()     # public_user_reactions (user_id recovery)
        self._load_gds()           # pagerank rollup -> per-property influence
        self._load_users()
        self._load_lookups()
        self._load_podcast_categories()
        self._loaded = True
        self._loaded_at = time.time()
        return self

    def _ensure(self):
        if not self._loaded or (time.time() - self._loaded_at) >= self.refresh_seconds:
            self.load()

    def _reset(self):
        for d in (self._entities, self._prop_to_eid, self._eid_to_prop, self._moment_by_id,
                  self._gds, self._podcast_cats, self._users):
            d.clear()
        for dd in (self._by_vertical, self._moments_by_entity, self._ctas_by_moment,
                   self._follows_by_user, self._followers_by_prop, self._reactions_by_user):
            dd.clear()
        self._all_moments.clear(); self._all_follows.clear(); self._all_reactions.clear()
        self._recency_cache.clear()

    # ── entities + bridge (public_properties ⋈ enrichment on media_source_guid) ──
    def _load_entities(self):
        sql = f"""
            SELECT p.id AS property_id, p.media_source_guid AS guid, p.media_type_id AS mtype,
                   p.name AS name, e.bm25_keywords AS bm25
            FROM {self.pg}.public_properties p
            LEFT JOIN {self.enrich} e ON CAST(p.media_source_guid AS STRING) = e.entity_id
            WHERE p.deleted_at IS NULL
              AND p.media_source_guid IS NOT NULL
              AND p.media_type_id IN {_VALID_MEDIA_TYPES}
        """
        for r in self._q(sql):
            guid = self._entity_id_of(r.get("guid"))
            pid = r.get("property_id")
            mtype = r.get("mtype")
            if guid is None or pid is None or mtype not in MEDIA_TYPE_TO_VERTICAL:
                continue
            vertical = MEDIA_TYPE_TO_VERTICAL[mtype]
            # bridge: EVERY property_id maps to its guid (so follows/moments on any of a guid's
            # property rows aggregate to the guid); reverse keeps one canonical property_id per guid.
            self._prop_to_eid[int(pid)] = guid
            if guid not in self._eid_to_prop or int(pid) < self._eid_to_prop[guid]:
                self._eid_to_prop[guid] = int(pid)
            if guid in self._entities:               # dedup: one Entity per guid (first non-dup wins)
                continue
            self._entities[guid] = Entity(
                entity_id=guid, vertical=vertical, name=r.get("name") or "",
                canonical_genres=[],                 # keywords-primary; genres additive (no source yet)
                bm25_keywords=_kw_list(r.get("bm25")))
            self._by_vertical[vertical].append(guid)

    def property_id_to_entity_id(self, property_id):
        self._ensure(); return self._prop_to_eid.get(int(property_id))

    def entity_id_to_property_id(self, entity_id):
        self._ensure(); return self._eid_to_prop.get(entity_id)

    def get_entity(self, entity_id):
        self._ensure(); return self._entities.get(entity_id)

    def get_entities_by_vertical(self, vertical):
        self._ensure(); return [self._entities[e] for e in self._by_vertical.get(vertical.lower(), [])]

    def all_entity_ids(self):
        self._ensure(); return list(self._entities.keys())

    # ── moments — source-switchable (Option A cutover, Greg: both feeds read the graph) ──────────
    # DISCOVERY_MOMENTS_SOURCE = "postgres" (default; Silver public_moments — complete content +
    # availability/live events, ~247k published) | "graph" (Aura :Moment via HAS_MOMENT — the source E3
    # already serves from). Flip to "graph" ONLY once graph_generation carries moment content
    # (title/description/url) + the availability kinds; until then the graph would serve empty titles.
    # Graph mode falls back to Postgres on any failure (never an empty feed from a connect error).
    def _load_moments(self):
        if os.getenv("DISCOVERY_MOMENTS_SOURCE", "postgres").strip().lower() == "graph":
            try:
                self._load_moments_graph()
            except Exception as ex:
                print(f"[live_source] graph moments failed ({type(ex).__name__}: {str(ex)[:120]}) — "
                      "falling back to public_moments", flush=True)
                self._load_moments_pg()
        else:
            self._load_moments_pg()
        _floor = datetime.min.replace(tzinfo=timezone.utc)
        for ms in self._moments_by_entity.values():  # newest-first; callers take [0] as latest
            ms.sort(key=lambda m: m.event_starts_at or _floor, reverse=True)

    def _load_moments_pg(self):
        """Silver public_moments (Published=3). profile_key + media_source_guid = the MOMENT's OWN
        composite (client unique index on moments(media_source_guid, profile_key) — resolves 1:1).
        guid is a STRING, never cast. Falls back to the legacy select if the mirror predates those
        columns (fields stay empty → the serializer emits null; a key is never fabricated)."""
        cols = ("id AS moment_id, property_id, media_type_id, moment_type_id, title, description, "
                "event_starts_at, event_ends_at, media_platform_id, created_at")
        where = "WHERE moment_status_id = 3 AND deleted_at IS NULL AND property_id IS NOT NULL"
        try:
            rows = self._q(f"SELECT {cols}, profile_key, media_source_guid "
                           f"FROM {self.pg}.public_moments {where}")
        except Exception as ex:
            print(f"[live_source] public_moments composite columns unavailable ({str(ex)[:120]}) — "
                  "moment items will emit null moment_profile_key/moment_media_source_guid", flush=True)
            rows = self._q(f"SELECT {cols} FROM {self.pg}.public_moments {where}")
        n = 0
        for r in rows:
            mid = r.get("moment_id"); pid = r.get("property_id")
            if mid is None or pid is None:
                continue
            eid = self._prop_to_eid.get(int(pid))
            if eid is None:                          # moment on an unbridged/non-served property
                continue
            self._index_moment(Moment(
                moment_id=int(mid), entity_id=eid, property_id=int(pid),
                media_type_id=r.get("media_type_id"), moment_type_id=r.get("moment_type_id"),
                title=r.get("title") or "", description=r.get("description") or "",
                event_starts_at=_utc(r.get("event_starts_at")), event_ends_at=_utc(r.get("event_ends_at")),
                media_platform_id=r.get("media_platform_id"), created_at=_utc(r.get("created_at")),
                profile_key=(str(r["profile_key"]) if r.get("profile_key") is not None else ""),
                media_source_guid=(str(r["media_source_guid"]) if r.get("media_source_guid") is not None else "")))
            n += 1
        print(f"[live_source] moments loaded: {n} (source=postgres public_moments)", flush=True)

    def _load_moments_graph(self):
        """Aura :Moment via (e:Entity)-[:HAS_MOMENT]->(m) — the SAME source/universe E3 serves from.
        Rows land in this source's bare-guid entity space via the PARENT's media_source_guid (works
        regardless of the graph's entity_id format). Content fields default to "" until the graph
        carries them (post graph_generation enrichment). NEO4J_* env comes from the deploy notebook."""
        from neo4j import GraphDatabase                   # lazy: only on the graph path
        uri = os.environ["NEO4J_URI"]                     # KeyError → caught by caller → pg fallback
        auth = (os.getenv("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"])
        q = """MATCH (e:Entity)-[:HAS_MOMENT]->(m:Moment)
               RETURN toString(e.media_source_guid) AS parent_guid,
                      m.moment_id AS moment_id, m.profile_key AS mpk,
                      toString(m.media_source_guid) AS mguid,
                      m.title AS title, m.description AS description,
                      m.event_starts_at AS starts, m.event_ends_at AS ends,
                      m.media_type_id AS media_type_id, m.moment_type_id AS moment_type_id,
                      m.media_platform_id AS media_platform_id, m.created_at AS created_at"""
        def _dt(v):                                       # neo4j DateTime -> aware python datetime
            return _utc(v.to_native() if hasattr(v, "to_native") else v)
        n = 0
        drv = GraphDatabase.driver(uri, auth=auth, max_connection_lifetime=300)
        try:
            with drv.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as s:
                for r in s.run(q):
                    eid = self._entity_id_of(r.get("parent_guid"))
                    mid = r.get("moment_id")
                    if eid is None or eid not in self._entities or mid is None:
                        continue
                    pid = self._eid_to_prop.get(eid)
                    self._index_moment(Moment(
                        moment_id=int(mid), entity_id=eid,
                        property_id=(int(pid) if pid is not None else 0),
                        media_type_id=r.get("media_type_id"), moment_type_id=r.get("moment_type_id"),
                        title=r.get("title") or "", description=r.get("description") or "",
                        event_starts_at=_dt(r.get("starts")), event_ends_at=_dt(r.get("ends")),
                        media_platform_id=r.get("media_platform_id"), created_at=_dt(r.get("created_at")),
                        profile_key=(str(r["mpk"]) if r.get("mpk") is not None else ""),
                        media_source_guid=(str(r["mguid"]) if r.get("mguid") is not None else "")))
                    n += 1
        finally:
            drv.close()
        if n == 0:                                        # empty graph read = misconfig, not "no moments"
            raise RuntimeError("graph returned 0 served moments")
        print(f"[live_source] moments loaded: {n} (source=graph HAS_MOMENT — E3-consistent)", flush=True)

    def _index_moment(self, m: "Moment"):
        self._moment_by_id[int(m.moment_id)] = m
        self._moments_by_entity[m.entity_id].append(m)
        self._all_moments.append(m)

    def get_moments_for_property(self, entity_id):
        self._ensure(); return list(self._moments_by_entity.get(entity_id, []))

    def get_moments_for_properties(self, entity_ids):
        self._ensure(); return {e: list(self._moments_by_entity.get(e, [])) for e in entity_ids}

    def get_moment(self, moment_id):
        self._ensure(); return self._moment_by_id.get(int(moment_id))

    def get_recent_moments(self, now, limit, vertical=None):
        self._ensure()
        from discovery_api.src import timeutil
        key = (now.isoformat() if now else None, vertical)
        ordered = self._recency_cache.get(key)
        if ordered is None:
            pool = self._all_moments
            if vertical:
                want = vertical.lower()
                pool = [m for m in pool if self._entities.get(m.entity_id)
                        and self._entities[m.entity_id].vertical == want]
            ordered = sorted(pool, key=lambda m: timeutil.recency_score(m.event_starts_at, now), reverse=True)
            self._recency_cache[key] = ordered
        return ordered[:limit] if limit else list(ordered)

    # ── CTAs (public_moment_ctas; API surface, not ranking) ──
    def _load_ctas(self):
        try:
            sql = f"""SELECT id AS cta_id, moment_id, cta_action_id, region_id, media_platform_id,
                             cta_button_text, url
                      FROM {self.pg}.public_moment_ctas"""
            for r in self._q(sql):
                mid = r.get("moment_id")
                if mid is None:
                    continue
                self._ctas_by_moment[int(mid)].append(Cta(
                    cta_id=int(r.get("cta_id") or 0), moment_id=int(mid),
                    cta_action_id=r.get("cta_action_id"), region_id=r.get("region_id"),
                    media_platform_id=r.get("media_platform_id"),
                    cta_button_text=r.get("cta_button_text") or "", url=r.get("url") or ""))
        except Exception as ex:                      # CTAs are additive — never block the feed on them
            print(f"[live_source] CTAs skipped: {type(ex).__name__}: {str(ex)[:120]}", flush=True)

    def get_ctas_for_moment(self, moment_id):
        self._ensure(); return list(self._ctas_by_moment.get(int(moment_id), []))

    def get_ctas_for_moments(self, moment_ids):
        self._ensure(); return {int(m): list(self._ctas_by_moment.get(int(m), [])) for m in moment_ids}

    # ── personal signals (follows = public_property_followers) ──
    def _load_follows(self):
        # user_id often lands NULL in the typed column (ingestion bug) with the real value in _rescued_data
        # JSON — recover it exactly as _load_reactions does, else authed users read as having ZERO follows
        # (typed user_id NULL → the old `user_id IS NOT NULL` filter dropped every rescued row).
        sql = f"""SELECT COALESCE(CAST(user_id AS BIGINT),
                                  CAST(get_json_object(_rescued_data, '$.user_id') AS BIGINT)) AS user_id,
                         property_id, created_at
                  FROM {self.pg}.public_property_followers
                  WHERE deleted_at IS NULL AND property_id IS NOT NULL
                    AND COALESCE(user_id, get_json_object(_rescued_data, '$.user_id')) IS NOT NULL"""
        for r in self._q(sql):
            uid, pid = r.get("user_id"), r.get("property_id")
            if uid is None or pid is None:
                continue
            uid, pid = int(uid), int(pid)
            eid = self._prop_to_eid.get(pid)
            created = _utc(r.get("created_at"))
            self._follows_by_user[uid].append(pid)
            self._followers_by_prop[pid].append(uid)
            self._all_follows.append((uid, pid, eid, created))

    def get_followed_property_ids(self, user_id):
        self._ensure(); return list(self._follows_by_user.get(int(user_id), []))

    def get_user_follow_events(self, user_id):
        self._ensure(); uid = int(user_id)
        return [FollowEvent(user_id=uid, property_id=pid, created_at=created, entity_id=eid)
                for (u, pid, eid, created) in self._all_follows if u == uid]

    # ── reactions (public_user_reactions; user_id recovery from _rescued_data) ──
    def _load_reactions(self):
        # NOTE: user_id often lands null in the typed column (ingestion bug) with the real value in
        # _rescued_data JSON — recover it. Reactions are near-empty on staging; engine degrades to
        # follows-only taste. Flag the malformed user_id to the data team.
        sql = f"""
            SELECT COALESCE(CAST(user_id AS BIGINT),
                            CAST(get_json_object(_rescued_data, '$.user_id') AS BIGINT)) AS user_id,
                   moment_id, reaction_type_id, created_at
            FROM {self.pg}.public_user_reactions
            WHERE COALESCE(user_id, get_json_object(_rescued_data, '$.user_id')) IS NOT NULL
              AND moment_id IS NOT NULL
        """
        try:
            rows = self._q(sql)
        except Exception as ex:                      # reactions are additive — a missing table or a schema
            print(f"[live_source] reactions skipped ({str(ex)[:120]}) — follows-only taste", flush=True)
            rows = []                                # without _rescued_data (dev) must NOT block warm-up
        for r in rows:
            uid, mid = r.get("user_id"), r.get("moment_id")
            if uid is None or mid is None:
                continue
            uid, mid = int(uid), int(mid)
            mom = self._moment_by_id.get(mid)
            ev = ReactionEvent(user_id=uid, moment_id=mid,
                               reaction_type_id=int(r.get("reaction_type_id") or 0),
                               created_at=_utc(r.get("created_at")),
                               entity_id=mom.entity_id if mom else None)
            self._reactions_by_user[uid].append(ev)
            self._all_reactions.append(ev)

    def get_user_reactions(self, user_id):
        self._ensure(); return list(self._reactions_by_user.get(int(user_id), []))

    # ── global signals (built from the cached full streams) ──
    def get_global_reaction_counts(self, window_days=None, now=None):
        self._ensure()
        from discovery_api.src import timeutil
        counts: Dict[str, int] = defaultdict(int)
        for ev in self._all_reactions:
            if ev.entity_id and timeutil.within_window(ev.created_at, window_days, now):
                counts[ev.entity_id] += 1
        return dict(counts)

    def get_global_follow_counts(self, window_days=None, now=None):
        self._ensure()
        from discovery_api.src import timeutil
        counts: Dict[str, int] = defaultdict(int)
        for (_u, _p, eid, created) in self._all_follows:
            if eid and timeutil.within_window(created, window_days, now):
                counts[eid] += 1
        return dict(counts)

    def get_followers_of_property(self, property_id):
        self._ensure(); return list(self._followers_by_prop.get(int(property_id), []))

    def iter_reaction_events(self):
        self._ensure(); return list(self._all_reactions)

    def iter_follow_events(self):
        self._ensure()
        return [FollowEvent(user_id=u, property_id=pid, created_at=created, entity_id=eid)
                for (u, pid, eid, created) in self._all_follows]

    # ── GDS: moment-level PageRank rolled up to ONE influence per property ──
    def _load_gds(self):
        # discovery_watchmode_pagerank_moments_v1 is MOMENT-level; the engine wants PROPERTY-level
        # influence -> aggregate (MAX over the property's moments). Community: games-only in a different
        # id space (IGDB_Game:X) -> deferred (None) for v1; clustering just loses the tie-break.
        try:
            sql = f"""SELECT property_id, MAX(pagerank_score) AS influence
                      FROM {self.ml}.discovery_watchmode_pagerank_moments_v1
                      WHERE property_id IS NOT NULL GROUP BY property_id"""
            for r in self._q(sql):
                pid = r.get("property_id")
                if pid is None:
                    continue
                eid = self._prop_to_eid.get(int(pid))
                if eid is None:
                    continue
                ent = self._entities.get(eid)
                self._gds[eid] = GdsSignal(entity_id=eid, vertical=(ent.vertical if ent else ""),
                                           influence=r.get("influence"), community=None)
        except Exception as ex:
            print(f"[live_source] GDS skipped: {type(ex).__name__}: {str(ex)[:120]}", flush=True)

    def get_gds_signal(self, entity_id):
        self._ensure(); return self._gds.get(entity_id)

    def iter_gds_signals(self):
        self._ensure(); return list(self._gds.values())

    # ── podcast categories (additive; deferred until the podchaser join is confirmed) ──
    def _load_podcast_categories(self):
        # TODO: podchaser.core_podcast_category keyed by media_source_guid -> categories. Confirm the
        # join key + column, then populate self._podcast_cats[guid] = [categories]. Podcasts run on
        # keywords until then (graceful).
        pass

    def get_podcast_categories(self, entity_id):
        self._ensure(); return list(self._podcast_cats.get(entity_id, []))

    # ── users + lookups ──
    def _load_users(self):
        try:
            sql = f"""SELECT id, onboarding_status, account_status_id, created_at
                      FROM {self.pg}.public_users WHERE id IS NOT NULL"""
            for r in self._q(sql):
                uid = r.get("id")
                if uid is None:
                    continue
                self._users[int(uid)] = User(
                    id=int(uid), onboarding_status=r.get("onboarding_status"),
                    account_status_id=r.get("account_status_id"), created_at=_utc(r.get("created_at")))
        except Exception as ex:
            print(f"[live_source] users skipped: {type(ex).__name__}: {str(ex)[:120]}", flush=True)

    def get_user(self, user_id):
        self._ensure(); return self._users.get(int(user_id))

    def _load_lookups(self):
        # media_platform decode is the load-bearing one ("New on {platform}" carousels). TODO: confirm
        # the platform-lookup table/columns and populate by_kind["media_platform"]. Empty = carousels
        # fall back to platform-id labels (graceful).
        self._lookups = Lookups(by_kind={})

    def lookups(self):
        self._ensure(); return self._lookups

    # ── diagnostics (parity with CsvDataSource.row_counts; used by the test cell) ──
    def row_counts(self) -> Dict[str, int]:
        self._ensure()
        return {"entities": len(self._entities), "bridge": len(self._prop_to_eid),
                "moments": len(self._all_moments), "ctas": sum(len(v) for v in self._ctas_by_moment.values()),
                "follows": len(self._all_follows), "reactions": len(self._all_reactions),
                "gds": len(self._gds), "users": len(self._users)}
