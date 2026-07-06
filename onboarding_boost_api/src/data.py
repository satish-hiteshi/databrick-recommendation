"""data.py — UC8 Onboarding Boost in-memory store (standalone; does NOT import UC6/discovery).

Loads ONCE at startup, row-aligned, into numpy arrays so the runtime does O(1) lookups per candidate
(no per-request DB hit — scalable). Shares the SAME external-id universe as UC6 (`property_vectors`
+ popularity/centrality/proximity), and ADDS the UC8 moment signal (`property_moments`).

ALL ids here are EXTERNAL ids (entity_id "Movie:1100083" -> 1100083). `property_moments` is keyed by
the same external id (built via the media_source_guid bridge — see precompute_moments.py), so it joins
1:1 to `property_vectors`. Public/sequential moment ids never reach the runtime.

TWO DATA SOURCES (BOOST_DATA_SOURCE):
  local (default) — psycopg2 to the local Postgres PoC (dev): property_vectors + property_* + properties.
  live            — Databricks serving: embeddings from the staged parquet (BOOST_PARQUET), and signals +
                    id-bridge from Silver via an INJECTED query_fn (set_query_fn) — no local Postgres.
                    popularity/centrality/proximity reuse UC6's Silver `adaptive_property_*`; the moment
                    signal comes from `boost_property_moments` (built by precompute_moments.py).

Row-aligned arrays (index = embedding row):
    emb          (N,1024) f32 L2-normalized   -> S1 relevance (cosine to seeds)
    popularity   (N,) [0,1]                    -> S5 (DOMINANT, 35%)
    centrality   (N,) [0,1] within-vertical    -> S4 (20%)
    moment_count (N,) int                       -> S7 hard gate (> 0)
    richness     (N,) [0,1] within-vertical     -> S7 (16%) + soft gate (>= floor)
    trending     (N,) [0,1] within-vertical     -> S3 (7%)
    recency      (N,) [0,1] release-date pctile -> S2 (4%)
    franchises / genres_sig                     -> why_string / display only (NOT in the blend)
"""
import os
import threading

import numpy as np
import pyarrow.parquet as pq

PG_DSN = dict(host="localhost", port=5433, user="postgres", password="postgres",
              dbname="feedsai_discovery")

# parquet source (serving reads this; model._bootstrap sets BOOST_PARQUET to the staged Volume parquet).
PARQUET = os.environ.get("BOOST_PARQUET", "")

# ── Databricks-serving seam ────────────────────────────────────────────────────
# When BOOST_DATA_SOURCE=live, signals + id-bridge read from Silver via an injected query_fn — a
# databricks-sql callable f(sql:str)->list[dict]. model.py injects it at load_context, BEFORE Data.get().
_QUERY_FN = None


def set_query_fn(fn):
    """Inject the Silver query function (called once, before Data.get(), by model.load_context)."""
    global _QUERY_FN
    _QUERY_FN = fn


def _live():
    return os.environ.get("BOOST_DATA_SOURCE", "").lower() == "live" and _QUERY_FN is not None


def _pid(entity_id):
    """'Movie:1100083' -> 1100083 (int) or None."""
    if entity_id is None:
        return None
    s = str(entity_id)
    if ":" in s:
        s = s.split(":", 1)[1]
    try:
        return int(s.strip())
    except (TypeError, ValueError):
        return None


