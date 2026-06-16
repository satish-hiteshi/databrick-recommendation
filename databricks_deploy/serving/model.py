import os
import sys

# Make sibling modules (parrot_adapter) importable regardless of MLflow's on-disk code layout.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mlflow
from mlflow.models import set_model

import parrot_adapter


# Engine wiring for the COLLAPSED deployment. Set BEFORE importing the router (blocks.py reads
# ROUTER_ENGINE_MODE at import). setdefault so an endpoint env var can still override any of them.
_ENGINE_ENV = {
    "ROUTER_ENGINE_MODE": "inprocess",   # blocks._post/_get → in-process dispatch (no engine servers)
    "VECTOR_BACKEND": "databricks",       # dense ANN via Databricks Vector Search
    "ENTITY_BACKEND": "memory",           # Postgres-free entity resolution (parquet-backed)
    "DATA_BACKEND": "parquet",            # get_all_entities() ← 57k embeddings parquet (BM25 corpus)
}


def _bootstrap_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    found = {"router": None, "vector": None, "graph": None, "serving": None}
    for dirpath, dirnames, filenames in os.walk(here):       # walk the model dir, NEVER the fs root
        if dirpath[len(here):].count(os.sep) > 5:            # depth guard (artifact is shallow)
            dirnames[:] = []
            continue
        f = set(filenames)
        if not found["router"] and {"route.py", "assembler.py"} <= f:
            found["router"] = dirpath
        if not found["graph"] and {"query.py", "connection.py"} <= f:
            found["graph"] = dirpath
        if not found["serving"] and {"inprocess_engines.py", "parrot_adapter.py"} <= f:
            found["serving"] = dirpath
        if not found["vector"] and "data_loader.py" in f and os.path.basename(dirpath) == "pipeline":
            found["vector"] = os.path.dirname(dirpath)       # the dir CONTAINING pipeline/

    missing = [k for k, v in found.items() if v is None]
    if missing:
        listing = sorted(os.listdir(here)) if os.path.isdir(here) else "?"
        raise ImportError(f"bundled sources not found: {missing} (here={here}, contents={listing})")

    for d in (found["graph"], found["vector"], found["router"], found["serving"], here):
        if d and d not in sys.path:
            sys.path.insert(0, d)


class RouterModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        for k, v in _ENGINE_ENV.items():
            os.environ.setdefault(k, v)
        _bootstrap_paths()
        import route                                         # noqa: E402  (paths + env set above)
        self._route = route.route
        # Pre-warm heavy singletons (57k embeddings + BM25) so the first — possibly parallel
        # multivertical — query doesn't race/duplicate-load them. Best-effort: must not block load.
        try:
            import inmemory_store
            inmemory_store.embeddings()                      # load the 57k parquet once
        except Exception as e:
            print(f"[parrot] warm-up embeddings failed: {e}", flush=True)
        try:
            from pipeline.vector_store import setup_qdrant
            setup_qdrant()                                   # build BM25 (Qdrant skipped on databricks backend)
        except Exception as e:
            print(f"[parrot] warm-up bm25 failed: {e}", flush=True)

    def predict(self, context, model_input, params=None):
        try:
            rows = parrot_adapter.parse_request(model_input)
        except Exception as e:                               # malformed body → empty envelope, never 5xx
            print(f"[parrot] bad request: {type(e).__name__}: {e}", flush=True)
            return [parrot_adapter.error_response(f"bad request: {type(e).__name__}: {e}")]
        preds = []
        for row in rows:
            if not row["query"]:
                preds.append(parrot_adapter.error_response("missing or empty 'query'"))
                continue
            try:
                import timing
                timing.reset()                               # per-request latency attribution (gated)
                out = self._route(row["query"], top_k=row["top_k"])
                bd = timing.snapshot()
                if bd:
                    out["timing_breakdown"] = bd             # → response.router.timing_breakdown
            except Exception as e:                           # never leak a 500 body to M2M callers
                print(f"[parrot] route failed for {row['query']!r}: {type(e).__name__}: {e}", flush=True)
                preds.append(parrot_adapter.error_response(
                    f"{type(e).__name__}: {e}", query=row["query"]))
                continue
            preds.append(parrot_adapter.to_parrot_response(out))
        return preds


set_model(RouterModel())
