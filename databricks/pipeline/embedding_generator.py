"""
Query embedding via Voyage AI.
Only the query-time functions are needed here; bulk entity embedding generation
is handled by notebook 02_load_entity_data.py.
"""

import numpy as np
import voyageai

from pipeline.config import VOYAGE_API_KEY, VOYAGE_MODEL

# Session-level cache so repeated identical queries don't hit the API
_query_cache: dict = {}


def embed_query_text(text: str) -> list:
    """
    Embed a query string using Voyage voyage-4-large (input_type='query').
    Returns a plain Python list of floats.
    Results are cached in memory for the duration of the model serving session.
    """
    if text in _query_cache:
        return _query_cache[text]

    client = voyageai.Client(api_key=VOYAGE_API_KEY)
    result = client.embed([text], model=VOYAGE_MODEL, input_type="query")
    vec = result.embeddings[0]
    _query_cache[text] = vec
    return vec
