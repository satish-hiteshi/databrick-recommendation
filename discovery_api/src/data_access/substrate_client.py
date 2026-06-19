"""SubstrateClient — thin HTTP wrapper over the SHARED vector (:8000) + graph (:8010) services.

The substrate is REUSED, never duplicated: Endpoint 2 reaches the same vector index + graph as
Endpoint 1 by calling these ports. Mirrors `agent_recs/src/blocks.py`'s `_post` (retry transient 5xx,
honour config timeout). Methods return plain lists of dicts; on hard failure they raise SubstrateError
so a candidate provider can catch it and degrade to an empty pool (the feed must never crash on a
substrate blip — cold-start global pools still work from local CSV signals).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional
from urllib.parse import urlsplit

import httpx

from .. import config


class SubstrateError(RuntimeError):
    """Raised when a substrate call fails after retries (engine should degrade gracefully)."""


def run_concurrent(tasks: Dict[object, Callable[[], object]],
                   max_workers: Optional[int] = None) -> Dict[object, object]:
    """Run {key: zero-arg callable} concurrently on a BOUNDED thread pool; return {key: result}.

    A task raising SubstrateError yields None for that key — the graceful per-call skip the providers
    used to do serially (so behaviour is identical); other exceptions propagate. Keys are unique, so
    a seed requested once runs once (the within-build memoisation/dedup). Each underlying call still
    carries its own per-call HTTP timeout. Result ORDER is the caller's responsibility: callers read
    results[key] in their original seed/vertical order, so the assembled candidate set is byte-identical
    to the old serial path — only wall-time and call concurrency change, never the results."""
    if not tasks:
        return {}
    mw = max_workers if max_workers is not None else config.SUBSTRATE_MAX_WORKERS
    mw = max(1, min(mw, len(tasks)))
    out: Dict[object, object] = {}
    with ThreadPoolExecutor(max_workers=mw) as ex:
        futures = {ex.submit(fn): key for key, fn in tasks.items()}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                out[key] = fut.result()
            except SubstrateError:
                out[key] = None                 # graceful skip (== old `except SubstrateError: continue`)
    return out


class SubstrateClient:
    def __init__(self, vector_url: Optional[str] = None, graph_url: Optional[str] = None,
                 timeout_s: Optional[float] = None, retries: Optional[int] = None):
        self.vector = (vector_url or config.VECTOR_API_URL).rstrip("/")
        self.graph = (graph_url or config.GRAPH_API_URL).rstrip("/")
        self.timeout = timeout_s or config.SUBSTRATE_HTTP_TIMEOUT_S
        self.retries = retries if retries is not None else config.SUBSTRATE_HTTP_RETRIES
        # COLLAPSE seam (Databricks): SUBSTRATE_MODE=inprocess dispatches to E1's in-process engines
        # (no :8000/:8010 servers) — same path + request/response contract. Default http = local unchanged.
        self._inproc = os.getenv("SUBSTRATE_MODE", "http").lower() == "inprocess"

    def _post(self, url: str, body: dict) -> dict:
        if self._inproc:                              # in-process dispatch into E1's collapsed engines
            from inprocess_engines import dispatch
            return dispatch("POST", urlsplit(url).path, body)
        last = None
        for _ in range(max(1, self.retries)):
            try:
                r = httpx.post(url, json=body, timeout=self.timeout)
                if r.status_code < 500:
                    r.raise_for_status()
                    return r.json()
                last = httpx.HTTPStatusError(str(r.status_code), request=r.request, response=r)
            except httpx.HTTPError as e:
                last = e
        raise SubstrateError(f"POST {url} failed after {self.retries} tries: {type(last).__name__}: {last}")

    # ── vector (:8000) ──────────────────────────────────────────────────
    def vector_neighbors(self, anchor_ids: List[str], exclude_ids: Optional[List[str]] = None,
                         vertical: Optional[str] = None, top_k: int = 20) -> List[dict]:
        """Nearest neighbours OF the anchor entities' STORED vectors (no re-embed). Works for ALL
        verticals — and is the ONLY similarity path for podcasts. Returns [{entity_id,name,vertical,score}]."""
        if not anchor_ids:
            return []
        body = {"anchor_ids": list(anchor_ids), "exclude_ids": list(exclude_ids or anchor_ids),
                "vertical": vertical if (vertical and vertical != "any") else None, "top_k": top_k}
        return self._post(f"{self.vector}/api/neighbors", body).get("neighbors", [])

    def vector_retrieve(self, phrase: str, vertical: Optional[str] = None, top_k: int = 50) -> List[dict]:
        """No-NLU semantic recall for a free-text phrase. Returns [{entity_id,name,vertical,score}]."""
        body = {"phrase": phrase, "vertical": vertical if (vertical and vertical != "any") else None, "top_k": top_k}
        return self._post(f"{self.vector}/api/retrieve", body).get("results", [])

    # ── graph (:8010) ───────────────────────────────────────────────────
    def graph_similar(self, entity_id: str, top_k: int = 10, vertical: Optional[str] = None) -> List[dict]:
        """Precomputed :SIMILAR_TO neighbours (game/movie/tv). For PODCASTS the graph returns
        status=no_graph_signal → this returns [] (caller should fall back to vector_neighbors)."""
        body = {"entity_id": entity_id, "top_k": top_k,
                "vertical": vertical if (vertical and vertical != "any") else None}
        data = self._post(f"{self.graph}/graph/similar", body)
        if data.get("status") != "success":
            return []                       # no_graph_signal / not_found
        return data.get("results", [])

    def graph_structured(self, vertical: Optional[str] = None, genre=None, keyword=None,
                         concept=None, franchise: Optional[str] = None, top_k: int = 10) -> List[dict]:
        """Relational retrieval: filter by vertical/genre/keyword/concept/franchise (ANDed). Genre matching
        is CASE-SENSITIVE — pass canonical capitalisation (e.g. 'Horror'). Returns [{entity_id,name,vertical,
        score,why}], influence-ranked. (Added for V2-P3 content + exploration; additive — no caller changes.)"""
        body: dict = {"top_k": top_k}
        if vertical and vertical != "any":
            body["vertical"] = vertical
        if genre:
            body["genre"] = genre if isinstance(genre, list) else [genre]
        if keyword:
            body["keyword"] = keyword if isinstance(keyword, list) else [keyword]
        if concept:
            body["concept"] = concept if isinstance(concept, list) else [concept]
        if franchise:
            body["franchise"] = franchise
        return self._post(f"{self.graph}/graph/structured", body).get("results", [])

    def graph_score_within(self, entity_ids: List[str]) -> Dict[str, dict]:
        """Per-id GDS signals (influence/community/concepts/...) for a FIXED set. Returns {entity_id: row}.
        (For bulk popularity prep we use the local gds_signals_dev.csv; this is for live per-id reads.)"""
        if not entity_ids:
            return {}
        data = self._post(f"{self.graph}/graph/score_within", {"entity_ids": list(entity_ids)})
        return {r["entity_id"]: r for r in data.get("results", [])}

    # ── health (optional integration probe) ─────────────────────────────
    def is_up(self) -> bool:
        if self._inproc:                              # engines live in-process → always reachable
            return True
        try:
            return (httpx.get(f"{self.vector}/api/stats", timeout=3).status_code < 500 and
                    httpx.get(f"{self.graph}/graph/health", timeout=3).status_code < 500)
        except httpx.HTTPError:
            return False
