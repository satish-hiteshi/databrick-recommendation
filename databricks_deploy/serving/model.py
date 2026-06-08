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
    "ENTITY_BACKEND": "memory",           # Postgres-free entity resolution
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
    roots = []
    for base in (here, os.path.dirname(here)):
        roots.append(base)
        try:
            roots += [os.path.join(base, n) for n in os.listdir(base)
                      if os.path.isdir(os.path.join(base, n))]
        except OSError:
            pass

    found = {"router": None, "vector": None, "graph": None}
    for r in roots:
        if not found["router"] and os.path.isfile(os.path.join(r, "route.py")) \
                and os.path.isfile(os.path.join(r, "assembler.py")):
            found["router"] = r
        if not found["vector"] and os.path.isfile(os.path.join(r, "pipeline", "data_loader.py")):
            found["vector"] = r
        if not found["graph"] and os.path.isfile(os.path.join(r, "query.py")) \
                and os.path.isfile(os.path.join(r, "connection.py")):
            found["graph"] = r

    missing = [k for k, v in found.items() if v is None]
    if missing:
        raise ImportError(f"bundled sources not found: {missing} (roots scanned: {roots})")

    for d in (found["graph"], found["vector"], found["router"], here):   # router ends up ahead of graph
        if d not in sys.path:
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
