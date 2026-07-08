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

# ── Retrieval mode — DEFAULT (no env) = ENHANCED: max_any_seed with M=10 ─────────────────────────
# "max_any_seed" (DEFAULT) = seed-shaped: for EACH seed, top-M ANN in the gap vertical (same server-side
#   filters); MERGE (union/dedup); relevance = MAX cosine to ANY seed. NOT a centroid.
# "centroid"               = the ORIGINAL team baseline: ONE ANN query on the L2-normalized seed CENTROID.
# The single documented fallback flag E8_LEGACY_BASELINE=1 restores the team baseline (centroid) in full.
# The granular E8X_RETRIEVAL_MODE / E8X_PER_SEED_M overrides remain for A/B. Read PER-CALL. The blend math,
# gates, selection, dedup, franchise cap, and caps are UNCHANGED — this only shapes the candidate pool.
def _legacy():
    return os.environ.get("E8_LEGACY_BASELINE", "0") == "1"

def _retrieval_mode():
    m = os.environ.get("E8X_RETRIEVAL_MODE")
    if m is not None:
        return m.lower()                                        # explicit A/B override
    return "centroid" if _legacy() else "max_any_seed"          # DEFAULT (no env) = enhanced

def _per_seed_m():
    return int(os.environ.get("E8X_PER_SEED_M", "10"))          # M = per-seed K for max_any_seed (default 10)


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

    def candidates(self, taste_vec, vertical, richness_floor, exclude, seed_pids=None):
        if _retrieval_mode() == "max_any_seed" and seed_pids:
            return self._candidates_max_any(seed_pids, vertical, richness_floor, exclude)
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
            out.append((pid, float(cos_all[row]), None))         # 3rd elem = nearest-seed pid (None for centroid)
        out.sort(key=lambda t: t[1], reverse=True)
        return out

    def _candidates_max_any(self, seed_pids, vertical, richness_floor, exclude):
        """max_any_seed (memory parity): per-seed top-M within the gated vertical, merged as max-to-any.
        Returns (pid, max_cos, nearest_seed_pid) — the seed giving the winning cosine (for the why_string)."""
        d = self.data; M = _per_seed_m()
        valid_seeds = [p for p in seed_pids if p in d.row_by_pid]
        srows = [d.row_by_pid[p] for p in valid_seeds]
        if not srows:
            return []
        gated = np.array([r for r, pid in enumerate(d.pids)
                          if d.meta[pid].get("vertical") == vertical and pid not in exclude
                          and int(d.moment_count[r]) > 0 and float(d.richness[r]) >= richness_floor])
        if gated.size == 0:
            return []
        cos = d.emb[gated] @ d.emb[srows].T                       # (G, S) cosine to each seed
        merged = {}; nearest = {}                                 # pid -> max cosine ; pid -> argmax seed pid
        for j in range(cos.shape[1]):
            col = cos[:, j]
            for gi in np.argsort(-col)[:M]:
                pid = d.pids[int(gated[gi])]; c = float(col[gi])
                if pid not in merged or c > merged[pid]:
                    merged[pid] = c; nearest[pid] = valid_seeds[j]
        return [(pid, merged[pid], nearest[pid]) for pid in merged]


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

    def candidates(self, taste_vec, vertical, richness_floor, exclude, seed_pids=None):
        from qdrant_client.models import (Filter, FieldCondition, MatchValue, Range, HasIdCondition)
        if _retrieval_mode() == "max_any_seed" and seed_pids:
            return self._candidates_max_any(seed_pids, vertical, richness_floor, exclude)
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
        return [(p.id, float(p.score), None) for p in res]      # 3rd elem = nearest-seed pid (None for centroid)

    def _candidates_max_any(self, seed_pids, vertical, richness_floor, exclude):
        """max_any_seed retrieval: N per-seed top-M ANN queries (same server-side filters), merged as a
        union with relevance = MAX cosine to ANY seed. NOT a centroid — genuine seed-shaped retrieval.
        Returns (pid, max_cos, nearest_seed_pid) — the seed giving the winning cosine (for the why_string)."""
        from qdrant_client.models import (Filter, FieldCondition, MatchValue, Range, HasIdCondition)
        recs = self.client.retrieve(self.collection, ids=list(seed_pids), with_vectors=True)
        seedvecs = [(r.id, np.asarray(r.vector, dtype=np.float32)) for r in recs if r.vector is not None]
        if not seedvecs:
            return []
        flt = Filter(
            must=[FieldCondition(key="vertical", match=MatchValue(value=vertical)),
                  FieldCondition(key="moment_count", range=Range(gt=0)),
                  FieldCondition(key="richness", range=Range(gte=richness_floor))],
            must_not=[HasIdCondition(has_id=list(exclude))] if exclude else None,
        )
        M = _per_seed_m()
        merged = {}; nearest = {}                           # pid -> MAX cosine to ANY seed ; -> argmax seed pid
        for sid, sv in seedvecs:
            res = self.client.query_points(self.collection, query=sv.tolist(), query_filter=flt,
                                           limit=M, with_payload=False, with_vectors=False).points
            for p in res:
                c = float(p.score)
                if p.id not in merged or c > merged[p.id]:
                    merged[p.id] = c; nearest[p.id] = sid
        return [(pid, merged[pid], nearest[pid]) for pid in merged]


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
