"""Startup substrate guard — FAIL LOUD if E1 is pointed at the wrong graph or parquet.

Ported from the dev tree (endpoint-1-agent-recs c331a4c) and adapted for serving: E1's earlier regression
was nearly invalidated by services silently running on an obsolete corpus. This asserts at startup that
the doc-vector parquet and (when configured) the graph carry the SAME entity universe, and raises a clear
found-vs-expected error otherwise — a wrong corpus fails the deploy instead of silently serving bad data.

Env:
  SUBSTRATE_EXPECT_ENTITIES   strict mode: exact expected count for BOTH parquet rows and :Entity nodes
  (unset)                     consistency mode: parquet rows vs graph :Entity within 2% (corpus grows over
                              time, so a hard-coded count would break warm-up on every content drop)
  SUBSTRATE_CHECK=0           bypass entirely (offline unit tests only)
Graph half is skipped when no NEO4J_URI is configured or E1_ENABLE_GRAPH=0 (vector-only deploys).
"""
import os


def _graph_count():
    try:
        from graph_src.connection import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
        try:
            from graph_src.connection import NEO4J_DATABASE
        except ImportError:
            NEO4J_DATABASE = "neo4j"
    except ImportError:
        from connection import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD          # flat layout (dev tree)
        NEO4J_DATABASE = "neo4j"
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), connection_timeout=8)
    try:
        with drv.session(database=NEO4J_DATABASE) as s:
            return NEO4J_URI, s.run("MATCH (e:Entity) RETURN count(e) AS n").single()["n"]
    finally:
        drv.close()


def assert_substrate():
    if os.getenv("SUBSTRATE_CHECK", "1") == "0":
        print("[substrate] check SKIPPED (SUBSTRATE_CHECK=0)", flush=True)
        return

    # 1) PARQUET — the Qwen doc-vector corpus E1 loads (same path inmemory_store resolves).
    import inmemory_store
    import pyarrow.parquet as pq
    ppath = inmemory_store._parquet_path()
    prows = pq.read_metadata(ppath).num_rows

    expect = os.getenv("SUBSTRATE_EXPECT_ENTITIES")
    if expect is not None and prows != int(expect):
        raise RuntimeError(
            f"[substrate] WRONG PARQUET: {ppath} has {prows} rows, expected {expect}. "
            f"E1 must load the current corpus embeddings.parquet (foundation 03 output). "
            f"Fix EMBEDDINGS_PARQUET / restage, or adjust SUBSTRATE_EXPECT_ENTITIES.")

    # 2) GRAPH — only when a graph is configured for this deploy.
    if os.getenv("E1_ENABLE_GRAPH", "1") == "0" or not os.getenv("NEO4J_URI"):
        print(f"[substrate] OK — parquet={ppath} rows={prows} (graph check skipped: no graph configured)",
              flush=True)
        return
    uri, gcount = _graph_count()
    if expect is not None and gcount != int(expect):
        raise RuntimeError(
            f"[substrate] WRONG GRAPH: {uri} has {gcount} :Entity nodes, expected {expect}. "
            f"E1 must point at the graph loaded from the SAME corpus (foundation 01). "
            f"Set NEO4J_URI to the correct instance, or adjust SUBSTRATE_EXPECT_ENTITIES.")
    if expect is None and gcount and abs(prows - gcount) > max(0.02 * gcount, 50):
        raise RuntimeError(
            f"[substrate] GRAPH/PARQUET MISMATCH: parquet {ppath} has {prows} rows but graph {uri} has "
            f"{gcount} :Entity nodes (>2% apart). One side is a stale artifact — rebuild via foundation "
            f"01/03 so both carry the same universe (or set SUBSTRATE_EXPECT_ENTITIES / SUBSTRATE_CHECK=0).")
    print(f"[substrate] OK — parquet={ppath} rows={prows}; graph={uri} entities={gcount}", flush=True)
