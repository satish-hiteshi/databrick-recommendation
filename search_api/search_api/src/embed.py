"""Qwen query-embed — REUSE of the existing deploy embedder (scripts/e1_testset_qwen.py pattern).

Query -> qwen3-embedding-0-6b (Databricks serving endpoint, instruction-prefixed, Qwen's native query
convention) -> 1024-d vector. Creds (DATABRICKS_TOKEN + QWEN_EMBED_ENDPOINT) come from shared/vector/.env,
exactly as E1 reads them. We do NOT re-embed the corpus and do NOT change the vector store — this is the
QUERY side only. Cached per-process. If the endpoint is unconfigured/unreachable, raise EmbedUnavailable so
the engine can degrade thematic gracefully (and log it) rather than crash the service.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from . import config


class EmbedUnavailable(RuntimeError):
    """Raised when the Qwen query-embed endpoint is missing creds or unreachable."""


class QwenQueryEmbedder:
    def __init__(self) -> None:
        # load DATABRICKS_TOKEN + QWEN_EMBED_ENDPOINT from shared/vector/.env (same file E1 uses)
        try:
            from dotenv import load_dotenv
            load_dotenv(config.QWEN_ENV_FILE)
        except Exception:
            pass
        self._url: Optional[str] = os.getenv("QWEN_EMBED_ENDPOINT")
        self._tok: Optional[str] = os.getenv("DATABRICKS_TOKEN")
        self._cache: dict = {}
        self.available = bool(self._url and self._tok and "qwen" in (self._url or "").lower())

    def embed(self, query: str) -> np.ndarray:
        if not self.available:
            raise EmbedUnavailable(
                "QWEN_EMBED_ENDPOINT / DATABRICKS_TOKEN not configured in shared/vector/.env")
        q = (query or "").strip()
        if q in self._cache:
            return self._cache[q]
        import time
        import httpx
        # Retry-with-validation. A transient bad response — a non-200, a malformed body, OR a non-finite /
        # degenerate embedding — is RE-FETCHED. A degenerate vector poisons cosine → NaN score → the
        # Databricks serving layer rejects the whole response with a 400 ("Out of range float values are not
        # JSON compliant"). Most of these failures are transient (embed endpoint cold-start / scale-to-zero),
        # so a retry returns a good vector and the query gets its REAL thematic result. Only after every
        # attempt fails do we degrade thematic gracefully (EmbedUnavailable → empty) — never a 400.
        attempts = getattr(config, "QWEN_EMBED_RETRIES", 3)
        last = "?"
        for i in range(attempts):
            try:
                r = httpx.post(self._url, json={"input": [config.QWEN_INSTRUCTION + q]},
                               headers={"Authorization": f"Bearer {self._tok}"},
                               timeout=config.QWEN_EMBED_TIMEOUT)
                r.raise_for_status()
                v = np.asarray(r.json()["data"][0]["embedding"], dtype=np.float32)
                norm = float(np.linalg.norm(v))
                if v.size and np.all(np.isfinite(v)) and norm >= 1e-6:      # good vector → done
                    v = v / (norm + 1e-9)
                    self._cache[q] = v
                    return v
                last = f"non-finite/degenerate vector (norm={norm:.3g})"     # bad vector → retry
            except Exception as e:                                          # network / auth / shape → retry
                last = f"{type(e).__name__}: {e}"
            if i < attempts - 1:
                time.sleep(0.4 * (i + 1))                                   # brief backoff before re-fetch
        raise EmbedUnavailable(f"Qwen embed failed after {attempts} attempts for {q!r}: {last}")
