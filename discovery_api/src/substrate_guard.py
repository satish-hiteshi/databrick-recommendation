"""Startup substrate guard — FAIL LOUD if E2 is pointed at the wrong vector/graph SERVICE.

Mirror of Endpoint 1's `staging_parrot_v3/code/substrate_guard.py`, adapted for Endpoint 2's
architecture: E2 owns NO parquet and NO Neo4j driver — it reaches the shared vector (:8000) and graph
(:8010) services ONLY over HTTP (see `data_access/substrate_client.py`). So the guard validates the
SERVICES those URLs resolve to, not local artifacts.

The machine carries multiple substrates — several obsolete parquets behind the vector service and three
Neo4j instances behind the graph service (:7687 57k, :7688 44k, :7690 re-keyed). A silently-wrong
service would invalidate the feed the same way E1's earlier regression was nearly invalidated. This
asserts, at startup, that:

  * the VECTOR service (`config.VECTOR_API_URL`) serves the re-keyed 52,510-entity universe from the
    `embeddings_updated` parquet, and
  * the GRAPH service (`config.GRAPH_API_URL`) serves the same 52,510-entity universe from the re-keyed
    Neo4j on :7690 (Part A.4 — NOT the obsolete :7687 / :7688).

and raises a clear found-vs-expected RuntimeError otherwise (rather than silently serving wrong data).

Env:
  SUBSTRATE_EXPECT_ENTITIES  expected total_entities / graph :Entity count (default 52510)
  SUBSTRATE_CHECK=0          bypass the check entirely (NOT recommended; offline/unit tests only)
"""

import os

import httpx

from . import config

# The re-keyed doc-vector corpus name the vector service must report (substring match).
_EXPECT_PARQUET_SUBSTR = "embeddings_updated"
# The re-keyed graph instance the graph service must be bound to (substring match on neo4j_uri).
_EXPECT_NEO4J_SUBSTR = "7690"
_HTTP_TIMEOUT_S = 8.0


def assert_substrate():
    """Validate the vector + graph services E2 talks to; raise RuntimeError on a wrong/unreachable one.

    No-op (prints a skip line) when SUBSTRATE_CHECK=0. Prints an OK line on success."""
    if os.getenv("SUBSTRATE_CHECK", "1") == "0":
        print("[substrate] check SKIPPED (SUBSTRATE_CHECK=0)", flush=True)
        return
    expect = int(os.getenv("SUBSTRATE_EXPECT_ENTITIES", "52510"))

    vector_url = config.VECTOR_API_URL.rstrip("/")
    graph_url = config.GRAPH_API_URL.rstrip("/")

    # 1) VECTOR SERVICE — GET {VECTOR_API_URL}/api/stats → total_entities + parquet name.
    stats_url = f"{vector_url}/api/stats"
    try:
        stats = httpx.get(stats_url, timeout=_HTTP_TIMEOUT_S)
        stats.raise_for_status()
        stats = stats.json()
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"[substrate] WRONG VECTOR SERVICE: {stats_url} is unreachable ({type(e).__name__}: {e}). "
            f"E2 needs the shared vector service serving the re-keyed {expect}-entity "
            f"'{_EXPECT_PARQUET_SUBSTR}' parquet. Point VECTOR_API_URL at the correct service "
            f"(or set SUBSTRATE_CHECK=0 to bypass).") from e
    v_entities = stats.get("total_entities")
    v_parquet = str(stats.get("parquet", ""))
    if v_entities != expect:
        raise RuntimeError(
            f"[substrate] WRONG VECTOR SERVICE: {stats_url} reports total_entities={v_entities}, "
            f"expected {expect}. E2 must use the shared vector service on the re-keyed "
            f"'{_EXPECT_PARQUET_SUBSTR}' parquet ({expect} rows). "
            f"Point VECTOR_API_URL at the correct service (or set SUBSTRATE_EXPECT_ENTITIES to override).")
    if _EXPECT_PARQUET_SUBSTR not in v_parquet:
        raise RuntimeError(
            f"[substrate] WRONG VECTOR SERVICE: {stats_url} serves parquet={v_parquet!r}, "
            f"expected a name containing '{_EXPECT_PARQUET_SUBSTR}'. That is a stale/obsolete corpus. "
            f"Point VECTOR_API_URL at the service backed by the re-keyed embeddings_updated.parquet.")

    # 2) GRAPH SERVICE — GET {GRAPH_API_URL}/graph/health → counts.entities + neo4j_uri (must be :7690).
    #    Part A.4: E2 fails loud if the graph service is NOT the re-keyed :7690.
    health_url = f"{graph_url}/graph/health"
    try:
        health = httpx.get(health_url, timeout=_HTTP_TIMEOUT_S)
        health.raise_for_status()
        health = health.json()
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"[substrate] WRONG GRAPH SERVICE: {health_url} is unreachable ({type(e).__name__}: {e}). "
            f"E2 needs the shared graph service on the re-keyed :{_EXPECT_NEO4J_SUBSTR} Neo4j "
            f"({expect} entities), NOT :7687 (57k) or :7688 (44k). Point GRAPH_API_URL at the correct "
            f"service (or set SUBSTRATE_CHECK=0 to bypass).") from e
    g_entities = (health.get("counts") or {}).get("entities")
    g_uri = str(health.get("neo4j_uri", ""))
    if g_entities != expect:
        raise RuntimeError(
            f"[substrate] WRONG GRAPH SERVICE: {health_url} reports counts.entities={g_entities}, "
            f"expected {expect}. E2 must point at the re-keyed :{_EXPECT_NEO4J_SUBSTR} graph, NOT "
            f":7687 (57k) or :7688 (44k). Point GRAPH_API_URL at the correct service "
            f"(or set SUBSTRATE_EXPECT_ENTITIES to override).")
    if _EXPECT_NEO4J_SUBSTR not in g_uri:
        raise RuntimeError(
            f"[substrate] WRONG GRAPH SERVICE: {health_url} is bound to neo4j_uri={g_uri!r}; it must be "
            f"the re-keyed :{_EXPECT_NEO4J_SUBSTR}, not :7687 (57k) or :7688 (44k). "
            f"Point GRAPH_API_URL at the service on bolt://…:7690.")

    print(
        f"[substrate] OK — vector={stats_url} total_entities={v_entities} parquet={v_parquet!r}; "
        f"graph={health_url} entities={g_entities} neo4j_uri={g_uri!r} (== {expect})",
        flush=True)
