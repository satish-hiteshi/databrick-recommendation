"""vector_store.py — pluggable vector backend for boost candidate retrieval.

The boost logic (gaps / blend / gates / cardinality) is backend-agnostic: it only asks the store for a
taste vector and for the nearest ACTIVE candidates in a vertical. Swapping the backend is a config change
(BOOST_VECTOR_BACKEND), not a logic change — same interface everywhere (local Qdrant now, Databricks
Vector Search later).

Backends:
  memory  — in-RAM numpy over property_vectors embeddings (exact parity / offline fallback; embeddings in RAM)
  qdrant  — Qdrant ANN. Embeddings live IN Qdrant (not the app's RAM) -> scalable + fast startup.
            Local: embedded on-disk mode (no Docker) via QDRANT_PATH, or a server via QDRANT_URL.

Interface (both backends) — seeds + exclude are UNAMBIGUOUS ROW indices (twin-correct for the ~321 collisions):
  taste_vector(seed_rows)                                              -> np.ndarray | None   (L2-norm centroid)
  candidates(taste_vec, vertical, richness_floor, exclude, seed_rows)  -> list[(pid, row, cosine, nseed_row)]
        active props in vertical, nearest-to-taste first. "active" = moment_count > 0 AND richness >= floor.
"""
import hashlib
import os
import sys

import numpy as np

# repo root on sys.path so the FROZEN shared.identity is importable (used for the guid->entity_id fallback
# when mapping a runtime pid to its collision-safe Qdrant point id).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

CANDIDATE_K = int(os.environ.get("BOOST_CANDIDATE_K", "500"))   # top-K retrieved per vertical (then blend-reranked)
COLLECTION = os.environ.get("QDRANT_COLLECTION", "boost_properties")


