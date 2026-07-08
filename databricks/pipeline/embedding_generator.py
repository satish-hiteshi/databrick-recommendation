"""
Query embedding (legacy — superseded by the Qwen endpoint).
Only the query-time functions are needed here; bulk entity embedding generation
is handled by notebook 02_load_entity_data.py.
"""

import numpy as np


# Session-level cache so repeated identical queries don't hit the API
_query_cache: dict = {}


def embed_query_text(text: str) -> list:
    """
    Legacy query embed — superseded by the Qwen endpoint.
    Returns a plain Python list of floats.
    Results are cached in memory for the duration of the model serving session.
    """
    if text in _query_cache:
        return _query_cache[text]

    raise RuntimeError("document-embedding path removed — corpus embeddings are built by foundation 02 (Qwen); queries use embed_query_text via QUERY_EMBED_ENDPOINT")
    result = None  # unreachable — query path is Qwen (QUERY_EMBED_ENDPOINT)
    vec = result.embeddings[0]
    _query_cache[text] = vec
    return vec
