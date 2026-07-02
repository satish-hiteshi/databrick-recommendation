"""MLflow pyfunc for Endpoint 4 (search) — UC4 in-app Search + UC7 onboarding thematic search.

Wraps the E4 engine (search_api/src) as-is. E4 is SELF-CONTAINED at serve time — no E1/E2 HTTP substrate:
  • bridge   ← the Aura :Entity graph (property_id<->entity_id) via SearchBridge/GraphMoments (neo4j bolt)
  • store    ← Silver `search_property_popularity` (+ optional `search_entity_centrality`) via the injected
               databricks-sql query_fn (SEARCH_DATA_SOURCE=live) — built by precompute_search_tables.py
  • thematic ← the Qwen doc-vector parquet (pyarrow matmul), staged from a Volume
  • embed    ← the Qwen query-embed serving endpoint (httpx; QWEN_EMBED_ENDPOINT + DATABRICKS_TOKEN)
  • follows  ← Silver `public_property_followers` via LiveFollowSource (same injected query_fn)
It reuses E3 (`home_feed` bridge/vectors/follows) + E2 (`timeutil`), vendored under _e3/ and _e2/.
predict() maps {query,user_id,mode,verticals,…} records -> the UC4/UC7 predictions[] envelope.

Registered as a NEW UC model (e.g. stg_feeds_silver.ml.search-staging), served at its OWN endpoint.
"""

import os
import sys
import time

import mlflow
from mlflow.models import set_model

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # serving dir (otel_setup beside this file)
try:
    import otel_setup       # noqa: E402  best-effort OTLP telemetry (no-op if unset / not bundled)
except Exception:
    otel_setup = None

_ENDPOINT = os.getenv("OTEL_SERVICE_NAME", "search")

# Defaults set BEFORE importing search_api.src.* (config/store/follows read these at import time).
_ENV = {
    "SEARCH_DATA_SOURCE": "live",                # store + follows read Silver (not Postgres/CSV)
    "SEARCH_SILVER_CATALOG": "stg_feeds_silver", # catalog for the precompute tables + public_property_followers
}


