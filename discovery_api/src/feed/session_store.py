"""Discovery v2 — interactive SESSION store + overlay (the live "build your own taste" demo).

Holds per-browser-session engagement (follows/reactions) over REAL served entities, IN MEMORY. A
MultiSessionOverlay merges a session's engagement onto the CSV base, dispatched by a minted session
user_id, so the SAME v2 engine builds a live feed for the session user. Production data is NEVER modified;
session user_ids live in a high range (800_000_001+) so they never collide with real ids.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..data_access.records import FollowEvent, ReactionEvent

_UID_BASE = 800_000_001


class SessionStore:
    """Mutable per-session engagement. Each session gets a stable synthetic user_id."""

    def __init__(self):
        self._by_sid: Dict[str, dict] = {}
        self._uid_to_sid: Dict[int, str] = {}
        self._next = _UID_BASE

    def ensure(self, sid: str) -> dict:
        s = self._by_sid.get(sid)
        if s is None:
            uid = self._next
            self._next += 1
            s = {"sid": sid, "uid": uid, "follows": [], "reactions": []}
            self._by_sid[sid] = s
            self._uid_to_sid[uid] = sid
        return s

    def uid(self, sid: str) -> int:
        return self.ensure(sid)["uid"]

    def by_uid(self, uid: int) -> Optional[dict]:
        sid = self._uid_to_sid.get(uid)
        return self._by_sid.get(sid) if sid is not None else None

    def follow(self, sid: str, property_id: int, ts: datetime) -> None:
        s = self.ensure(sid)
        if property_id not in [p for p, _ in s["follows"]]:
            s["follows"].append((property_id, ts))

    def unfollow(self, sid: str, property_id: int) -> None:
        s = self.ensure(sid)
        s["follows"] = [(p, t) for p, t in s["follows"] if p != property_id]

    def react(self, sid: str, moment_id: int, ts: datetime) -> None:
        s = self.ensure(sid)
        if moment_id not in [m for m, _ in s["reactions"]]:
            s["reactions"].append((moment_id, ts))

    def unreact(self, sid: str, moment_id: int) -> None:
        s = self.ensure(sid)
        s["reactions"] = [(m, t) for m, t in s["reactions"] if m != moment_id]

    def reset(self, sid: str) -> None:
        s = self.ensure(sid)
        s["follows"], s["reactions"] = [], []

    def follows(self, sid: str) -> List[Tuple[int, datetime]]:
        return list(self.ensure(sid)["follows"])

    def reactions(self, sid: str) -> List[Tuple[int, datetime]]:
        return list(self.ensure(sid)["reactions"])


class MultiSessionOverlay:
    """Wraps the base DataSource; for a session user_id it serves that session's live follows/reactions,
    everything else delegates to base. Global signals (trending) intentionally stay = base."""

    def __init__(self, base, store: SessionStore):
        self._base = base
        self._store = store

    def __getattr__(self, name):
        return getattr(self._base, name)

    def get_followed_property_ids(self, user_id):
        s = self._store.by_uid(user_id)
        if s is not None:
            return [pid for pid, _ in s["follows"]]
        return self._base.get_followed_property_ids(user_id)

    def get_user_follow_events(self, user_id):
        s = self._store.by_uid(user_id)
        if s is not None:
            return [FollowEvent(user_id=user_id, property_id=pid, created_at=ts,
                                entity_id=self._base.property_id_to_entity_id(pid)) for pid, ts in s["follows"]]
        return self._base.get_user_follow_events(user_id)

    def get_user_reactions(self, user_id):
        s = self._store.by_uid(user_id)
        if s is not None:
            out = []
            for mid, ts in s["reactions"]:
                m = self._base.get_moment(mid)
                out.append(ReactionEvent(user_id=user_id, moment_id=mid, reaction_type_id=1,
                                         created_at=ts, entity_id=(m.entity_id if m else None)))
            return out
        return self._base.get_user_reactions(user_id)
