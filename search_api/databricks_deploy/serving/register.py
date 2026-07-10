"""register.py — log Endpoint 4 (search) as a NEW UC model with the E4 engine bundled.

models-from-code: model.py is the pyfunc; code_paths bundle:
  • search_api/                the E4 engine package (search_api/src — bridge/store/thematic/embed/
                               follows/ranking/…; store+follows have env-gated Silver live paths)
  • vector/data_v2/<parquet>   the Qwen 44k doc-vector parquet, staged from a Volume (thematic reads it)

E4 is SELF-CONTAINED at serve time — no E1/E2/E3 HTTP substrate. store + follows read Silver via the
injected databricks-sql query_fn (SEARCH_DATA_SOURCE=live); bridge reads the Aura :Entity graph.

Run in a notebook:
    import os, sys
    os.environ["UC_MODEL_NAME"] = "stg_feeds_silver.ml.search-staging"
    os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet"
    sys.path.insert(0, "<repo>/search_api/databricks_deploy/serving"); import register; register.main()
"""

import os
import shutil
import tempfile

import mlflow
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import ColSpec, Schema

try:                                         # UC needs outputs; the envelope is a nested JSON object → AnyType
    from mlflow.types.schema import AnyType
    _RT = AnyType()
    _HAS_ANYTYPE = True
except ImportError:
    _RT = "string"
    _HAS_ANYTYPE = False

MODEL_NAME = os.getenv("UC_MODEL_NAME", "stg_feeds_silver.ml.search-staging")

_HERE = os.path.dirname(os.path.abspath(__file__))            # search_api/databricks_deploy/serving
_E4_ROOT = os.path.dirname(os.path.dirname(_HERE))            # search_api/  (the bundle root)
_REPO = os.path.dirname(_E4_ROOT)                             # repo root (for the shared otel_setup fallback)


def _optional_col(dtype, name):
    try:
        return ColSpec(dtype, name, required=False)
    except TypeError:
        return None


_INPUT_COLS = [ColSpec("string", "query")]
_OPTIONAL = [("long", "user_id"), ("string", "session_id"), ("string", "mode"), ("long", "limit"),
             ("boolean", "exclude_followed"), ("string", "source_context"),
             ("boolean", "disambiguation"), ("boolean", "debug")]
if _HAS_ANYTYPE:
    _OPTIONAL += [(_RT, "verticals")]
for _d, _n in _OPTIONAL:
    _c = _optional_col(_d, _n)
    if _c is not None:
        _INPUT_COLS.append(_c)

_SIGNATURE = ModelSignature(
    inputs=Schema(_INPUT_COLS),
    outputs=Schema([ColSpec(_RT, "version"), ColSpec(_RT, "endpoint"), ColSpec(_RT, "results"),
                    ColSpec(_RT, "result_count"), ColSpec(_RT, "has_more"), ColSpec(_RT, "query_echo")]))


def _stage():
    s = tempfile.mkdtemp(prefix="search_e4_")
    shutil.copy(os.path.join(_HERE, "model.py"), s)
    # otel_setup: prefer the vendored copy beside model.py; fall back to E1's serving copy
    for cand in (os.path.join(_HERE, "otel_setup.py"),
                 os.path.join(_REPO, "databricks_deploy", "serving", "otel_setup.py")):
        if os.path.isfile(cand):
            shutil.copy(cand, s)
            break

    # engine trees (as-is)
    shutil.copytree(os.path.join(_E4_ROOT, "search_api"), os.path.join(s, "search_api"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # Qwen parquet staged from a Volume -> vector/data_v2 (model._bootstrap sets SEARCH_VECTOR_PARQUET to it)
    vec = os.path.join(s, "vector", "data_v2")
    os.makedirs(vec, exist_ok=True)
    pq = os.getenv("EMBEDDINGS_PARQUET_SRC",
                   "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet")
    shutil.copy(pq, os.path.join(vec, os.path.basename(pq)))
    print(f"staged parquet: {pq}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        code_paths = [os.path.join(s, "search_api"), os.path.join(s, "vector")]
        if os.path.isfile(os.path.join(s, "otel_setup.py")):
            code_paths.append(os.path.join(s, "otel_setup.py"))
        with mlflow.start_run(run_name="search-e4"):
            info = mlflow.pyfunc.log_model(
                artifact_path="search",
                python_model=os.path.join(s, "model.py"),
                code_paths=code_paths,
                signature=_SIGNATURE,
                pip_requirements=os.path.join(_HERE, "requirements.txt"),
                registered_model_name=MODEL_NAME,
            )
        print(f"Logged + registered new version of {MODEL_NAME}")
        if info is not None and getattr(info, "model_uri", None):
            print(f"  model_uri: {info.model_uri}")
        print("Next: create/repoint the search endpoint with the env block, then smoke-test.")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
