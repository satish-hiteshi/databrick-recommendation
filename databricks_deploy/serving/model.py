import os
import sys
import time

# Make sibling modules (parrot_adapter) importable regardless of MLflow's on-disk code layout.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mlflow
from mlflow.models import set_model

import parrot_adapter
import otel_setup                                # OTLP push telemetry (best-effort, never blocks)

_ENDPOINT = os.getenv("OTEL_SERVICE_NAME", "agent-recs")


# Engine wiring for the COLLAPSED deployment. Set BEFORE importing the router (blocks.py reads
# ROUTER_ENGINE_MODE at import). setdefault so an endpoint env var can still override any of them.
_ENGINE_ENV = {
    "ROUTER_ENGINE_MODE": "inprocess",   # blocks._post/_get → in-process dispatch (no engine servers)
    "VECTOR_BACKEND": "qdrant",           # DEFAULT: in-memory qdrant from the parquet (set VECTOR_BACKEND=databricks for Vector Search)
    "ENTITY_BACKEND": "memory",           # Postgres-free entity resolution (parquet-backed)
    "DATA_BACKEND": "parquet",            # get_all_entities() ← 57k embeddings parquet (BM25 corpus)
    # RUNTIME EMBEDDER = QWEN (Greg's decision: Qwen is the deploy model). Setting QUERY_EMBED_ENDPOINT
    # makes get_query_embedding take the QWEN branch (instruction-prefixed query, Qwen's native convention)
    # instead of Voyage. Query-model == doc-model: the DOC vectors must also be Qwen (set EMBEDDINGS_PARQUET
    # to the Qwen deploy parquet; default name is the Qwen file — see inmemory_store._PARQUET_NAME).
    # The Qwen path also needs DATABRICKS_HOST + DATABRICKS_TOKEN in the deploy env (provided by the wiring).
    "QUERY_EMBED_ENDPOINT": "databricks-qwen3-embedding-0-6b",   # Qwen serving-endpoint NAME (deploy env overrides)
    # Graph schema names for the RE-KEYED neo4j 2026.05 graph (the deploy target). The graph_src Cypher is
    # env-driven (connection.py); these setdefaults point it at the new schema. Override via env for another
    # graph. On the new graph: PageRank=`pagerank` (not `influence`); maker edges HAS_DEVELOPER/HAS_PUBLISHER.
    "GRAPH_INFLUENCE_PROP": "pagerank",
    "GRAPH_DEVELOPER_REL": "HAS_DEVELOPER",
    "GRAPH_PUBLISHER_REL": "HAS_PUBLISHER",
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
        otel_setup.init(_ENDPOINT)                       # one-time OTLP provider setup (no-op if env unset)
        _bootstrap_paths()
        import substrate_guard                               # noqa: E402  (paths set above)
        substrate_guard.assert_substrate()                  # FAIL LOUD on a wrong graph/parquet (stale-artifact guard)
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
            t0 = time.perf_counter()
            with otel_setup.span("request", {"endpoint": _ENDPOINT}) as sp:
                try:
                    import timing
                    timing.reset()                               # per-request latency attribution (gated)
                    out = self._route(row["query"], top_k=row["top_k"])
                    bd = timing.snapshot()
                    if bd:
                        out["timing_breakdown"] = bd             # → response.router.timing_breakdown
                except Exception as e:                           # never leak a 500 body to M2M callers
                    print(f"[parrot] route failed for {row['query']!r}: {type(e).__name__}: {e}", flush=True)
                    otel_setup.record_request(_ENDPOINT, (time.perf_counter() - t0) * 1000.0, "error")
                    otel_setup.record_error(_ENDPOINT, type(e).__name__)
                    sp.set_attribute("error", True)
                    preds.append(parrot_adapter.error_response(
                        f"{type(e).__name__}: {e}", query=row["query"]))
                    continue
                # success — emit the H1.6 signal set (all best-effort; see otel_setup.py)
                self._emit_metrics(sp, out, bd, (time.perf_counter() - t0) * 1000.0)
                preds.append(parrot_adapter.to_parrot_response(out))
        return preds

    @staticmethod
    def _emit_metrics(sp, out, bd, latency_ms):
        otel_setup.record_request(_ENDPOINT, latency_ms, "ok")
        otel_setup.record_stage_latencies(_ENDPOINT, bd)
        path = out.get("path_taken")
        results = out.get("results") or []
        evr = out.get("exact_vs_related") or {}
        exact = evr.get("exact") if isinstance(evr, dict) else None
        related = evr.get("related") if isinstance(evr, dict) else None
        otel_setup.record_routing(_ENDPOINT, path=path, extraction_ok=out.get("extraction_ok"),
                                  result_count=len(results), exact=exact, related=related)
        # token counts are emitted only if the router surfaces them (not yet wired — see otel_setup.py)
        tok = out.get("tokens") or {}
        otel_setup.record_tokens(_ENDPOINT, tok.get("input"), tok.get("output"))
        if sp is not None:
            sp.set_attribute("routing.path", str(path))
            sp.set_attribute("result.count", len(results))
            sp.set_attribute("extraction.ok", bool(out.get("extraction_ok")))


set_model(RouterModel())
