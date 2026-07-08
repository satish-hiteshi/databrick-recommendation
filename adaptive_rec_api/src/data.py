"""data.py — adaptive-rec (UC6) vector store.

Loads the 44k-qwen property embeddings from the parquet ONCE into memory (L2-normalized numpy matrix)
for in-app cosine vector search. Separate dataset from discovery (legacy 57k) — does NOT touch it.

Parquet columns: entity_id ("Vertical:property_id"), name, vertical, bm25_keywords[], embedding[1024], release_date_ts.
"""
import os
import threading

import numpy as np
import pyarrow.parquet as pq

# the 44k-qwen parquet (separate adaptive-rec dataset)
PARQUET = os.environ.get(
    "ADAPTIVE_PARQUET",
    r"C:\Users\Raj Singh\Downloads\embeddings_qwen_44k_prefixed 2 1.parquet",
)

# ── Databricks live source (env-gated; INERT for local Postgres runs) ────────────────────────────
# When ADAPTIVE_DATA_SOURCE=live: embeddings come from the parquet (no local Postgres), and the 3 signal
# tables (centrality/popularity/proximity) are read from Silver via an injected query_fn (databricks-sql-
# connector in serving) — SAME columns the Postgres path reads. Those Silver tables are built by
# databricks_deploy/precompute/*.py (part of this bundle). Missing table -> that signal stays neutral.
_LIVE = os.environ.get("ADAPTIVE_DATA_SOURCE", "").lower() == "live"
_SILVER_CAT = os.environ.get("ADAPTIVE_SILVER_CATALOG", "stg_feeds_silver")
_SILVER_SCHEMA = os.environ.get("ADAPTIVE_SILVER_SCHEMA", "ml")
_CENT_TABLE = os.environ.get("ADAPTIVE_CENT_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.adaptive_property_centrality")
_POP_TABLE = os.environ.get("ADAPTIVE_POP_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.adaptive_property_popularity")
_PROX_TABLE = os.environ.get("ADAPTIVE_PROX_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.adaptive_property_proximity")
_QUERY_FN = None


def set_query_fn(fn):
    """Inject the Silver query function (serving). Call before Data.get() when live."""
    global _QUERY_FN
    _QUERY_FN = fn


