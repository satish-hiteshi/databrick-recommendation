"""register.py — log the UC8 Onboarding Boost endpoint as a NEW UC model.

models-from-code: model.py is the pyfunc; code_paths bundle the FLAT engine modules + the parquet:
  • data.py / gaps.py / vector_store.py / store.py / api.py / ui.py   the boost engine (data.py has an
        env-gated Silver signals path via the injected query_fn; serving uses the memory backend)
  • vector/data_v2/<parquet>      the Qwen 44k doc-vector parquet, staged from a Volume (data.py reads it)
  • otel_setup.py                 best-effort OTLP telemetry

Self-contained at serve time — embeddings from the parquet, signals from Silver via the injected
databricks-sql query_fn (BOOST_DATA_SOURCE=live), follows stateless.

Run in a notebook:
    import os, sys
    os.environ["UC_MODEL_NAME"] = "stg_feeds_silver.ml.onboarding-boost-staging"
    os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen.parquet"
    sys.path.insert(0, "<repo>/onboarding_boost_v2/databricks_deploy/serving"); import register; register.main()
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

MODEL_NAME = os.getenv("UC_MODEL_NAME", "stg_feeds_silver.ml.onboarding-boost-staging")

_HERE = os.path.dirname(os.path.abspath(__file__))            # onboarding_boost_v2/databricks_deploy/serving
_BUNDLE = os.path.dirname(os.path.dirname(_HERE))             # onboarding_boost_v2/
_SRC = os.path.join(_BUNDLE, "src")                           # engine
_REPO = os.path.dirname(_BUNDLE)                              # notebooks root (shared otel_setup fallback)

_ENGINE_MODULES = ("data.py", "gaps.py", "vector_store.py")   # serving path (no FastAPI/store — stateless, memory backend)


def _optional_col(dtype, name):
    try:
        return ColSpec(dtype, name, required=False)
    except TypeError:
        return None


_INPUT_COLS = [ColSpec("string", "session_id")]
_OPTIONAL = [("string", "op"), ("string", "action"), ("string", "user_id"), ("boolean", "debug")]
if _HAS_ANYTYPE:
    _OPTIONAL += [(_RT, "followed_property_ids"), (_RT, "offered_property_ids"),
                  (_RT, "exclude_ids"), (_RT, "exclude_verticals")]
for _d, _n in _OPTIONAL:
    _c = _optional_col(_d, _n)
    if _c is not None:
        _INPUT_COLS.append(_c)

_SIGNATURE = ModelSignature(
    inputs=Schema(_INPUT_COLS),
    outputs=Schema([ColSpec(_RT, "endpoint"), ColSpec(_RT, "session_id"), ColSpec(_RT, "context"),
                    ColSpec(_RT, "boost_payload"), ColSpec(_RT, "generated_at")]))


def _stage():
    s = tempfile.mkdtemp(prefix="onboarding_boost_")
    shutil.copy(os.path.join(_HERE, "model.py"), s)
    for cand in (os.path.join(_HERE, "otel_setup.py"),
                 os.path.join(_REPO, "databricks_deploy", "serving", "otel_setup.py")):
        if os.path.isfile(cand):
            shutil.copy(cand, s)
            break

    # FLAT engine modules (they import each other as `from data import ...` / `import gaps`) — stage as files
    for mod in _ENGINE_MODULES:
        src = os.path.join(_SRC, mod)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(s, mod))

    # Qwen parquet staged from a Volume -> vector/data_v2 (model._bootstrap sets BOOST_PARQUET to it)
    vec = os.path.join(s, "vector", "data_v2")
    os.makedirs(vec, exist_ok=True)
    pq = os.getenv("EMBEDDINGS_PARQUET_SRC",
                   "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen.parquet")
    shutil.copy(pq, os.path.join(vec, os.path.basename(pq)))
    print(f"staged parquet: {pq}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        code_paths = [os.path.join(s, m) for m in _ENGINE_MODULES if os.path.isfile(os.path.join(s, m))]
        code_paths.append(os.path.join(s, "vector"))
        if os.path.isfile(os.path.join(s, "otel_setup.py")):
            code_paths.append(os.path.join(s, "otel_setup.py"))
        with mlflow.start_run(run_name="onboarding-boost"):
            info = mlflow.pyfunc.log_model(
                artifact_path="onboarding_boost",
                python_model=os.path.join(s, "model.py"),
                code_paths=code_paths,
                signature=_SIGNATURE,
                pip_requirements=os.path.join(_HERE, "requirements.txt"),
                registered_model_name=MODEL_NAME,
            )
        print(f"Logged + registered new version of {MODEL_NAME}")
        if info is not None and getattr(info, "model_uri", None):
            print(f"  model_uri: {info.model_uri}")
        print("Next: create/repoint the onboarding-boost endpoint with the env block, then smoke-test.")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
