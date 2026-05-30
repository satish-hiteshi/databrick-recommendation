import json, os, pickle
import mlflow
import mlflow.pyfunc
import pandas as pd
import numpy as np


def _sanitize(obj):
    if isinstance(obj, dict):  return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_sanitize(v) for v in obj]
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    return obj


class FeedsAIModel(mlflow.pyfunc.PythonModel):

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
                results.append(json.dumps(_sanitize(process_query(q))))
            except Exception as e:
                results.append(json.dumps({"error": str(e), "query": q}))

        return pd.DataFrame({"result": results})


def log_model(entities_meta_path, pipeline_src_dir, run_name="feedsai", registered_model_name=None):
    pip_deps = [
        "voyageai>=0.3", "rank-bm25>=0.2.2", "numpy>=1.24",
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
