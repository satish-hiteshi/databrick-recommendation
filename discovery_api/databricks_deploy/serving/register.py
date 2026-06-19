"""register.py — log Endpoint 2 (discovery-api) as a NEW UC model with the COLLAPSED stack bundled.

models-from-code: model.py is the pyfunc; code_paths bundle everything it needs into one artifact:
  • E2 serving:   model.py + discovery_adapter + live_source_dbx
  • E2 engine:    discovery_api/src  (the taste-learning feed engine, vendored as-is)
  • E1 collapsed substrate (REUSED read-only via SUBSTRATE_MODE=inprocess):
        inprocess_engines + inmemory_store + timing + vs_store + router_src + vector(pipeline) + graph_src
  • the Qwen embeddings parquet (staged from a Volume) → E1's in-memory matrix + BM25.

Registers UC_MODEL_NAME. Run in a notebook:
    import os, sys, importlib
    os.environ["UC_MODEL_NAME"] = "stg_feeds_silver.ml.discovery-api-staging"
    os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen.parquet"
    sys.path.insert(0, "<repo>/discovery_api/databricks_deploy/serving"); import register; register.main()
"""

import os
import shutil
import tempfile

import mlflow
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import ColSpec, Schema

try:                                         # UC needs outputs; the feed is a nested JSON object → AnyType
    from mlflow.types.schema import AnyType  # so it isn't coerced to a stringified blob.
    _RT = AnyType()
except ImportError:
    _RT = "string"

MODEL_NAME = os.getenv("UC_MODEL_NAME", "stg_feeds_silver.ml.discovery-api-staging")

_HERE = os.path.dirname(os.path.abspath(__file__))            # discovery_api/databricks_deploy/serving
_DISC_ROOT = os.path.dirname(os.path.dirname(_HERE))          # discovery_api/
_REPO = os.path.dirname(_DISC_ROOT)                           # repo root
_E1 = os.path.join(_REPO, "databricks_deploy")               # E1's deploy bundle (engines + serving)
_E1_SERVING = os.path.join(_E1, "serving")
_E1_ENG = os.path.join(_E1, "engines")

_SIGNATURE = ModelSignature(
    inputs=Schema([ColSpec("long", "user_id")]),             # only user_id enforced; rest are optional
    outputs=Schema([ColSpec("string", "endpoint"), ColSpec(_RT, "context"),
                    ColSpec(_RT, "main_feed"), ColSpec(_RT, "carousels")]))

_E2_SERVING = ("model.py", "discovery_adapter.py", "live_source_dbx.py")
_E1_GLUE = ("inprocess_engines.py", "inmemory_store.py", "timing.py")


def _copy_py(src, dst):
    os.makedirs(dst, exist_ok=True)
    for fn in os.listdir(src):
        if fn.endswith(".py") and not fn.startswith("test_"):
            shutil.copy(os.path.join(src, fn), dst)


def _stage():
    s = tempfile.mkdtemp(prefix="discovery_collapse_")
    for fn in _E2_SERVING:                                    # E2 serving (flat)
        shutil.copy(os.path.join(_HERE, fn), s)
    for fn in _E1_GLUE:                                       # E1 serving glue (flat)
        shutil.copy(os.path.join(_E1_SERVING, fn), s)
    shutil.copy(os.path.join(_E1, "vector_search", "vs_store.py"), s)

    _copy_py(os.path.join(_E1_ENG, "router_src"), os.path.join(s, "router_src"))
    _copy_py(os.path.join(_E1_ENG, "vector", "pipeline"), os.path.join(s, "vector", "pipeline"))
    _copy_py(os.path.join(_E1_ENG, "graph_src"), os.path.join(s, "graph_src"))

    # E2 engine — keep the package path so `import discovery_api.src.*` resolves in the bundle.
    shutil.copytree(os.path.join(_DISC_ROOT, "src"), os.path.join(s, "discovery_api", "src"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test_*"))

    # Qwen parquet for E1's in-memory matrix/BM25 — staged from a Volume, under the name inmemory_store
    # discovers via the pipeline DATA_DIR (vector/data_v2). Content is Qwen; the legacy filename is what
    # the discovery glob expects.
    data_dst = os.path.join(s, "vector", "data_v2")
    os.makedirs(data_dst, exist_ok=True)
    pq = os.getenv("EMBEDDINGS_PARQUET_SRC",
                   "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen.parquet")
    shutil.copy(pq, os.path.join(data_dst, "embeddings_voyage_57k.parquet"))
    print(f"staged parquet from {pq}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        with mlflow.start_run(run_name="discovery-api-collapsed"):
            info = mlflow.pyfunc.log_model(
                artifact_path="discovery",
                python_model=os.path.join(s, "model.py"),
                code_paths=[
                    os.path.join(s, "discovery_adapter.py"),
                    os.path.join(s, "live_source_dbx.py"),
                    os.path.join(s, "inprocess_engines.py"),
                    os.path.join(s, "inmemory_store.py"),
                    os.path.join(s, "timing.py"),
                    os.path.join(s, "vs_store.py"),
                    os.path.join(s, "router_src"),
                    os.path.join(s, "vector"),                # pipeline/*.py + data_v2/<parquet>
                    os.path.join(s, "graph_src"),
                    os.path.join(s, "discovery_api"),         # discovery_api/src
                ],
                signature=_SIGNATURE,
                pip_requirements=os.path.join(_HERE, "requirements.txt"),
                registered_model_name=MODEL_NAME,
            )
        print(f"Logged + registered new version of {MODEL_NAME}")
        if info is not None and getattr(info, "model_uri", None):   # log_model returns None on some MLflow versions
            print(f"  model_uri: {info.model_uri}")
        print("Next: create/repoint the discovery-api-staging endpoint with the env block, then smoke-test.")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
