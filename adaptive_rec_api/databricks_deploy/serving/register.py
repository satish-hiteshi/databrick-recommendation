"""register.py — log the Onboarding Adaptive-Rec endpoint (UC6) as a NEW UC model.

models-from-code: model.py is the pyfunc; code_paths bundle the FLAT engine modules + the parquet:
  • api.py / data.py / store.py   the adaptive-rec engine (byte-identical to the dev branch; data.py has
                                  an env-gated Silver signals path, store.py degrades to in-memory)
  • vector/data_v2/<parquet>      the Qwen 44k doc-vector parquet, staged from a Volume (data.py reads it)
  • otel_setup.py                 best-effort OTLP telemetry

Self-contained at serve time — embeddings from the parquet, the 3 signal tables from Silver via the
injected databricks-sql query_fn (ADAPTIVE_DATA_SOURCE=live), session in-memory (ADAPTIVE_PG=0).

Run in a notebook:
    import os, sys
    os.environ["UC_MODEL_NAME"] = "stg_feeds_silver.ml.onboarding-adaptive-staging"
    os.environ["EMBEDDINGS_PARQUET_SRC"] = "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet"
    sys.path.insert(0, "<repo>/adaptive_rec_api/databricks_deploy/serving"); import register; register.main()
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

MODEL_NAME = os.getenv("UC_MODEL_NAME", "stg_feeds_silver.ml.onboarding-adaptive-staging")

_HERE = os.path.dirname(os.path.abspath(__file__))            # adaptive_rec_api/databricks_deploy/serving
_BUNDLE = os.path.dirname(os.path.dirname(_HERE))             # adaptive_rec_api/
_SRC = os.path.join(_BUNDLE, "src")                           # engine (api/data/store)
_REPO = os.path.dirname(_BUNDLE)                              # repo root (shared otel_setup fallback)


def _optional_col(dtype, name):
    try:
        return ColSpec(dtype, name, required=False)
    except TypeError:
        return None


_INPUT_COLS = [ColSpec("string", "session_id")]
_OPTIONAL = [("double", "confidence_threshold"), ("long", "limit"), ("boolean", "debug")]
if _HAS_ANYTYPE:
    _OPTIONAL += [(_RT, "followed_property_ids"), (_RT, "skipped_property_ids"),
                  (_RT, "exclude_ids"), (_RT, "verticals")]
for _d, _n in _OPTIONAL:
    _c = _optional_col(_d, _n)
    if _c is not None:
        _INPUT_COLS.append(_c)

_SIGNATURE = ModelSignature(
    inputs=Schema(_INPUT_COLS),
    outputs=Schema([ColSpec(_RT, "endpoint"), ColSpec(_RT, "session_id"), ColSpec(_RT, "context"),
                    ColSpec(_RT, "suggestion"), ColSpec(_RT, "generated_at")]))


def _stage():
    s = tempfile.mkdtemp(prefix="adaptive_rec_")
    shutil.copy(os.path.join(_HERE, "model.py"), s)
    for cand in (os.path.join(_HERE, "otel_setup.py"),
                 os.path.join(_REPO, "databricks_deploy", "serving", "otel_setup.py")):
        if os.path.isfile(cand):
            shutil.copy(cand, s)
            break

    # FLAT engine modules (api imports `from data import ...` / `from store import ...`) — stage as files
    for mod in ("api.py", "data.py", "store.py"):
        shutil.copy(os.path.join(_SRC, mod), os.path.join(s, mod))

    # Qwen parquet staged from a Volume -> vector/data_v2 (model._bootstrap sets ADAPTIVE_PARQUET to it)
    vec = os.path.join(s, "vector", "data_v2")
    os.makedirs(vec, exist_ok=True)
    pq = os.getenv("EMBEDDINGS_PARQUET_SRC",
                   "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings_qwen_44k_prefixed.parquet")
    shutil.copy(pq, os.path.join(vec, os.path.basename(pq)))
    print(f"staged parquet: {pq}")
    return s


def main():
    mlflow.set_registry_uri("databricks-uc")
    s = _stage()
    try:
        code_paths = [os.path.join(s, "api.py"), os.path.join(s, "data.py"), os.path.join(s, "store.py"),
                      os.path.join(s, "vector")]
        if os.path.isfile(os.path.join(s, "otel_setup.py")):
            code_paths.append(os.path.join(s, "otel_setup.py"))
        with mlflow.start_run(run_name="onboarding-adaptive"):
            info = mlflow.pyfunc.log_model(
                artifact_path="adaptive_rec",
                python_model=os.path.join(s, "model.py"),
                code_paths=code_paths,
                signature=_SIGNATURE,
                pip_requirements=os.path.join(_HERE, "requirements.txt"),
                registered_model_name=MODEL_NAME,
            )
        print(f"Logged + registered new version of {MODEL_NAME}")
        if info is not None and getattr(info, "model_uri", None):
            print(f"  model_uri: {info.model_uri}")
        print("Next: create/repoint the onboarding-adaptive endpoint with the env block, then smoke-test.")
    finally:
        shutil.rmtree(s, ignore_errors=True)


if __name__ == "__main__":
    main()
