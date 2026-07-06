"""vector_store.py — pluggable vector backend for boost candidate retrieval.

The boost logic (gaps / blend / gates / cardinality) is backend-agnostic: it only asks the store for a
taste vector and for the nearest ACTIVE candidates in a vertical. Swapping the backend is a config change
(BOOST_VECTOR_BACKEND), not a logic change — same interface everywhere (local Qdrant now, Databricks
Vector Search later).

Backends:
  memory  — in-RAM numpy over property_vectors embeddings (exact parity / offline fallback; embeddings in RAM)
  qdrant  — Qdrant ANN. Embeddings live IN Qdrant (not the app's RAM) -> scalable + fast startup.
            Local: embedded on-disk mode (no Docker) via QDRANT_PATH, or a server via QDRANT_URL.

Interface (both backends):
  taste_vector(seed_pids)                                   -> np.ndarray | None   (L2-normalized centroid)
  candidates(taste_vec, vertical, richness_floor, exclude)  -> list[(pid, cosine)]  active props in vertical,
        nearest-to-taste first. "active" = moment_count > 0 AND richness >= richness_floor.
"""
import os

import numpy as np

CANDIDATE_K = int(os.environ.get("BOOST_CANDIDATE_K", "500"))   # top-K retrieved per vertical (then blend-reranked)
COLLECTION = os.environ.get("QDRANT_COLLECTION", "boost_properties")


def _norm(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


class MemoryStore:
    """Numpy brute-force over property_vectors embeddings held in RAM (data.emb). Exact-parity backend."""

    name = "memory"

    def __init__(self, data):
        self.data = data
        if data.emb is None:
            raise RuntimeError("MemoryStore needs embeddings in RAM — set BOOST_VECTOR_BACKEND=memory")

    def taste_vector(self, seed_pids):
        vs = [self.data.emb[self.data.row_by_pid[p]] for p in seed_pids if p in self.data.row_by_pid]
        return _norm(np.mean(vs, axis=0)) if vs else None

    def candidates(self, taste_vec, vertical, richness_floor, exclude):
        d = self.data
        if taste_vec is None:
            cos_all = np.zeros(len(d.pids), dtype=np.float32)
        else:
            cos_all = d.emb @ taste_vec.astype(np.float32)
        out = []
        for row, pid in enumerate(d.pids):
            if d.meta[pid].get("vertical") != vertical:
                continue
            if pid in exclude:
                continue
            if int(d.moment_count[row]) <= 0 or float(d.richness[row]) < richness_floor:
                continue
            out.append((pid, float(cos_all[row])))
        out.sort(key=lambda t: t[1], reverse=True)
        return out


class QdrantStore:
    """Qdrant ANN. Embeddings live in Qdrant; the app holds only small signal arrays. Scalable path."""

    name = "qdrant"

    def __init__(self, client, collection=COLLECTION, k=CANDIDATE_K):
        self.client = client
        self.collection = collection
        self.k = k

    def taste_vector(self, seed_pids):
        if not seed_pids:
            return None
        recs = self.client.retrieve(self.collection, ids=list(seed_pids), with_vectors=True)
        vs = [np.asarray(r.vector, dtype=np.float32) for r in recs if r.vector is not None]
        return _norm(np.mean(vs, axis=0)) if vs else None

    def candidates(self, taste_vec, vertical, richness_floor, exclude):
        from qdrant_client.models import (Filter, FieldCondition, MatchValue, Range, HasIdCondition)
        if taste_vec is None:
            return []
        flt = Filter(
            must=[FieldCondition(key="vertical", match=MatchValue(value=vertical)),
                  FieldCondition(key="moment_count", range=Range(gt=0)),
                  FieldCondition(key="richness", range=Range(gte=richness_floor))],
            must_not=[HasIdCondition(has_id=list(exclude))] if exclude else None,
        )
        res = self.client.query_points(self.collection, query=taste_vec.tolist(), query_filter=flt,
                                       limit=self.k, with_payload=False, with_vectors=False).points
        return [(p.id, float(p.score)) for p in res]


def get_store(data):
    """Build the store for the configured backend. Falls back to memory if Qdrant is unreachable."""
    backend = os.environ.get("BOOST_VECTOR_BACKEND", "qdrant").lower()
    if backend == "memory":
        return MemoryStore(data)
    try:
        from qdrant_client import QdrantClient
        url = os.environ.get("QDRANT_URL")
        if url:
            client = QdrantClient(url=url, timeout=30)
        else:
            path = os.environ.get("QDRANT_PATH",
                                  os.path.join(os.path.dirname(os.path.dirname(__file__)), "qdrant_data"))
            client = QdrantClient(path=path)
        client.get_collection(COLLECTION)          # verify the collection exists / is reachable
        return QdrantStore(client)
    except Exception as e:  # pragma: no cover
        print(f"[boost.vs] qdrant unavailable ({str(e)[:90]}) — falling back to MemoryStore", flush=True)
        if data.emb is None:
            raise RuntimeError("qdrant backend failed AND no in-RAM embeddings; load Qdrant or use memory")
        return MemoryStore(data)
