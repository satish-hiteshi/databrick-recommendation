import json, os, pickle
import pandas as pd
import numpy as np

# mlflow is the serving framework — it is available in the notebook environment
# but may not be importable inside the serving container's user Python env.
# Use a graceful fallback so FeedsAIModel can be imported either way.
try:
    from mlflow.pyfunc import PythonModel
except ImportError:
    PythonModel = object  # serving container: MLflow calls load_context/predict directly


def _sanitize(obj):
    if isinstance(obj, dict):      return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):      return [_sanitize(v) for v in obj]
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    return obj


def _save_history(result: dict) -> None:
    try:
        from databricks import sql as dbsql

        host       = os.getenv("DATABRICKS_HOST", "").replace("https://", "").replace("http://", "")
        token      = os.getenv("DATABRICKS_TOKEN", "")
        http_path  = os.getenv("FEEDSAI_SQL_HTTP_PATH", "")
        catalog    = os.getenv("FEEDSAI_CATALOG", "dev_feeds_silver_infotech")
        schema     = os.getenv("FEEDSAI_SCHEMA", "feedsai")

        def _esc(s: str) -> str:
            return s.replace("'", "''")

        query_text     = _esc(result.get("query", ""))
        parsed_intent  = _esc(json.dumps(_sanitize(result.get("parsed_intent", {}))))
        results_json   = _esc(json.dumps(_sanitize(result)))
        latency_ms     = result.get("timings", {}).get("total_ms", 0)

        conn = dbsql.connect(server_hostname=host, http_path=http_path, access_token=token)
        cur  = conn.cursor()
        cur.execute(
            f"INSERT INTO {catalog}.{schema}.query_history "
            f"(query_text, parsed_intent, results, latency_ms) "
            f"VALUES ('{query_text}', '{parsed_intent}', '{results_json}', {latency_ms})"
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"History save failed (non-critical): {e}")


class FeedsAIModel(PythonModel):

    def load_context(self, context):
        with open(context.artifacts["entities_meta"], "rb") as f:
            entities = pickle.load(f)

        from pipeline import entity_store
        entity_store.init_from_list(entities)

        from pipeline.vector_store import setup
        setup()
        print(f"Model loaded: {len(entities)} entities")

    def predict(self, context, model_input):
        from pipeline.query_engine import process_query

        if isinstance(model_input, pd.DataFrame):
            queries = model_input["query"].tolist()
        elif isinstance(model_input, list):
            queries = [q["query"] if isinstance(q, dict) else str(q) for q in model_input]
        elif isinstance(model_input, dict):
            queries = [model_input.get("query", "")]
        else:
            queries = [str(model_input)]

        results = []
        for q in queries:
            try:
                result = process_query(q)
                _save_history(result)
                results.append(json.dumps(_sanitize(result)))
            except Exception as e:
                results.append(json.dumps({"error": str(e), "query": q}))

        return pd.DataFrame({"result": results})


def log_model(entities_meta_path, pipeline_src_dir, run_name="feedsai", registered_model_name=None):
    import mlflow
    import mlflow.pyfunc

    pip_deps = [
        "rank-bm25>=0.2.2", "numpy>=1.24",
        "databricks-vectorsearch>=0.40", "databricks-sql-connector>=3.0",
        "pandas>=2.0",
    ]
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=FeedsAIModel(),
            artifacts={"entities_meta": entities_meta_path},
            code_paths=[os.path.join(pipeline_src_dir, "pipeline")],
            pip_requirements=pip_deps,
            registered_model_name=registered_model_name,
        )
        print(f"run_id={run.info.run_id}")
        return run.info.run_id
