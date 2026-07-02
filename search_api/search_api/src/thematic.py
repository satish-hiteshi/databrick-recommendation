"""Thematic retrieval — in-memory cosine ANN over the 44k Qwen doc vectors, with PER-VERTICAL quotas.

REUSE NOTE: there is NO Qwen-44k Qdrant collection (the shared Qdrant is Voyage/57k — wrong corpus). The
existing in-memory ANN over the Qwen-44k vectors is the brute-force matrix cosine in
scripts/e1_testset_qwen.py (`sims = MAT @ qn`). We reuse that exactly.

v1.3.2 FIX (candidate generation only): a single GLOBAL top-N scan lets one vertical's nearest neighbours
crowd out the others (UC7 Story 3 breadth fails when the query's NN cluster in one vertical). So we retrieve
top-K PER VERTICAL and merge. Implementation: ONE matmul over the full matrix (same cost as the global scan),
then a cheap per-vertical top-K selection over row-indices PRE-GROUPED by vertical at startup — so it is N
small selections, not N matmuls. Each entity lives in exactly one vertical, so the merged pool is disjoint
(no cross-vertical dup). Scoring/fairness/name-path are untouched; this only widens the candidate set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pyarrow.parquet as pq

from . import config


@dataclass(slots=True)
class ThematicHit:
    entity_id: str
    name: str
    vertical: str
    cosine: float


class ThematicIndex:
    def __init__(self, parquet_path: Optional[str] = None) -> None:
        self.path = parquet_path or config.VECTOR_PARQUET
        self._loaded = False
        self._mat: Optional[np.ndarray] = None
        self.entity_ids: List[str] = []
        self.names: List[str] = []
        self.verticals: List[str] = []
        self._vert_idx: Dict[str, np.ndarray] = {}      # vertical → row indices (pre-grouped at startup)

    def load(self) -> "ThematicIndex":
        if self._loaded:
            return self
        t = pq.read_table(self.path, columns=["entity_id", "name", "vertical", "embedding"])
        n = t.num_rows
        self.entity_ids = [str(x) for x in t.column("entity_id").to_pylist()]
        self.names = [x if x is not None else "" for x in t.column("name").to_pylist()]
        self.verticals = [str(x).lower() for x in t.column("vertical").to_pylist()]
        mat = (t.column("embedding").combine_chunks().flatten().to_numpy(zero_copy_only=False)
               .reshape(n, -1).astype(np.float32))
        self._mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        grouped: Dict[str, List[int]] = {}
        for i, v in enumerate(self.verticals):
            grouped.setdefault(v, []).append(i)
        self._vert_idx = {v: np.asarray(ix, dtype=np.int64) for v, ix in grouped.items()}
        self._loaded = True
        return self

    @property
    def size(self) -> int:
        return len(self.entity_ids)

    @property
    def verticals_present(self) -> List[str]:
        return sorted(self._vert_idx.keys())

    def _topk_in(self, sims: np.ndarray, idx: np.ndarray, k: int) -> np.ndarray:
        """Global row-indices of the top-k cosines among `idx` (argpartition + local sort; O(|idx|))."""
        k = min(k, len(idx))
        if k <= 0:
            return np.empty(0, dtype=np.int64)
        s = sims[idx]
        part = np.argpartition(s, -k)[-k:]
        return idx[part[np.argsort(s[part])[::-1]]]

    def search(self, qvec: np.ndarray, verticals: Optional[Sequence[str]] = None,
               k_per_vertical: int = None) -> List[ThematicHit]:
        """Per-vertical top-K (quota), merged. Respects the `verticals` filter (else all four). One matmul."""
        if self._mat is None:
            self.load()
        k = k_per_vertical or config.THEMATIC_K_PER_VERTICAL
        sims = self._mat @ qvec.astype(np.float32)                       # ONE matmul over the full matrix
        targets = [v.lower() for v in verticals] if verticals else list(self._vert_idx.keys())
        rows: List[int] = []
        for v in targets:
            idx = self._vert_idx.get(v)
            if idx is None or len(idx) == 0:
                continue
            rows.extend(int(i) for i in self._topk_in(sims, idx, k))    # per-vertical quota
        rows.sort(key=lambda i: sims[i], reverse=True)                   # global desc for min-max + display
        return [ThematicHit(entity_id=self.entity_ids[i], name=self.names[i], vertical=self.verticals[i],
                            cosine=float(sims[i])) for i in rows]