def _pid(entity_id):
    """'Movie:1100083' -> 1100083 (int), or None."""
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
        self.emb = None               # (N, 1024) float32 L2-normalized
        self.emb_dim = 0
        self.pids = []                # row -> property_id
        self.row_by_pid = {}          # property_id -> row index
        self.meta = {}                # property_id -> {property_id, entity_id, name, vertical, genres, release_ts}
        self.kw_text = None           # (N,) object: row-aligned lowercased keyword text (cross-vertical topical bridge)
        # graph-derived ranking signals (precomputed offline, row-aligned, loaded once) — UC6 / RANKING_MODEL
        self.centrality = None        # (N,) S4 graph PageRank centrality [0,1]
        self.popularity = None        # (N,) S5 graph popularity (user_rating) [0,1] — DOMINANT signal
        self.recency = None           # (N,) S2 release recency [0,1]
        self.franchises = None        # row -> frozenset(franchise names)  (proximity overlap)
        self.genres_sig = None        # row -> frozenset(genre names)      (proximity overlap)
        self._source = None           # "postgres" | "parquet"

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                d = cls()
                d._load()
                cls._instance = d
            return cls._instance

    def _load(self):
        # Postgres `property_vectors` is the store (client directive); parquet is the fallback.
        # LIVE (Databricks serving): no local Postgres — go straight to the staged parquet.
        if not _LIVE and self._load_pg():
            self._source = "postgres"
        else:
            self._load_parquet()
            self._source = "parquet"
        # Precompute row-aligned lowercased keyword text ONCE (scalable: cross-vertical topical bridge masks
        # are built per-topic from this, cached for the process — never re-joined per request).
        self.kw_text = np.array(
            [" ".join(str(x) for x in (self.meta[p].get("genres") or [])).lower() for p in self.pids],
            dtype=object,
        )
        self._load_signals()

    def _load_signals(self):
        """Load precomputed graph ranking signals (centrality / popularity / proximity) row-aligned.
        Best-effort: missing table/row -> zero/empty so the runtime degrades gracefully (no boost, no crash).
        Scalable: loaded ONCE at startup into numpy arrays; runtime does O(1) row lookups, no per-request DB hit."""
        n = len(self.pids)
        self.centrality = np.zeros(n, dtype=np.float32)
        self.popularity = np.zeros(n, dtype=np.float32)
        self.recency = np.zeros(n, dtype=np.float32)
        self.franchises = [frozenset() for _ in range(n)]
        self.genres_sig = [frozenset() for _ in range(n)]
        # S4 centrality base = weighted DEGREE (better hub signal than the graph's pagerank_pct, which over-ranks
        # dense generic clusters — obscure Hallmark movies hit ~1.0). Normalized within-vertical below.
        wdeg = np.zeros(n, dtype=np.float64)
        if _LIVE and _QUERY_FN is not None:                 # Silver (serving) — no Postgres; same signals/shape
            self._load_signals_live(wdeg)
            self._finalize_signals(wdeg)
            return
        try:
            import psycopg2
            conn = psycopg2.connect(host="localhost", port=5433, user="postgres",
                                    password="postgres", dbname="feedsai_discovery", connect_timeout=5)
            cur = conn.cursor()

            def _exists(t):
                cur.execute("SELECT to_regclass(%s)", (f"public.{t}",))
                return cur.fetchone()[0] is not None

            if _exists("property_centrality"):
                cur.execute("SELECT property_id, wdegree FROM property_centrality")
                for pid, v in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is not None and v is not None:
                        wdeg[r] = v
            # S5 popularity: REAL per-source values, already within-vertical normalized (0..1), from v2.
            # Fall back to the older proxy table only for pids v2 is missing (keeps game coverage until the
            # v2 game reload switches hype_count -> game_combined_rating).
            pop_table = "property_popularity_v2" if _exists("property_popularity_v2") else "property_popularity"
            if _exists(pop_table):
                cur.execute(f"SELECT property_id, popularity FROM {pop_table}")
                for pid, v in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is not None and v is not None:
                        self.popularity[r] = v
            if pop_table != "property_popularity" and _exists("property_popularity"):
                cur.execute("SELECT property_id, popularity FROM property_popularity")
                for pid, v in cur.fetchall():
                    r = self.row_by_pid.get(pid)
                    if r is not None and v is not None and self.popularity[r] == 0.0:
                        self.popularity[r] = v
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
            conn.close()
        except Exception as e:  # pragma: no cover
            print(f"[adaptive.data] signal load skipped ({str(e)[:80]}) — runtime runs taste-only", flush=True)
        self._finalize_signals(wdeg)

    def _load_signals_live(self, wdeg):
        """Serving: load the 3 precompute signal tables from Silver via the injected query_fn — SAME
        columns the Postgres path reads (wdegree / popularity / franchises+genres). Best-effort per table:
        a missing or failing read leaves that signal neutral (zeros / empty), exactly like Postgres degrades."""
        try:
            for r in _QUERY_FN(f"SELECT property_id, wdegree FROM {_CENT_TABLE}"):
                row = self.row_by_pid.get(r.get("property_id"))
                v = r.get("wdegree")
                if row is not None and v is not None:
                    wdeg[row] = float(v)
        except Exception as e:
            print(f"[adaptive.data] centrality (live) skipped ({str(e)[:80]})", flush=True)
        try:
            for r in _QUERY_FN(f"SELECT property_id, popularity FROM {_POP_TABLE}"):
                row = self.row_by_pid.get(r.get("property_id"))
                v = r.get("popularity")
                if row is not None and v is not None:
                    self.popularity[row] = float(v)
        except Exception as e:
            print(f"[adaptive.data] popularity (live) skipped ({str(e)[:80]})", flush=True)
        try:
            for r in _QUERY_FN(f"SELECT property_id, franchises, genres FROM {_PROX_TABLE}"):
                row = self.row_by_pid.get(r.get("property_id"))
                if row is None:
                    continue
                fr, ge = r.get("franchises"), r.get("genres")
                if fr:
                    self.franchises[row] = frozenset(str(x).lower() for x in fr)
                if ge:
                    self.genres_sig[row] = frozenset(str(x).lower() for x in ge)
        except Exception as e:
            print(f"[adaptive.data] proximity (live) skipped ({str(e)[:80]})", flush=True)

    def _finalize_signals(self, wdeg):
        """Shared post-processing (Postgres + Silver paths): S2 recency rank-percentile + S4 within-vertical
        centrality rank-percentile of weighted-degree (de-biases denser verticals / de-saturates the top)."""
        # S2 recency: rank-percentile of release_ts (newer -> higher); 0 where no timestamp
        ts = np.array([float(self.meta[p].get("release_ts") or 0) for p in self.pids], dtype=np.float64)
        valid = np.where(ts > 0)[0]
        if valid.size > 1:
            order = ts[valid].argsort()
            ranks = np.empty(order.size, dtype=np.float64)
            ranks[order] = np.arange(order.size)
            self.recency[valid] = (ranks / (order.size - 1)).astype(np.float32)
        # S4 centrality: rank-percentile of weighted-degree WITHIN each vertical.
        groups = {}
        for r, p in enumerate(self.pids):
            groups.setdefault(self.meta[p].get("vertical"), []).append(r)
        for rows in groups.values():
            idx = np.array(rows)
            w = wdeg[idx]
            pos = idx[w > 0]
            if pos.size > 1:
                wp = wdeg[pos]
                order = wp.argsort()
                ranks = np.empty(order.size, dtype=np.float64)
                ranks[order] = np.arange(order.size)
                self.centrality[pos] = (ranks / (order.size - 1)).astype(np.float32)
        # Observability guard (ported from the dev reference): never let a signals-off state degrade to a
        # TASTE-ONLY pass silently — this is exactly the signal-key regression the UC6 report hit (~0% overlap
        # -> popularity & centrality read 0.0). Behaviour-neutral (logging only).
        nz_pop = int((self.popularity > 0).sum())
        nz_cen = int((self.centrality > 0).sum())
        if nz_pop == 0 and nz_cen == 0:
            print("[adaptive.data] WARNING: 0 popularity AND 0 centrality — ranking is TASTE-ONLY "
                  "(popularity-dominant blend DISABLED). Check the adaptive_property_* Silver tables "
                  "(precompute_adaptive_signals) / re-key to media_source_guid.", flush=True)
        else:
            print(f"[adaptive.data] graph signals active: popularity={nz_pop}, centrality={nz_cen} properties", flush=True)

    def _load_pg(self):
        try:
            import psycopg2
            conn = psycopg2.connect(host="localhost", port=5433, user="postgres",
                                    password="postgres", dbname="feedsai_discovery", connect_timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.property_vectors')")
            if cur.fetchone()[0] is None:
                conn.close(); return False
            cur.execute("SELECT property_id, entity_id, name, vertical, release_ts, bm25_keywords, embedding "
                        "FROM property_vectors")
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return False
            mat = []
            for pid, ent, name, vert, rts, kws, emb in rows:
                if pid in self.row_by_pid:
                    continue
                self.row_by_pid[pid] = len(self.pids)
                self.pids.append(pid)
                mat.append(emb)
                self.meta[pid] = {"property_id": pid, "entity_id": ent, "name": name or f"Property {pid}",
                                  "vertical": (str(vert).lower() if vert else None),
                                  "genres": list(kws) if kws else [],
                                  "release_ts": int(rts) if rts is not None else None}
            m = np.asarray(mat, dtype=np.float32)
            self.emb = m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)
            self.emb_dim = self.emb.shape[1]
            return True
        except Exception as e:  # pragma: no cover
            print(f"[adaptive.data] PG embedding load failed ({str(e)[:90]}); falling back to parquet", flush=True)
            return False

    def _load_parquet(self):
        t = pq.read_table(PARQUET)
        cols = {n: t.column(n).to_pylist() for n in t.schema.names}
        embs = cols["embedding"]
        n = len(embs)
        ents = cols.get("entity_id", [None] * n)
        names = cols.get("name", [None] * n)
        verts = cols.get("vertical", [None] * n)
        kws = cols.get("bm25_keywords", [None] * n)
        rdts = cols.get("release_date_ts", [None] * n)
        # Keep only rows with a parseable property_id; build the matrix + maps in ONE aligned pass.
        keep_rows = []
        for i in range(n):
            pid = _pid(ents[i])
            if pid is None or pid in self.row_by_pid:     # skip unparseable + duplicate pids
                continue
            self.row_by_pid[pid] = len(self.pids)
            self.pids.append(pid)
            keep_rows.append(i)
            self.meta[pid] = {
                "property_id": pid,
                "entity_id": ents[i],
                "name": names[i] or f"Property {pid}",
                "vertical": (str(verts[i]).lower() if verts[i] else None),
                "genres": list(kws[i]) if kws[i] is not None else [],
                "release_ts": int(rdts[i]) if rdts[i] not in (None, "") else None,
            }
        mat = np.asarray([embs[i] for i in keep_rows], dtype=np.float32)   # (kept, 1024), pids-aligned
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        self.emb = mat / np.clip(norms, 1e-9, None)                        # L2-normalize -> cosine = dot
        self.emb_dim = self.emb.shape[1]

    def vec(self, pid):
        r = self.row_by_pid.get(pid)
        return None if r is None else self.emb[r]

    def stats(self):
        return {"properties": len(self.pids), "emb_dim": self.emb_dim, "source": self._source}
