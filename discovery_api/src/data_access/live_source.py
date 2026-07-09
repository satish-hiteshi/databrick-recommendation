"""LiveDataSource — reads E2's universe + per-entity fields DIRECTLY from the shared substrate
(the re-keyed graph + the Qwen doc parquet), so E2 stops using its 57k CSVs as the source of truth.
Returns the SAME record dataclasses + shapes as CsvDataSource, so the engine/ranking/API are unchanged
(this is the data-access layer only). Selected by DISCOVERY_DATA_SOURCE=live.

ENVIRONMENT-AGNOSTIC: every source LOCATION is read from env with a local-dev default; NOTHING here assumes
an entity count or dataset size. Point the env at a different-sized substrate and the same code runs.

Sources (all READ-ONLY):
  universe + name + vertical + bm25_keywords   ← Qwen parquet  (DISCOVERY_LIVE_PARQUET)  [== the vector
                                                  service's corpus, so retrieved ids always resolve here]
  canonical_genres, community, influence(=pagerank), profile_key/media_source_guid, podcast categories,
  moments (via HAS_MOMENT)                      ← the re-keyed graph (DISCOVERY_LIVE_NEO4J_*)
  lookups (media_platform/region decode names) ← a static decode CSV (DISCOVERY_LIVE_LOOKUPS_CSV)
  follows / reactions / users / moment CTAs    ← NOT present on the substrate → EMPTY. Interactive taste
                                                  comes via the SESSION overlay; CTAs are display-only; global
                                                  velocity counts are therefore empty (thin-signal, as on dev).

Identity (POST composite-key migration): E2 keys on the opaque entity_id "Prefix:media_source_guid".
The old PUBLIC `Entity.property_id` is GONE from the graph, and the public↔entity moment bridge with it,
so moments are now attached by traversing HAS_MOMENT anchored on entity_id (the graph ships 222k of them).
The stable identity is the composite (profile_key + media_source_guid), fully derivable from entity_id via
`shared.identity`. `media_source_guid` is NOT globally unique (~321 cross-vertical guid collisions), so it
is NOT used as a bridge key; entity_id is authoritative everywhere.
"""

from __future__ import annotations

import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .. import config, timeutil
from .base import DataSource
from .records import (Cta, Entity, FollowEvent, GdsSignal, Lookups, Moment, ReactionEvent, User,
                      parse_json_list)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))   # long moment descriptions

_log = logging.getLogger("discovery_api.live_source")

_REPO_ROOT = Path(__file__).resolve().parents[5]     # …/data_access → src → discovery_api → local_code → E2 → ROOT

# ── central identity (the ONE place the composite is built/parsed) — import shared/identity.py ──
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from shared import identity as _ident   # noqa: E402  (composite_of / parse_entity_id / candidate_entity_ids)