# ── COLLISION-SAFE Qdrant point id (post-migration) ─────────────────────────────────────────────
# The OLD scheme used the bare guid as the point id (`PointStruct(id=int(guid))`). A guid is unique only
# WITHIN a vertical, so the ~321 guids that collide across verticals (Game:119163 vs Movie:119163) mapped
# to the SAME point -> last upsert won -> one entity's embedding was silently lost. We now derive the point
# id from the FULL entity_id ("<Prefix>:<guid>"), which is globally unique, via a deterministic 63-bit
# blake2b digest (stable across processes/runs; positive-signed so it is a valid Qdrant unsigned id).
# Identity is ALSO written to the payload (entity_id/profile_key/media_source_guid), so a returned point
# reconstructs its bare-guid pid (the runtime key) without reversing the hash.
def qdrant_point_id(entity_id: str) -> int:
    h = hashlib.blake2b(str(entity_id).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") & ((1 << 63) - 1)

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

    def taste_vector(self, seed_rows):
        # seed_rows are UNAMBIGUOUS row indices -> read each seed's OWN embedding (twin-correct centroid).
        vs = [self.data.emb[r] for r in (seed_rows or []) if r is not None and 0 <= r < self.data.emb.shape[0]]
        return _norm(np.mean(vs, axis=0)) if vs else None

    def candidates(self, taste_vec, vertical, richness_floor, exclude, seed_rows=None):
        if _retrieval_mode() == "max_any_seed" and seed_rows:
            return self._candidates_max_any(seed_rows, vertical, richness_floor, exclude)
        d = self.data
        if taste_vec is None:
            cos_all = np.zeros(len(d.pids), dtype=np.float32)
        else:
            cos_all = d.emb @ taste_vec.astype(np.float32)
        out = []
        for row, pid in enumerate(d.pids):
            if d.row_meta(row).get("vertical") != vertical:      # row-aligned meta -> twin-correct vertical
                continue
            if row in exclude:                                   # exclude = ROWS (twin-correct)
                continue
            if int(d.moment_count[row]) <= 0 or float(d.richness[row]) < richness_floor:
                continue
            out.append((pid, row, float(cos_all[row]), None))    # (pid, ROW, cosine, nearest-seed ROW|None)
        out.sort(key=lambda t: t[2], reverse=True)
        return out

    def _candidates_max_any(self, seed_rows, vertical, richness_floor, exclude):
        """max_any_seed (memory parity): per-seed top-M within the gated vertical, merged as max-to-any.
        seeds + exclude + the returned nearest-seed are ROWS (twin-correct). Returns (pid, row, max_cos, nseed_row)."""
        d = self.data; M = _per_seed_m()
        srows = [r for r in (seed_rows or []) if r is not None and 0 <= r < d.emb.shape[0]]
        if not srows:
            return []
        gated = np.array([r for r, pid in enumerate(d.pids)
                          if d.row_meta(r).get("vertical") == vertical and r not in exclude
                          and int(d.moment_count[r]) > 0 and float(d.richness[r]) >= richness_floor])
        if gated.size == 0:
            return []
        cos = d.emb[gated] @ d.emb[srows].T                       # (G, S) cosine to each seed
        merged = {}; nearest = {}                                 # ROW -> max cosine ; ROW -> nearest SEED ROW
        for j in range(cos.shape[1]):
            col = cos[:, j]
            for gi in np.argsort(-col)[:M]:
                row = int(gated[gi]); c = float(col[gi])
                if row not in merged or c > merged[row]:         # dedup on ROW -> both twins survive distinctly
                    merged[row] = c; nearest[row] = srows[j]
        return [(d.pids[row], row, merged[row], nearest[row]) for row in merged]


class QdrantStore:
    """Qdrant ANN. Embeddings live in Qdrant; the app holds only small signal arrays. Scalable path.

    POST-MIGRATION: point ids are the collision-safe :func:`qdrant_point_id` (a digest of the FULL
    entity_id), NOT the bare guid. The runtime still keys on the bare guid (pid), so this store maps
    pid -> point_id on the way IN (seed retrieve, exclude) using ``data.meta[pid].entity_id``, and maps
    point payload -> pid on the way OUT (``media_source_guid``, numeric for properties). ``data`` is
    therefore required; ``get_store`` passes it."""

    name = "qdrant"

    def __init__(self, client, data, collection=COLLECTION, k=CANDIDATE_K):
        self.client = client
        self.data = data
        self.collection = collection
        self.k = k

    def _point_id(self, pid):
        """Runtime bare-guid pid -> Qdrant point id (via the row's entity_id). None if unknown."""
        m = self.data.meta.get(pid) if self.data is not None else None
        eid = (m or {}).get("entity_id")
        if eid:
            return qdrant_point_id(eid)
        vert = (m or {}).get("vertical")
        if vert:                                             # fall back to building the entity_id
            from shared.identity import make_entity_id
            return qdrant_point_id(make_entity_id(vert, pid))
        return None

    def _pids_to_point_ids(self, pids):
        out = []
        for p in (pids or []):
            q = self._point_id(p)
            if q is not None:
                out.append(q)
        return out

    def _point_id_from_row(self, row):
        """Served ROW -> Qdrant point id via the row's OWN entity_id (twin-correct). None if unknown."""
        m = self.data.row_meta(row) if self.data is not None else {}
        eid = (m or {}).get("entity_id")
        if eid:
            return qdrant_point_id(eid)
        vert = (m or {}).get("vertical")
        if vert:                                             # fall back to building the entity_id from the row
            from shared.identity import make_entity_id
            return qdrant_point_id(make_entity_id(vert, self.data.pids[row]))
        return None

    def _rows_to_point_ids(self, rows):
        out = []
        for r in (rows or []):
            q = self._point_id_from_row(r)
            if q is not None:
                out.append(q)
        return out

    def _pid_row_from_payload(self, payload):
        """Qdrant payload -> (runtime bare-guid pid, UNAMBIGUOUS row). Prefers entity_id -> row_by_eid
        (collision-safe: the ~321 twins resolve to their OWN row); pid from media_source_guid (numeric).
        Falls back to the bare-pid row when the payload has no entity_id (legacy collection)."""
        if not payload:
            return None, None
        eid = payload.get("entity_id")
        row = self.data.row_by_eid.get(str(eid)) if eid else None
        g = payload.get("media_source_guid")
        try:
            pid = int(g) if g is not None else None
        except (TypeError, ValueError):
            pid = None
        if row is None and pid is not None:                      # legacy payload w/o entity_id -> pid fallback
            row = self.data.row_by_pid.get(pid)
        if pid is None and row is not None:
            pid = self.data.pids[row]
        return pid, row

    def taste_vector(self, seed_rows):
        if not seed_rows:
            return None
        recs = self.client.retrieve(self.collection, ids=self._rows_to_point_ids(seed_rows),
                                    with_vectors=True)      # per-row point ids -> twin-correct seed vectors
        vs = [np.asarray(r.vector, dtype=np.float32) for r in recs if r.vector is not None]
        return _norm(np.mean(vs, axis=0)) if vs else None

    def candidates(self, taste_vec, vertical, richness_floor, exclude, seed_rows=None):
        from qdrant_client.models import (Filter, FieldCondition, MatchValue, Range, HasIdCondition)
        if _retrieval_mode() == "max_any_seed" and seed_rows:
            return self._candidates_max_any(seed_rows, vertical, richness_floor, exclude)
        if taste_vec is None:
            return []
        excl_points = self._rows_to_point_ids(exclude)       # exclude = ROWS -> exact-twin point ids
        flt = Filter(
            must=[FieldCondition(key="vertical", match=MatchValue(value=vertical)),
                  FieldCondition(key="moment_count", range=Range(gt=0)),
                  FieldCondition(key="richness", range=Range(gte=richness_floor))],
            must_not=[HasIdCondition(has_id=excl_points)] if excl_points else None,
        )
        # with_payload=True so we can map the collision-safe point id back to the runtime bare-guid pid
        res = self.client.query_points(self.collection, query=taste_vec.tolist(), query_filter=flt,
                                       limit=self.k, with_payload=True, with_vectors=False).points
        out = []
        for p in res:
            pid, row = self._pid_row_from_payload(p.payload)
            if pid is not None and row is not None:
                out.append((pid, row, float(p.score), None))     # (pid, ROW, cosine, nearest-seed pid|None)
        return out

    def _candidates_max_any(self, seed_rows, vertical, richness_floor, exclude):
        """max_any_seed retrieval: N per-seed top-M ANN queries (same server-side filters), merged as a
        union with relevance = MAX cosine to ANY seed. NOT a centroid — genuine seed-shaped retrieval.
        seeds + exclude + the returned nearest-seed are ROWS (twin-correct). Returns (pid, row, max_cos, nseed_row)."""
        from qdrant_client.models import (Filter, FieldCondition, MatchValue, Range, HasIdCondition)
        # map seed ROWS -> point ids, retaining the reverse mapping so we can name the nearest seed as a ROW
        seed_point_ids = {self._point_id_from_row(r): r for r in (seed_rows or [])
                          if self._point_id_from_row(r) is not None}
        recs = self.client.retrieve(self.collection, ids=list(seed_point_ids.keys()), with_vectors=True)
        seedvecs = [(r.id, np.asarray(r.vector, dtype=np.float32)) for r in recs if r.vector is not None]
        if not seedvecs:
            return []
        excl_points = self._rows_to_point_ids(exclude)
        flt = Filter(
            must=[FieldCondition(key="vertical", match=MatchValue(value=vertical)),
                  FieldCondition(key="moment_count", range=Range(gt=0)),
                  FieldCondition(key="richness", range=Range(gte=richness_floor))],
            must_not=[HasIdCondition(has_id=excl_points)] if excl_points else None,
        )
        M = _per_seed_m()
        merged = {}; nearest = {}                           # ROW -> MAX cosine to ANY seed ; -> nearest SEED ROW
        for spoint, sv in seedvecs:
            seed_row = seed_point_ids.get(spoint)
            res = self.client.query_points(self.collection, query=sv.tolist(), query_filter=flt,
                                           limit=M, with_payload=True, with_vectors=False).points
            for p in res:
                pid, row = self._pid_row_from_payload(p.payload)
                if row is None:
                    continue
                c = float(p.score)
                if row not in merged or c > merged[row]:        # dedup on ROW -> both twins survive distinctly
                    merged[row] = c; nearest[row] = seed_row
        return [(self.data.pids[row], row, merged[row], nearest[row]) for row in merged]


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
        return QdrantStore(client, data)
    except Exception as e:  # pragma: no cover
        print(f"[boost.vs] qdrant unavailable ({str(e)[:90]}) — falling back to MemoryStore", flush=True)
        if data.emb is None:
            raise RuntimeError("qdrant backend failed AND no in-RAM embeddings; load Qdrant or use memory")
        return MemoryStore(data)
