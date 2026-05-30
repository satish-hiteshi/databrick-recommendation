"""
Qdrant vector store and BM25 keyword search for Feeds.ai pipeline.
In-memory Qdrant for fast ANN search + rank-bm25 for keyword scoring.
"""

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    Range,
    VectorParams,
)
from rank_bm25 import BM25Okapi
from tqdm import tqdm

from pipeline.config import EMBEDDING_DIMENSION, QDRANT_COLLECTION, TOP_K_RETRIEVAL
from pipeline.data_loader import get_all_entities
from pipeline.embedding_generator import load_embeddings

# Module-level singletons
_client = None
_bm25_index = None
_bm25_entities = None


def get_client():
    """Get or create the in-memory Qdrant client."""
    global _client
    if _client is None:
        _client = QdrantClient(":memory:")
    return _client


def create_collection():
    """Create the Qdrant collection."""
    client = get_client()

    # Recreate collection
    if client.collection_exists(QDRANT_COLLECTION):
        client.delete_collection(QDRANT_COLLECTION)

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=Distance.COSINE,
        ),
    )
    print(f"Qdrant collection '{QDRANT_COLLECTION}' created (dim={EMBEDDING_DIMENSION}, cosine).")


def upload_vectors():
    """Upload all entity vectors to Qdrant."""
    entities = get_all_entities()
    embeddings = load_embeddings()
    if not embeddings:
        raise RuntimeError("No embeddings found. Run embedding_generator.py first.")

    client = get_client()
    points = []

    for idx, e in enumerate(entities):
        eid = e["entity_id"]
        emb = embeddings.get(eid)
        if emb is None:
            continue

        vec = emb.tolist() if isinstance(emb, np.ndarray) else emb
        points.append(PointStruct(
            id=idx,
            vector=vec,
            payload={
                "entity_id": eid,
                "name": e["name"],
                "vertical": e["vertical"],
                "bm25_keywords": e["bm25_keywords"],
                "franchise": e.get("franchise"),
                "composed_text_preview": e["composed_text"][:200],
                "release_date_int": int(e["release_date"].replace("-", "")) if e.get("release_date") else None,
                "release_date": e.get("release_date"),
            },
        ))

    # Upload in batches of 500
    batch_size = 500
    for i in tqdm(range(0, len(points), batch_size), desc="Uploading to Qdrant"):
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points[i : i + batch_size],
        )

    count = client.get_collection(QDRANT_COLLECTION).points_count
    print(f"Uploaded {count} vectors to Qdrant.")
    return count


def vector_search(query_embedding, target_verticals=None, top_k=TOP_K_RETRIEVAL,
                   date_start=None, date_end=None):
    """
    Search Qdrant by embedding vector.
    Returns list of (entity_id, name, vertical, score) tuples.
    """
    client = get_client()

    must_conditions = []
    if target_verticals:
        must_conditions.append(
            FieldCondition(key="vertical", match=MatchAny(any=list(target_verticals)))
        )
    if date_start or date_end:
        ds_int = int(date_start.replace("-", "")) if date_start else None
        de_int = int(date_end.replace("-", "")) if date_end else None
        must_conditions.append(
            FieldCondition(
                key="release_date_int",
                range=Range(gte=ds_int, lte=de_int),
            )
        )

    query_filter = Filter(must=must_conditions) if must_conditions else None

    vec = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vec,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )

    return [
        (hit.payload["entity_id"], hit.payload["name"], hit.payload["vertical"], hit.score)
        for hit in results.points
    ]


def _build_bm25_index():
    """Build the BM25 index from all entity keywords."""
    global _bm25_index, _bm25_entities
    entities = get_all_entities()
    # Tokenize: each entity's keywords lowercased
    corpus = [
        [kw.lower() for kw in e["bm25_keywords"]] for e in entities
    ]
    _bm25_index = BM25Okapi(corpus)
    _bm25_entities = entities


def keyword_search(anchor_keywords, target_verticals=None, top_k=TOP_K_RETRIEVAL,
                    date_start=None, date_end=None):
    """
    BM25 keyword search across all entities.
    anchor_keywords: list of keyword strings from the anchor entity.
    Returns list of (entity_id, name, vertical, bm25_score) tuples.
    """
    if _bm25_index is None:
        _build_bm25_index()

    query_tokens = [kw.lower() for kw in anchor_keywords]
    scores = _bm25_index.get_scores(query_tokens)

    # Pair with entity info and filter
    scored = []
    for idx, score in enumerate(scores):
        e = _bm25_entities[idx]
        if target_verticals and e["vertical"] not in target_verticals:
            continue
        # Date filter on BM25 results
        if date_start or date_end:
            rd = e.get("release_date")
            if not rd:
                continue  # exclude entities without release_date when filter is active
            if date_start and rd < date_start:
                continue
            if date_end and rd > date_end:
                continue
        scored.append((e["entity_id"], e["name"], e["vertical"], float(score)))

    # Sort descending by score, return top_k
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_k]


def setup_qdrant():
    """Run full Qdrant setup: create collection + upload vectors."""
    create_collection()
    count = upload_vectors()
    _build_bm25_index()
    print(f"BM25 index built over {len(_bm25_entities)} entities.")
    print("\nQdrant + BM25 setup complete.")
    return count


if __name__ == "__main__":
    setup_qdrant()