class Data:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.emb = None
        self.emb_dim = 0
        self.pids = []
        self.row_by_pid = {}
        self.meta = {}                # pid -> {property_id, entity_id, name, vertical, genres, release_ts}
        self.popularity = None        # S5
        self.centrality = None        # S4
        self.recency = None           # S2
        self.moment_count = None      # S7 gate
        self.richness = None          # S7
        self.trending = None          # S3
        self.last_event = None        # (N,) object: last moment datetime (display/debug)
        self.franchises = None        # row -> frozenset (why_string / proximity)
        self.genres_sig = None        # row -> frozenset
        self.verticals = []           # sorted distinct verticals present in the served set
        self.public_to_ext = {}       # public sequential id -> external id (property_vectors space)
        self.ext_to_public = {}       # external id -> public id (only for served props)
        self.backend = None           # vector backend in use (memory | qdrant)
        self._source = None

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                d = cls()
                d._load()
                cls._instance = d
            return cls._instance

    def _load(self):
        # embeddings only need to be in RAM for the `memory` backend; for `qdrant` they live in Qdrant.
        self.backend = os.environ.get("BOOST_VECTOR_BACKEND", "qdrant").lower()
        load_emb = self.backend == "memory"
        # live (serving): embeddings come from the staged parquet — no local Postgres.
        if _live() or not self._load_pg(load_emb=load_emb):
            self._load_parquet()                      # parquet fallback always carries embeddings
            self._source = "parquet"
        else:
            self._source = "postgres"
        self._load_signals()
        self._load_id_bridge()
        self.verticals = sorted({m.get("vertical") for m in self.meta.values() if m.get("vertical")})

    # ── embeddings + meta ──────────────────────────────────────────────────────
    def _load_pg(self, load_emb=True):
        try:
            import psycopg2
            conn = psycopg2.connect(connect_timeout=5, **PG_DSN)
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.property_vectors')")
            if cur.fetchone()[0] is None:
                conn.close(); return False
            cols = "property_id, entity_id, name, vertical, release_ts, bm25_keywords"
            cur.execute(f"SELECT {cols}{', embedding' if load_emb else ''} FROM property_vectors")
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return False
            mat = []
            for r in rows:
                if load_emb:
                    pid, ent, name, vert, rts, kws, emb = r
                else:
                    pid, ent, name, vert, rts, kws = r
                if pid in self.row_by_pid:
                    continue
                self.row_by_pid[pid] = len(self.pids)
                self.pids.append(pid)
                if load_emb:
                    mat.append(emb)
                self.meta[pid] = {"property_id": pid, "entity_id": ent, "name": name or f"Property {pid}",
                                  "vertical": (str(vert).lower() if vert else None),
                                  "genres": list(kws) if kws else [],
                                  "release_ts": int(rts) if rts is not None else None}
            if load_emb:
                m = np.asarray(mat, dtype=np.float32)
                self.emb = m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)
                self.emb_dim = self.emb.shape[1]
            else:
                self.emb = None
                self.emb_dim = 1024
            return True
        except Exception as e:  # pragma: no cover
            print(f"[boost.data] PG load failed ({str(e)[:90]}); parquet fallback", flush=True)
            return False

    def _load_parquet(self):
        if not PARQUET or not os.path.exists(PARQUET):
            raise RuntimeError(f"BOOST_PARQUET not set / not found ({PARQUET!r}) — serving needs the staged "
                               f"Qwen parquet (model._bootstrap sets it).")
        t = pq.read_table(PARQUET)
        cols = {n: t.column(n).to_pylist() for n in t.schema.names}
        embs = cols["embedding"]
        n = len(embs)
        ents = cols.get("entity_id", [None] * n)
        names = cols.get("name", [None] * n)
        verts = cols.get("vertical", [None] * n)
        kws = cols.get("bm25_keywords", [None] * n)
        rdts = cols.get("release_date_ts", [None] * n)
        keep = []
        for i in range(n):
            pid = _pid(ents[i])
            if pid is None or pid in self.row_by_pid:
                continue
            self.row_by_pid[pid] = len(self.pids)
            self.pids.append(pid)
            keep.append(i)
            self.meta[pid] = {"property_id": pid, "entity_id": ents[i], "name": names[i] or f"Property {pid}",
                              "vertical": (str(verts[i]).lower() if verts[i] else None),
                              "genres": list(kws[i]) if kws[i] is not None else [],
                              "release_ts": int(rdts[i]) if rdts[i] not in (None, "") else None}
        mat = np.asarray([embs[i] for i in keep], dtype=np.float32)
        self.emb = mat / np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9, None)
        self.emb_dim = self.emb.shape[1]

    # ── precomputed signals (best-effort; missing -> zeros, runtime degrades gracefully) ──
    def _load_signals(self):
        n = len(self.pids)
        self.popularity = np.zeros(n, dtype=np.float32)
        self.centrality = np.zeros(n, dtype=np.float32)
        self.recency = np.zeros(n, dtype=np.float32)
        self.moment_count = np.zeros(n, dtype=np.int32)
        self.richness = np.zeros(n, dtype=np.float32)
        self.trending = np.zeros(n, dtype=np.float32)
        self.last_event = np.array([None] * n, dtype=object)
        self.franchises = [frozenset() for _ in range(n)]
        self.genres_sig = [frozenset() for _ in range(n)]
        wdeg = np.zeros(n, dtype=np.float64)

        if _live():
            self._fill_signals_live(wdeg)
        else:
            self._fill_signals_pg(wdeg)

        # S2 recency: rank-percentile of release_ts (newer -> higher)
        ts = np.array([float(self.meta[p].get("release_ts") or 0) for p in self.pids], dtype=np.float64)
        valid = np.where(ts > 0)[0]
        if valid.size > 1:
            order = ts[valid].argsort()
            ranks = np.empty(order.size, dtype=np.float64)
            ranks[order] = np.arange(order.size)
            self.recency[valid] = (ranks / (order.size - 1)).astype(np.float32)

        # S4 centrality: within-vertical rank-percentile of weighted degree (de-biases denser verticals).
        groups = {}
        for r, p in enumerate(self.pids):
            groups.setdefault(self.meta[p].get("vertical"), []).append(r)
        for rows in groups.values():
            idx = np.array(rows)
            pos = idx[wdeg[idx] > 0]
            if pos.size > 1:
                order = wdeg[pos].argsort()
                ranks = np.empty(order.size, dtype=np.float64)
                ranks[order] = np.arange(order.size)
                self.centrality[pos] = (ranks / (order.size - 1)).astype(np.float32)

    def _fill_signals_pg(self, wdeg):
        """Local dev: read the four signal tables from the local Postgres PoC."""
        try:
            import psycopg2
            conn = psycopg2.connect(connect_timeout=5, **PG_DSN)
            cur = conn.cursor()

            def _exists(t):
                cur.execute("SELECT to_regclass(%s)", (f"public.{t}",))
                return cur.fetchone()[0] is not None

            pop_table = ("property_popularity_v2" if _exists("property_popularity_v2")
                         else ("property_popularity" if _exists("property_popularity") else None))
            self._pop_source = pop_table
            if pop_table:
                cur.execute(f"SELECT property_id, popularity FROM {pop_table}")
                for pid, v in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is not None and v is not None:
                        self.popularity[r] = v
            if _exists("property_centrality"):
                cur.execute("SELECT property_id, wdegree FROM property_centrality")
                for pid, v in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is not None and v is not None:
                        wdeg[r] = v
            if _exists("property_proximity"):
                cur.execute("SELECT property_id, franchises, genres FROM property_proximity")
                for pid, fr, ge in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is None:
                        continue
                    if fr:
                        self.franchises[r] = frozenset(str(x).lower() for x in fr)
                    if ge:
                        self.genres_sig[r] = frozenset(str(x).lower() for x in ge)
            if _exists("property_moments"):
                cur.execute("SELECT property_id, moment_count, richness, trending, last_event_at "
                            "FROM property_moments")
                for pid, mc, rich, trend, le in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is None:
                        continue
                    self.moment_count[r] = int(mc or 0)
                    self.richness[r] = float(rich or 0.0)
                    self.trending[r] = float(trend or 0.0)
                    self.last_event[r] = le
            conn.close()
        except Exception as e:  # pragma: no cover
            print(f"[boost.data] signal load skipped ({str(e)[:80]}) — boost runs on relevance only", flush=True)

    def _fill_signals_live(self, wdeg):
        """Serving: read signals from Silver via the injected query_fn. popularity/centrality/proximity
        reuse UC6's `adaptive_property_*`; the moment signal is `boost_property_moments`. All keyed by the
        external id (media_source_guid) = self.row_by_pid space."""
        cat = os.environ.get("BOOST_SILVER_CATALOG", "stg_feeds_silver")
        sch = os.environ.get("BOOST_SILVER_SCHEMA", "ml")
        NS = f"{cat}.{sch}"

        def q(sql):
            try:
                return _QUERY_FN(sql) or []
            except Exception as e:  # pragma: no cover
                print(f"[boost.data] live query failed ({str(e)[:90]})", flush=True)
                return []

        def _row(v):
            try:
                return self.row_by_pid.get(int(v))
            except (TypeError, ValueError):
                return None

        # popularity: E8's own boost_property_popularity (precompute_popularity_v2); fall back to UC6's table.
        pop_rows = q(f"SELECT property_id, popularity FROM {NS}.boost_property_popularity")
        self._pop_source = f"{NS}.boost_property_popularity"
        if not pop_rows:
            pop_rows = q(f"SELECT property_id, popularity FROM {NS}.adaptive_property_popularity")
            self._pop_source = f"{NS}.adaptive_property_popularity"
        for rec in pop_rows:
            r = _row(rec.get("property_id"))
            if r is not None and rec.get("popularity") is not None:
                self.popularity[r] = float(rec["popularity"])
        for rec in q(f"SELECT property_id, wdegree FROM {NS}.adaptive_property_centrality"):
            r = _row(rec.get("property_id"))
            if r is not None and rec.get("wdegree") is not None:
                wdeg[r] = float(rec["wdegree"])
        for rec in q(f"SELECT property_id, franchises, genres FROM {NS}.adaptive_property_proximity"):
            r = _row(rec.get("property_id"))
            if r is None:
                continue
            fr, ge = rec.get("franchises"), rec.get("genres")
            if fr:
                self.franchises[r] = frozenset(str(x).lower() for x in fr)
            if ge:
                self.genres_sig[r] = frozenset(str(x).lower() for x in ge)
        for rec in q(f"SELECT property_id, moment_count, richness, trending, last_event_at "
                     f"FROM {NS}.boost_property_moments"):
            r = _row(rec.get("property_id"))
            if r is None:
                continue
            self.moment_count[r] = int(rec.get("moment_count") or 0)
            self.richness[r] = float(rec.get("richness") or 0.0)
            self.trending[r] = float(rec.get("trending") or 0.0)
            self.last_event[r] = rec.get("last_event_at")

    # ── id-space bridge (accept seeds in EITHER public or external space) ──────────
    def _load_id_bridge(self):
        """Build public<->external id maps. Local: the `properties` PoC table. Live: Silver
        `public_properties` (id <-> media_source_guid) via the injected query_fn. Best-effort."""
        if _live():
            cat = os.environ.get("BOOST_SILVER_CATALOG", "stg_feeds_silver")
            try:
                rows = _QUERY_FN(f"SELECT id, media_source_guid FROM {cat}.feedspostgres.public_properties "
                                 f"WHERE media_source_guid IS NOT NULL") or []
            except Exception as e:  # pragma: no cover
                print(f"[boost.data] live id-bridge skipped ({str(e)[:80]}) — external ids only", flush=True)
                return
            for rec in rows:
                try:
                    pub = int(rec["id"]); ext = int(rec["media_source_guid"])
                except (TypeError, ValueError, KeyError):
                    continue
                self.public_to_ext[pub] = ext
                if ext in self.row_by_pid:
                    self.ext_to_public[ext] = pub
            return
        try:
            import psycopg2
            conn = psycopg2.connect(connect_timeout=5, **PG_DSN)
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.properties')")
            if cur.fetchone()[0] is None:
                conn.close(); return
            cur.execute("SELECT property_id, media_source_guid FROM properties")
            for pub, guid in cur.fetchall():
                try:
                    pub = int(pub); ext = int(guid)
                except (TypeError, ValueError):
                    continue
                self.public_to_ext[pub] = ext
                if ext in self.row_by_pid:              # only expose served externals for the reverse map
                    self.ext_to_public[ext] = pub
            conn.close()
        except Exception as e:  # pragma: no cover
            print(f"[boost.data] id-bridge load skipped ({str(e)[:80]}) — external ids only", flush=True)

    def resolve(self, pid, mode="auto"):
        """Resolve an incoming seed id to a served EXTERNAL id, or None. mode:
        'external' = treat as external; 'public' = translate public->external; 'auto' = external if it
        is already a served external id, otherwise try public->external."""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return None
        if mode == "external":
            return pid if pid in self.row_by_pid else None
        if mode == "public":
            ext = self.public_to_ext.get(pid)
            return ext if ext is not None and ext in self.row_by_pid else None
        # auto: prefer an already-served external id, else fall back to public->external
        if pid in self.row_by_pid:
            return pid
        ext = self.public_to_ext.get(pid)
        return ext if ext is not None and ext in self.row_by_pid else None

    def public_id(self, ext_pid):
        """External id -> public id (or None if unmapped)."""
        return self.ext_to_public.get(ext_pid)

    # ── accessors ──────────────────────────────────────────────────────────────
    def vec(self, pid):
        r = self.row_by_pid.get(pid)
        return None if r is None else self.emb[r]

    def stats(self):
        n = len(self.pids)
        active = int((self.moment_count > 0).sum()) if self.moment_count is not None else 0
        per_vert = {}
        for p in self.pids:
            v = self.meta[p].get("vertical")
            per_vert[v] = per_vert.get(v, 0) + 1
        return {"properties": n, "emb_dim": self.emb_dim, "source": self._source,
                "backend": self.backend, "emb_in_ram": self.emb is not None,
                "popularity_source": getattr(self, "_pop_source", None),
                "verticals": per_vert, "moment_active": active}
