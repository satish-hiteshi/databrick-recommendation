"""Startup substrate guard — FAIL LOUD if E3 is pointed at the wrong graph or parquet.

Ported from the dev tree (endpoint-3-feeds-ranking 119c2cc, mirroring E1's guard) and adapted for
serving — this is called from engine startup, so it must not break warm-up as the catalog grows:

  SUBSTRATE_EXPECT_ENTITIES   strict mode: exact expected count for BOTH parquet rows and :Entity nodes
  (unset)                     consistency mode: parquet rows vs graph :Entity within 2% (catalog growth
                              must not fail a deploy; a 44k-vs-52k stale artifact still fails loudly)
  SUBSTRATE_CHECK=0           bypass entirely (offline unit tests only)
Graph half is skipped when no NEO4J_URI is configured.
"""
import os


def assert_substrate():
    if os.getenv("SUBSTRATE_CHECK", "1") == "0":
        print("[substrate] check SKIPPED (SUBSTRATE_CHECK=0)", flush=True)
        return
    from . import config
    import pyarrow.parquet as pq
    ppath = config.VECTOR_PARQUET
    prows = pq.read_metadata(ppath).num_rows
    expect = os.getenv("SUBSTRATE_EXPECT_ENTITIES")
    if expect is not None and prows != int(expect):
        raise RuntimeError(
            f"[substrate] WRONG PARQUET: {ppath} has {prows} rows, expected {expect}. "
            f"E3 must load the current corpus embeddings.parquet (foundation 03 output). "
            f"Point HOME_VECTOR_PARQUET at the correct file, or adjust SUBSTRATE_EXPECT_ENTITIES.")
    if not getattr(config, "NEO4J_URI", None):
        print(f"[substrate] OK — parquet={ppath} rows={prows} (graph check skipped: no NEO4J_URI)", flush=True)
        return
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
                               connection_timeout=8)
    try:
        with drv.session(database=config.NEO4J_DATABASE) as s:
            gcount = s.run("MATCH (e:Entity) RETURN count(e) AS n").single()["n"]
    finally:
        drv.close()
    if expect is not None and gcount != int(expect):
        raise RuntimeError(
            f"[substrate] WRONG GRAPH: {config.NEO4J_URI} has {gcount} :Entity nodes, expected {expect}. "
            f"E3 must point at the graph loaded from the SAME corpus (foundation 01). "
            f"Set NEO4J_URI correctly, or adjust SUBSTRATE_EXPECT_ENTITIES.")
    if expect is None and gcount and abs(prows - gcount) > max(0.02 * gcount, 50):
        raise RuntimeError(
            f"[substrate] GRAPH/PARQUET MISMATCH: parquet {ppath} has {prows} rows but graph "
            f"{config.NEO4J_URI} has {gcount} :Entity nodes (>2% apart) — one side is a stale artifact. "
            f"Rebuild via foundation 01/03 (or set SUBSTRATE_EXPECT_ENTITIES / SUBSTRATE_CHECK=0).")
    print(f"[substrate] OK — parquet={ppath} rows={prows}; graph={config.NEO4J_URI} entities={gcount}", flush=True)
