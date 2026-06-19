"""MLflow pyfunc for Endpoint 2 (discovery-api) on Databricks — the COLLAPSED discovery feed engine.

Registered as a NEW UC model (e.g. dev_feeds_silver.ml.discovery-api-staging), served at its OWN endpoint.
Reuses, never rebuilds:
  • the discovery ENGINE (discovery_api/src) as-is — V2FeedBuilder builds the taste-learning feed,
  • E1's COLLAPSED substrate (inprocess_engines + inmemory_store + vs_store + Aura) via SUBSTRATE_MODE=
    inprocess (SubstrateClient dispatches in-process — no :8000/:8010 servers),
  • the SAME Qwen vector + Aura graph E1 staging uses (so retrieval is consistent).
The ONE new piece is the data: LiveDataSource reads the Silver tables via a databricks-sql-connector
query (no SparkSession in serving). predict() maps {user_id,…} -> the v1.0 discovery envelope.
"""

import os
import sys
import threading

import mlflow
from mlflow.models import set_model

# E2 serving dir on path (discovery_adapter, live_source_dbx live beside this file)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import discovery_adapter   # noqa: E402

# Engine wiring (set BEFORE the engine imports; setdefault so an endpoint env var still overrides).
_ENV = {
    "SUBSTRATE_MODE": "inprocess",      # SubstrateClient -> in-process dispatch into E1's engines
    "DISCOVERY_DATA_SOURCE": "live",    # use LiveDataSource (not the dev CSVs)
    "DISCOVERY_DEFAULT_ENGINE": "v2",   # the taste-learning engine
    "DISCOVERY_NOW_ISO": "",            # wall-clock now in prod (dev pins a fixed date)
    "ROUTER_ENGINE_MODE": "inprocess",  # E1 engine collapse flags (also settable via endpoint env)
    "VECTOR_BACKEND": "databricks",
    "ENTITY_BACKEND": "memory",
    "DATA_BACKEND": "parquet",
}


def _bootstrap_paths():
    """Discover the bundled trees in the artifact and put them on sys.path (MLflow's code layout varies):
      • discovery package root (dir CONTAINING discovery_api/)  -> import discovery_api.src.*
      • E1 serving  (inprocess_engines + inmemory_store + vs_store)
      • E1 router_src / vector(pipeline) / graph_src  (so inprocess_engines' imports resolve)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    # climb to the artifact root, then walk down (shallow) finding each tree by marker files
    root = here
    for _ in range(6):
        root = os.path.dirname(root)
    found = {"disc_parent": None, "e1_serving": None, "router": None, "vector": None, "graph": None}
    for dp, dns, fns in os.walk(root):
        if dp[len(root):].count(os.sep) > 8:
            dns[:] = []; continue
        f = set(fns)
        if not found["e1_serving"] and {"inprocess_engines.py", "inmemory_store.py"} <= f:
            found["e1_serving"] = dp
        if not found["router"] and {"route.py", "assembler.py", "blocks.py"} <= f:
            found["router"] = dp
        if not found["graph"] and {"query.py", "connection.py"} <= f:
            found["graph"] = dp
        if not found["vector"] and "data_loader.py" in f and os.path.basename(dp) == "pipeline":
            found["vector"] = os.path.dirname(dp)            # dir CONTAINING pipeline/
        if not found["disc_parent"] and os.path.basename(dp) == "discovery_api" and \
                os.path.isfile(os.path.join(dp, "src", "data_access", "base.py")):
            found["disc_parent"] = os.path.dirname(dp)       # dir CONTAINING discovery_api/
    for k, d in found.items():
        if d and d not in sys.path:
            sys.path.insert(0, d)
    missing = [k for k, v in found.items() if v is None]
    if missing:
        raise ImportError(f"E2 bundle: trees not found {missing} (root={root})")


class _SqlConn:
    """Persistent databricks-sql-connector connection for LiveDataSource (lock-protected; reconnect on
    failure). One small query per user request (follows); the heavy global reads run once on load."""
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = None

    def _connect(self):
        from databricks import sql as dbsql
        host = os.environ["DATABRICKS_HOST"].replace("https://", "").replace("http://", "").rstrip("/")
        self._conn = dbsql.connect(server_hostname=host,
                                   http_path=os.environ["DATABRICKS_HTTP_PATH"],
                                   access_token=os.environ["DATABRICKS_TOKEN"])

    def query(self, sql):
        with self._lock:
            last = None
            for attempt in range(2):
                try:
                    if self._conn is None:
                        self._connect()
                    cur = self._conn.cursor()
                    cur.execute(sql)
                    cols = [c[0] for c in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    cur.close()
                    return rows
                except Exception as e:                       # stale conn → reconnect once
                    last = e; self._conn = None
            raise last


class DiscoveryModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        for k, v in _ENV.items():
            os.environ.setdefault(k, v)
        _bootstrap_paths()

        from live_source_dbx import LiveDataSource
        from discovery_api.src.data_access.substrate_client import SubstrateClient
        from discovery_api.src.feed.blend import V2FeedBuilder
        from discovery_api.src import timeutil

        self._timeutil = timeutil
        self._sql = _SqlConn()
        catalog = os.getenv("DISCOVERY_CATALOG", "stg_feeds_silver")
        self._ds = LiveDataSource(self._sql.query, catalog=catalog)
        self._ds.load()                                      # warm: global Silver reads once
        # SubstrateClient picks up SUBSTRATE_MODE=inprocess -> dispatches into E1's collapsed engines
        self._builder = V2FeedBuilder(self._ds, substrate=SubstrateClient())
        # warm E1's in-process engines (57k embeddings + BM25) so the first feed isn't a cold race
        try:
            import inmemory_store; inmemory_store.embeddings()
            from pipeline.vector_store import setup_qdrant; setup_qdrant()
        except Exception as e:
            print(f"[discovery] engine warm-up: {type(e).__name__}: {e}", flush=True)

    def predict(self, context, model_input, params=None):
        try:
            rows = discovery_adapter.parse_request(model_input)
        except Exception as e:
            print(f"[discovery] bad request: {type(e).__name__}: {e}", flush=True)
            return [discovery_adapter.error_response(f"bad request: {type(e).__name__}: {e}")]
        out = []
        for req in rows:
            try:
                now = self._timeutil.parse_ts(req["now"]) if req.get("now") else self._timeutil.now()
                uid = req["user_id"]
                feed, meta = self._builder.build(
                    (int(uid) if uid is not None else -1), now=now,
                    limit=1_000_000, offset=0,                 # build whole feed; adapter date-filters+pages
                    seen_ids=req["seen_ids"], excluded_property_ids=req["property_ids"])
                out.append(discovery_adapter.serialize(feed, meta, req, now, self._ds))
            except Exception as e:
                print(f"[discovery] feed failed for user {req.get('user_id')}: {type(e).__name__}: {e}", flush=True)
                out.append(discovery_adapter.error_response(f"{type(e).__name__}: {e}", req.get("user_id")))
        return out


set_model(DiscoveryModel())
