"""model.py — MLflow pyfunc for Endpoint 3 (home-feed) on Databricks.

Wraps the LOCAL home-feed engine (home_feed/src + discovery/src) byte-unchanged. The ONLY Databricks
piece is the data source: HOME_DATA_SOURCE=live makes discovery/src/{data,store}.py read the Silver
lakehouse via a databricks-sql-connector query_fn (no SparkSession in serving), keyed by property_id —
the SAME public_properties / public_moments / public_property_followers / ml.pagerank tables Endpoint 2
reads. predict() maps {user_id,…} records -> the UC3 home-feed envelope by calling home_api._build_one
(the exact code the local FastAPI app runs).

Registered as a NEW UC model (e.g. stg_feeds_silver.ml.home-feed-staging), served at its OWN endpoint.
"""

import os
import sys
import time

import mlflow
from mlflow.models import set_model

# serving dir on path (otel_setup / obs live beside this file if bundled)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import otel_setup       # noqa: E402  best-effort OTLP telemetry (no-op if unset / not bundled)
except Exception:
    otel_setup = None

_ENDPOINT = os.getenv("OTEL_SERVICE_NAME", "home-feed")

# Engine wiring — set BEFORE the engine imports (setdefault so an endpoint env var still overrides).
_ENV = {
    "HOME_DATA_SOURCE": "live",          # discovery/src/{data,store}.py read Silver (not the dev CSVs)
    "DISCOVERY_PG": "0",                 # no Postgres in serving (follows come from Silver; scores skip)
    "HOME_SILVER_CATALOG": "stg_feeds_silver",
}


def _bootstrap_paths():
    """Find the bundled home_feed/src + discovery/src trees in the artifact and put them on sys.path so
    `import home_api` and the engine's bare imports (`from data import Data`) resolve. MLflow's code
    layout varies, so we walk the artifact root and match each tree by its marker files."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
    found = {"home": None, "disc": None}
    for dp, dns, fns in os.walk(root):
        if dp[len(root):].count(os.sep) > 8:
            dns[:] = []
            continue
        f = set(fns)
        if not found["home"] and {"home_api.py", "home_ranking.py", "home_schema.py"} <= f:
            found["home"] = dp
        if not found["disc"] and {"data.py", "store.py", "ranking.py", "carousels.py"} <= f:
            found["disc"] = dp
    for k, d in found.items():
        if d and d not in sys.path:
            sys.path.insert(0, d)
    missing = [k for k, v in found.items() if v is None]
    if missing:
        raise ImportError(f"home-feed bundle: trees not found {missing} (root={root})")


class _SqlConn:
    """databricks-sql-connector access for the live data source. A BOUNDED POOL (default size 1, set via
    HOME_SQL_POOL_SIZE) so concurrent per-user requests don't serialize on one connection lock. The
    global Silver reads (properties/moments/influence) run once on load; per-request reads are one small
    follows query. Reconnects a dead connection on failure."""

    def __init__(self, pool_size=None):
        import queue
        if pool_size is None:
            pool_size = max(1, int(os.getenv("HOME_SQL_POOL_SIZE", "1")))
        self._pool = queue.Queue()
        for _ in range(pool_size):
            self._pool.put(None)            # lazily connected on first checkout

    def _connect(self):
        from databricks import sql as dbsql
        host = os.environ["DATABRICKS_HOST"].replace("https://", "").replace("http://", "").rstrip("/")
        return dbsql.connect(server_hostname=host,
                             http_path=os.environ["DATABRICKS_HTTP_PATH"],
                             access_token=os.environ["DATABRICKS_TOKEN"])

    def query(self, sql):
        conn = self._pool.get()             # checkout (blocks only if all connections are in use)
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
                except Exception as e:       # stale conn -> drop it, reconnect next attempt
                    last = e
                    conn = None
            raise last
        finally:
            self._pool.put(conn)             # return to pool (None if it died -> re-lazy-connects)


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
        _bootstrap_paths()
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
        import data as _data          # discovery/src/data.py (engine loader)
        import store as _store         # discovery/src/store.py (follow state)
        _data.set_query_fn(self._sql.query)
        _store.set_query_fn(self._sql.query)
        self._data = _data

        import home_api                # the local FastAPI app module (imports the engine, builds the app)
        self._home_api = home_api

        _data.Data.load()              # warm: global Silver reads once (properties/moments/embeddings/influence)
        try:
            print(f"[home_feed] warm: {_data.Data.get().stats()}", flush=True)
        except Exception:
            pass

    def predict(self, context, model_input, params=None):
        records = _parse_records(model_input)
        out = []
        for r in records:
            t0 = time.perf_counter()
            try:
                env = self._home_api._build_one(r)
                out.append(env)
                if otel_setup is not None:
                    try:
                        main = (env.get("main_feed") or {}) if isinstance(env, dict) else {}
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "ok")
                        otel_setup.record_routing(_ENDPOINT, path=(env.get("context") or {}).get("mode"),
                                                  result_count=main.get("count"))
                    except Exception:
                        pass
            except Exception as e:
                # home_api._build_one raises HTTPException (e.g. 422 missing user_id) -> structured error/record
                status = getattr(e, "status_code", 500)
                detail = getattr(e, "detail", f"{type(e).__name__}: {e}")
                print(f"[home_feed] record failed (user={r.get('user_id') if isinstance(r, dict) else '?'}): "
                      f"{type(e).__name__}: {e}", flush=True)
                if otel_setup is not None:
                    try:
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "error")
                        otel_setup.record_error(_ENDPOINT, type(e).__name__)
                    except Exception:
                        pass
                out.append({"error": True, "status": status, "detail": detail})
        return out


set_model(HomeFeedModel())
