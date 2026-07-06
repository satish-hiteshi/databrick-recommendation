"""MLflow pyfunc for the UC8 Onboarding Boost endpoint on Databricks Model Serving.

Wraps the boost engine (src/{data,gaps,vector_store}.py) — self-contained at serve time:
  • embeddings ← the staged Qwen parquet (data.py's BOOST_PARQUET; memory backend, no Qdrant)
  • signals    ← Silver via the injected databricks-sql query_fn (BOOST_DATA_SOURCE=live):
                 popularity/centrality/proximity reuse UC6 `adaptive_property_*`; the moment gate reads
                 `boost_property_moments` (built by databricks_deploy/precompute/precompute_moments.py)
  • follows    ← STATELESS. /boost returns a payload; /boost/confirm just validates + echoes the accepted
                 ids back (the app performs the real follow write). No server-side offer store — so it is
                 replica-safe (the offered ids are echoed by the client in the confirm record).

ONE predict, TWO ops — routed on the record's `op` field ("boost" default | "confirm"), or inferred as
"confirm" when an `action` field is present. Registered as its OWN UC model + serving endpoint.
"""

import os
import sys
import time
from datetime import datetime, timezone

import mlflow
from mlflow.models import set_model

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # serving dir (otel_setup beside this file)
try:
    import otel_setup       # noqa: E402  best-effort OTLP telemetry (no-op if unset / not bundled)
except Exception:
    otel_setup = None

_ENDPOINT = os.getenv("OTEL_SERVICE_NAME", "onboarding-boost")

# Defaults set BEFORE importing the engine (data.py reads these at import/get time).
_ENV = {
    "BOOST_DATA_SOURCE": "live",                  # data.py: parquet embeddings + Silver signals (no Postgres)
    "BOOST_SILVER_CATALOG": "stg_feeds_silver",
    "BOOST_SILVER_SCHEMA": "ml",
    "BOOST_VECTOR_BACKEND": "memory",             # in-RAM embeddings from the parquet (no Qdrant in serving)
}


def _bootstrap():
    """Find the bundled engine modules + the staged Qwen parquet in the artifact: ensure the dir holding
    data.py/gaps.py/vector_store.py is on sys.path (so `import data`/`import gaps` resolve) and point
    BOOST_PARQUET at the staged parquet (data.py reads it for the memory backend)."""
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
        if eng_dir is None and "data.py" in fns and "gaps.py" in fns and "vector_store.py" in fns:
            eng_dir = dp
        if parquet is None:
            for fn in fns:
                if fn.endswith(".parquet"):
                    parquet = os.path.join(dp, fn)
                    break
    if eng_dir and eng_dir not in sys.path:
        sys.path.insert(0, eng_dir)
    if parquet:
        os.environ.setdefault("BOOST_PARQUET", parquet)


class _SqlConn:
    """databricks-sql-connector access for the Silver signal reads. A BOUNDED POOL (default size 1): the
    signal tables load once at warm-up; there are NO per-request queries. Reconnects a dead connection."""

    def __init__(self, pool_size=None):
        import queue
        if pool_size is None:
            pool_size = max(1, int(os.getenv("BOOST_SQL_POOL_SIZE", "1")))
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
    """MLflow model_input -> list of plain request dicts."""
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


def _ints(xs):
    out = []
    for x in (xs or []):
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


class BoostModel(mlflow.pyfunc.PythonModel):
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

        # Inject the Silver query_fn into data.py BEFORE Data.get() (signals read via it).
        self._sql = _SqlConn()
        import data as _data
        _data.set_query_fn(self._sql.query)
        self._data_mod = _data

        import gaps as _gaps
        import vector_store as _vs
        self._gaps = _gaps
        # Warm exactly like api._startup: load embeddings + signals, warm gaps, build the vector store.
        d = _data.Data.get()
        _gaps.warm(d)
        self._vs = _vs.get_store(d)
        print(f"[boost] engine ready — {d.stats()} | vector_backend={self._vs.name}", flush=True)

    # ── ops ──────────────────────────────────────────────────────────────────────
    def _boost(self, rec):
        data = self._data_mod.Data.get()
        gaps = self._gaps
        followed = _ints(rec.get("followed_property_ids"))
        ctx, groups, dbg = gaps.build_boost(
            data, self._vs, followed=followed,
            target_per_vertical=rec.get("target_per_vertical") or gaps.DEFAULT_TARGET_PER_VERTICAL,
            total_cap=rec.get("total_cap") or gaps.DEFAULT_TOTAL_CAP,
            gap_threshold=rec.get("gap_threshold") or gaps.DEFAULT_GAP_THRESHOLD,
            exclude_verticals=rec.get("exclude_verticals") or [],
            exclude_ids=_ints(rec.get("exclude_ids")),
            richness_floor=rec.get("richness_floor"),
            id_space=(rec.get("id_space") or "auto").lower(),
            deepen_covered=bool(rec.get("deepen_covered", True)),
            deepen_per_vertical=rec.get("deepen_per_vertical"),
            debug=bool(rec.get("debug")))
        offered = [p["property_id"] for g in groups for p in g["properties"]]
        return {
            "version": "1.0", "endpoint": "onboarding-boost",
            "user_id": rec.get("user_id"), "session_id": rec.get("session_id"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "context": ctx, "boost_payload": groups,
            "offered_property_ids": offered,     # echo back for stateless /confirm
            "write_path": "confirm_then_write", "debug": dbg,
        }

    def _confirm(self, rec):
        """Stateless confirm: the client echoes the accepted ids in `followed_property_ids` (or the whole
        offered set); we validate them against the served universe and return them. The app writes follows."""
        data = self._data_mod.Data.get()
        action = (rec.get("action") or "confirm").lower()
        now = datetime.now(timezone.utc).isoformat()
        if action == "skip":
            return {"version": "1.0", "endpoint": "onboarding-boost-confirm", "user_id": rec.get("user_id"),
                    "session_id": rec.get("session_id"), "action": "skip", "written": 0, "generated_at": now}
        accepted = _ints(rec.get("followed_property_ids") or rec.get("offered_property_ids"))
        id_space = (rec.get("id_space") or "auto").lower()
        resolved, public = [], []
        for pid in accepted:
            ext = data.resolve(pid, mode=id_space)
            if ext is not None and ext not in resolved:
                resolved.append(ext)
                public.append(data.public_id(ext))
        return {"version": "1.0", "endpoint": "onboarding-boost-confirm", "user_id": rec.get("user_id"),
                "session_id": rec.get("session_id"), "action": "confirm", "generated_at": now,
                "followed_property_ids": resolved, "followed_public_ids": public,
                "written": len(resolved),
                "error": None if resolved else "no_valid_ids"}

    def predict(self, context, model_input, params=None):
        records = _parse_records(model_input) or [{}]
        out = []
        for rec in records:
            t0 = time.perf_counter()
            op = str(rec.get("op") or ("confirm" if rec.get("action") else "boost")).lower()
            try:
                pred = self._confirm(rec) if op == "confirm" else self._boost(rec)
                out.append(pred)
                if otel_setup is not None:
                    try:
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "ok")
                    except Exception:
                        pass
            except Exception as e:
                sid = rec.get("session_id") if isinstance(rec, dict) else "?"
                print(f"[boost] record failed (op={op} session={sid}): {type(e).__name__}: {e}", flush=True)
                if otel_setup is not None:
                    try:
                        otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "error")
                        otel_setup.record_error(_ENDPOINT, type(e).__name__)
                    except Exception:
                        pass
                out.append({"error": True, "op": op, "detail": f"{type(e).__name__}: {e}"})
        return out


set_model(BoostModel())