def _bootstrap():
    """Find the bundled packages + the staged Qwen parquet in the artifact and wire them up:
      • put the `search_api` package parent on sys.path (so `import search_api.src.*` resolves),
      • put `_e3/` and `_e2/` on sys.path (so `import home_feed.src.*` / `discovery_api.src.*` resolve),
      • point SEARCH_VECTOR_PARQUET at the staged parquet (thematic index reads config.VECTOR_PARQUET).
    MLflow normally adds the code dir to sys.path itself; this is a belt-and-suspenders walk."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
    pkg_parent = None
    e3_root = None
    e2_root = None
    parquet = None
    for dp, dns, fns in os.walk(root):
        if dp[len(root):].count(os.sep) > 8:
            dns[:] = []
            continue
        base = os.path.basename(dp)
        if pkg_parent is None and base == "search_api" \
           and os.path.isfile(os.path.join(dp, "src", "engine.py")):
            pkg_parent = os.path.dirname(dp)
        if e3_root is None and base == "_e3" and os.path.isdir(os.path.join(dp, "home_feed")):
            e3_root = dp
        if e2_root is None and base == "_e2" and os.path.isdir(os.path.join(dp, "discovery_api")):
            e2_root = dp
        if parquet is None:
            for fn in fns:
                if fn.endswith(".parquet"):
                    parquet = os.path.join(dp, fn)
                    break
    if pkg_parent is None:
        raise ImportError(f"search bundle: search_api package not found under {root}")
    for p in (pkg_parent, e3_root, e2_root):
        if p and p not in sys.path:
            sys.path.insert(0, p)
    if parquet:
        os.environ.setdefault("SEARCH_VECTOR_PARQUET", parquet)


class _SqlConn:
    """databricks-sql-connector access for the Silver store + follows reads. A BOUNDED POOL (default
    size 1, via SEARCH_SQL_POOL_SIZE): the store's two bulk loads run once at warm-up, then per-request
    follow reads are one cheap query each. Reconnects a dead connection on failure."""

    def __init__(self, pool_size=None):
        import queue
        if pool_size is None:
            pool_size = max(1, int(os.getenv("SEARCH_SQL_POOL_SIZE", "1")))
        self._pool = queue.Queue()
        for _ in range(pool_size):
            self._pool.put(None)

    def _connect(self):
        from databricks import sql as dbsql
        host = os.environ["DATABRICKS_HOST"].replace("https://", "").replace("http://", "").rstrip("/")
        return dbsql.connect(server_hostname=host,
                             http_path=os.environ["DATABRICKS_HTTP_PATH"],
                             access_token=os.environ["DATABRICKS_TOKEN"])

    def query(self, sql):
        conn = self._pool.get()
        try:
            last = None
            for _ in range(2):
                try:
                    if conn is None:
                        conn = self._connect()
                    cur = conn.cursor()
                    cur.execute(sql)
                    cols = [c[0] for c in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    cur.close()
                    return rows
                except Exception as e:
                    last = e
                    conn = None
            raise last
        finally:
            self._pool.put(conn)


def _parse_records(model_input):
    """MLflow model_input -> list of plain request dicts. Accepts a pandas DataFrame (serving rows), a
    {dataframe_records:[...]} envelope, a list of dicts, or a single dict."""
    try:
        import pandas as pd
        if isinstance(model_input, pd.DataFrame):
            out = []
            for row in model_input.to_dict("records"):
                out.append({k: v for k, v in row.items()
                            if not (isinstance(v, float) and pd.isna(v)) and v is not None})
            return out
    except Exception:
        pass
    if isinstance(model_input, dict):
        if "dataframe_records" in model_input:
            return list(model_input.get("dataframe_records") or [])
        return [model_input]
    if isinstance(model_input, list):
        return list(model_input)
    return [model_input]


class SearchModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        for k, v in _ENV.items():
            os.environ.setdefault(k, v)
        _bootstrap()
        global otel_setup
        if otel_setup is None:
            try:
                import otel_setup as _o
                otel_setup = _o
            except Exception:
                otel_setup = None
        if otel_setup is not None:
            try:
                otel_setup.init(_ENDPOINT)
            except Exception:
                pass

        # Inject the Silver query_fn into store + follows BEFORE building the engine (both read the
        # module-level _QUERY_FN when SEARCH_DATA_SOURCE=live; the engine constructs them eagerly).
        self._sql = _SqlConn()
        from search_api.src import store, follows
        store.set_query_fn(self._sql.query)
        follows.set_query_fn(self._sql.query)

        from search_api.src.engine import SearchEngine
        from search_api.src.request import SearchRequest
        self._Request = SearchRequest
        self._engine = SearchEngine()
        h = self._engine.health()
        print(f"[search] engine ready — bridge={h.get('bridge_properties')} names={h.get('name_index_size')} "
              f"thematic={h.get('thematic_vectors')} pop={h.get('popularity_rows')} "
              f"cent={h.get('centrality_rows')} qwen={h.get('qwen_embed_available')} "
              f"neo4j={os.getenv('NEO4J_URI')} parquet={os.getenv('SEARCH_VECTOR_PARQUET')}", flush=True)

    def predict(self, context, model_input, params=None):
        records = _parse_records(model_input)
        out = []
        for r in records:
            t0 = time.perf_counter()
            try:
                req = self._Request.from_dict(r)
                env = self._engine.handle(req)
                pred = env["predictions"][0] if isinstance(env, dict) and env.get("predictions") else env
                out.append(pred)
                if otel_setup is not None:
                    try:
                        dbg = (pred.get("debug") or {}) if isinstance(pred, dict) else {}
                        rc = pred.get("result_count") if isinstance(pred, dict) else None
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "ok")
                        otel_setup.record_routing(_ENDPOINT, path=dbg.get("mode_taken"), result_count=rc)
                    except Exception:
                        pass
            except Exception as e:
                q = r.get("query") if isinstance(r, dict) else "?"
                print(f"[search] record failed (query={q!r}): {type(e).__name__}: {e}", flush=True)
                if otel_setup is not None:
                    try:
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "error")
                        otel_setup.record_error(_ENDPOINT, type(e).__name__)
                    except Exception:
                        pass
                out.append({"error": True, "detail": f"{type(e).__name__}: {e}"})
        return out


set_model(SearchModel())
