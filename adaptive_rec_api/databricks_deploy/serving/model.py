"""MLflow pyfunc for the Onboarding Adaptive-Rec endpoint (UC6) on Databricks Model Serving.

Wraps the adaptive-rec engine (src/api.py) as-is — pure vector-taste over the 44k-qwen embeddings:
  • embeddings ← the staged Qwen parquet (data.py's parquet path; no local Postgres in serving)
  • signals    ← Silver `adaptive_property_{centrality,popularity,proximity}` via the injected databricks-sql
                 query_fn (ADAPTIVE_DATA_SOURCE=live) — built by databricks_deploy/precompute/*.py
  • session    ← in-memory (ADAPTIVE_PG=0 → store.py's degraded path; the client passes exclude_ids to dedup)
predict() maps {session_id, followed_property_ids, …} records → the UC6 predictions[] envelope by calling
api.adaptive_rec unchanged (engine code is byte-identical to the dev branch).

Registered as a NEW UC model (e.g. stg_feeds_silver.ml.onboarding-adaptive-staging), served at its OWN endpoint.
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

_ENDPOINT = os.getenv("OTEL_SERVICE_NAME", "onboarding-adaptive")

# Defaults set BEFORE importing the engine (data.py/store.py read these at import time).
_ENV = {
    "ADAPTIVE_DATA_SOURCE": "live",              # data.py: parquet embeddings + Silver signals (no Postgres)
    "ADAPTIVE_SILVER_CATALOG": "stg_feeds_silver",
    "ADAPTIVE_PG": "0",                          # store.py: in-memory session (no local Postgres in serving)
}


def _bootstrap():
    """Find the bundled engine modules + the staged Qwen parquet in the artifact: ensure the dir holding
    api.py/data.py/store.py is on sys.path (MLflow adds the code root, so `import api` resolves) and point
    ADAPTIVE_PARQUET at the staged parquet (data.py reads it when no Postgres)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
    eng_dir = None
    parquet = None
    for dp, dns, fns in os.walk(root):
        if dp[len(root):].count(os.sep) > 8:
            dns[:] = []
            continue
        if eng_dir is None and "api.py" in fns and "data.py" in fns and "store.py" in fns:
            eng_dir = dp
        if parquet is None:
            for fn in fns:
                if fn.endswith(".parquet"):
                    parquet = os.path.join(dp, fn)
                    break
    if eng_dir and eng_dir not in sys.path:
        sys.path.insert(0, eng_dir)
    if parquet:
        os.environ.setdefault("ADAPTIVE_PARQUET", parquet)


class _SqlConn:
    """databricks-sql-connector access for the Silver signal reads. A BOUNDED POOL (default size 1, via
    ADAPTIVE_SQL_POOL_SIZE): the 3 signal tables load once at warm-up; there are NO per-request queries
    (all signals are in-memory numpy after startup). Reconnects a dead connection on failure."""

    def __init__(self, pool_size=None):
        import queue
        if pool_size is None:
            pool_size = max(1, int(os.getenv("ADAPTIVE_SQL_POOL_SIZE", "1")))
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


class AdaptiveRecModel(mlflow.pyfunc.PythonModel):
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

        # Inject the Silver query_fn into data.py BEFORE anything triggers Data.get() (signals read via it).
        self._sql = _SqlConn()
        import data as _data
        _data.set_query_fn(self._sql.query)

        import api as _api
        self._api = _api
        # Warm exactly like api._startup: load embeddings+signals, precompute name/franchise arrays + masks.
        d = _api.Data.get()
        _api._ensure_name_arrays(d)
        for v in _api._BRIDGE_TERMS:
            _api._topic_mask(d, v)
        print(f"[adaptive] engine ready — {d.stats()} | session_persistent={_api.STORE.health()['persistent']} "
              f"| parquet={os.getenv('ADAPTIVE_PARQUET')}", flush=True)

    def predict(self, context, model_input, params=None):
        records = _parse_records(model_input) or [{}]
        api = self._api
        out = []
        for rec in records:
            t0 = time.perf_counter()
            try:
                res = api.adaptive_rec(api.DataframeBody(dataframe_records=[rec]))
                preds = res.get("predictions") if isinstance(res, dict) else None
                preds = preds if preds else [res]
                out.extend(preds)
                if otel_setup is not None:
                    try:
                        p0 = preds[0] if preds else {}
                        ctx = (p0.get("context") or {}) if isinstance(p0, dict) else {}
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "ok")
                        otel_setup.record_routing(_ENDPOINT, path=("threshold_met" if ctx.get("threshold_met") else "no_suggestion"),
                                                  result_count=len([p for p in preds if isinstance(p, dict) and p.get("suggestion")]))
                    except Exception:
                        pass
            except Exception as e:
                sid = rec.get("session_id") if isinstance(rec, dict) else "?"
                print(f"[adaptive] record failed (session={sid}): {type(e).__name__}: {e}", flush=True)
                if otel_setup is not None:
                    try:
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "error")
                        otel_setup.record_error(_ENDPOINT, type(e).__name__)
                    except Exception:
                        pass
                out.append({"error": True, "detail": f"{type(e).__name__}: {e}"})
        return out


set_model(AdaptiveRecModel())
