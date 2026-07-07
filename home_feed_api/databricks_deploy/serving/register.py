"""register.py — log Endpoint 3 (home-feed) as a NEW UC model with the E3 engine bundled.

models-from-code: model.py is the pyfunc; code_paths bundle:
  • home_feed/         the E3 engine (home_feed/src — reads follows from Silver, moments from Aura,
                       vectors from the parquet; LiveFollowSource implemented, carousels stubbed)
  • _e2/               a MINIMAL vendored copy of E2 (discovery_api/src {config,timeutil}) for the reuse seam
  • vector/data_v2/<parquet>   the Qwen 44k parquet, staged from a Volume (VectorStore reads it)

E3 is SELF-CONTAINED at serve time — no E1/E2 HTTP substrate, no inprocess engines.

Run in a notebook:
    import os, sys
    os.environ["UC_MODEL_NAME"] = "stg_feeds_silver.ml.home-feed-staging"
    os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet"
    sys.path.insert(0, "<repo>/home_feed_api/databricks_deploy/serving"); import register; register.main()
"""

import os
import shutil
import tempfile

import mlflow
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import ColSpec, Schema

try:                                         # UC needs outputs; the feed is a nested JSON object → AnyType
    from mlflow.types.schema import AnyType
    _RT = AnyType()
    _HAS_ANYTYPE = True
except ImportError:
    _RT = "string"
    _HAS_ANYTYPE = False

MODEL_NAME = os.getenv("UC_MODEL_NAME", "stg_feeds_silver.ml.home-feed-staging")

_HERE = os.path.dirname(os.path.abspath(__file__))            # home_feed_api/databricks_deploy/serving
_E3_ROOT = os.path.dirname(os.path.dirname(_HERE))            # home_feed_api/
_REPO = os.path.dirname(_E3_ROOT)                             # repo root (for the shared otel_setup fallback)


def _optional_col(dtype, name):
    try:
        return ColSpec(dtype, name, required=False)
    except TypeError:
        return None


_INPUT_COLS = [ColSpec("long", "user_id")]
_OPTIONAL = [("string", "sort_order"), ("string", "time_window"),
             ("long", "limit"), ("long", "offset"), ("boolean", "debug")]
if _HAS_ANYTYPE:
    _OPTIONAL += [(_RT, "seen_ids"), (_RT, "done_ids"), (_RT, "dismissed_property_ids"),
                  (_RT, "blocked_property_ids"), (_RT, "reacted_moment_ids")]
for _d, _n in _OPTIONAL:
    _c = _optional_col(_d, _n)
    if _c is not None:
        _INPUT_COLS.append(_c)

_SIGNATURE = ModelSignature(
    inputs=Schema(_INPUT_COLS),
    outputs=Schema([ColSpec(_RT, "context"), ColSpec(_RT, "main_feed"),
                    ColSpec(_RT, "carousels"), ColSpec(_RT, "pagination")]))


def _stage():
    s = tempfile.mkdtemp(prefix="home_feed_e3_")
    shutil.copy(os.path.join(_HERE, "model.py"), s)
    # otel_setup: prefer the vendored copy beside model.py; fall back to E1's serving copy
    for cand in (os.path.join(_HERE, "otel_setup.py"),
                 os.path.join(_REPO, "databricks_deploy", "serving", "otel_setup.py")):
        if os.path.isfile(cand):
            shutil.copy(cand, s)
            break

    # engine trees (as-is)
    shutil.copytree(os.path.join(_E3_ROOT, "home_feed"), os.path.join(s, "home_feed"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(os.path.join(_E3_ROOT, "_e2"), os.path.join(s, "_e2"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # Qwen parquet staged from a Volume -> vector/data_v2 (model._bootstrap sets HOME_VECTOR_PARQUET to it)
    vec = os.path.join(s, "vector", "data_v2")
    os.makedirs(vec, exist_ok=True)
    pq = os.getenv("EMBEDDINGS_PARQUET_SRC",
                   "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet")
    shutil.copy(pq, os.path.join(vec, "embeddings.parquet"))
    print(f"staged parquet: {pq}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        code_paths = [os.path.join(s, "home_feed"), os.path.join(s, "_e2"), os.path.join(s, "vector")]
        if os.path.isfile(os.path.join(s, "otel_setup.py")):
            code_paths.append(os.path.join(s, "otel_setup.py"))
        with mlflow.start_run(run_name="home-feed-e3"):
            info = mlflow.pyfunc.log_model(
                artifact_path="home_feed",
                python_model=os.path.join(s, "model.py"),
                code_paths=code_paths,
                signature=_SIGNATURE,
                pip_requirements=os.path.join(_HERE, "requirements.txt"),
                registered_model_name=MODEL_NAME,
            )
        print(f"Logged + registered new version of {MODEL_NAME}")
        if info is not None and getattr(info, "model_uri", None):
            print(f"  model_uri: {info.model_uri}")
        print("Next: create/repoint the home-feed endpoint with the env block, then smoke-test.")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
