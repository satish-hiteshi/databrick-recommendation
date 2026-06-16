import os
import shutil
import tempfile

import mlflow
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import ColSpec, Schema

try:                                        # UC requires an output signature; `response` is a nested
    from mlflow.types.schema import AnyType  # JSON object → type it AnyType so it isn't coerced to a
    _RESPONSE_TYPE = AnyType()               # stringified blob. Falls back to string on older MLflow.
except ImportError:
    _RESPONSE_TYPE = "string"

MODEL_NAME = os.getenv("UC_MODEL_NAME", "dev_feeds_silver.ml.parrot-api-hitashi-dev")

_HERE = os.path.dirname(os.path.abspath(__file__))          # databricks_deploy/serving
_DEPLOY = os.path.dirname(_HERE)                            # databricks_deploy
_ENG = os.path.join(_DEPLOY, "engines")                    # vendored engine sources

_SIGNATURE = ModelSignature(
    inputs=Schema([ColSpec("string", "user_id"),
                   ColSpec("string", "query"),
                   ColSpec("string", "requesting_agent")]),
    outputs=Schema([ColSpec("string", "query"),
                    ColSpec("string", "routed_to"),
                    ColSpec(_RESPONSE_TYPE, "response")]),
)
_INPUT_EXAMPLE = {"dataframe_records": [
    {"user_id": "12345", "query": "pokemon", "requesting_agent": "morgan"}]}

_SERVING_GLUE = ("model.py", "parrot_adapter.py", "inprocess_engines.py", "inmemory_store.py", "timing.py")
_DATA_FILES = ("embeddings_v2.npy", "embeddings_ids_v2.json",
               "all_compositions_v2.json", "entity_profiles_v2.json")


def _copy_py(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    for fn in os.listdir(src_dir):
        if fn.endswith(".py") and not fn.startswith("test_"):
            shutil.copy(os.path.join(src_dir, fn), dst_dir)


def _stage():
    s = tempfile.mkdtemp(prefix="parrot_collapse_")
    for fn in _SERVING_GLUE:
        shutil.copy(os.path.join(_HERE, fn), s)
    shutil.copy(os.path.join(_DEPLOY, "vector_search", "vs_store.py"), s)

    _copy_py(os.path.join(_ENG, "router_src"), os.path.join(s, "router_src"))
    _copy_py(os.path.join(_ENG, "vector", "pipeline"), os.path.join(s, "vector", "pipeline"))
    _copy_py(os.path.join(_ENG, "graph_src"), os.path.join(s, "graph_src"))

    # 57k embeddings parquet — staged from a VOLUME (not git; it's ~291 MB). Powers the bundle's
    # in-memory resolver + score_set/neighbors + BM25 corpus (inmemory_store / data_loader).
    data_dst = os.path.join(s, "vector", "data_v2")
    os.makedirs(data_dst)
    parquet_src = os.getenv("EMBEDDINGS_PARQUET_SRC",
                            "/Volumes/dev_feeds_silver/ml/feedsai_src/embeddings_voyage_57k.parquet")
    shutil.copy(parquet_src, os.path.join(data_dst, "embeddings_voyage_57k.parquet"))
    print(f"staged parquet from {parquet_src}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        with mlflow.start_run(run_name="parrot-router-v3-collapsed"):
            info = mlflow.pyfunc.log_model(
                artifact_path="router",
                python_model=os.path.join(s, "model.py"),                 # models-from-code
                code_paths=[
                    os.path.join(s, "parrot_adapter.py"),
                    os.path.join(s, "inprocess_engines.py"),
                    os.path.join(s, "inmemory_store.py"),
                    os.path.join(s, "timing.py"),
                    os.path.join(s, "vs_store.py"),
                    os.path.join(s, "router_src"),
                    os.path.join(s, "vector"),                            # pipeline/*.py + data_v2/*
                    os.path.join(s, "graph_src"),
                ],
                signature=_SIGNATURE,
                pip_requirements=os.path.join(_HERE, "requirements.txt"),
                registered_model_name=MODEL_NAME,
            )
        print(f"Logged + registered new version of {MODEL_NAME}")
        print(f"  model_uri: {info.model_uri}")
        print("Next: Serving → repoint the served entity to this version, then set env vars from")
        print("../config.example.env (NEO4J_* with password via secret, VS_*, VOYAGE_API_KEY, DATABRICKS_*).")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
