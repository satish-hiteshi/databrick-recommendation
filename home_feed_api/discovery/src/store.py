"""store.py — per-user state for the Discovery feed.

Now PERSISTENT (Phase 2 of the recommendation redesign). Each follow/like/dislike is written
through to Postgres (feedsai_discovery on :5433): the current-state projection tables
`user_follows` / `user_reactions` (fast read for the taste centroid) AND the append-only
`user_events` log (history + trend aggregation + future ML). WATCH / SKIP / CLICK go to
`user_events` only.

Robustness: every write is write-through to an in-memory cache as well, and if Postgres is
unreachable the store transparently degrades to the old in-memory-only behaviour (the demo never
500s). Set DISCOVERY_PG=0 to force pure in-memory (e.g. tests with no DB).

entity_id format is "Vertical:integer"; we store the integer property_id internally so it joins
directly with the catalogue / embeddings / graph.
"""
import os
import threading

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover
    psycopg2 = None

_PG_CONN = dict(host="localhost", port=5433, user="postgres", password="postgres",
                dbname="feedsai_discovery")
_PG_ENABLED = os.environ.get("DISCOVERY_PG", "1") != "0" and psycopg2 is not None

# ── Databricks live source (env-gated; INERT for local runs) ───────────────────────────────────────
# When HOME_DATA_SOURCE=live, snapshot() reads the user's follows from Silver
# (public_property_followers) via the injected query_fn instead of Postgres. Reactions/watched stay
# empty on live for now (additive) — the follow-gated feed only needs `followed`; taste degrades to
# follows-only, which the ranker already handles.
_LIVE = os.environ.get("HOME_DATA_SOURCE", "").lower() == "live"
_SILVER_PG = f"{os.environ.get('HOME_SILVER_CATALOG', 'stg_feeds_silver')}.feedspostgres"
_QUERY_FN = None   # set by the serving pyfunc: query_fn(sql) -> list[dict]


def set_query_fn(fn):
    """Inject the Silver query function (serving). MUST be called before the first snapshot() when live."""
    global _QUERY_FN
    _QUERY_FN = fn

# event_type -> default engagement weight written to user_events (trend engine reads these)
EVENT_TYPES = {"HEART", "FIRE", "CONFETTI", "LIKE", "DISLIKE", "FOLLOW", "UNFOLLOW",
               "WATCH", "SKIP", "CLICK", "IMPRESSION"}

# production reaction model (public_reaction_types): all POSITIVE, weighted by intensity for the
# taste centroid. fire 🔥 > heart ❤️ > confetti 🎉. No dislike exists in production.
REACTION_WEIGHTS = {"fire": 3.0, "heart": 2.0, "confetti": 1.5}


def parse_entity_id(entity_id):
    """'Movie:88177' -> 88177 (int). Tolerates lowercase vertical and stray spaces.

    Returns None if the entity_id is malformed.
    """
    if entity_id is None:
        return None
    s = str(entity_id).strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        return None


class _UserState:
    __slots__ = ("followed", "reactions")

    def __init__(self):
        self.followed = set()   # property_ids the user follows
        self.reactions = {}     # property_id -> reaction_type ('heart'/'fire'/'confetti')


