"""CsvDataSource — loads discovery_api/data/dev/*.csv into in-memory indexes (the dev default).

Pure-stdlib (csv + dicts) so the data-access layer stays dependency-light and the LiveDataSource can
mirror the SAME return types from SQL. Loads once (lazily on first use), then all reads are dict/list
lookups. Moment `description` is dropped on load (memory: 141K rows); fetch it on demand later.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .. import config
from .. import timeutil
from .base import DataSource
from .records import (Cta, Entity, FollowEvent, GdsSignal, Lookups, Moment, ReactionEvent, User,
                      clean_scalar, parse_json_list)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))   # long moment descriptions


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


class CsvDataSource(DataSource):
    def __init__(self, data_dir: Optional[Path] = None):
        self.dir = Path(data_dir or config.DEV_DATA_DIR)
        self._loaded = False
        # indexes
        self._entities: Dict[str, Entity] = {}
        self._by_vertical: Dict[str, List[str]] = defaultdict(list)
        self._prop_to_eid: Dict[int, str] = {}
        self._eid_to_prop: Dict[str, int] = {}
        self._moments_by_entity: Dict[str, List[Moment]] = defaultdict(list)
        self._moment_by_id: Dict[int, Moment] = {}
        self._all_moments: List[Moment] = []
        self._ctas_by_moment: Dict[int, List[Cta]] = defaultdict(list)
        self._follows_by_user: Dict[int, List[int]] = defaultdict(list)
        self._followers_by_prop: Dict[int, List[int]] = defaultdict(list)
        self._all_follows: List[tuple] = []      # (user_id, property_id, entity_id|None, created_at)
        self._reactions_by_user: Dict[int, List[ReactionEvent]] = defaultdict(list)
        self._all_reactions: List[ReactionEvent] = []
        self._podcast_cats: Dict[str, List[str]] = {}
        self._gds: Dict[str, GdsSignal] = {}
        self._users: Dict[int, User] = {}
        self._lookups = Lookups()
        self._recency_cache: Dict[tuple, List[Moment]] = {}

    # ── loading ─────────────────────────────────────────────────────────
    def _rows(self, fname: str):
        path = self.dir / fname
        if not path.exists():
            raise FileNotFoundError(f"missing dev CSV: {path}")
        with open(path, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)

    def load(self) -> "CsvDataSource":
        if self._loaded:
            return self
        self._load_entities()
        self._load_bridge()
        self._load_moments()
        self._load_ctas()
        self._load_follows()
        self._load_reactions()
        self._load_podcast_categories()
        self._load_gds()
        self._load_users()
        self._load_lookups()
        self._loaded = True
        return self

    def _ensure(self):
        if not self._loaded:
            self.load()

    def _load_entities(self):
        for r in self._rows("entities_dev.csv"):
            eid = r["entity_id"]
            e = Entity(
                entity_id=eid, vertical=r["vertical"].lower(), name=r.get("name", ""),
                canonical_genres=parse_json_list(r.get("canonical_genres")),
                themes=parse_json_list(r.get("themes")),
                franchise=clean_scalar(r.get("franchise")),
                developer=clean_scalar(r.get("developer")),
                publisher=clean_scalar(r.get("publisher")),
                release_date=clean_scalar(r.get("release_date")),
                release_date_int=_int(r.get("release_date_int")),
                bm25_keywords=parse_json_list(r.get("bm25_keywords")),
            )
            self._entities[eid] = e
            self._by_vertical[e.vertical].append(eid)

    def _load_bridge(self):
        for r in self._rows("property_bridge_dev.csv"):
            pid = _int(r["property_id"])
            eid = r["entity_id"]
            if pid is not None:
                self._prop_to_eid[pid] = eid
                self._eid_to_prop[eid] = pid

    def _load_moments(self):
        for r in self._rows("moments_dev.csv"):
            mid = _int(r["moment_id"])
            if mid is None:
                continue
            m = Moment(
                moment_id=mid, entity_id=r["entity_id"], property_id=_int(r.get("property_id")) or 0,
                media_type_id=_int(r.get("media_type_id")), moment_type_id=_int(r.get("moment_type_id")),
                title=r.get("title", "") or "", description=r.get("description", "") or "",
                event_starts_at=timeutil.parse_ts(r.get("event_starts_at")),
                event_ends_at=timeutil.parse_ts(r.get("event_ends_at")),
                media_platform_id=_int(r.get("media_platform_id")),
                profile_key=r.get("profile_key", "") or "",
                created_at=timeutil.parse_ts(r.get("created_at")),
            )
            self._moment_by_id[mid] = m
            self._moments_by_entity[m.entity_id].append(m)
            self._all_moments.append(m)
        # sort each property's moments newest-first (event_starts_at DESC; None last)
        _floor = datetime.min.replace(tzinfo=timeutil.now().tzinfo)
        for ms in self._moments_by_entity.values():
            ms.sort(key=lambda m: m.event_starts_at or _floor, reverse=True)

    def _load_ctas(self):
        for r in self._rows("moment_ctas_dev.csv"):
            mid = _int(r["moment_id"])
            if mid is None:
                continue
            self._ctas_by_moment[mid].append(Cta(
                cta_id=_int(r.get("cta_id")) or 0, moment_id=mid,
                cta_action_id=_int(r.get("cta_action_id")), region_id=_int(r.get("region_id")),
                media_platform_id=_int(r.get("media_platform_id")),
                cta_button_text=r.get("cta_button_text", "") or "", url=r.get("url", "") or "",
            ))

    def _load_follows(self):
        for r in self._rows("follows_dev.csv"):
            uid = _int(r["user_id"]); pid = _int(r["property_id"])
            if uid is None or pid is None:
                continue
            eid = self._prop_to_eid.get(pid)
            created = timeutil.parse_ts(r.get("created_at"))
            self._follows_by_user[uid].append(pid)
            self._followers_by_prop[pid].append(uid)
            self._all_follows.append((uid, pid, eid, created))

    def _load_reactions(self):
        for r in self._rows("reactions_dev.csv"):
            uid = _int(r["user_id"]); mid = _int(r["moment_id"]); rt = _int(r.get("reaction_type_id"))
            if uid is None or mid is None:
                continue
            mom = self._moment_by_id.get(mid)
            ev = ReactionEvent(user_id=uid, moment_id=mid, reaction_type_id=rt or 0,
                               created_at=timeutil.parse_ts(r.get("created_at")),
                               entity_id=mom.entity_id if mom else None)
            self._reactions_by_user[uid].append(ev)
            self._all_reactions.append(ev)

    def _load_podcast_categories(self):
        for r in self._rows("podcast_categories_dev.csv"):
            self._podcast_cats[r["entity_id"]] = parse_json_list(r.get("categories"))

    def _load_gds(self):
        path = self.dir / "gds_signals_dev.csv"
        if not path.exists():     # P2 export; gitignored but on disk for dev
            return
        for r in self._rows("gds_signals_dev.csv"):
            eid = r["entity_id"]
            self._gds[eid] = GdsSignal(entity_id=eid, vertical=r.get("vertical", "").lower(),
                                       influence=_float(r.get("influence")), community=_int(r.get("community")))

    def _load_users(self):
        for r in self._rows("users_dev.csv"):
            uid = _int(r["id"])
            if uid is None:
                continue
            self._users[uid] = User(id=uid, onboarding_status=clean_scalar(r.get("onboarding_status")),
                                    account_status_id=_int(r.get("account_status_id")),
                                    created_at=timeutil.parse_ts(r.get("created_at")))

    def _load_lookups(self):
        by_kind: Dict[str, Dict[int, str]] = defaultdict(dict)
        for r in self._rows("lookups_dev.csv"):
            kid = _int(r.get("id"))
            if kid is not None:
                by_kind[r["kind"]][kid] = r.get("name", "")
        self._lookups = Lookups(by_kind=dict(by_kind))

    # ── entities ────────────────────────────────────────────────────────
    def get_entity(self, entity_id):
        self._ensure(); return self._entities.get(entity_id)

    def get_entities_by_vertical(self, vertical):
        self._ensure(); return [self._entities[e] for e in self._by_vertical.get(vertical.lower(), [])]

    def all_entity_ids(self):
        self._ensure(); return list(self._entities.keys())

    # ── bridge ──────────────────────────────────────────────────────────
    def property_id_to_entity_id(self, property_id):
        self._ensure(); return self._prop_to_eid.get(int(property_id))

    def entity_id_to_property_id(self, entity_id):
        self._ensure(); return self._eid_to_prop.get(entity_id)

    # ── moments ─────────────────────────────────────────────────────────
    def get_moments_for_property(self, entity_id):
        self._ensure(); return list(self._moments_by_entity.get(entity_id, []))

    def get_moments_for_properties(self, entity_ids):
        self._ensure(); return {e: list(self._moments_by_entity.get(e, [])) for e in entity_ids}

    def get_moment(self, moment_id):
        self._ensure(); return self._moment_by_id.get(int(moment_id))

    def get_recent_moments(self, now, limit, vertical=None):
        """Freshest moments by soft-recency around `now` (cached per (now, vertical) for the request)."""
        self._ensure()
        key = (now.isoformat() if now else None, vertical)
        ordered = self._recency_cache.get(key)
        if ordered is None:
            pool = self._all_moments
            if vertical:
                want = vertical.lower()
                pool = [m for m in pool if self._entities.get(m.entity_id) and self._entities[m.entity_id].vertical == want]
            ordered = sorted(pool, key=lambda m: timeutil.recency_score(m.event_starts_at, now), reverse=True)
            self._recency_cache[key] = ordered
        return ordered[:limit] if limit else list(ordered)

    def get_ctas_for_moment(self, moment_id):
        self._ensure(); return list(self._ctas_by_moment.get(int(moment_id), []))

    def get_ctas_for_moments(self, moment_ids):
        self._ensure(); return {int(m): list(self._ctas_by_moment.get(int(m), [])) for m in moment_ids}

    # ── personal signals ────────────────────────────────────────────────
    def get_followed_property_ids(self, user_id):
        self._ensure(); return list(self._follows_by_user.get(int(user_id), []))

    def get_user_follow_events(self, user_id):
        """Timestamped follows for the v2 engagement log (entity_id pre-resolved via the bridge at load)."""
        self._ensure()
        uid = int(user_id)
        return [FollowEvent(user_id=uid, property_id=pid, created_at=created, entity_id=eid)
                for (u, pid, eid, created) in self._all_follows if u == uid]

    def get_user_reactions(self, user_id):
        self._ensure(); return list(self._reactions_by_user.get(int(user_id), []))

    # ── global signals ──────────────────────────────────────────────────
    def get_global_reaction_counts(self, window_days=None, now=None):
        self._ensure()
        counts: Dict[str, int] = defaultdict(int)
        for ev in self._all_reactions:
            if ev.entity_id and timeutil.within_window(ev.created_at, window_days, now):
                counts[ev.entity_id] += 1
        return dict(counts)

    def get_global_follow_counts(self, window_days=None, now=None):
        self._ensure()
        counts: Dict[str, int] = defaultdict(int)
        for (_uid, _pid, eid, created) in self._all_follows:
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

    # ── gds ─────────────────────────────────────────────────────────────
    def get_gds_signal(self, entity_id):
        self._ensure(); return self._gds.get(entity_id)

    def iter_gds_signals(self):
        self._ensure(); return list(self._gds.values())

    # ── podcast categories ──────────────────────────────────────────────
    def get_podcast_categories(self, entity_id):
        self._ensure(); return list(self._podcast_cats.get(entity_id, []))

    # ── users + lookups ─────────────────────────────────────────────────
    def get_user(self, user_id):
        self._ensure(); return self._users.get(int(user_id))

    def lookups(self):
        self._ensure(); return self._lookups

    # ── diagnostics (used by tests/report; not part of the abstract interface) ──
    def row_counts(self) -> Dict[str, int]:
        self._ensure()
        return {
            "entities_dev.csv": len(self._entities),
            "property_bridge_dev.csv": len(self._prop_to_eid),
            "moments_dev.csv": len(self._all_moments),
            "moment_ctas_dev.csv": sum(len(v) for v in self._ctas_by_moment.values()),
            "follows_dev.csv": len(self._all_follows),
            "reactions_dev.csv": len(self._all_reactions),
            "podcast_categories_dev.csv": len(self._podcast_cats),
            "users_dev.csv": len(self._users),
            "lookups_dev.csv": sum(len(v) for v in self._lookups.by_kind.values()),
            "gds_signals_dev.csv": len(self._gds),
        }