def _int(s) -> Optional[int]:
    s = (str(s).strip() if s is not None else "")
    if not s or s.lower() == "null":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _float(s) -> Optional[float]:
    s = (str(s).strip() if s is not None else "")
    if not s or s.lower() == "null":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _as_list(v) -> List[str]:
    """Parquet bm25_keywords is a native list; be defensive about str/JSON/None too."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return parse_json_list(v)


class LiveDataSource(DataSource):
    def __init__(self, parquet=None, moments_csv=None, lookups_csv=None, synth_dir=None,
                 neo4j_uri=None, neo4j_user=None, neo4j_password=None, neo4j_database=None):
        # ── source locations (env → local-dev default; overridable per environment) ──
        # default = the VERIFIED re-keyed 52,512-row parquet (E_PARQUET_VERIFICATION.md); the old
        # embeddings_qwen_44k_prefixed.parquet is OBSOLETE.
        self.parquet = Path(parquet or os.getenv(
            "DISCOVERY_LIVE_PARQUET", str(_REPO_ROOT / "embeddings_updated.parquet")))
        # moments_csv is RETIRED as the moment source (the PUBLIC-id bridge it needed is gone); moments now
        # come from the graph via HAS_MOMENT. Kept only so an explicit legacy override still parses.
        self.moments_csv = Path(moments_csv or os.getenv(
            "DISCOVERY_LIVE_MOMENTS_CSV", str(_REPO_ROOT / "endpoint_3_home_feed" / "data" / "moments_staging_44k.csv")))
        self.lookups_csv = Path(lookups_csv or os.getenv(
            "DISCOVERY_LIVE_LOOKUPS_CSV", str(config.DEV_DATA_DIR / "lookups_dev.csv")))
        # NEO4J: prefer the standard NEO4J_* env (the re-keyed graph); fall back to the E2-specific override.
        self.neo4j_uri = neo4j_uri or os.getenv("DISCOVERY_LIVE_NEO4J_URI") or os.getenv(
            "NEO4J_URI", "bolt://localhost:7690")
        self.neo4j_auth = (neo4j_user or os.getenv("DISCOVERY_LIVE_NEO4J_USER") or os.getenv("NEO4J_USER", "neo4j"),
                           neo4j_password or os.getenv("DISCOVERY_LIVE_NEO4J_PASSWORD") or os.getenv(
                               "NEO4J_PASSWORD", "feedsaiRekeyGraph2026"))
        self.neo4j_db = neo4j_database or os.getenv("DISCOVERY_LIVE_NEO4J_DATABASE", "neo4j")
        # OPTIONAL synthetic engagement (Layer 3): a dir with follows_synth/reactions_synth/users_synth CSVs.
        # Unset → follows/reactions/users stay empty (Layer-2 behaviour). CLEARLY-LABELLED synthetic data.
        _sd = synth_dir or os.getenv("DISCOVERY_LIVE_SYNTH_DIR", "")
        self.synth_dir = Path(_sd) if _sd else None
        # GENRE ADAPTATION: :7688 game "genres" are coarse IGDB categories (horror/survival are Themes). Union
        # game HAS_THEME into canonical_genres so genre matching/carousels aren't broken/over-broad (default on).
        self.include_game_themes = os.getenv("DISCOVERY_LIVE_GAME_GENRES_INCLUDE_THEMES", "1").lower() in ("1", "true", "yes")

        self._loaded = False
        # indexes (identical shapes to CsvDataSource)
        self._entities: Dict[str, Entity] = {}
        self._by_vertical: Dict[str, List[str]] = defaultdict(list)
        # composite/identity: entity_id is authoritative. _guid_to_eids maps a BARE media_source_guid to
        # every entity_id that owns it (>1 ⇒ cross-vertical collision → ambiguous, resolve via the composite).
        self._guid_to_eids: Dict[str, List[str]] = defaultdict(list)
        # legacy bare-guid → entity_id shim (collision-lossy; last-write-wins) kept ONLY for the display-only
        # demo/session paths that still call property_id_to_entity_id with a bare source_id.
        self._prop_to_eid: Dict[int, str] = {}          # bare media_source_guid(int) → entity_id (collision-lossy)
        self._eid_to_prop: Dict[str, int] = {}          # entity_id → media_source_guid(int) (numeric guids only)
        self._moments_by_entity: Dict[str, List[Moment]] = defaultdict(list)
        self._moment_by_id: Dict[int, Moment] = {}
        self._all_moments: List[Moment] = []
        self._podcast_cats: Dict[str, List[str]] = {}
        self._gds: Dict[str, GdsSignal] = {}
        self._lookups = Lookups()
        self._recency_cache: Dict[tuple, List[Moment]] = {}
        self._stats: Dict[str, int] = {}
        # engagement (populated only from synthetic CSVs when synth_dir is set; else empty)
        self._follows_by_user: Dict[int, List[int]] = defaultdict(list)
        self._followers_by_prop: Dict[int, List[int]] = defaultdict(list)
        self._all_follows: List[tuple] = []              # (user_id, property_id, entity_id|None, created_at)
        self._reactions_by_user: Dict[int, List[ReactionEvent]] = defaultdict(list)
        self._all_reactions: List[ReactionEvent] = []
        self._users: Dict[int, User] = {}

    # ── loading ──────────────────────────────────────────────────────────
    def load(self) -> "LiveDataSource":
        if self._loaded:
            return self
        self._load_universe_from_parquet()   # entity_id / name / vertical / bm25_keywords
        self._enrich_from_graph()            # canonical_genres / influence(pagerank) / community / composite / podcast cats
        self._load_moments()                 # moments via HAS_MOMENT traversal anchored on entity_id (graph)
        self._load_lookups()                 # static decode tables
        self._load_synth_engagement()        # OPTIONAL synthetic follows/reactions/users (Layer 3)
        self._loaded = True
        return self

    def _ensure(self):
        if not self._loaded:
            self.load()

    def _load_universe_from_parquet(self):
        import pyarrow.parquet as pq
        t = pq.read_table(self.parquet, columns=["entity_id", "name", "vertical", "bm25_keywords"])
        eids = t.column("entity_id").to_pylist()
        names = t.column("name").to_pylist()
        verts = t.column("vertical").to_pylist()
        kws = t.column("bm25_keywords").to_pylist()
        for eid, nm, vt, kw in zip(eids, names, verts, kws):
            if not eid:
                continue
            e = Entity(entity_id=str(eid), vertical=str(vt or "").lower(), name=nm or "",
                       bm25_keywords=_as_list(kw))   # canonical_genres/themes/etc filled from graph or left empty
            self._entities[e.entity_id] = e
            self._by_vertical[e.vertical].append(e.entity_id)
        self._stats["entities"] = len(self._entities)

    def _enrich_from_graph(self):
        """Enrich the parquet universe from the re-keyed graph, keyed on entity_id (NOT the gone PUBLIC
        property_id). Reads the composite fields (profile_key, media_source_guid) and builds the collision
        map so a bare inbound guid can be resolved/flagged. genres/themes/pagerank/community/podcast-cats
        as before."""
        from neo4j import GraphDatabase
        cypher = (
            "MATCH (e:Entity) "
            "RETURN e.entity_id AS eid, e.profile_key AS pk, e.media_source_guid AS guid, "
            "       e.pagerank AS pr, e.community AS comm, "
            "       [(e)-[:HAS_GENRE]->(g:Genre)     | g.name] AS genres, "
            "       [(e)-[:HAS_THEME]->(t:Theme)     | t.name] AS themes, "
            "       [(e)-[:HAS_CATEGORY]->(c:Category)| c.name] AS cats")
        drv = GraphDatabase.driver(self.neo4j_uri, auth=self.neo4j_auth)
        try:
            with drv.session(database=self.neo4j_db) as s:
                for r in s.run(cypher):
                    eid = r["eid"]
                    e = self._entities.get(eid)
                    if e is None:
                        continue                    # graph entity outside the parquet universe → skip
                    genres = [g for g in (r["genres"] or []) if g]
                    themes = [t for t in (r["themes"] or []) if t]
                    e.themes = themes
                    # genre adaptation: for GAMES, union Themes (horror/survival/scifi) into the coarse IGDB genres
                    e.canonical_genres = (genres + [t for t in themes if t not in genres]) \
                        if (self.include_game_themes and e.vertical == "game") else genres
                    # composite identity: media_source_guid is a STRING (never int-cast). Build the collision
                    # map, plus the legacy int shim for numeric guids (display-only demo paths).
                    guid = r["guid"]
                    if guid is not None:
                        guid = str(guid).strip()
                        self._guid_to_eids[guid].append(eid)
                        try:
                            gi = int(guid)
                        except (TypeError, ValueError):
                            gi = None
                        if gi is not None:
                            self._prop_to_eid[gi] = eid      # collision-lossy (last-write-wins), display-only
                            self._eid_to_prop[eid] = gi
                    self._gds[eid] = GdsSignal(entity_id=eid, vertical=e.vertical,
                                               influence=(float(r["pr"]) if r["pr"] is not None else None),
                                               community=(int(r["comm"]) if r["comm"] is not None else None))
                    cats = [c for c in (r["cats"] or []) if c]
                    if cats:
                        self._podcast_cats[eid] = cats
        finally:
            drv.close()
        self._stats["bridge"] = len(self._prop_to_eid)
        self._stats["gds"] = len(self._gds)
        self._stats["podcast_categories"] = len(self._podcast_cats)

    def resolve_inbound_id(self, value) -> Optional[str]:
        """Normalise an inbound property reference to a served entity_id (or None). Accepts:
          * an entity_id string ("Movie:119163"),
          * a composite dict {profile_key|vertical, media_source_guid},
          * a bare guid (int/str) → resolved against the served universe via candidate_entity_ids; if it
            matches MORE THAN ONE vertical the ref is AMBIGUOUS → a warning is logged and it is dropped
            (the caller should send the composite/entity_id form instead).
        Only returns ids that actually exist in the served universe."""
        self._ensure()
        eid = _ident.coerce_to_entity_id(value)
        if eid is not None:
            return eid if eid in self._entities else None
        # bare guid (no vertical) → resolve against the served graph
        cands = [c for c in _ident.candidate_entity_ids(value) if c in self._entities]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            _log.warning("ambiguous inbound property id %r resolves to %s across verticals; "
                         "send the composite/entity_id form — dropped", value, cands)
        return None

    def _load_moments(self):
        """Attach moments by traversing HAS_MOMENT anchored on entity_id (the re-keyed graph ships the
        edges; the old PUBLIC-property_id CSV bridge is gone). Only moments for a SERVED entity (in the
        parquet universe) are kept. Moment nodes no longer carry title/description/moment_type_id/CTAs —
        those come back empty (E2 surfaces the property_name + event date; titles are null by design)."""
        from neo4j import GraphDatabase
        cypher = (
            "MATCH (e:Entity)-[:HAS_MOMENT]->(m:Moment) "
            "WHERE e.entity_id IN $eids "
            "RETURN e.entity_id AS eid, m.moment_id AS mid, m.media_type_id AS mtype, "
            "       m.profile_key AS mpk, m.event_starts_at AS starts, m.published_at AS pub")
        served = list(self._entities.keys())
        drv = GraphDatabase.driver(self.neo4j_uri, auth=self.neo4j_auth)
        try:
            with drv.session(database=self.neo4j_db) as s:
                # chunk the anchor list so the IN clause stays bounded
                for i in range(0, len(served), 10_000):
                    batch = served[i:i + 10_000]
                    for r in s.run(cypher, eids=batch):
                        eid = r["eid"]
                        mid = _int(r["mid"])            # moment_id is numeric even when the moment guid is not
                        if mid is None or eid not in self._entities:
                            continue
                        starts = r["starts"]           # neo4j DateTime | None → python datetime
                        m = Moment(
                            moment_id=mid, entity_id=eid,
                            property_id=self._eid_to_prop.get(eid) or 0,   # entity source_id (int); 0 if non-numeric
                            media_type_id=_int(r["mtype"]), moment_type_id=None,
                            title="", description="",                       # not on the re-keyed Moment node
                            event_starts_at=(starts.to_native() if hasattr(starts, "to_native") else
                                             timeutil.parse_ts(starts)),
                            event_ends_at=None,
                            media_platform_id=None,
                            profile_key=(str(r["mpk"]) if r["mpk"] is not None else ""),
                            created_at=timeutil.parse_ts(r["pub"]),
                        )
                        self._moment_by_id[mid] = m
                        self._moments_by_entity[eid].append(m)
                        self._all_moments.append(m)
        finally:
            drv.close()
        _floor = datetime.min.replace(tzinfo=timeutil.now().tzinfo)
        for ms in self._moments_by_entity.values():
            ms.sort(key=lambda m: m.event_starts_at or _floor, reverse=True)   # newest/upcoming first
        self._stats["moments"] = len(self._all_moments)

    def _load_lookups(self):
        by_kind: Dict[str, Dict[int, str]] = defaultdict(dict)
        if self.lookups_csv.exists():
            with open(self.lookups_csv, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    kid = _int(r.get("id"))
                    if kid is not None:
                        by_kind[r["kind"]][kid] = r.get("name", "")
        self._lookups = Lookups(by_kind=dict(by_kind))

    def _load_synth_engagement(self):
        """Load CLEARLY-LABELLED synthetic follows/reactions/users (Layer 3) so population-driven signals
        (trending/collaborative/velocity) fire. No-op when synth_dir is unset (→ empty engagement)."""
        if not self.synth_dir:
            return
        up, fp, rp = (self.synth_dir / "users_synth.csv", self.synth_dir / "follows_synth.csv",
                      self.synth_dir / "reactions_synth.csv")
        if up.exists():
            with open(up, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    uid = _int(r.get("id"))
                    if uid is not None:
                        self._users[uid] = User(id=uid, onboarding_status=(r.get("onboarding_status") or None),
                                                account_status_id=_int(r.get("account_status_id")),
                                                created_at=timeutil.parse_ts(r.get("created_at")))
        if fp.exists():
            with open(fp, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    uid, pid = _int(r.get("user_id")), _int(r.get("property_id"))
                    if uid is None or pid is None:
                        continue
                    eid = self._prop_to_eid.get(pid)     # bare source_id → entity_id (legacy synth shim)
                    created = timeutil.parse_ts(r.get("created_at"))
                    self._follows_by_user[uid].append(pid)
                    self._followers_by_prop[pid].append(uid)
                    self._all_follows.append((uid, pid, eid, created))
        if rp.exists():
            with open(rp, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    uid, mid = _int(r.get("user_id")), _int(r.get("moment_id"))
                    if uid is None or mid is None:
                        continue
                    mom = self._moment_by_id.get(mid)
                    ev = ReactionEvent(user_id=uid, moment_id=mid,
                                       reaction_type_id=_int(r.get("reaction_type_id")) or 1,
                                       created_at=timeutil.parse_ts(r.get("created_at")),
                                       entity_id=(mom.entity_id if mom else None))
                    self._reactions_by_user[uid].append(ev)
                    self._all_reactions.append(ev)
        self._stats.update(synth_follows=len(self._all_follows), synth_reactions=len(self._all_reactions),
                           synth_users=len(self._users))

    # ── entities ─────────────────────────────────────────────────────────
    def get_entity(self, entity_id):
        self._ensure(); return self._entities.get(entity_id)

    def get_entities_by_vertical(self, vertical):
        self._ensure(); return [self._entities[e] for e in self._by_vertical.get(vertical.lower(), [])]

    def all_entity_ids(self):
        self._ensure(); return list(self._entities.keys())

    # ── legacy bare-source_id ↔ entity_id shim (collision-lossy; display-only demo/session paths) ──
    # The PUBLIC property_id is gone; this now maps the bare media_source_guid. It is AMBIGUOUS across the
    # ~321 colliding guids (last-write-wins). Inbound request ids must go through resolve_inbound_id().
    def property_id_to_entity_id(self, property_id):
        self._ensure()
        try:
            return self._prop_to_eid.get(int(property_id))
        except (TypeError, ValueError):
            return _ident.coerce_to_entity_id(property_id)   # tolerate a composite/entity_id being passed in

    def entity_id_to_property_id(self, entity_id):
        self._ensure(); return self._eid_to_prop.get(entity_id)

    # ── moments ──────────────────────────────────────────────────────────
    def get_moments_for_property(self, entity_id):
        self._ensure(); return list(self._moments_by_entity.get(entity_id, []))

    def get_moments_for_properties(self, entity_ids):
        self._ensure(); return {e: list(self._moments_by_entity.get(e, [])) for e in entity_ids}

    def get_moment(self, moment_id):
        self._ensure(); return self._moment_by_id.get(int(moment_id))

    def get_recent_moments(self, now, limit, vertical=None):
        self._ensure()
        key = (now.isoformat() if now else None, vertical)
        ordered = self._recency_cache.get(key)
        if ordered is None:
            pool = self._all_moments
            if vertical:
                want = vertical.lower()
                pool = [m for m in pool
                        if self._entities.get(m.entity_id) and self._entities[m.entity_id].vertical == want]
            ordered = sorted(pool, key=lambda m: timeutil.recency_score(m.event_starts_at, now), reverse=True)
            self._recency_cache[key] = ordered
        return ordered[:limit] if limit else list(ordered)

    # ── CTAs — no 44k source (display-only) → empty ──────────────────────
    def get_ctas_for_moment(self, moment_id):
        return []

    def get_ctas_for_moments(self, moment_ids):
        return {int(m): [] for m in moment_ids}

    # ── personal signals — from synthetic engagement when loaded; else empty (interactive taste via overlay) ─
    def get_followed_property_ids(self, user_id):
        self._ensure(); return list(self._follows_by_user.get(int(user_id), []))

    def get_user_follow_events(self, user_id):
        self._ensure(); uid = int(user_id)
        return [FollowEvent(user_id=uid, property_id=pid, created_at=created, entity_id=eid)
                for (u, pid, eid, created) in self._all_follows if u == uid]

    def get_user_reactions(self, user_id):
        self._ensure(); return list(self._reactions_by_user.get(int(user_id), []))

    # ── global signals — aggregate the synthetic population (empty when no synth loaded) ─
    def get_global_reaction_counts(self, window_days=None, now=None):
        self._ensure(); counts: Dict[str, int] = defaultdict(int)
        for ev in self._all_reactions:
            if ev.entity_id and timeutil.within_window(ev.created_at, window_days, now):
                counts[ev.entity_id] += 1
        return dict(counts)

    def get_global_follow_counts(self, window_days=None, now=None):
        self._ensure(); counts: Dict[str, int] = defaultdict(int)
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

    # ── gds signals (influence=pagerank + community, from the graph) ─────
    def get_gds_signal(self, entity_id):
        self._ensure(); return self._gds.get(entity_id)

    def iter_gds_signals(self):
        self._ensure(); return list(self._gds.values())

    # ── podcast categories (from :7688 HAS_CATEGORY; ~50% coverage) ──────
    def get_podcast_categories(self, entity_id):
        self._ensure(); return list(self._podcast_cats.get(entity_id, []))

    # ── users + lookups ──────────────────────────────────────────────────
    def get_user(self, user_id):
        self._ensure(); return self._users.get(int(user_id))   # synthetic users when loaded, else None

    def lookups(self):
        self._ensure(); return self._lookups

    # ── diagnostics (mirrors CsvDataSource.row_counts; not part of the abstract interface) ──
    def row_counts(self) -> Dict[str, int]:
        self._ensure()
        return {
            "entities(parquet)": len(self._entities),
            "guid_shim(source_id→eid)": len(self._prop_to_eid),
            "colliding_guids": sum(1 for v in self._guid_to_eids.values() if len(v) > 1),
            "moments(HAS_MOMENT)": len(self._all_moments),
            "gds(pagerank+community)": len(self._gds),
            "podcast_categories": len(self._podcast_cats),
            "synth_follows": len(self._all_follows), "synth_reactions": len(self._all_reactions),
            "synth_users": len(self._users), "ctas(no 44k source)": 0,
        }