class UserStore:
    """All users' follow/like/dislike state, keyed by integer user_id.

    Postgres is the source of truth when reachable; the in-memory cache is a write-through mirror
    and the fallback. The public method surface is unchanged from the in-memory-only version, plus
    `event()` for raw WATCH/SKIP/CLICK logging.
    """

    def __init__(self):
        self._users = {}
        self._lock = threading.Lock()
        self._conn = None
        self._pg = _PG_ENABLED
        self._degraded = False   # True once a working PG connection was lost (surfaced in /health)
        self._loaded = set()   # user_ids already hydrated from PG into the cache
        if self._pg:
            self._connect()

    # ── postgres plumbing ──────────────────────────────────────────────────────
    def _connect(self):
        try:
            self._conn = psycopg2.connect(connect_timeout=5, **_PG_CONN)
            self._conn.autocommit = True
            return True
        except Exception as e:  # pragma: no cover
            print(f"[store] Postgres unavailable ({str(e)[:80]}); using in-memory only", flush=True)
            self._conn = None
            self._pg = False
            self._degraded = True
            return False

    def _exec(self, sql, params=None, fetch=False):
        """Run a statement, reconnecting once on a dropped connection. Returns rows if fetch=True,
        or None on failure (caller falls back to the in-memory cache)."""
        if not self._pg:
            return None
        for attempt in (1, 2):
            try:
                with self._conn.cursor() as cur:
                    cur.execute(sql, params or ())
                    return cur.fetchall() if fetch else True
            except Exception as e:
                if attempt == 1 and self._connect():
                    continue
                print(f"[store] PG op failed ({str(e)[:80]}); degrading to in-memory", flush=True)
                self._pg = False
                self._degraded = True
                return None

    def _log_event(self, user_id, entity_id, pid, event_type, weight, meta=None):
        if not self._pg:
            return
        import json
        self._exec(
            "INSERT INTO user_events (user_id, entity_id, property_id, event_type, weight, meta) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, entity_id, pid, event_type, float(weight),
             json.dumps(meta) if meta else None),
        )

    def _hydrate(self, user_id):
        """Load a user's current state from PG into the cache once (lazy)."""
        if not self._pg or user_id in self._loaded:
            return
        st = self._state(user_id)
        rows = self._exec("SELECT property_id FROM user_follows WHERE user_id=%s", (user_id,), fetch=True)
        if rows is not None:
            st.followed = {int(r[0]) for r in rows}
        rows = self._exec("SELECT property_id, reaction FROM user_reactions WHERE user_id=%s",
                          (user_id,), fetch=True)
        if rows is not None:
            st.reactions = {int(p): r for p, r in rows}
        self._loaded.add(user_id)

    def _state(self, user_id):
        st = self._users.get(user_id)
        if st is None:
            st = _UserState()
            self._users[user_id] = st
        return st

    # ── mutations ─────────────────────────────────────────────────────────────
    def follow(self, user_id, entity_id):
        pid = parse_entity_id(entity_id)
        if pid is None:
            return False
        with self._lock:
            self._hydrate(user_id)
            st = self._state(user_id)
            st.followed.add(pid)
            self._exec("INSERT INTO user_follows (user_id, property_id) VALUES (%s,%s) "
                       "ON CONFLICT (user_id, property_id) DO NOTHING", (user_id, pid))
            self._log_event(user_id, entity_id, pid, "FOLLOW", 1.0)
        return True

    def unfollow(self, user_id, entity_id):
        pid = parse_entity_id(entity_id)
        if pid is None:
            return False
        with self._lock:
            self._hydrate(user_id)
            st = self._state(user_id)
            st.followed.discard(pid)
            self._exec("DELETE FROM user_follows WHERE user_id=%s AND property_id=%s", (user_id, pid))
            self._log_event(user_id, entity_id, pid, "UNFOLLOW", 1.0)
        return True

    def react(self, user_id, entity_id, reaction_type):
        """Set/replace the user's reaction on an entity (production model: heart/fire/confetti)."""
        rt = (reaction_type or "").lower()
        if rt not in REACTION_WEIGHTS:
            return False
        pid = parse_entity_id(entity_id)
        if pid is None:
            return False
        with self._lock:
            self._hydrate(user_id)
            st = self._state(user_id)
            st.reactions[pid] = rt
            self._exec("INSERT INTO user_reactions (user_id, property_id, reaction) VALUES (%s,%s,%s) "
                       "ON CONFLICT (user_id, property_id) DO UPDATE SET reaction=EXCLUDED.reaction, created_at=now()",
                       (user_id, pid, rt))
            self._log_event(user_id, entity_id, pid, rt.upper(), REACTION_WEIGHTS[rt])
        return True

    def unreact(self, user_id, entity_id):
        """Clear the user's reaction on an entity (toggle off)."""
        pid = parse_entity_id(entity_id)
        if pid is None:
            return False
        with self._lock:
            self._hydrate(user_id)
            st = self._state(user_id)
            st.reactions.pop(pid, None)
            self._exec("DELETE FROM user_reactions WHERE user_id=%s AND property_id=%s", (user_id, pid))
        return True

    # back-compat for older scripts (proof/recall): like = heart reaction; dislike no longer exists
    def like(self, user_id, entity_id):
        return self.react(user_id, entity_id, "heart")

    def dislike(self, user_id, entity_id):
        return self.unreact(user_id, entity_id)

    def event(self, user_id, entity_id, event_type, weight=1.0, meta=None):
        """Log a raw engagement event (WATCH / SKIP / CLICK and friends) to user_events.

        These don't change current follow/like/dislike state; they feed the trend engine and the
        time-decayed profile. Returns False on an unknown type or malformed entity_id.
        """
        et = (event_type or "").upper()
        if et not in EVENT_TYPES:
            return False
        pid = parse_entity_id(entity_id)   # may be None for non-entity events; still logged
        with self._lock:
            self._log_event(user_id, entity_id, pid, et, weight, meta)
        return True

    # ── reads ─────────────────────────────────────────────────────────────────
    def _watched(self, user_id):
        """What the user has already WATCHED, for feed suppression. Returns
        (watched_moment_ids, watched_property_ids):
          - NEW watches carry meta.moment_id -> suppress only THAT moment (spec: property NOT penalised).
          - LEGACY watches (no meta.moment_id) -> fall back to property-level suppression (F6), so moving
            to moment-level doesn't silently lose suppression for events logged before clients send it.
        Read fresh from the append-only user_events log; empty sets if PG is unavailable."""
        if not self._pg:
            return set(), set()
        rows = self._exec(
            "SELECT DISTINCT property_id, meta->>'moment_id' FROM user_events "
            "WHERE user_id=%s AND event_type='WATCH' AND property_id IS NOT NULL",
            (user_id,), fetch=True)
        if not rows:
            return set(), set()
        moment_ids = {int(r[1]) for r in rows if r[1] is not None}
        property_ids = {int(r[0]) for r in rows if r[1] is None}   # legacy rows only (no moment_id)
        return moment_ids, property_ids

    def _live_snapshot(self, user_id):
        """Serving: build the snapshot from the Silver follows table. The follow-gated feed only needs
        `followed`; reactions/watched stay empty for now (additive) — taste degrades to follows-only."""
        try:
            rows = _QUERY_FN(
                f"SELECT property_id FROM {_SILVER_PG}.public_property_followers "
                f"WHERE user_id = {int(user_id)} AND deleted_at IS NULL AND property_id IS NOT NULL")
        except Exception as e:  # pragma: no cover - environment dependent
            print(f"[store] live follows read failed for user {user_id}: {str(e)[:100]}", flush=True)
            rows = []
        followed = {int(r["property_id"]) for r in rows if r.get("property_id") is not None}
        return {"followed": followed, "reactions": {}, "liked": set(), "disliked": set(),
                "watched_moments": set(), "watched_properties": set()}

    def snapshot(self, user_id):
        """Return a plain-dict copy of a user's state (safe to read outside the lock)."""
        # UC5 cold-start: a null user_id has no state — return an empty snapshot WITHOUT touching the DB
        # or polluting self._users with a None key. MUST be the first statement (before lock/_hydrate).
        if user_id is None:
            return {"followed": set(), "reactions": {}, "liked": set(), "disliked": set(),
                    "watched_moments": set(), "watched_properties": set()}
        if _LIVE and _QUERY_FN is not None:                # Silver: public_property_followers
            return self._live_snapshot(user_id)
        with self._lock:
            self._hydrate(user_id)
            st = self._users.get(user_id)
            watched_moments, watched_props = self._watched(user_id)   # moment-level (+ legacy property fallback)
            if st is None:
                return {"followed": set(), "reactions": {}, "liked": set(), "disliked": set(),
                        "watched_moments": watched_moments, "watched_properties": watched_props}
            reactions = dict(st.reactions)
            return {
                "followed": set(st.followed),
                "reactions": reactions,             # {pid: 'heart'/'fire'/'confetti'} — weighted taste
                "liked": set(reactions.keys()),     # back-compat: every reaction is positive
                "disliked": set(),                  # no dislike in the production model
                "watched_moments": watched_moments,         # spec: suppress these MOMENTS (property kept)
                "watched_properties": watched_props,        # legacy fallback: suppress whole property
            }

    # ── ops/demo helpers ────────────────────────────────────────────────────────
    def health(self):
        """Persistence status for /health — so the operator KNOWS if writes are hitting Postgres
        (the store silently degrades to in-memory on a PG failure; this surfaces that)."""
        return {"persistent": bool(self._pg), "degraded": bool(self._degraded)}

    def reset_user(self, user_id):
        """Demo reset: wipe a user's follows/reactions/events (Postgres + in-memory) so a clean,
        reproducible personalized walkthrough can start from cold."""
        with self._lock:
            self._users.pop(user_id, None)
            self._loaded.discard(user_id)
            for tbl in ("user_follows", "user_reactions", "user_events"):
                self._exec(f"DELETE FROM {tbl} WHERE user_id=%s", (user_id,))
        return True


# process-wide singleton
STORE = UserStore()
