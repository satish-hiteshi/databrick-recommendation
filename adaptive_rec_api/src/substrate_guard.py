"""Startup substrate guard — FAIL LOUD if E6 is pointed at the wrong vector universe.

The machine carries several obsolete Qwen parquets (notably the 44,097-row
`embeddings_qwen_44k_prefixed.parquet`) and the PG `property_vectors` table has itself been through a
44k -> 52,510 regeneration. E6 loads its serving universe from PG `property_vectors` first (PG-first,
client directive) and falls back to the `embeddings_updated.parquet` doc-vector corpus. An earlier E1
regression was nearly invalidated by a service silently running on the 44k substrate; this guard makes
the same class of mistake impossible for E6.

It asserts, against an ALREADY-LOADED ``Data`` instance, that BOTH:
  (1) the number of vectors E6 actually loaded == SUBSTRATE_EXPECT_ENTITIES (default 52,510), AND
  (2) the SOURCE it loaded from carries that same universe:
        - source == "postgres"  -> re-query ``SELECT count(*) FROM property_vectors`` == expected
        - source == "parquet"   -> the parquet's on-disk row count == expected
and raises a clear found-vs-expected ``RuntimeError`` naming the wrong count (e.g. "expected 52510, not
44k") otherwise — rather than silently serving the wrong data.

Env:
  SUBSTRATE_EXPECT_ENTITIES  expected loaded-vector / source-row count (default 52510)
  SUBSTRATE_CHECK=0          bypass the check entirely (NOT recommended; offline unit tests only)
"""
import os


def assert_substrate(data):
    """Verify the loaded ``Data`` universe and its backing source both carry the expected count.

    ``data`` is a loaded ``Data`` instance (has ``.pids``, ``.stats()`` and ``._source``). Raises
    ``RuntimeError`` (found-vs-expected) on any mismatch; prints an OK line and returns on success.
    """
    if os.getenv("SUBSTRATE_CHECK", "1") == "0":
        print("[substrate] check SKIPPED (SUBSTRATE_CHECK=0)", flush=True)
        return
    _exp = os.getenv("SUBSTRATE_EXPECT_ENTITIES")
    if _exp is None:
        # serving adaptation: the corpus GROWS with the catalog — a hard-coded count would fail
        # every warm-up after a content drop. Strict mode is opt-in via SUBSTRATE_EXPECT_ENTITIES.
        print("[substrate] soft mode — SUBSTRATE_EXPECT_ENTITIES unset; strict universe assert skipped", flush=True)
        return
    expect = int(_exp)

    # 1) LOADED UNIVERSE — the vectors E6 actually put in memory (what it will serve).
    loaded = len(data.pids)
    source = getattr(data, "_source", None)
    if loaded != expect:
        raise RuntimeError(
            f"[substrate] WRONG SOURCE: E6 loaded {loaded} vectors from {source!r}, expected {expect}, "
            f"not 44k. E6 must serve the re-keyed 52,510-entity universe (PG property_vectors, or the "
            f"embeddings_updated.parquet fallback) — NOT the obsolete 44k parquet "
            f"(embeddings_qwen_44k_prefixed.parquet, 44,097 rows). Point ADAPTIVE_PARQUET / the PG "
            f"property_vectors table at the correct universe (or set SUBSTRATE_EXPECT_ENTITIES to override).")

    # 2) SOURCE — re-verify the store E6 loaded from independently carries the expected universe, so a
    #    lucky in-memory count (e.g. dedup masking a wrong file) cannot pass.
    if source == "postgres":
        import psycopg2
        conn = psycopg2.connect(host="localhost", port=5433, user="postgres",
                                password="postgres", dbname="feedsai_discovery", connect_timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.property_vectors')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("[substrate] WRONG SOURCE: PG table property_vectors does not exist "
                                   "on :5433/feedsai_discovery (source claimed 'postgres').")
            cur.execute("SELECT count(*) FROM property_vectors")
            pg_rows = cur.fetchone()[0]
        finally:
            conn.close()
        if pg_rows != expect:
            raise RuntimeError(
                f"[substrate] WRONG SOURCE: PG property_vectors has {pg_rows} rows, expected {expect}, "
                f"not 44k. The :5433/feedsai_discovery property_vectors table must carry the re-keyed "
                f"52,510-entity universe (set SUBSTRATE_EXPECT_ENTITIES to override).")
        print(f"[substrate] OK — source=postgres property_vectors={pg_rows} rows; "
              f"loaded={loaded} (== {expect})", flush=True)
    elif source == "parquet":
        import pyarrow.parquet as pq
        import data as _data_mod          # E6's data.py — PARQUET is the resolved fallback path it read
        ppath = _data_mod.PARQUET
        prows = pq.read_metadata(ppath).num_rows
        if prows != expect:
            raise RuntimeError(
                f"[substrate] WRONG SOURCE: parquet {ppath} has {prows} rows, expected {expect}, "
                f"not 44k. E6's parquet fallback must be the re-keyed embeddings_updated.parquet "
                f"(52,510 rows) — NOT the obsolete embeddings_qwen_44k_prefixed.parquet (44,097 rows). "
                f"Point ADAPTIVE_PARQUET at the correct file (or set SUBSTRATE_EXPECT_ENTITIES to override).")
        print(f"[substrate] OK — source=parquet {ppath} rows={prows}; loaded={loaded} (== {expect})",
              flush=True)
    else:
        raise RuntimeError(
            f"[substrate] UNKNOWN SOURCE {source!r}: cannot verify the vector universe (expected "
            f"'postgres' or 'parquet'). Refusing to serve unverified data (set SUBSTRATE_CHECK=0 to bypass).")
