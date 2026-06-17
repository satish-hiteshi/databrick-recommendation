"""
Query embedding via a Databricks Qwen serving endpoint (OpenAI-compatible llm/v1/embeddings).
Only the query-time function is needed here; bulk entity embeddings are precomputed
(embeddings_v2.npy, loaded by notebook 02_load_entity_data.py).
"""

from pipeline.config import EMBEDDING_ENDPOINT

# Session-level cache so repeated identical queries don't hit the endpoint
_query_cache: dict = {}
_client = None


def _get_client():
    global _client
    if _client is None:
        from mlflow.deployments import get_deploy_client  # type: ignore[import-untyped]
        _client = get_deploy_client("databricks")
    return _client


def embed_query_text(text: str) -> list:
    """
    Embed a query string using the Qwen endpoint (qwen3-embedding-0-6b).
    Returns a plain Python list of floats.
    Results are cached in memory for the duration of the model serving session.
    """
    if text in _query_cache:
        return _query_cache[text]

    response = _get_client().predict(endpoint=EMBEDDING_ENDPOINT, inputs={"input": [text]})
    vec = response["data"][0]["embedding"]
    _query_cache[text] = vec
    return vec
