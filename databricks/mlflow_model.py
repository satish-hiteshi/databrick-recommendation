"""
MLflow pyfunc model for the Feeds.ai pipeline.

Lifecycle
---------
load_context():
    1. Loads entities_meta.pkl from the model artifact directory.
    2. Initialises entity_store (in-memory dict used by BM25, reranker, neg-filter).
    3. Builds the BM25 index.
    4. Pre-connects to the Databricks Vector Search index.

predict(model_input):
    Accepts a pandas DataFrame with a "query" column (one row per request)
    and returns a DataFrame with a "result" column containing a JSON string
    per row.

REST call format (Databricks Model Serving):
    POST /invocations
    {"dataframe_records": [{"query": "Games like Elden Ring"}]}
"""

import json
import pickle

import mlflow
import mlflow.pyfunc
import pandas as pd
import numpy as np


def _sanitize(obj):
    """Recursively make an object JSON-serialisable (strip numpy scalars, etc.)."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


class FeedsAIModel(mlflow.pyfunc.PythonModel):

    def load_context(self, context):
        # 1. Load entity data from pickle artifact
        artifact_path = context.artifacts["entities_meta"]
        with open(artifact_path, "rb") as f:
            entities = pickle.load(f)

        # 2. Initialise entity_store (must happen before anything else)
        from pipeline import entity_store
        entity_store.init_from_list(entities)

        # 3. Build BM25 index + connect to VS index
        from pipeline.vector_store import setup
        setup()

        print(f"FeedsAI model loaded: {len(entities)} entities in store.")

    def predict(self, context, model_input):
        from pipeline.query_engine import process_query

        # Accept DataFrame, list-of-dicts, or a single dict
        if isinstance(model_input, pd.DataFrame):
            queries = model_input["query"].tolist()
        elif isinstance(model_input, list):
            queries = [
                q["query"] if isinstance(q, dict) else str(q)
                for q in model_input
            ]
        elif isinstance(model_input, dict):
            queries = [model_input.get("query", "")]
        else:
            queries = [str(model_input)]

        results = []
        for q in queries:
            try:
                result = process_query(q)
                results.append(json.dumps(_sanitize(result)))
            except Exception as exc:
                results.append(json.dumps({"error": str(exc), "query": q}))

        return pd.DataFrame({"result": results})


# ── Convenience: log / register the model ────────────────────────────

def log_model(
    entities_meta_path: str,
    pipeline_src_dir: str,
    run_name: str = "feedsai-databricks",
    registered_model_name: str | None = None,
):
    """
    Log FeedsAIModel to MLflow with the entities pickle as an artifact.

    Parameters
    ----------
    entities_meta_path : str
        Local path to the entities_meta.pkl file (created by notebook 02).
        Example: /Volumes/dev_feeds_silver_infotech/feedsai/artifacts/entities_meta.pkl
    pipeline_src_dir : str
        Path to the databricks/ directory (the one that CONTAINS the pipeline/ package).
        MLflow bundles this directory into the model so Model Serving can import it.
        Example: /Workspace/Repos/you@company.com/feeds-ai-poc-internal/databricks
    run_name : str
        MLflow run name.
    registered_model_name : str, optional
        Unity Catalog model name, e.g. "dev_feeds_silver_infotech.feedsai.feedsai_model".
    """
    import mlflow

    pip_deps = [
        "voyageai>=0.3",
        "rank-bm25>=0.2.2",
        "numpy>=1.24",
        "databricks-vectorsearch>=0.40",
        "databricks-sql-connector>=3.0",
        "pandas>=2.0",
        "mlflow>=2.14",
    ]

    artifacts = {"entities_meta": entities_meta_path}

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=FeedsAIModel(),
            artifacts=artifacts,
            # code_paths bundles the databricks/ directory into the model so that
            # `from pipeline.config import ...` works inside Model Serving containers.
            code_paths=[pipeline_src_dir],
            pip_requirements=pip_deps,
            registered_model_name=registered_model_name,
        )
        print(f"Model logged: run_id={run.info.run_id}")
        if registered_model_name:
            print(f"Registered as: {registered_model_name}")
        return run.info.run_id
