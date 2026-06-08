"""MLflow pyfunc that serves the feeds.ai unified router behind the Parrot / M2M endpoint.

Registered as a NEW VERSION of  dev_feeds_silver.ml.parrot-api-hitashi-dev  (see register.py), so the
endpoint URL and the wire contract are unchanged — only the brain behind it changes.

    predict():  parrot request  →  route(query, top_k)  →  parrot response
                (request/response mapping lives entirely in parrot_adapter)

The router core is REUSED, not copied. route() reaches the Graph engine and Vector engine over HTTP
(URLs from GRAPH_API_URL / VECTOR_API_URL) and the LLM over HTTP (DATABRICKS_LLM_ENDPOINT / _TOKEN), so
this serving model imports only the router source + httpx — no Qdrant, Neo4j, or Voyage dependencies.

Logged with MLflow "models from code": register.py bundles router/src and parrot_adapter via
code_paths; `set_model(...)` at import time registers the instance.
"""

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
    """Discover the bundled sources in the model artifact and put them on sys.path:
      • router source   (route.py + assembler.py + blocks.py + config.py …)  → flat imports
      • vector pipeline (the dir CONTAINING `pipeline/`)                      → `import pipeline.*`
      • graph source    (query.py + connection.py)                           → flat imports
    MLflow's code_paths layout varies by version, so we DISCOVER each rather than hard-code it. Flat
    module names are unique across the three trees (router=route/blocks/config…, graph=query/connection…,
    vector is namespaced under `pipeline`), so order only needs router before graph for safety.
    """
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

    def predict(self, context, model_input, params=None):
        rows = parrot_adapter.parse_request(model_input)
        preds = []
        for row in rows:
            if not row["query"]:
                preds.append(parrot_adapter.error_response("missing or empty 'query'"))
                continue
            try:
                out = self._route(row["query"], top_k=row["top_k"])
            except Exception as e:                           # never leak a 500 body to M2M callers
                preds.append(parrot_adapter.error_response(
                    f"{type(e).__name__}: {e}", query=row["query"]))
                continue
            preds.append(parrot_adapter.to_parrot_response(out))
        return preds


set_model(RouterModel())
