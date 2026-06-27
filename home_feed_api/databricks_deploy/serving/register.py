"""register.py — log Endpoint 3 (home-feed) as a NEW UC model with the LOCAL engine bundled as-is.

models-from-code: model.py is the pyfunc; code_paths bundle the local home-feed engine unchanged:
  • home_feed/   (home_api + the 4 UC3 modules — byte-identical to dev)
  • discovery/   (the engine: data/store/ranking/carousels/profile/recall/reco/trends — data.py + store.py
                  carry an env-gated Silver branch that is inert unless HOME_DATA_SOURCE=live)
  • vector/data_v2/embeddings_qwen.parquet  (REUSES E1's Qwen parquet from the Volume; guid-keyed, the
                                              loader bridges media_source_guid → property_id)

Unlike Endpoint 2, home-feed is SELF-CONTAINED: its discovery engine owns its embeddings + reads Silver
directly, so it does NOT bundle E1's collapsed substrate (no router_src/vector pipeline/graph_src).

Registers UC_MODEL_NAME. Run in a notebook:
    import os, sys
    os.environ["UC_MODEL_NAME"] = "stg_feeds_silver.ml.home-feed-staging"
    os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet"
    sys.path.insert(0, "<repo>/home_feed_api/databricks_deploy/serving"); import register; register.main()
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
    _HAS_ANYTYPE = True
except ImportError:
    _RT = "string"
    _HAS_ANYTYPE = False

MODEL_NAME = os.getenv("UC_MODEL_NAME", "stg_feeds_silver.ml.home-feed-staging")

_HERE = os.path.dirname(os.path.abspath(__file__))            # home_feed_api/databricks_deploy/serving
_E3_ROOT = os.path.dirname(os.path.dirname(_HERE))            # home_feed_api/
_REPO = os.path.dirname(_E3_ROOT)                             # repo root


def _optional_col(dtype, name):
    try:
        return ColSpec(dtype, name, required=False)
    except TypeError:                         # older MLflow: keep the current non-breaking signature
        return None


_INPUT_COLS = [ColSpec("long", "user_id")]
_OPTIONAL_INPUTS = [
    ("long", "limit"),
    ("long", "offset"),
    ("string", "sort_order"),
    ("string", "time_window"),
    ("boolean", "debug"),
    ("string", "now"),
]
if _HAS_ANYTYPE:
    _OPTIONAL_INPUTS += [
        (_RT, "date_range"),
        (_RT, "seen_ids"),
        (_RT, "done_ids"),
        (_RT, "dismissed_property_ids"),
        (_RT, "blocked_property_ids"),
        (_RT, "user_prefs"),
    ]
for _dtype, _name in _OPTIONAL_INPUTS:
    _col = _optional_col(_dtype, _name)
    if _col is not None:
        _INPUT_COLS.append(_col)

_SIGNATURE = ModelSignature(
    inputs=Schema(_INPUT_COLS),
    outputs=Schema([ColSpec(_RT, "context"), ColSpec(_RT, "main_feed"),
                    ColSpec(_RT, "carousels"), ColSpec(_RT, "pagination")]))


def _stage():
    s = tempfile.mkdtemp(prefix="home_feed_")
    shutil.copy(os.path.join(_HERE, "model.py"), s)
    # best-effort: bundle E1's otel_setup for shared telemetry (optional — model.py degrades if absent)
    e1_otel = os.path.join(_REPO, "databricks_deploy", "serving", "otel_setup.py")
    if os.path.isfile(e1_otel):
        shutil.copy(e1_otel, s)

    # engine trees, vendored as-is (sibling layout preserved so the relative paths in data.py/home_api.py work)
    shutil.copytree(os.path.join(_E3_ROOT, "home_feed"), os.path.join(s, "home_feed"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(os.path.join(_E3_ROOT, "discovery"), os.path.join(s, "discovery"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test_*"))

    # Embeddings parquet staged from a Volume -> vector/data_v2/embeddings_qwen.parquet (the path data.py
    # reads as EMB_PARQUET; VEC_DIR is a sibling of discovery/, so ROOT/vector/data_v2 resolves in the
    # artifact code dir). REUSES E1's Qwen parquet (guid-keyed); data.py bridges guid -> property_id.
    vec = os.path.join(s, "vector", "data_v2")
    os.makedirs(vec, exist_ok=True)
    pq = os.getenv("EMBEDDINGS_PARQUET_SRC",
                   "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet")
    shutil.copy(pq, os.path.join(vec, "embeddings_qwen.parquet"))
    print(f"staged embeddings parquet: {pq}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        code_paths = [os.path.join(s, "home_feed"), os.path.join(s, "discovery"), os.path.join(s, "vector")]
        if os.path.isfile(os.path.join(s, "otel_setup.py")):
            code_paths.append(os.path.join(s, "otel_setup.py"))
        with mlflow.start_run(run_name="home-feed"):
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
        print("Next: create/repoint the home-feed-staging endpoint with the env block, then smoke-test.")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
