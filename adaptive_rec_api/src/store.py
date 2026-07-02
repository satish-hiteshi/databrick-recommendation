"""store.py — adaptive-rec onboarding session memory (server-side persist).

Per red-team must-fix: followed/skipped come from the REQUEST each call (client is source of truth, supports
unfollow). The SERVER persists only what the client cannot track: the set of properties WE have already
suggested (so we never re-suggest) + accepted (analytics). Keyed by session_id (works pre-auth, no user_id).

Tiny table in the existing local Postgres (:5433/feedsai_discovery). Degrades to in-memory if PG is down.
"""
import os
import threading

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover
    psycopg2 = None

_PG = dict(host="localhost", port=5433, user="postgres", password="postgres", dbname="feedsai_discovery")
_PG_ON = os.environ.get("ADAPTIVE_PG", "1") != "0" and psycopg2 is not None

_DDL = """
CREATE TABLE IF NOT EXISTS onboarding_sessions (
  session_id  TEXT PRIMARY KEY,
  suggested   BIGINT[] NOT NULL DEFAULT '{}',
  accepted    BIGINT[] NOT NULL DEFAULT '{}',
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._mem = {}                 # fallback: session_id -> {"suggested":set,"accepted":set}
        self._conn = None
        self._pg = _PG_ON
        if self._pg:
            self._connect()

    def _connect(self):
        try:
            self._conn = psycopg2.connect(connect_timeout=5, **_PG)
            self._conn.autocommit = True
            with self._conn.cursor() as cur:
                cur.execute(_DDL)
            return True
        except Exception as e:  # pragma: no cover
            print(f"[adaptive.store] PG off ({str(e)[:80]}); in-memory only", flush=True)
            self._pg = False
            return False

    def get(self, session_id):
        """Return {'suggested': set(int), 'accepted': set(int)} for this session."""
        if not session_id:
            return {"suggested": set(), "accepted": set()}
        if self._pg:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT suggested, accepted FROM onboarding_sessions WHERE session_id=%s",
                                (session_id,))
                    row = cur.fetchone()
                if row:
                    return {"suggested": set(row[0] or []), "accepted": set(row[1] or [])}
                return {"suggested": set(), "accepted": set()}
            except Exception as e:  # pragma: no cover
                print(f"[adaptive.store] get failed ({str(e)[:60]}); mem", flush=True)
                self._pg = False
        return dict(self._mem.get(session_id, {"suggested": set(), "accepted": set()}))

    def record(self, session_id, suggested_ids=None, accepted_ids=None):
        """Append suggested/accepted property_ids to the session (union, idempotent)."""
        if not session_id:
            return
        sug = [int(x) for x in (suggested_ids or [])]
        acc = [int(x) for x in (accepted_ids or [])]
        with self._lock:
            if self._pg:
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO onboarding_sessions (session_id, suggested, accepted) "
                            "VALUES (%s,%s,%s) "
                            "ON CONFLICT (session_id) DO UPDATE SET "
                            "  suggested = (SELECT ARRAY(SELECT DISTINCT unnest(onboarding_sessions.suggested || EXCLUDED.suggested))), "
                            "  accepted  = (SELECT ARRAY(SELECT DISTINCT unnest(onboarding_sessions.accepted  || EXCLUDED.accepted))), "
                            "  updated_at = now()",
                            (session_id, sug, acc))
                    return
                except Exception as e:  # pragma: no cover
                    print(f"[adaptive.store] record failed ({str(e)[:60]}); mem", flush=True)
                    self._pg = False
            st = self._mem.setdefault(session_id, {"suggested": set(), "accepted": set()})
            st["suggested"].update(sug)
            st["accepted"].update(acc)

    def health(self):
        return {"persistent": bool(self._pg)}
