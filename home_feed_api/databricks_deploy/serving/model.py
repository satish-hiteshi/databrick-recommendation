"""MLflow pyfunc for Endpoint 3 (home-feed) — the follow-gated home feed, on Databricks Model Serving.

Wraps the E3 engine (home_feed/src) as-is. E3's main-feed path is SELF-CONTAINED — it never calls the
E1/E2 HTTP substrate:
  • follows  ← Silver `public_property_followers` via LiveFollowSource (injected databricks-sql query_fn)
  • moments  ← the Aura graph via GraphMoments (neo4j bolt driver, :Moment / HAS_MOMENT traversal)
  • vectors  ← the Qwen parquet via VectorStore (pyarrow, staged from a Volume)
It reuses E2 only for `config` + `timeutil` (vendored under _e2/; the heavier reuse is for the not-yet-
implemented carousel assembler). predict() maps {user_id,…} records -> the UC3 home-feed envelope via
HomeFeedEngine.build (carousels are [] until home_assembler lands).

Registered as a NEW UC model (e.g. stg_feeds_silver.ml.home-feed-staging), served at its OWN endpoint.
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

_ENDPOINT = os.getenv("OTEL_SERVICE_NAME", "home-feed")

_ENV = {
    "HOME_SILVER_CATALOG": "stg_feeds_silver",   # Silver catalog for LiveFollowSource (public_property_followers)
}


def _bootstrap():
    """Find the bundled `home_feed` package + the staged Qwen parquet in the artifact: put the package
    parent on sys.path (so `import home_feed.src.*` resolves) and point HOME_VECTOR_PARQUET at the parquet.
    (`_e2/` is added to sys.path by home_feed.src.reuse itself.)"""
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
    home_parent = None
    parquet = None
    for dp, dns, fns in os.walk(root):
        if dp[len(root):].count(os.sep) > 8:
            dns[:] = []
            continue
        if home_parent is None and os.path.basename(dp) == "home_feed" \
           and os.path.isfile(os.path.join(dp, "src", "engine.py")):
            home_parent = os.path.dirname(dp)
        if parquet is None:
            for fn in fns:
                if fn.endswith(".parquet"):
                    parquet = os.path.join(dp, fn)
                    break
    if home_parent is None:
        raise ImportError(f"home-feed bundle: home_feed package not found under {root}")
    if home_parent not in sys.path:
        sys.path.insert(0, home_parent)
    if parquet:
        os.environ.setdefault("HOME_VECTOR_PARQUET", parquet)


class _SqlConn:
    """databricks-sql-connector access for LiveFollowSource. A BOUNDED POOL (default size 1, via
    HOME_SQL_POOL_SIZE) so concurrent per-user follow reads don't serialize on one connection lock.
    One small query per request. Reconnects a dead connection on failure."""

    def __init__(self, pool_size=None):
        import queue
        if pool_size is None:
            pool_size = max(1, int(os.getenv("HOME_SQL_POOL_SIZE", "1")))
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


class HomeFeedModel(mlflow.pyfunc.PythonModel):
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

        self._sql = _SqlConn()
        from home_feed.src.engine import HomeFeedEngine
        from home_feed.src.follow_source import LiveFollowSource
        from home_feed.src.graph_moments import GraphMoments
        from home_feed.src.vectors import VectorStore
        from home_feed.src.request import HomeFeedRequest
        self._Request = HomeFeedRequest

        catalog = os.getenv("HOME_SILVER_CATALOG", "stg_feeds_silver")
        self._engine = HomeFeedEngine(
            follow_source=LiveFollowSource(self._sql.query, catalog=catalog),   # Silver follows
            graph=GraphMoments(),        # NEO4J_* env -> Aura (neo4j+s bolt); :Moment / HAS_MOMENT
            vectors=VectorStore())       # HOME_VECTOR_PARQUET -> staged Qwen parquet
        print(f"[home_feed] engine ready (catalog={catalog}, "
              f"neo4j={os.getenv('NEO4J_URI')}, parquet={os.getenv('HOME_VECTOR_PARQUET')})", flush=True)

    def predict(self, context, model_input, params=None):
        records = _parse_records(model_input)
        out = []
        for r in records:
            t0 = time.perf_counter()
            try:
                req = self._Request.from_dict(r)
                env = self._engine.build(req)
                pred = env["predictions"][0] if isinstance(env, dict) and env.get("predictions") else env
                out.append(pred)
                if otel_setup is not None:
                    try:
                        mf = (pred.get("main_feed") or {}) if isinstance(pred, dict) else {}
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "ok")
                        otel_setup.record_routing(_ENDPOINT, path=(pred.get("context") or {}).get("mode"),
                                                  result_count=mf.get("count"))
                    except Exception:
                        pass
            except Exception as e:
                uid = r.get("user_id") if isinstance(r, dict) else "?"
                print(f"[home_feed] record failed (user={uid}): {type(e).__name__}: {e}", flush=True)
                if otel_setup is not None:
                    try:
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "error")
                        otel_setup.record_error(_ENDPOINT, type(e).__name__)
                    except Exception:
                        pass
                out.append({"error": True, "detail": f"{type(e).__name__}: {e}"})
        return out


set_model(HomeFeedModel())
