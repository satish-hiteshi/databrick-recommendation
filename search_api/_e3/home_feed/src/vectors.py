"""Property-vector source — the Qwen parquet (entity_id-keyed, dim 1024).

Step 0 established the vectors are NOT on the graph node and the local setup exposes them via this
parquet (the same file the deploy/E1 stack uses). E2's HTTP vector substrate (:8000) is the WRONG
corpus here (legacy 57k), so E3 reads the parquet directly, read-only. Vectors are stored
L2-normalized so taste cosine is a plain dot product.
"""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pyarrow.parquet as pq

from . import config


class VectorStore:
    def __init__(self, parquet_path: Optional[str] = None):
        self.path = parquet_path or config.VECTOR_PARQUET
        self._vec: Optional[dict] = None
        self._dim: Optional[int] = None

    def _load(self) -> dict:
        if self._vec is not None:
            return self._vec
        t = pq.read_table(self.path, columns=["entity_id", "embedding"])
        ids = [str(x) for x in t.column("entity_id").to_pylist()]
        mat = (t.column("embedding").combine_chunks().flatten().to_numpy(zero_copy_only=False)
               .reshape(len(ids), -1).astype(np.float32))
        mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        self._dim = mat.shape[1]
        self._vec = {eid: mat[i] for i, eid in enumerate(ids)}
        return self._vec

    @property
    def dim(self) -> int:
        self._load(); return self._dim

    def vector_for(self, entity_id: str) -> Optional[np.ndarray]:
        """L2-normalized property vector, or None if this entity has no vector (≈239 graph-only ids)."""
        return self._load().get(str(entity_id))

    def mean_vector(self, entity_ids: Iterable[str]) -> Optional[np.ndarray]:
        """Normalized mean of the available vectors among entity_ids (None if none are present)."""
        vecs = [v for v in (self.vector_for(e) for e in entity_ids) if v is not None]
        if not vecs:
            return None
        m = np.mean(np.stack(vecs), axis=0)
        return m / (np.linalg.norm(m) + 1e-9)
