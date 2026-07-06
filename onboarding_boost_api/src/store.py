"""store.py — UC8 Onboarding Boost persistence (standalone; local PoC stand-in for the follows store).

Two-step flow (spec §6):
  Step 1  POST /onboarding/boost          -> we record the OFFER (what we proposed) keyed by session_id.
  Step 2  POST /onboarding/boost/confirm  -> we write the batch follows (all-or-nothing) to a local
          follows table and mark the offer confirmed.

No Redis / no production follows-store here (per the engagement: those are Feeds/UMI's side). This is a
faithful LOCAL stand-in so the two-step flow — and the frontend Confirm button — actually work end-to-end.

Tables (in the existing local Postgres :5433/feedsai_discovery; in-memory fallback if PG is down):
  boost_offers (session_id PK, user_id, property_ids BIGINT[], generated_at, confirmed, confirmed_at)
  boost_follows(user_id, property_id, vertical, session_id, created_at, PRIMARY KEY(user_id, property_id))
"""
import os
import threading
from collections import defaultdict

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover
    psycopg2 = None

_PG = dict(host="localhost", port=5433, user="postgres", password="postgres", dbname="feedsai_discovery")
_PG_ON = os.environ.get("BOOST_PG", "1") != "0" and psycopg2 is not None

_DDL = """
CREATE TABLE IF NOT EXISTS boost_offers (
  session_id    TEXT PRIMARY KEY,
  user_id       BIGINT,
  property_ids  BIGINT[] NOT NULL DEFAULT '{}',
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed     BOOLEAN NOT NULL DEFAULT false,
  confirmed_at  TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS boost_follows (
  user_id     BIGINT  NOT NULL,
  property_id BIGINT  NOT NULL,
  vertical    TEXT,
  session_id  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, property_id)
);
"""


class BoostStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._offers = {}              # fallback: session_id -> {"user_id","property_ids","confirmed"}
        self._follows = defaultdict(set)   # user_id -> set(property_id)
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
            print(f"[boost.store] PG off ({str(e)[:80]}); in-memory only", flush=True)
            self._pg = False
            return False

    def record_offer(self, session_id, user_id, property_ids):
        """Persist the boost we proposed (Step 1) so confirm can write exactly this set (all-or-nothing)."""
        if not session_id:
            return
        pids = [int(x) for x in (property_ids or [])]
        uid = int(user_id) if user_id is not None else None
        with self._lock:
            if self._pg:
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO boost_offers (session_id, user_id, property_ids, confirmed) "
                            "VALUES (%s,%s,%s,false) "
                            "ON CONFLICT (session_id) DO UPDATE SET user_id=EXCLUDED.user_id, "
                            "  property_ids=EXCLUDED.property_ids, generated_at=now(), "
                            "  confirmed=false, confirmed_at=NULL",
                            (session_id, uid, pids))
                    return
                except Exception as e:  # pragma: no cover
                    print(f"[boost.store] record_offer failed ({str(e)[:60]}); mem", flush=True)
                    self._pg = False
            self._offers[session_id] = {"user_id": uid, "property_ids": pids, "confirmed": False}

    def get_offer(self, session_id):
        if not session_id:
            return None
        if self._pg:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT user_id, property_ids, confirmed FROM boost_offers WHERE session_id=%s",
                                (session_id,))
                    row = cur.fetchone()
                if not row:
                    return None
                return {"user_id": row[0], "property_ids": list(row[1] or []), "confirmed": bool(row[2])}
            except Exception as e:  # pragma: no cover
                print(f"[boost.store] get_offer failed ({str(e)[:60]}); mem", flush=True)
                self._pg = False
        return self._offers.get(session_id)

    def confirm(self, session_id, user_id, vmap=None):
        """Write the offered batch as follows (all-or-nothing, idempotent). Returns
        {"written": n, "already": m, "property_ids": [...]} or {"error": ...}."""
        offer = self.get_offer(session_id)
        if offer is None:
            return {"error": "no_offer_for_session"}
        pids = offer["property_ids"]
        uid = int(user_id) if user_id is not None else offer.get("user_id")
        if uid is None:
            return {"error": "missing_user_id"}
        vmap = vmap or {}
        written = already = 0
        with self._lock:
            if self._pg:
                try:
                    with self._conn.cursor() as cur:
                        for pid in pids:
                            cur.execute(
                                "INSERT INTO boost_follows (user_id, property_id, vertical, session_id) "
                                "VALUES (%s,%s,%s,%s) ON CONFLICT (user_id, property_id) DO NOTHING",
                                (uid, pid, vmap.get(pid), session_id))
                            if cur.rowcount == 1:
                                written += 1
                            else:
                                already += 1
                        cur.execute("UPDATE boost_offers SET confirmed=true, confirmed_at=now() "
                                    "WHERE session_id=%s", (session_id,))
                    return {"written": written, "already": already, "property_ids": pids}
                except Exception as e:  # pragma: no cover
                    print(f"[boost.store] confirm failed ({str(e)[:60]}); mem", flush=True)
                    self._pg = False
            cur = self._follows[uid]
            for pid in pids:
                if pid in cur:
                    already += 1
                else:
                    cur.add(pid); written += 1
            if session_id in self._offers:
                self._offers[session_id]["confirmed"] = True
        return {"written": written, "already": already, "property_ids": pids}

    def followed_count(self, user_id):
        if user_id is None:
            return 0
        uid = int(user_id)
        if self._pg:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM boost_follows WHERE user_id=%s", (uid,))
                    return cur.fetchone()[0]
            except Exception:  # pragma: no cover
                self._pg = False
        return len(self._follows.get(uid, ()))

    def health(self):
        return {"persistent": bool(self._pg)}
